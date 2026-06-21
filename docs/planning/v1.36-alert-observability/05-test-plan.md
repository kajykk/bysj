# 05-test-plan — v1.36-alert-observability

> 验证清单. 每完成标记 `[x]`.
> **版本**: Round 2 修订 (含工具测试 + 性能断言)

---

## Phase 0: 基础工具

### TC-CACHE-001: cache 工具

- [x] test_cache_get_hit
- [x] test_cache_get_miss
- [x] test_cache_get_redis_down_falls_back
- [x] test_cache_set_success
- [x] test_cache_set_redis_down_logs_only
- [x] test_make_cache_key_stable_for_same_params
- [x] test_make_cache_key_differs_for_different_params

### TC-INSTANCE-001: instance 工具

- [x] test_get_instance_id_format
- [x] test_get_instance_id_unique_per_pid

---

## Phase 1: 数据源改造

### TC-DATA-001: notifier 记录通道

- [x] test_channel_sent_logged_on_success
- [x] test_channel_failed_logged_on_failure
- [x] test_channel_log_includes_duration_ms
- [x] test_channel_log_failure_does_not_block_notification
- [x] test_channel_log_detail_includes_error

### TC-DATA-002: am_sync 记录同步

- [x] test_am_sync_success_logged
- [x] test_am_sync_failed_logged
- [x] test_am_sync_log_includes_am_silence_id
- [x] test_am_sync_log_failure_does_not_block_sync

### TC-DATA-003: dedup_lock 统计

- [x] test_lock_stats_incremented_on_skipped
- [x] test_lock_stats_incremented_on_fallback
- [x] test_flush_lock_stats_writes_to_db
- [x] test_flush_lock_stats_clears_memory
- [x] test_flush_lock_stats_failure_keeps_memory

### TC-DATA-004: 复合索引

- [x] test_idx_oplog_action_created_exists
- [x] test_idx_oplog_target_action_exists

---

## Phase 2: 7 个观测端点

### TC-OBS-000: 路由骨架

- [x] test_observability_router_importable
- [x] test_observability_registered_in_api_router
- [x] test_observability_helpers_export
- [x] test_observability_health_via_test_client
- [x] test_observability_health_with_admin
- [x] test_cached_or_compute_cache_hit
- [x] test_cached_or_compute_cache_miss
- [x] test_with_instance_meta_basic
- [x] test_with_instance_meta_extra

### TC-OBS-001: 趋势 API

- [x] test_trend_basic_24h
- [x] test_trend_with_severity_filter
- [x] test_trend_with_status_filter
- [x] test_trend_group_by_rule
- [x] test_trend_admin_required
- [x] test_trend_cached_5min
- [x] test_trend_response_includes_instance_id

### TC-OBS-002: 响应时长 API

- [x] test_response_time_basic
- [x] test_response_time_percentiles
- [x] test_response_time_pending_alerts
- [x] test_response_time_admin_required
- [x] test_response_time_response_includes_instance_id
- [x] test_percentile_basic
- [x] test_percentile_empty
- [x] test_response_time_severity_breakdown

### TC-OBS-003: 升级率 API

- [x] test_escalation_rate_basic
- [x] test_escalation_by_level
- [x] test_escalation_by_rule
- [x] test_escalation_by_severity
- [x] test_escalation_admin_required
- [x] test_escalation_response_includes_instance_id

### TC-OBS-004: 通道成功率 API

- [x] test_channel_stats_basic
- [x] test_channel_stats_zero_failures
- [x] test_channel_stats_multiple_channels
- [x] test_channel_stats_duration_tracking
- [x] test_channel_stats_admin_required
- [x] test_channel_stats_response_includes_instance_id

### TC-OBS-005: 静默命中率 API

- [x] test_silence_hit_rate_basic
- [x] test_silence_hit_rate_by_matcher
- [x] test_silence_hit_rate_by_severity
- [x] test_silence_hit_rate_empty
- [x] test_silence_hit_rate_admin_required
- [x] test_silence_hit_rate_response_includes_instance_id

### TC-OBS-006: AM 同步可观测

- [x] test_am_sync_stats_basic
- [x] test_am_sync_by_operation
- [x] test_am_sync_recent_failures
- [x] test_am_sync_operation_filter
- [x] test_am_sync_empty
- [x] test_am_sync_admin_required
- [x] test_am_sync_response_includes_instance_id

### TC-OBS-007: Redis 锁可观测

- [x] test_lock_stats_basic
- [x] test_lock_stats_recent_flushes
- [x] test_lock_stats_historical_aggregation
- [x] test_lock_stats_empty
- [x] test_lock_stats_admin_required
- [x] test_lock_stats_response_includes_instance_id

---

## Phase 3: 集成 + 性能测试

### TC-INT-001: 端到端

- [x] test_e2e_alert_to_channel_stats
- [x] test_e2e_silence_to_am_sync
- [x] test_e2e_lock_fallback_to_stats

### TC-PERF-001: 性能

- [x] test_trend_7d_under_500ms
- [x] test_trend_30d_under_1500ms
- [x] test_response_time_7d_under_300ms
- [x] test_response_time_p99_calculation
- [x] test_channel_stats_7d_under_200ms
- [x] test_silence_hit_rate_under_100ms
- [x] test_am_sync_under_100ms
- [x] test_lock_stats_under_50ms

---

## Phase 4: 全量回归

### TC-REG-001: 核心测试不破坏

- [x] test_dedup.py 全过 (7/7)
- [x] test_dedup_lock.py 全过 (20/20)
- [x] test_am_sync.py 全过 (19/19)
- [x] test_alert_tasks.py 全过 (9/9)
- [x] test_silences_api.py 全过 (8/8)
- [x] test_alerts_webhook.py 全过 (11/11)
- [x] test_silence.py 全过 (11/11)
- [x] test_escalation.py 全过 (9/9)
- [x] test_notifier.py 全过 (26/26)
- [x] test_alert_archive_api.py 全过 (6/6)

---

## 进度统计

- 总测试: 5 phases
- 完成: 5/5 (100%) ✅
