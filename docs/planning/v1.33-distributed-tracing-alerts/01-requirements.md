# 01-requirements — v1.33-distributed-tracing-alerts

> **迭代**: v1.33-distributed-tracing-alerts
> **基础**: v1.32-observability-complete (DELIVERED)
> **创建**: 2026-06-03
> **类型**: Observability / Notification

---

## 1. 目标

完成可观测性最后一公里 — 分布式追踪 + 告警通知:

| 维度 | v1.32 | v1.33 目标 |
|:---|:---:|:---:|
| 请求追踪 | request_id (无父子关系) | **W3C traceparent (trace_id+span_id)** ✅ |
| 跨服务追踪 | 不支持 | **trace_id 传播** ✅ |
| 告警通道 | 仅 Webhook | **Webhook + Slack + 钉钉 + Email** ✅ |
| 告警接收 | 无 | **`/api/v1/alerts/webhook` (AlertManager)** ✅ |
| 告警升级 | 无 | **10m→30m→1h 三级升级** ✅ |
| 告警历史 | 无 | **持久化到 OperationLog** ✅ |

---

## 2. 范围

### 2.1 W3C Trace Context 集成 (P0)

- 路径: `app/core/tracing.py`
- 实现:
  - 解析 `traceparent` header (W3C Trace Context)
  - 生成 `trace_id` (16 字节 hex) + `span_id` (8 字节 hex)
  - 嵌套 `span_context` 上下文管理器
  - 自动注入到 `request_id` 体系
  - 注入到 Sentry tags
  - 注入到响应 header
- 零外部依赖 (不引入 OpenTelemetry)

### 2.2 Trace 传播到所有日志 (P0)

- 路径: `app/core/middlewares.py` (request_id_middleware)
- 增强:
  - log record 自动添加 `trace_id` / `span_id` 字段
  - Sentry `set_tag("trace_id", ...)`
  - 响应 header `X-Trace-Id` / `X-Span-Id`

### 2.3 告警多通道通知 (P0)

- 路径: `app/monitoring/notifier.py`
- 通道:
  - `webhook` (通用 JSON POST)
  - `slack` (Slack Incoming Webhook 格式)
  - `dingtalk` (钉钉机器人签名)
  - `email` (复用现有 smtp 配置)
- 配置: 通过 `ALERT_*` 环境变量

### 2.4 AlertManager Webhook 接收 (P0)

- 端点: `POST /api/v1/alerts/webhook`
- 路径: `app/api/v1/alerts.py`
- 行为:
  - 接收 AlertManager JSON payload
  - 解析为内部 `AlertEvent`
  - 触发 `AlertingEngine.evaluate`
  - 记录到 `OperationLog`
  - 返回 200 阻止 AlertManager 重试

### 2.5 告警升级策略 (P1)

- 路径: `app/monitoring/escalation.py`
- 策略:
  - 10 分钟未确认 → 升级到 P1
  - 30 分钟未确认 → 升级到 P0
  - 1 小时未确认 → 触发 P0 + 记录 P0 告警
  - 支持 acknowledge 端点

### 2.6 告警历史查询 (P1)

- 端点: `GET /api/v1/alerts/history`
- 路径: `app/api/v1/alerts.py`
- 支持过滤: severity, status, start_time, end_time

---

## 3. 非功能需求

- **零外部依赖**: 追踪不引入 OpenTelemetry SDK
- **告警通知失败不阻塞**: 重试 + 降级到日志
- **trace_id 兼容性**: 与 Sentry/OpenTelemetry trace_id 格式一致 (16 字节 hex)
- **PII 安全**: trace 不记录敏感数据

---

## 4. 不在范围

- 完整 OpenTelemetry instrumentation
- Jaeger/Tempo 后端部署
- PagerDuty / OpsGenie 集成
- 告警静默/抑制 (silencing)

---

## 5. 关联文档

| 文档 | 路径 |
|:---|:---|
| 上一迭代 | [../v1.32-observability-complete/RALPH_STATE.md](../v1.32-observability-complete/RALPH_STATE.md) |
| Sentry 集成 | [../v1.32-observability-complete/DELIVERY_REPORT.md](../v1.32-observability-complete/DELIVERY_REPORT.md) |
