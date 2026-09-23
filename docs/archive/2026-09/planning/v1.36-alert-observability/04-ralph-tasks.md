# 04-ralph-tasks — v1.36-alert-observability

> **执行原则**: 按物理顺序执行。每完成标记 `[x]`。
> **版本**: Round 2 修订 (含 cache / instance 工具 + 性能断言)

---

## Phase 0: 基础工具 (P0)

### T0.1 cache 工具

- [x] `app/core/cache.py` 新建
- [x] `async def cache_get(key: str) -> Any | None`
- [x] `async def cache_set(key: str, value: Any, ttl: int = 300) -> bool`
- [x] `def make_cache_key(endpoint: str, params: dict) -> str`
- [x] Redis 不可用降级
- [x] 单元测试 (20/20 通过)

### T0.2 instance 工具

- [x] `app/core/instance.py` 新建
- [x] `def get_instance_id() -> str` (hostname-pid)
- [x] 单元测试 (6/6 通过)

---

## Phase 1: 数据源改造 (P0)

### T1.1 notifier 记录通道发送

- [x] `app/monitoring/notifier.py::CompositeNotifier.send()` 增加 `db` 参数
- [x] 每个 notifier 成功 → 写 OperationLog `alert_channel_sent`
- [x] 每个 notifier 失败 → 写 OperationLog `alert_channel_failed`
- [x] detail 包含 channel/duration_ms/error
- [x] 写日志失败不影响通知返回
- [x] 单元测试

### T1.2 am_sync 记录同步结果

- [x] `app/monitoring/am_sync.py::push_silence` 增加 `db` 参数
- [x] 成功 → 写 OperationLog `am_sync_success`
- [x] 失败 → 写 OperationLog `am_sync_failed`
- [x] `delete_silence` / `pull_silences` 同理
- [x] 写日志失败不影响同步返回
- [x] 单元测试

### T1.3 dedup_lock 内存计数 + flush

- [x] `app/monitoring/dedup_lock.py` 增加模块级 `_stats`
- [x] `try_acquire_lock` 返回时增加 skipped/fallback 计数
- [x] 新增 `flush_lock_stats(db)` 函数
- [x] 新增 `app/tasks/observability.py::flush_lock_stats_task`
- [x] Celery beat 注册 60s 调度
- [x] flush 失败不清零, 下次重试
- [x] 单元测试

### T1.4 OperationLog 复合索引

- [x] `app/models/admin.py::OperationLog.__table_args__` 增加 2 个复合索引
  - `idx_oplog_action_created` (action_type, created_at)
  - `idx_oplog_target_action` (target_type, target_id, action_type)
- [x] Alembic migration 生成/检查
- [x] 单元测试

---

## Phase 2: 7 个观测端点 (P0)

### T2.1 observability 路由骨架

- [x] `app/api/v1/observability.py` 新建
- [x] 注册到 `app/api/v1/__init__.py`
- [x] 公共依赖: db, current_user, require_role("admin")
- [x] 复用 cache 工具 (T0.1)
- [x] 复用 instance 工具 (T0.2)

### T2.2 EP-1 告警趋势

- [x] `GET /alerts/observability/trend`
- [x] 参数: start_time, end_time, bucket, severity, status, group_by
- [x] SQL: GROUP BY date_trunc, severity, action_type
- [x] 集成 cache (5min)
- [x] 集成 instance_id + cached
- [x] 单元测试

### T2.3 EP-2 响应时长

- [x] `GET /alerts/observability/response-time`
- [x] SQL: self-JOIN fired + acknowledged
- [x] 计算 mean / p50 / p95 / p99
- [x] LIMIT 10000 兜底
- [x] 集成 cache / instance_id
- [x] 单元测试

### T2.4 EP-3 升级率

- [x] `GET /alerts/observability/escalation`
- [x] SQL: GROUP BY rule, severity
- [x] 计算 by_level (L1/L2/L3)
- [x] 集成 cache / instance_id
- [x] 单元测试

