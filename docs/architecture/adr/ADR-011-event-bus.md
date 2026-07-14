# ADR-011: 进程内 EventBus 事件驱动可观测性改造

## 状态 (Status)
Accepted

## 日期 (Date)
2026-07-03

## 上下文 (Context)
DWS 系统的 `ObservabilityExporter` (v1.39) 采用 60s 周期轮询 `_compute_*` 函数采集指标并发布到 Prometheus。该方案在以下场景存在不足:

1. **延迟高**: 告警触发后, 最坏情况需等待 60s 下次轮询周期才能反映到 Prometheus 指标, 不满足实时告警需求;
2. **资源浪费**: 无论是否有事件发生, 每 60s 都会执行 8 个 `_compute_*` 查询, 低负载时产生不必要的 DB 压力;
3. **无法捕获瞬态事件**: 短时间内多次触发-恢复的告警 (如 flapping) 可能在两次轮询间发生并消失, 导致指标漏报;
4. **Grafana Alerting 延迟**: Grafana Alert rules 查询 Prometheus 指标, 60s 的采集周期加上 Grafana 自身的评估间隔, 端到端告警延迟可达 2 分钟以上。

需求:
1. **实时性**: 关键业务事件 (告警触发/恢复/升级、风险预警创建、复核任务提交) 发生后, Prometheus 指标在 5s 内更新;
2. **可靠性**: 事件丢失不影响系统正确性, 60s 周期轮询作为兜底;
3. **低耦合**: 事件发布不应侵入业务逻辑, 不阻塞业务主流程;
4. **可扩展**: 支持后续添加新事件类型和订阅者。

## 决策 (Decision)
采用轻量级进程内 `EventBus` 实现事件驱动指标更新, 保留 60s 周期轮询作为兜底。

### 架构设计

```
业务服务 ──publish──> EventBus (asyncio.Queue, maxsize=10000)
                            │
                            ├──> ObservabilityExporter._on_alert_fired
                            │     → metrics.event_alerts_fired_total.inc()
                            ├──> ObservabilityExporter._on_warning_created
                            │     → metrics.event_warnings_created_total.inc()
                            └──> ... (其他事件处理器)

                       ┌──── 兜底 ────┐
ObservabilityExporter   │  60s 轮询    │  ← 防止事件丢失
_loop() ──────────────> └──────────────┘
```

### 核心组件

1. **`app/core/event_bus.py`** — 进程内异步事件总线:
   - `EventBus` 类: `subscribe(event_type, handler)` / `publish(event_type, data)` / `start()` / `stop()`
   - 使用 `asyncio.Queue` (maxsize=10000) 作为事件缓冲
   - 非阻塞 publish (`put_nowait`), 队列满时丢弃事件并递增 `events_dropped` 计数
   - 单 handler 异常不影响其他 handler (try/except 隔离)
   - 全局单例 `event_bus = EventBus()`

2. **5 类关键业务事件**:
   | 事件类型 | 发布点 | 订阅者 |
   |---------|--------|--------|
   | `alert.fired` | `AlertLifecycleService.transition_alert` (目标状态 TRIGGERED) | `ObservabilityExporter._on_alert_fired` |
   | `alert.resolved` | `AlertLifecycleService.transition_alert` (目标状态 RESOLVED) | `ObservabilityExporter._on_alert_resolved` |
   | `alert.escalated` | `AlertLifecycleService.transition_alert` (目标状态 ACKNOWLEDGED) | `ObservabilityExporter._on_alert_escalated` |
   | `warning.created` | `RiskService._check_warning_trigger` (WarningNotification 创建后) | `ObservabilityExporter._on_warning_created` |
   | `review.submitted` | `ReviewService.create_review_task` (ReviewTask 创建后) | `ObservabilityExporter._on_review_submitted` |

3. **6 个事件驱动 Prometheus Counter** (`app/core/metrics.py`):
   - `event_alerts_fired_total` / `event_alerts_resolved_total` / `event_alerts_escalated_total`
   - `event_warnings_created_total` / `event_reviews_submitted_total`
   - `event_bus_dropped_total` (队列满丢弃计数)

4. **lifespan 集成**:
   - `ObservabilityExporter.start()` 内部调用 `await event_bus.start()` 启动消费循环
   - `ObservabilityExporter.stop()` 内部调用 `await event_bus.stop()` 停止消费循环
   - 不在 `main.py` lifespan 中单独管理 EventBus 生命周期, 避免双重管理

### 设计要点

