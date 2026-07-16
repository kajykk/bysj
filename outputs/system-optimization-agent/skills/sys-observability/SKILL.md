---
name: sys-observability
description: >-
  This skill should be used when building monitoring, alerting, and tracing —
  "监控告警", "链路追踪", "告警噪音", "分层监控", "告警分级", "Runbook".
  It implements §4.3.3 and supports every phase of the optimization plan.
agent_created: true
---

# sys-observability

## 用途
建立分层监控、告警分级与链路追踪，使问题可发现、可定位、可自动响应。

## 何时使用
- 每个阶段开始前盘点/补齐埋点；阶段末核验指标。
- 用户要求「配监控」「降告警噪音」「加链路追踪」。

## 执行流程
1. **分层监控**：基础设施（CPU/内存/磁盘/网络）→ 服务（健康/依赖）→ 接口（P95/错误率）→ 业务指标。
2. **链路追踪**：关键链路注入 trace_id；跨服务用 OpenTelemetry 串联。
3. **告警分级**：按 P0–P3 分组，避免噪音；设置静默/收敛/值班路由。
4. **自动发现/定位**：异常聚类、错误率突增、依赖超时自动告警并附上下文。
5. **Runbook**：为高频告警配处置手册；SLO 看板可视化。
6. **验证**：注入故障，确认告警在阈值内触发且信息充分。

## 工具与脚本
- APM/错误：`Sentry`（`@sentry/vue` 前端、后端可接入 `sentry-sdk`）。
- 指标：`Prometheus` + `Grafana`（或云监控）。
- 追踪：`OpenTelemetry`（后端 FastAPI 中间件注入）。
- 日志：结构化日志 + 脱敏（见 `sys-security-hardening`）。

## 验收与 KPI（§3）
- 分层监控覆盖；告警分级、噪音下降。
- 故障自动发现与定位能力形成，异常聚类可用。

## 与本工程栈的对应
- 前端已用 Sentry；后端 `backend/app/monitoring` 已有可观测模块可扩展。
- 日志目录 `backend/logs`；需结构化 + 脱敏中间件。

## 注意事项
- 告警必须带「做什么」的上下文，避免纯数字噪音。
- 敏感字段在日志层脱敏，切勿把 PII 打入指标标签。
