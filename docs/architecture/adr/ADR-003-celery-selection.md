# ADR-003: 选择 Celery 而非 RQ/Dramatiq 异步任务

## 状态 (Status)
Accepted

## 日期 (Date)
2026-07-03

## 上下文 (Context)
DWS 系统存在大量超出请求生命周期的后台任务, 不能阻塞 FastAPI 事件循环:

1. **PDF 报告生成**: 风险评估报告导出 (`app/services/pdf_report_service.py`、`app/tasks/pdf_report.py`) 使用 reportlab 渲染, 单次耗时 5-30 秒, 需异步执行并通过任务 ID 轮询状态。
2. **ML 模型训练与推理**: 模型训练 (`app/tasks/model_training.py`、`app/services/experiment_trainer.py`) 涉及 TensorFlow/PyTorch/Transformers, 耗时数分钟到数小时, 需独立 worker 进程隔离, 避免阻塞 API。
3. **异常检测**: 安全审计中的异常访问检测 (`app/tasks/anomaly_detection.py`、`app/services/anomaly_detection_service.py`) 需周期性扫描 OperationLog。
4. **定时任务调度**: 每日风险扫描、过期告警提醒、干预检查、日志归档、上传目录清理等 (见 `app/core/celery_app.py` 的 `beat_schedule`)。
5. **可靠性要求**: 任务需支持重试、超时、持久化、失败上下文记录 (DLQ)、多 worker 部署, 以满足告警系统的稳定性 SLA。

## 决策 (Decision)
选择 **Celery 5.4 (>=5.4.0)** 作为分布式任务队列, 配置如下 (见 `backend/requirements.txt` 与 `app/core/celery_app.py`):

- **Broker & Backend**: Redis (`redis>=5.0.4`), 与缓存层 (`app/core/cache.py`) 复用 Redis 实例。
- **定时调度**: Celery Beat, 时区 `Asia/Shanghai`, 启用 UTC。
- **关键配置**:
  - `task_acks_late=True`: 任务执行成功后才 ack, 防止 worker 崩溃丢任务。
  - `worker_prefetch_multiplier=1`: 长任务场景避免单个 worker 囤积任务。
  - `task_default_max_retries=2`、`task_default_retry_delay=60`: 默认重试策略。
  - `result_expires=3600`: 结果保留 1 小时。
- **DLQ 替代方案**: 通过 `task_failure` 信号 (`on_task_failure`) 记录完整失败上下文 (脱敏后) 到日志, 配合 Prometheus 指标 `celery_task_failures_total` 与告警规则 AR-204 触发告警。
- **熔断器**: `app/core/celery_breaker.py` 包装 Celery 调用, 防止 broker 故障时拖垮 API。
- **Beat 调度示例**: `daily-risk-scan` (每日 08:00)、`stale-warning-reminder` (每日 09:00)、`escalate-pending-alerts` (每 60 秒)、`detect-anomaly-access` (每 5 分钟)。

## 替代方案 (Alternatives Considered)
- **RQ (Redis Queue)**: 轻量但无内置定时任务 (需配合 rq-scheduler), 重试与任务追踪能力弱, 不适合复杂调度场景。
- **Dramatiq**: 生态小, 团队熟悉度低, Beat 等价能力需额外集成。
- **Huey**: 功能较弱, 分布式与监控能力不足, 不满足多 worker 部署需求。
- **asyncio.create_task (进程内)**: 进程内调度, 不可跨节点, 进程重启即丢失, 无法满足持久化与多 worker 隔离 ML 训练的需求。

## 后果 (Consequences)
- **正面**:
  - 成熟生态, 文档完善, 团队上手快。
  - Celery Beat 原生支持 cron 与间隔调度, 满足每日风险扫描、告警升级等周期任务。
  - 重试机制 (`max_retries` + `retry_delay`) 内置, 配合 `task_acks_late` 保证任务不丢。
  - Redis broker 与缓存层复用, 减少基础设施组件数。
  - `autodiscover_tasks` 自动扫描 `app/tasks/` 下模块, 任务注册零配置。
- **负面**:
  - Celery 配置项繁多, 检修难度高 (需熟悉 prefetch、acks_late、序列化器语义)。
  - Redis broker 为单点风险, 需通过 Redis 哨兵 (Sentinel) 或集群模式缓解 (当前部署文档见 `docs/DEPLOYMENT_GUIDE.md`)。
  - DLQ 需自建 (通过信号 + 日志 + Prometheus 实现), 不如商业队列开箱即用。
- **中性**:
  - ML 训练 worker 需独立队列与资源隔离, 避免与 PDF 生成任务争抢 GPU/CPU。
  - 需建立 Celery 监控 (Flower 或 Prometheus exporter), 接入告警规则 AR-204。

## 关联 (Related)
- ADR-001: FastAPI 框架选型 (API 层通过 `app/core/celery_async.py` 投递任务)
- `backend/requirements.txt` (Celery / Redis 版本)
- `backend/app/core/celery_app.py` (Celery 实例与 Beat 调度配置)
- `backend/app/core/celery_async.py` (API 层任务投递封装)
- `backend/app/core/celery_breaker.py` (Celery 熔断器)
- `backend/app/tasks/` (任务实现: pdf_report / model_training / anomaly_detection / alerts / scheduler / observability)
- `backend/app/core/alert_rules.py` (AR-204 Celery 失败告警规则)
- `docs/DEPLOYMENT_GUIDE.md` (worker 部署与 Redis 哨兵配置)
- `docs/EMERGENCY_RUNBOOK.md` (broker 故障应急流程)
