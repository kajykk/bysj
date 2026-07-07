# 资源利用率维度任务清单 (Resource Tasks)

> 维度: resource | 负责人: - | 最后更新: 2026-07-03
> 评估来源: sysopt-resource assess 模式

## P0 任务 (必须立即处理)
- [x] RES-P0-001: ModelEngine.models 无界缓存所有模型 → LRUCache(maxsize=20) + 大模型按需加载 (model_engine.py:195) ✅ 2026-06-29
  - `self.models` 从 `dict` 改为 `OrderedDict` 实现 LRU 缓存
  - 新增 `_cache_get` (命中移到 MRU) / `_cache_put` (超限 popitem(last=False) 淘汰 LRU) 方法
  - 新增 `_cache_lock = threading.Lock()` 保护并发访问 (模型加载通过 asyncio.to_thread 在线程池执行)
  - 新增 `_cache_evictions` 计数器 + `get_metrics_snapshot()` 暴露 cache_evictions/cache_maxsize 指标
  - config.py 新增 `model_cache_maxsize: int = 20` (0 禁用淘汰, 测试用)
  - `_load_model` / `_load_model_async` 改用 `_cache_get` / `_cache_put`
  - 新增 21 个测试 (test_model_cache_lru.py), 覆盖 LRU 基本+线程安全+集成+监控+源码检查+配置
  - 回归 82 个相关测试全部通过
- [x] RES-P0-002: 缺少日志文件轮转配置 → RotatingFileHandler 或 logrotate ✅ 2026-06-29
  - 新增 `app/core/logging_config.py`：dictConfig 统一配置
  - RotatingFileHandler：app.log (INFO+) + error.log (ERROR+)，10MB×5 份轮转
  - config.py 新增 6 项日志配置 (log_dir/log_level/log_max_bytes/log_backup_count/log_to_file/log_console)
  - main.py lifespan 启动时调用 configure_logging()
  - 新增 17 个测试用例 (tests/test_logging_config.py)，覆盖率 100%
  - 回归测试 134/134 通过

## P1 任务 (高优先级)
- [x] RES-P1-001: predict_structured 每次执行 3 路实验性推理 CPU 放大 4 倍 → 实验开关 ✅ 2026-07-03
  - config.py 新增 `structured_experimental_enabled: bool = True` 配置开关 (默认开启保持兼容)
  - model_engine_predict.py 的 predict_structured 添加实验路径开关逻辑 (关闭时跳过 v121/v123/adapter 3 路实验性推理, 填充 14 个 None 占位字段保持响应结构一致)
  - 关闭时 CPU 放大从 4 倍降至 1 倍
  - 新增 4 个测试 (test_predict_structured_parallel.py): 源码引用开关 + 配置默认值 True + 开关关闭跳过实验路径 + 开关开启执行实验路径
  - 回归 14 tests passed (4 new + 10 regression)
- [x] RES-P1-002: LiteFeatureExtractor 嵌套关键词扫描 O(n*k) → Aho-Corasick 或正则 ✅ 2026-07-02 (T-P2-013)
  - 在 app/core/model_engine.py LiteFeatureExtractor 类中新增 `_KEYWORD_TO_CATEGORY` 映射 (扁平化 KEYWORD_CATEGORIES)
  - 新增 `_SORTED_KEYWORDS` (按长度降序排列, 避免短关键词覆盖长关键词的子串, 例如 "不出门" vs "不想出门")
  - 新增 `_COMPILED_PATTERN` (`re.compile` + `re.escape` 转义特殊字符)
  - `extract()` 方法改用 `re.finditer` 一次扫描替代 60 次独立 `str.count`
  - 时间复杂度从 O(n*k) 改善为 O(n+m) (n 为文本长度, m 为匹配数)
  - 选择 re 而非 pyahocorasick 因后者未安装, 且 re 引擎内部使用类似自动机算法
  - 行为差异分析: 唯一子串关系 "不出门"(exercise_deficit) vs "不想出门"(social_withdrawal), 正则方案优先匹配更长关键词更合理
  - 回归 42 tests passed (含 10 LiteFeatureExtractor + 26 feature_maps + 6 model_status_cache)
