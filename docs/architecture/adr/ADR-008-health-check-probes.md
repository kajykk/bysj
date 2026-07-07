# ADR-008: 健康检查分层 (live/ready/startup) 三探针

## 状态 (Status)
Accepted

## 日期 (Date)
2026-07-03

## 上下文 (Context)
DWS 系统在 docker-compose 与 Kubernetes 中编排部署, 编排器需要通过 HTTP 探针回答三个本质不同的问题:

1. **进程是否存活, 需要重启?** — 用于检测死锁、活锁、事件循环卡死。此检查必须极轻量, 不依赖任何外部依赖 (DB/Redis), 否则依赖抖动会引发误重启雪崩。
2. **是否可以接收流量?** — 用于负载均衡器决定是否将请求路由到本实例。需要真实检查依赖项 (DB/Redis/Celery) 连通性, 但检查频率高, 不能每次都打 DB。
3. **是否完成启动初始化?** — 用于避免「启动期间流量涌入」。DWS 启动期间需完成: 模型文件加载 (3 个核心模型)、Alembic 迁移、Redis 连接池预热, 耗时 5–30s。若此时就绪探针已通过, 会导致首批请求 504。

单一 `/health` 端点无法区分这三个语义: 若 `/health` 检查 DB, 则 DB 抖动会触发 live 探针失败 → 容器被杀 → 重启风暴; 若 `/health` 不检查 DB, 则 DB 断开时 ready 仍通过 → 请求涌入 → 500。

## 决策 (Decision)
实现三层独立健康检查端点, 实现位于 `app/core/health.py`, 路由注册于 `app/main.py`。

### 1. `/health/live` (Liveness Probe)
- **语义**: 进程是否存活, 是否需要重启;
- **实现**: 无任何 I/O, 仅返回 `{"status": "ok"}` 与 200。进程能响应即代表事件循环未卡死;
- **用途**: docker-compose `healthcheck` 与 K8s `livenessProbe`, 失败时重启容器;
- **频率**: 每 10s 一次。

### 2. `/health/ready` (Readiness Probe)
- **语义**: 是否可以接收流量;
- **实现**: 检查 DB 连通性 (`SELECT 1`)、Redis 连通性 (`PING`, 复用共享客户端)、Celery worker 心跳、ML 模型文件存在性 (`structured_logistic_regression_quick` + `text_depression_model` + `text_depression_tfidf`);
- **缓存优化**: 后台健康监控任务以 `HEALTH_MONITOR_INTERVAL_SECONDS = 10.0` 周期性调用 `get_health_snapshot` 刷新内存缓存 `_snapshot`, `/health/ready` 端点仅读取缓存 (P99 < 5ms), 永不阻塞在 DB/Redis I/O 上;
- **降级**: 若缓存未填充 (启动初期), `get_health_snapshot_nonblocking` 返回 `verified=False` 的静态值, 端点返回 503;
- **用途**: K8s `readinessProbe`, 失败时从 Service endpoints 摘除 (不重启);
- **频率**: 每 5s 一次, 缓存 TTL 10s。

### 3. `/health/startup` (Startup Probe)
- **语义**: 是否完成初始化, 可以开始接受 live/ready 探针;
- **实现**: 检查 ModelEngine 是否完成首次模型加载 (`_model_cache` 非空)、Alembic 是否已 upgrade head (通过 `alembic_version` 表版本号校验)、Redis 连接池是否预热;
- **用途**: K8s `startupProbe` (在 startup 通过前, live/ready 探针不生效), 避免启动期间被 live 误杀;
- **频率**: 每 10s 一次, 失败阈值 30 次 (覆盖最长 5 分钟启动)。

### 测试环境特殊处理
- `_is_test_environment()` 检测 `PYTEST_CURRENT_TEST` 环境变量, 测试环境下跳过后台健康监控任务, 避免 Redis/Celery 超时阻塞测试用例。

## 替代方案 (Alternatives Considered)
1. **单一 `/health` 端点** — 无法区分存活与就绪。若检查依赖, DB 抖动会触发容器重启雪崩; 若不检查, DB 断开时仍接收流量导致 500。已被否决 (见上下文)。
2. **外部探针脚本 (shell + pg_isready + redis-cli)** — 在容器外运行脚本检查依赖。缺点: 维护成本高 (脚本需随依赖演进), 无法复用应用内已有的连接池与客户端, 且无法检查应用层语义 (如模型是否加载)。
3. **仅 readiness, 不分 live/startup** — 无法检测死锁/活锁: 事件循环卡死时, 若 ready 检查也卡住, 编排器只能等超时, 检测延迟高。也无法保护启动期间 — 启动初期 ready 未通过时, K8s 默认 live 探针已生效, 可能误杀正在加载模型的容器。
4. **基于 Prometheus metrics 的探针** — 通过 `/metrics` 端点暴露 `up=1` 之类的指标, 由外部 PromQL 判断。过度复杂, 且引入 Prometheus 作为编排器强依赖, 不符合「编排器应直接通过 HTTP 探针判断」的最佳实践。

## 后果 (Consequences)
- **正面**:
  - docker-compose / K8s healthcheck 可精准控制: live 失败重启、ready 失败摘流、startup 保护启动期;
  - 避免启动期间流量涌入导致的 504/500 首批请求失败;
  - 快速检测事件循环死锁 (live 探针超时即重启), MTTR 显著降低;
  - ready 检查结果缓存, 高频探针不打爆 DB/Redis;
  - `HealthSnapshot` 数据结构统一, 便于在 Grafana dashboard 展示依赖健康度。
- **负面**:
  - 三个端点的实现与测试维护成本高于单端点 (需分别覆盖 live/ready/startup 路径与缓存逻辑);
  - 缓存方案引入「最多 10s 滞后」— DB 断开后 ready 最迟 10s 后才摘流, 期间部分请求会失败。可接受, 因上层有重试与熔断 (`db_breaker.py`)。
- **中性**:
  - ready 缓存需正确处理并发: 后台任务与端点读取共享 `_snapshot`, 用锁保护或使用不可变 dataclass 替换语义;
  - startup 探针的「完成条件」需随启动流程演进同步更新 (新增初始化步骤时易遗漏);
  - 测试环境需 mock 或跳过, 否则单元测试会被后台监控任务拖慢。

## 关联 (Related)
- 实现: `backend/app/core/health.py` (`HealthSnapshot`, `check_database`, `check_redis`, 后台监控任务, `HEALTH_MONITOR_INTERVAL_SECONDS`)
- 路由: `backend/app/main.py` (`/health/live`, `/health/ready`, `/health/startup` 注册)
- 配置: `backend/app/core/config.py` (Redis URL、DB URL 等依赖配置)
- 熔断: `backend/app/core/db_breaker.py`, `backend/app/core/ml_breaker.py` (上层熔断与探针互补)
- 测试: `backend/tests/test_core_health.py`, `backend/tests/test_core_health_extended.py`, `backend/tests/test_health_models_check.py`
- 编排: `docker-compose.yml` (healthcheck 配置), `docs/architecture.md` (部署拓扑)
- 相关 ADR: ADR-006 (startup 探针依赖 ModelEngine 加载完成), ADR-010 (startup 探针校验 Alembic 版本)