- **fire-and-forget**: 事件发布采用 `put_nowait`, 不等待处理完成, 不阻塞业务主流程
- **异常隔离**: 单个 handler 抛异常时, 仅记录 `handler_errors` 计数, 不影响其他 handler
- **兜底机制**: 保留 60s 周期轮询, 即使事件全部丢失, 指标最迟 60s 后自动修正
- **不保证 exactly-once**: 事件可能与 60s 轮询重复计数, Prometheus Counter 语义为单调递增, Grafana Alert rules 使用 `rate()` 函数消解重复计数的影响

## 替代方案 (Alternatives Considered)

1. **Redis pubsub 跨进程事件总线** — 使用 Redis `PUBLISH/SUBSCRIBE` 实现跨进程事件分发。优点: 支持多 worker 部署; 缺点: 引入 Redis 依赖, 增加网络延迟 (1-2ms), 需处理订阅断连重试。当前 ObservabilityExporter 在单进程内运行, 跨进程事件留待后续升级。

2. **Celery task 异步事件** — 将事件发布为 Celery task。优点: 复用现有 Celery 基础设施; 缺点: Celery task 序列化/反序列化开销大 (~10ms), broker 不可用时事件丢失, 不满足 < 5s 延迟要求。

3. **WebSocket 实时推送** — 通过 WebSocket 将事件推送到前端。优点: 用户可实时感知; 缺点: 不解决 Prometheus 指标延迟问题, 且前端非本方案目标受众。

4. **缩短轮询周期至 5s** — 将 60s 轮询改为 5s。优点: 实现最简单; 缺点: DB 查询频率提升 12 倍, 低负载时浪费严重; 8 个 `_compute_*` 查询每 5s 执行一次, 高负载时可能压垮 DB。

5. **Prometheus pushgateway** — 业务服务主动 push 指标到 pushgateway。优点: 实时性最好; 缺点: pushgateway 非本系统部署组件, 需额外引入, 且 Prometheus 官方不建议用于服务端指标推送。

## 后果 (Consequences)
- **正面**:
  - 端到端延迟从 60s 降至 < 5s (单进程内通常 < 100ms), 满足实时告警需求;
  - 事件驱动指标实时反映业务状态, Grafana Alert rules 可更快触发告警通知;
  - 60s 轮询保留作为兜底, 系统健壮性不受影响;
  - EventBus 设计轻量 (单文件 ~140 行), 无外部依赖, 易于维护;
  - 事件发布非阻塞 (`put_nowait`), 不影响业务请求延迟;
  - 事件类型可扩展, 后续添加新事件只需 `subscribe` + `publish`。
- **负面**:
  - 进程内事件总线不跨进程: Celery worker 触发的事件无法通知到 FastAPI 进程的 ObservabilityExporter (后续升级为 Redis pubsub 可解决);
  - 事件队列满时丢弃事件: 队列容量 10000, 正常负载下不会触发, 但突发流量时可能丢失少量事件 (60s 轮询兜底修正);
  - 事件可能与轮询重复计数: Prometheus Counter 单调递增, Grafana 使用 `rate()` 消解重复, 但裸查询 Counter 值可能偏高;
  - 事件发布在 `flush()` 之后但 `commit()` 之前: 若后续 commit 失败, 指标略有偏差 (事件已发布但 DB 事务回滚), 60s 轮询会自动修正。
- **中性**:
  - 新增 6 个 Prometheus Counter 指标, Grafana dashboard 需对应添加面板;
  - 业务服务新增 `await event_bus.publish(...)` 调用, 但为非阻塞操作, 对请求延迟影响可忽略 (< 0.1ms);
  - 测试需 mock EventBus 或使用独立实例, `test_event_bus.py` 提供完整测试覆盖。

## 关联 (Related)
- 核心模块: `backend/app/core/event_bus.py` (EventBus 实现), `backend/app/core/metrics.py:248-273` (6 个事件驱动 Counter)
- 订阅者: `backend/app/services/observability_exporter.py:62-96` (5 个事件处理器)
- 事件发布点:
  - `backend/app/services/alert_lifecycle_service.py:206-243` (alert.fired/resolved/escalated)
  - `backend/app/services/risk_service.py:750-770` (warning.created)
  - `backend/app/services/review_service.py:99-117` (review.submitted)
- lifespan 集成: `backend/app/main.py:84-85` (ObservabilityExporter.start/stop 内部管理 EventBus 生命周期)
- 测试: `backend/tests/test_event_bus.py` (9 个测试: 基本功能/容错/实时指标/延迟/生命周期)
- 计划文档: `docs/SYSTEM_OPTIMIZATION_FOLLOWUP_PLAN.md:1031-1259` (R-C 任务详细实施计划)
- 相关 ADR: ADR-006 (ObservabilityExporter 60s 周期轮询设计 — 本 ADR 在此基础上增加事件驱动层)