- [x] RES-P1-003: Celery 任务每次创建事件循环 → 评估 celery[asyncio] 或 asyncio.Task ✅ 2026-07-03
  - 新增 app/core/celery_async.py 公共模块 (get_celery_loop + run_async, 模块级单例 _event_loop + threading.Lock 保护 + is_closed() 检查重建)
  - 4 个 Celery 任务模块 (alerts.py/anomaly_detection.py/observability.py/scheduler.py) 改为别名导入 `from app.core.celery_async import get_celery_loop as _get_loop, run_async as _run_async` 复用公共模块, 移除各模块重复的 asyncio/threading 导入和 _event_loop/_get_loop/_run_async 辅助函数
  - 别名导入保持测试兼容: patch("app.tasks.xxx._run_async") 和 from app.tasks.xxx import _get_loop 等 mock 路径仍有效
  - 适配 test_scheduler.py: reset_event_loop fixture 和 test_recreates_closed_loop 改为操作 celery_async_mod._event_loop
  - 修复时区相关测试 bug: test_plan_end_date_passed_marks_completed 的 mock_plan.end_date 从 date.today() 改为 datetime.now(UTC).date() 避免凌晨时区不一致
  - 新增 11 个测试 (test_celery_async.py): get_celery_loop 3 (返回/缓存/重建关闭) + run_async 3 (执行/带参数/异常传播) + 4 模块别名导入兼容性 + 模块无重复 _event_loop 检查
  - 回归 209 tests passed (test_scheduler 56 + test_alert_tasks + test_anomaly_detection + test_observability + test_celery_async 11)
- [x] RES-P1-004: ObservabilityCollector 缓冲区上限 10000 → 确认消费者或改 1000 ✅ 2026-07-03
  - config.py 调整 `observability_max_buffer_size: int = 1000` (从 10000 降至 1000)
  - observability_service.py 的 ObservabilityCollector 类 docstring 添加死缓冲区状态说明 (生产环境 start/stop/_flush_loop 未被调用, flush_to_db 直接从 _pending_logs 取数据绕过 _flushed_buffer, consume_flushed_logs 接口保留但无生产消费者)
  - consume_flushed_logs 方法添加 warning docstring 标注死缓冲区状态 (保留接口供未来接入外部消费者如 TSDB 导出器)
  - 新增 4 个测试 (test_observability_service.py): 配置默认值 1000 + Collector 读取配置 + 缓冲区上限 1000 溢出丢弃最旧 + docstring 文档化验证
  - 回归 28 tests passed (4 new + 24 regression)
- [x] RES-P1-005: TRAINING_JOBS 全局字典无清理 → cleanup_old_jobs + LRU 上限 100 ✅ 2026-07-02
  - 在 app/services/model_predict_service.py 新增 `TRAINING_JOBS_MAX_SIZE = 100` 常量 + `_ACTIVE_JOB_STATUSES = frozenset({"running", "queued"})` 不淘汰集合
  - 新增 `cleanup_old_training_jobs(max_size=100)` 函数: 超过上限时按 `created_at` 升序淘汰非活跃任务, running/queued 任务不淘汰避免误删
  - 安全机制: sort key 用 `_safe_created_at` 包装 try/except (TypeError/ValueError) → 非法值视为 0 (最老), 避免损坏数据导致清理崩溃
  - 触发点: 模块加载后立即清理 + `start_training_job` 两个分支 (Celery + Thread fallback) 添加任务后清理
  - 持久化: 清理后调用 `_save_training_jobs()` 同步到磁盘 `training_jobs.json`
- [x] RES-P1-006: uploads/ 目录无自动清理 → cleanup_uploads.py + Celery 每日 ✅ 2026-07-02
  - 在 app/tasks/scheduler.py 新增 `_cleanup_uploads_dir_impl(max_age_days=30)` 同步实现函数
  - 清理策略: 遍历 `uploads/` 下的用户目录 (数字命名), 跳过公共目录 (audio/content), 删除 mtime > 30 天的文件, 空用户目录自动 rmdir
  - 使用 mtime 而非 atime (atime 在很多 FS 上不可靠)
  - 新增 `cleanup_uploads_dir_task` Celery 任务 (max_retries=1, time_limit=300s), beat schedule 每日 03:30 触发
- [x] RES-P1-007: experiment_trainer artifact 无清理 → 保留最近 10 次归档 ✅ 2026-07-02
  - 在 app/tasks/scheduler.py 新增 `_cleanup_experiment_artifacts_impl(keep_recent=10)` 同步实现函数
  - 清理策略: 收集 `models/trained/*` 目录, 按 mtime 降序排序, 保留最新 10 个, 删除更旧的
  - 安全机制: 收集 `MODEL_PATHS` 中所有注册的 active 模型绝对路径, 若目录包含 active 模型文件则跳过删除 (避免误删生产模型)
  - 新增 `cleanup_experiment_artifacts_task` Celery 任务 (max_retries=1, time_limit=300s), beat schedule 每周一 04:00 触发
  - beat_schedule 在 app/core/celery_app.py 注册 3 个清理任务条目