### T2.5 EP-4 通道成功率

- [x] `GET /alerts/observability/channel-stats`
- [x] SQL: GROUP BY channel
- [x] 计算 sent / failed / success_rate
- [x] 集成 cache / instance_id
- [x] 单元测试 (6/6 通过: basic/zero_failures/multiple_channels/duration_tracking/admin_required/instance_id)

### T2.6 EP-5 静默命中率

- [x] `GET /alerts/observability/silence-hit-rate`
- [x] 简单 ratio: silenced / fired
- [x] 集成 cache / instance_id
- [x] 单元测试 (6/6 通过: basic/by_matcher/by_severity/empty/admin_required/instance_id)

### T2.7 EP-6 AM 同步可观测

- [x] `GET /alerts/observability/am-sync`
- [x] 统计 success/failed + 最近失败
- [x] 集成 cache / instance_id
- [x] 单元测试 (7/7 通过: stats_basic/by_operation/recent_failures/operation_filter/empty/admin_required/instance_id)

### T2.8 EP-7 Redis 锁可观测

- [x] `GET /alerts/observability/lock-stats`
- [x] 读内存 + 上次 flush 时间
- [x] 集成 cache / instance_id
- [x] 单元测试 (6/6 通过: basic/recent_flushes/historical_aggregation/empty/admin_required/instance_id)

---

## Phase 3: 集成 + 性能测试 (P0)

### T3.1 端到端测试

- [x] 触发告警 → webhook → notifier 写 OperationLog → API 查到
- [x] 创建静默 → am_sync 写 OperationLog → API 查到
- [x] 锁降级 → flush 任务 → API 查到

### T3.2 性能测试 (具体断言)

- [x] test_trend_7d_under_500ms (100K rows)
- [x] test_trend_30d_under_1500ms
- [x] test_response_time_7d_under_300ms
- [x] test_response_time_p99_calculation
- [x] test_channel_stats_7d_under_200ms
- [x] test_silence_hit_rate_under_100ms
- [x] test_am_sync_under_100ms
- [x] test_lock_stats_under_50ms

### T3.3 工具模块测试

- [x] test_cache_get_hit / miss / redis_down (已被 TC-CACHE-001 覆盖, Phase 0 完成)
- [x] test_cache_set_redis_down (已被 TC-CACHE-001 覆盖, Phase 0 完成)
- [x] test_make_cache_key_stable (已被 TC-CACHE-001 覆盖, Phase 0 完成)
- [x] test_get_instance_id_format (已被 TC-INSTANCE-001 覆盖, Phase 0 完成)

> **注意**: T3.3 子项均为 Phase 0 (T0.1/T0.2) 已完成的工具模块测试的回归验证.
> 29/29 tests/test_cache.py + tests/test_instance.py 2026-06-03 全通过.

---

## Phase 4: 回归测试 (P0)

### T4.1 核心测试不破坏

- [x] tests/test_dedup.py 全过 (7/7)
- [x] tests/test_dedup_lock.py 全过 (20/20)
- [x] tests/test_am_sync.py 全过 (19/19)
- [x] tests/test_alert_tasks.py 全过 (9/9)
- [x] tests/api/test_silences_api.py 全过 (8/8)
- [x] tests/api/test_alerts_webhook.py 全过 (11/11)
- [x] tests/test_silence.py 全过 (11/11)
- [x] tests/test_escalation.py 全过 (9/9)
- [x] tests/test_notifier.py 全过 (26/26)
- [x] tests/api/test_alert_archive_api.py 全过 (6/6)

> **总计**: 126/126 测试通过, 2 个 RuntimeWarning (unawaited coroutine in test mocks, 非失败)

---

## 进度统计

- 总任务: 5 phases (含 Phase 0)
- P0: 5 phases
- 完成: 0/5 (0%)
