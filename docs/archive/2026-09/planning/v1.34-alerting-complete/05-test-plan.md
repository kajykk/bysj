# 05-test-plan — v1.34-alerting-complete

> 验证清单. 每完成标记 `[x]`.

---

## Phase 1: 告警去重

### TC-DEDUP-001: 基础去重

- [ ] test_should_send_first_alert
- [ ] test_should_skip_duplicate_within_5min
- [ ] test_should_send_again_after_5min
- [ ] test_dedup_with_no_fingerprint
- [ ] test_dedup_different_fingerprints_independent

---

## Phase 2: 静默窗口

### TC-SIL-001: 模型基础

- [ ] test_create_silence
- [ ] test_silence_with_matcher
- [ ] test_silence_starts_ends

### TC-SIL-002: 匹配逻辑

- [ ] test_is_silenced_by_alertname
- [ ] test_is_silenced_by_severity
- [ ] test_is_silenced_by_combined_matcher
- [ ] test_not_silenced_outside_window
- [ ] test_not_silenced_no_match

### TC-SIL-003: API

- [ ] test_api_create_silence_requires_admin
- [ ] test_api_create_silence_success
- [ ] test_api_list_silences
- [ ] test_api_delete_silence
- [ ] test_api_list_active_silences
- [ ] test_api_silence_overlap_validation

### TC-SIL-004: webhook 集成

- [ ] test_webhook_silenced_does_not_notify
- [ ] test_webhook_silenced_persists_to_log

---

## Phase 3: Celery 升级调度

### TC-CEL-001: 任务执行

- [ ] test_escalate_task_invokes_logic
- [ ] test_escalate_task_handles_no_alerts
- [ ] test_escalate_task_retries_on_failure
- [ ] test_escalate_task_logs_execution

### TC-CEL-002: beat 调度

- [ ] test_beat_schedule_contains_escalate
- [ ] test_escalate_schedule_minute_interval

---

## Phase 4: 告警归档

### TC-ARC-001: 模型基础

- [ ] test_create_archive
- [ ] test_archive_preserves_fields

### TC-ARC-002: 归档逻辑

- [ ] test_archive_older_than_90_days
- [ ] test_archive_keeps_recent
- [ ] test_archive_idempotent
- [ ] test_archive_task_executes

---

## Phase 5: 全量回归

### TC-REG-001: 核心测试不破坏

- [ ] test_tracing.py 全过
- [ ] test_notifier.py 全过
- [ ] test_escalation.py 全过
- [ ] test_alerts_webhook.py 全过
- [ ] test_metrics.py 全过
- [ ] test_admin_metrics.py 全过
- [ ] test_audit_logs.py 全过
- [ ] test_operation_logs.py 全过
- [ ] test_sentry.py 全过
- [ ] test_model_inference_metrics.py 全过

---

## 进度统计

- 总测试: 5 phases
- 完成: 0/5 (0%)
