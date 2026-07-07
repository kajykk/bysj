# ADR-006: 模型推理使用 asyncio.to_thread 而非专用进程

## 状态 (Status)
Accepted

## 日期 (Date)
2026-07-03

## 上下文 (Context)
DWS 系统的核心能力是基于多模态融合的抑郁症风险评分, 后端集成 scikit-learn (LogisticRegression/LightGBM) 与 PyTorch (MLP/TF-IDF 文本模型) 进行实时推理。这些 ML 库的 API 是同步阻塞的 CPU 密集操作, 而服务层基于 FastAPI + SQLAlchemy 2.0 async 全异步栈构建。

若直接在 FastAPI 事件循环中调用 `model.predict()` / `pipeline.predict_proba()`, 单次推理耗时 50–300ms, 期间事件循环被完全占用, 所有其他 HTTP 请求、WebSocket 心跳、Celery 结果回写、Redis pubsub 订阅均会被阻塞, 引发请求堆积与超时级联。

因此需要在「异步 API 层」与「同步 ML 推理层」之间引入一个低延迟、低运维成本的桥接方案, 同时保证:
- 模型加载 (pickle/joblib 反序列化) 只发生一次, 后续推理复用内存中的模型对象;
- 推理调用栈保持简单, 便于在 `app/core/model_engine.py` 中统一异常处理与监控埋点;
- 部署形态不引入新进程/容器, 复用现有 Uvicorn worker 进程。

## 决策 (Decision)
采用 Python 3.9+ 标准库 `asyncio.to_thread()` 将同步模型推理委托到默认线程池执行, 复用解释器自带的 `ThreadPoolExecutor`。

具体实施:
- `ModelEngine` (`app/core/model_engine.py`) 的所有 CPU 密集方法均通过 `await asyncio.to_thread(...)` 包装, 包括:
  - `_load_model(model_id)` → `await asyncio.to_thread(self._load_model, model_id)` (625 行附近)
  - `_load_adapter()` → `await asyncio.to_thread(self._load_adapter)` (631 行附近)
  - `predict_*` / `explain_prediction` 等推理入口在 `model_engine_predict.py` 中同样使用 to_thread 包装
- 推理监控计数器 (inference inflight gauge) 在多线程环境下使用 `threading.Lock` 保护, 避免 counter 错乱 (model_engine.py:222 注释明确说明);
- 模型缓存 (`_model_cache` LRU) 的读改写通过锁保护, 因为 to_thread 在线程池中执行 (model_engine.py:193, 477);
- 线程池并发度通过 `asyncio` 默认 `ThreadPoolExecutor` 的 `max_workers` 控制 (默认 `min(32, os.cpu_count() + 4)`), 必要时通过 `loop.set_default_executor()` 调优;
- 推理路径中 GIL 释放点主要依赖 scikit-learn 的 Cython 内核与 PyTorch 的 C++ 后端, 这两段在原生代码中执行时 GIL 已释放, 线程池可真正并行。

## 替代方案 (Alternatives Considered)
1. **独立推理进程 + IPC (gRPC/Unix Socket)** — 将模型服务拆为独立进程, 通过 gRPC 或 Unix Socket 调用。优点是进程隔离、绕开 GIL; 缺点是部署复杂度增加 (新增 sidecar 容器、健康检查、序列化协议), 模型权重需在两个进程间重复加载, 内存占用翻倍, 且 IPC 引入额外 1–5ms 延迟。本系统模型体量小 (单模型 < 50MB), 不值得引入此复杂度。
2. **Celery 任务推理** — 把每次推理作为 Celery 任务投递。缺点: 任务序列化 (pickle)、Broker 往返、worker 调度引入 100ms+ 延迟, 无法满足同步 API < 500ms SLO; 且推理任务与已有后台任务 (训练/导出) 争抢 worker。
3. **`concurrent.futures.ProcessPoolExecutor`** — 真并行, 绕开 GIL。但每次 fork/spawn 进程的开销远大于推理本身, 且模型需在每个子进程中重新加载, 内存膨胀严重, 进程间无法共享缓存。
4. **同步直接调用 (不包装)** — 在 async def 中直接 `model.predict()`, 阻塞事件循环, 不可接受 (已在上下文中说明)。

## 后果 (Consequences)
- **正面**:
  - 零部署成本, 不引入新进程/容器/IPC, 复用现有 Uvicorn worker;
  - 低延迟, to_thread 仅有线程调度开销 (μs 级), 模型对象在进程内共享, 无序列化;
  - 实现简单, 单一 `await asyncio.to_thread(fn, *args)` 调用, 异常处理与同步代码一致;
  - 监控埋点 (`app/core/metrics.py` 的推理耗时 histogram) 可在协程层统一注入。
- **负面**:
  - GIL 限制: 仅当模型推理在原生代码 (Cython/C++) 中释放 GIL 时, 多线程才真正并行; 纯 Python 后处理 (如 SHAP 解释的特征重组) 仍受 GIL 串行化影响;
  - 线程池满时请求排队, 高并发场景下 P99 延迟可能上升, 需通过 `max_workers` 调优 + 排队指标暴露;
  - 线程内同步异常栈不会自动传播为 async 异常, 需在调用处 try/except 并包装为 `ModelException`。
- **中性**:
  - 需在线程池配置与监控上建立规范: 暴露 `asyncio` 默认 executor 的 inflight/排队指标;
  - 模型加载锁 (`_cache_lock`) 需为 `threading.Lock` 而非 `asyncio.Lock`, 因为临界区在线程中执行;
  - 文档需明确: 任何新增的同步 ML 调用必须经 to_thread 包装, 不允许在 async 路径直接调用。

## 关联 (Related)
- 实现: `backend/app/core/model_engine.py` (to_thread 调用点 625/631 行, 锁与监控注释 193/222/237/477 行)
- 实现: `backend/app/core/model_engine_predict.py` (PredictMixin 推理包装)
- 监控: `backend/app/core/metrics.py` (推理耗时/并发指标)
- 异常: `backend/app/core/exceptions.py:ModelException`
- 测试: `backend/tests/test_model_engine.py`, `backend/tests/test_qa009_inference_performance.py`
- 相关 ADR: ADR-008 (健康检查 — startup 探针依赖模型加载完成)