- [x] RES-P1-008: notifier/am_sync async 内同步 requests → asyncio.to_thread 卸载到线程池 ✅ 2026-07-02
  - am_sync.py: async 函数内调用同步 requests.post → `await asyncio.to_thread(_HTTP_SESSION.post, ...)` 卸载到线程池避免阻塞事件循环
  - notifier.py CompositeNotifier.send: `self._dispatch(n, payload)` → `await asyncio.to_thread(self._dispatch, n, payload)` 卸载同步 `_dispatch` (内部调用 n.send → requests.post)
  - 19/19 am_sync tests + 55/55 notifier tests passed
- [x] RES-P1-009: email_service SMTP 连接未复用 → 线程本地连接复用 (threading.local) ✅ 2026-07-02
  - 新增 `_SMTP_TLS = threading.local()` 模块级 thread-local 存储
  - 新增 `_get_thread_smtp()` / `_close_thread_smtp()` / `_create_thread_smtp()` 三个辅助函数
  - `_send_smtp` 改为: 先 `_get_thread_smtp()` 取缓存连接, `conn.noop()` 检查活性, 失败则 `_close_thread_smtp()` 关闭后 `_create_thread_smtp()` 重建
  - 配合 `asyncio.to_thread` 线程池模型, 每个线程维护自己的 SMTP 连接
  - 新增 2 个连接复用测试 (复用验证 + NOOP 失败重连验证), 6/6 email_service tests passed
- [x] RES-P1-010: requests 未用 Session 复用 TCP → 模块级 _HTTP_SESSION = requests.Session() ✅ 2026-07-02
  - am_sync.py + notifier.py 模块级新增 `_HTTP_SESSION = requests.Session()`
  - 内部维护 urllib3.HTTPConnectionPool, 同一 host 的后续请求复用 TCP 连接 (避免每次握手 1-3s 开销)
  - WebhookNotifier/SlackNotifier/DingTalkNotifier: `requests.post(...)` → `_HTTP_SESSION.post(...)`
  - 测试 mock 路径同步迁移: `patch("...requests.post")` → `patch("..._HTTP_SESSION.post")`
  - 19/19 am_sync + 55/55 notifier tests passed

## P2 任务 (中优先级)
- [ ] RES-P2-001: celery_app worker 并发参数未配置 → max_tasks_per_child + 队列分离
- [ ] RES-P2-002: pdf_report_service 全量加载 PDF → StreamingResponse
- [ ] RES-P2-003: excel_export_service 输入全量入内存 → 自动切换流式
- [ ] RES-P2-004: _pdf_executor 线程池队列无上限 → Semaphore 限流
- [ ] RES-P2-005: monitoring_logs 表无归档 → 扩展 archive_old_logs 多表
- [ ] RES-P2-006: monitoring_snapshot.json 本地持久化冗余 → 统一 Prometheus
- [ ] RES-P2-007: 前端依赖 Google Fonts CDN → 自托管字体
- [ ] RES-P2-008: nginx Brotli 未启用 → nginx-mod-http-brotli

## P3 任务 (低优先级)
- [ ] RES-P3-001: FusionEngine numpy 处理标量 → 纯 Python 内建
- [ ] RES-P3-002: SHAP explainer 未缓存 → 缓存到 _explainers dict
- [ ] RES-P3-003: monitoring_score_deltas 用 list → deque(maxlen=500)
- [ ] RES-P3-004: ws_manager 未限制总用户数 → 全局连接上限告警
- [ ] RES-P3-005: .sha256 侧车文件累积 → 模型升级时清理
- [ ] RES-P3-006: _verify_redis_backend 新建客户端 → 复用 cache 客户端
- [ ] RES-P3-007: nginx WebSocket timeout 3600s → 改为 600s

---
## 进度统计
- P0: 2/2 ✅ RES-P0-001/002
- P1: 10/10 ✅ RES-P1-001 + RES-P1-002 + RES-P1-003 + RES-P1-004 + RES-P1-005 + RES-P1-006 + RES-P1-007 + RES-P1-008 + RES-P1-009 + RES-P1-010
- P2: 0/8
- P3: 0/7
- **总计**: 12/27
