# 01-requirements — v1.32-observability-complete

> **迭代**: v1.32-observability-complete
> **基础**: v1.31-iteration-cleanup (DELIVERED)
> **创建**: 2026-06-03
> **类型**: Observability / Compliance

---

## 1. 目标

在 v1.30 Prometheus 集成基础上, 完善生产级可观测性与合规审计能力:

| 维度 | v1.31 | v1.32 目标 |
|:---|:---:|:---:|
| 监控可视化 | 仅 Prometheus metrics | **Grafana Dashboard** ✅ |
| 告警规则 | 无 | **Prometheus Alert Rules** ✅ |
| 错误追踪 | Sentry stub | **Sentry 性能追踪 + 弃用 API 修复** ✅ |
| 模型推理指标 | 仅 total counter | **total + duration + 状态** ✅ |
| 运维摘要 | 无 | **`/api/v1/admin/metrics-summary`** ✅ |
| 合规审计 | `operation-logs` (单 action_type) | **`audit-logs` (多 action_type + 统计)** ✅ |

---

## 2. 范围

### 2.1 Grafana Dashboard (P0)

- 路径: `monitoring/grafana/dashboard.json`
- 覆盖面板:
  - HTTP RPS (按 method/path 维度)
  - HTTP P50/P95/P99 延迟
  - 5xx 错误率
  - WebSocket 活跃连接数
  - 模型推理次数 (按 model_name 维度)
  - 模型推理 P95 延迟
  - 数据库连接池大小
  - 应用信息 (`app_info`)

### 2.2 Prometheus Alert Rules (P0)

- 路径: `monitoring/prometheus/alerts.yml`
- 关键告警 (3 个等级):
  - **Critical**: `HighErrorRate` (>5% 5xx), `ModelInferenceFailure` (>10% error), `DatabasePoolExhausted` (>90%), `ApplicationDown` (1m)
  - **Warning**: `HighLatencyP99` (>1s), `ModelInferenceLatency` (P95>2s), `WebSocketConnectionsHigh` (>1000)
  - **Info**: `ElevatedErrorRate` (>1%), `SlowRequestRate`, `RequestVolumeSpike`, `ModelInferenceSlow`
- 记录规则 (5 个): `dws:http_requests:rate5m`, `dws:http_requests:error_rate5m`, `dws:http_request_duration:p99_5m`, `dws:http_request_duration:p50_5m`, `dws:model_inference:rate5m`, `dws:model_inference:error_rate5m`

### 2.3 Sentry 集成增强 (P0)

- 路径: `app/core/sentry.py`
- 升级内容:
  - 修复 `push_scope` 弃用警告 → `new_scope`
  - 添加性能追踪 (`traces_sample_rate`, `profiles_sample_rate`)
  - 添加 FastAPI + SQLAlchemy 集成
  - 测试覆盖: `test_sentry.py` 4/4 通过

### 2.4 模型推理指标 (P0)

- 新增: `track_model_inference` 上下文管理器
- 路径: `app/core/metrics.py`
- 接入: `app/api/v1/model_predict.py` 4 个端点 (`tabular`, `text`, `physiological`, `fusion`)
- 自动记录:
  - `model_inference_total{model_name, status}` (success/error)
  - `model_inference_duration_seconds{model_name}` (Histogram)
- 测试: `test_model_inference_metrics.py` 5/5 通过

### 2.5 Admin Metrics Summary (P0)

- 端点: `GET /api/v1/admin/metrics-summary`
- 路径: `app/api/v1/admin_metrics.py`
- 返回:
  - `http`: total_requests, 5xx_errors, error_rate, top_paths
  - `websocket`: active_connections
  - `database`: pool_size
  - `model_inference`: 按 model_name 的 success/error 统计
  - `version`, `env`, `timestamp`
- 测试: `test_admin_metrics.py` 3/3 通过

### 2.6 Audit-Logs 合规端点 (P1)

- 端点: `GET /api/v1/admin/audit-logs`
- 路径: `app/api/v1/admin.py`, `app/services/admin_service.py::list_audit_logs`
- 与 `operation-logs` 差异:
  - 支持**多 action_type** 过滤 (合规批量查询)
  - 新增 `target_type` 过滤
  - 返回 `compliance.action_breakdown` (按类型分组)
  - 返回 `compliance.retention_days` (90 天)
  - 返回 `compliance.earliest_log` / `latest_log` (范围检查)
- 适用场景: GDPR 审查 / 等保 2.0 审计 / 内控合规
- 测试: `test_audit_logs_api.py` 5/5 通过

---

## 3. 非功能需求

- **零外部依赖**: Grafana/Prometheus 配置文件不引入运行时依赖
- **优雅降级**: Sentry 缺失时, `init_sentry` 直接返回, 不影响主应用
- **指标无侵入**: `track_model_inference` 失败被吞掉, 不影响主流程
- **版本一致性**: 全部指标/version 字符串统一为 `v1.32-observability-complete`

---

## 4. 不在范围

- 训练 v2 模型
- 实时告警通知 (Slack/Email 集成) — 由 v1.33 计划
- 分布式追踪 (OpenTelemetry) — 由 v1.33 计划
- 审计日志归档自动化 (依赖 `archive-logs` 已存在)

---

## 5. 关联文档

| 文档 | 路径 |
|:---|:---|
| 上一迭代 | [../v1.31-iteration-cleanup/RALPH_STATE.md](../v1.31-iteration-cleanup/RALPH_STATE.md) |
| Prometheus 集成 | [../v1.30-quality-and-monitoring/PROMETHEUS_INTEGRATION.md](../v1.30-quality-and-monitoring/PROMETHEUS_INTEGRATION.md) |
