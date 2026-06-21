# 05-test-plan — v1.35-multi-instance-alerting

> 验证清单. 每完成标记 `[x]`.

---

## Phase 1: 跨实例去重

### TC-DLOCK-001: Redis 锁

- [x] test_acquire_lock_success
- [x] test_acquire_lock_already_held_returns_false
- [x] test_acquire_lock_ttl_expires
- [x] test_acquire_lock_redis_down_falls_back

### TC-DLOCK-002: 集成

- [x] test_should_send_uses_redis_when_available
- [x] test_should_send_redis_skip_returns_false
- [x] test_should_send_redis_down_uses_sql

---

## Phase 2: AlertArchive 模型

### TC-ARC-001: 模型基础

- [x] test_create_archive
- [x] test_archive_preserves_original_id
- [x] test_archive_preserves_labels

---

## Phase 3: 实际归档

### TC-ARC-002: 归档逻辑

- [x] test_archive_older_than_90_days
- [x] test_archive_keeps_recent
- [x] test_archive_idempotent
- [x] test_archive_transaction_atomic
- [x] test_archive_batch_limit_1000

### TC-ARC-003: 归档查询 API

- [x] test_archive_api_requires_admin
- [x] test_archive_api_filter_by_rule
- [x] test_archive_api_filter_by_severity
- [x] test_archive_api_pagination

---

## Phase 4: AlertManager 同步

### TC-AMS-001: push 同步

- [x] test_push_silence_to_am
- [x] test_push_silence_am_unavailable
- [x] test_create_silence_syncs_to_am

### TC-AMS-002: pull 同步

- [x] test_pull_silences_from_am
- [x] test_am_silence_deactivate_local

### TC-AMS-003: webhook 接收

- [x] test_am_webhook_creates_silence
- [x] test_am_webhook_deactivates_silence
- [x] test_am_webhook_invalid_signature

---

## Phase 5: 全量回归

### TC-REG-001: 核心测试不破坏

- [x] test_dedup.py 全过
- [x] test_silence.py 全过
- [x] test_alert_tasks.py 全过
- [x] test_silences_api.py 全过
- [x] test_alerts_webhook.py 全过
- [x] test_escalation.py 全过
- [x] test_metrics.py 全过
- [x] test_tracing.py 全过
- [x] test_notifier.py 全过

---

## 进度统计

- 总测试: 5 phases
- 完成: 5/5 (100%)
