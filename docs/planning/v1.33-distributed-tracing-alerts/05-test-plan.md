# 05-test-plan — v1.33-distributed-tracing-alerts

> 验证清单. 每完成标记 `[x]`.

---

## Phase 1: W3C Trace Context

### TC-TR-001: tracing 模块基础

- [x] test_parse_traceparent_valid
- [x] test_parse_traceparent_invalid_format
- [x] test_parse_traceparent_invalid_ids
- [x] test_new_trace_context
- [x] test_new_trace_context_unique
- [x] test_trace_context_to_traceparent

### TC-TR-002: span 嵌套

- [x] test_trace_context_child_span
- [x] test_span_context_creates_child
- [x] test_span_context_nested
- [x] test_span_context_exception_cleanup

### TC-TR-003: 跨服务传播

- [x] test_extract_or_new_trace_with_parent
- [x] test_extract_or_new_trace_without_parent

### TC-TR-004: 日志注入

- [x] test_trace_log_filter
- [x] test_trace_log_filter_no_trace

### TC-TR-005: 序列化

- [x] test_to_dict

**Phase 1 通过**: 15/15

---

## Phase 2: 告警多通道

### TC-NT-001: Webhook 通知

- [x] test_webhook_notifier_is_configured
- [x] test_webhook_notifier_is_configured_with_url
- [x] test_webhook_notifier_send_success
- [x] test_webhook_notifier_retry_on_5xx
- [x] test_webhook_notifier_give_up_after_max_retries
- [x] test_webhook_notifier_silent_on_exception

### TC-NT-002: Slack 通知

- [x] test_slack_notifier_unconfigured
- [x] test_slack_notifier_send_success
- [x] test_slack_notifier_resolved_status
- [x] test_slack_notifier_p1_color

### TC-NT-003: 钉钉通知

- [x] test_dingtalk_notifier_sign
- [x] test_dingtalk_notifier_send_without_secret
- [x] test_dingtalk_notifier_at_mobiles_p0
- [x] test_dingtalk_notifier_no_at_for_p1

### TC-NT-004: Email 通知

- [x] test_email_notifier_no_recipients
- [x] test_email_notifier_smtp_not_configured
- [x] test_email_notifier_send_success

### TC-NT-005: Composite 通知

- [x] test_composite_skips_unconfigured
- [x] test_composite_fans_out
- [x] test_composite_partial_failure
- [x] test_composite_handles_exception

**Phase 2 通过**: 21/21

---

## Phase 3: AlertManager Webhook

### TC-AW-001: payload 解析

- [x] test_webhook_receives_alertmanager_payload
- [x] test_webhook_handles_empty_alerts
- [x] test_webhook_severity_normalization
- [x] test_webhook_handles_resolved_status

### TC-AW-002: 持久化

- [x] test_webhook_persists_to_operation_log

### TC-AW-003: history 查询

- [x] test_history_requires_admin
- [x] test_history_admin_success
- [x] test_history_filter_by_severity
- [x] test_history_pagination

### TC-AW-004: acknowledge

- [x] test_ack_alert_not_found
- [x] test_ack_alert_requires_admin

**Phase 3 通过**: 11/11

---

## Phase 4: 告警升级

### TC-ESC-001: 升级策略

- [x] test_compute_escalation_p1_after_10m
- [x] test_compute_escalation_p1_before_10m
- [x] test_compute_escalation_p0_after_30m
- [x] test_compute_escalation_p0_after_1h
- [x] test_compute_escalation_acknowledged_stops
- [x] test_compute_escalation_idempotent
- [x] test_compute_escalation_not_firing
- [x] test_compute_escalation_p2_no_escalation

### TC-ESC-002: 阈值定义

- [x] test_thresholds_defined

**Phase 4 通过**: 9/9

---

## Phase 5: 全量回归

### TC-REG-001: 核心测试不破坏

- [x] test_tracing.py 15/15
- [x] test_notifier.py 21/21
- [x] test_escalation.py 9/9
- [x] test_alerts_webhook.py 11/11
- [x] test_metrics.py 9/9
- [x] test_admin_metrics.py 3/3
- [x] test_audit_logs.py 5/5
- [x] test_operation_logs.py 1/1
- [x] test_sentry.py 4/4
- [x] test_model_inference_metrics.py 5/5

**全量回归**: 83/83 (100%)

---

## 进度统计

| Phase | 测试数 | 通过率 |
|:---|:---:|:---:|
| Phase 1: Tracing | 15/15 | 100% ✅ |
| Phase 2: Notifier | 21/21 | 100% ✅ |
| Phase 3: Alerts Webhook | 11/11 | 100% ✅ |
| Phase 4: Escalation | 9/9 | 100% ✅ |
| Phase 5: 回归 | 27/27 | 100% ✅ |
| **总计** | **83/83** | **100%** ✅ |
