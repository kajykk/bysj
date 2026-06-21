# 05-test-plan — v1.32-observability-complete

> 验证清单. 每完成标记 `[x]`.

---

## Phase 1: Grafana Dashboard

### TC-GF-001: dashboard.json 结构

- [x] 路径: `monitoring/grafana/dashboard.json`
- [x] 包含 HTTP / WebSocket / Model / DB panels

---

## Phase 2: Prometheus Alerts

### TC-PM-001: alerts.yml 关键告警

- [x] 路径: `monitoring/prometheus/alerts.yml`
- [x] 包含 HighErrorRate (Critical)
- [x] 包含 ModelInferenceFailure (Critical)
- [x] 包含 DatabasePoolExhausted (Critical)
- [x] 包含 ApplicationDown (Critical)
- [x] 包含 4 个 info/warning 级告警
- [x] 包含 5+ 记录规则

---

## Phase 3: Sentry 集成

### TC-SEN-001: init_sentry 兼容性

- [x] tests/test_sentry.py::test_init_sentry_no_dsn
- [x] tests/test_sentry.py::test_capture_exception_without_sentry
- [x] tests/test_sentry.py::test_capture_message_without_sentry
- [x] tests/test_sentry.py::test_init_sentry_with_dsn
- [x] 无 `push_scope` 弃用警告

---

## Phase 4: 模型推理指标

### TC-MI-001: track_model_inference 基础

- [x] test_track_model_inference_success
- [x] test_track_model_inference_error
- [x] test_track_model_inference_duration
- [x] test_track_model_inference_metrics_failure_does_not_break
- [x] test_track_model_inference_nested

---

## Phase 5: Admin Metrics Summary

### TC-AMS-001: /api/v1/admin/metrics-summary

- [x] test_metrics_summary_requires_admin
- [x] test_metrics_summary_admin_success
- [x] test_metrics_summary_collects_http_stats
- [x] 验证 version 字段 = v1.32-observability-complete

### TC-AMS-002: Prometheus metrics 端点

- [x] test_metrics_endpoint_returns_200
- [x] test_metrics_endpoint_format_valid
- [x] test_metrics_contains_app_info (v1.32)
- [x] test_http_request_counter_increments
- [x] test_histogram_has_buckets
- [x] test_metrics_excludes_metrics_endpoint_itself
- [x] test_websocket_gauge
- [x] test_counter_label_validation
- [x] test_render_exposition_idempotent

### TC-AMS-003: Observability service

- [x] TestLatencyHistogram 4/4
- [x] TestCounter 3/3
- [x] TestObservabilityCollector 9/9

---

## Phase 6: Audit-Logs

### TC-AL-001: /api/v1/admin/audit-logs

- [x] test_admin_can_query_audit_logs
- [x] test_audit_logs_requires_admin
- [x] test_audit_logs_action_types_filter
- [x] test_audit_logs_target_type_filter
- [x] test_audit_logs_pagination

### TC-AL-002: operation-logs 不受影响

- [x] test_admin_can_query_operation_logs (回归)

---

## Phase 7: 全量回归

### TC-REG-001: 核心可观测性测试 100%

- [x] metrics, observability, model_inference, admin_metrics, audit_logs, operation_logs, sentry 全过

---

## 进度统计

- 总测试: 7 phases
- 完成: **7/7 (100%)**
- 单测通过率: **43/43 (100%)**
