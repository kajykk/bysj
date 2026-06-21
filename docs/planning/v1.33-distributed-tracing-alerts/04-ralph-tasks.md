# 04-ralph-tasks — v1.33-distributed-tracing-alerts

> **执行原则**: 按物理顺序执行。每完成标记 `[x]`。

---

## Phase 1: W3C Trace Context (P0)

### T1.1 创建 tracing 模块

- [x] `app/core/tracing.py` 新建
- [x] `TraceContext` dataclass (trace_id, span_id, parent_span_id, sampled)
- [x] `parse_traceparent(header)` 解析 W3C 格式
- [x] `format_traceparent(tc)` 生成 W3C 格式 (to_traceparent)
- [x] `new_trace_context()` 生成新 trace
- [x] `span_context(name)` 上下文管理器 (嵌套 span)

### T1.2 集成到 request_id middleware

- [x] 解析 `traceparent` header
- [x] 生成/继承 `trace_id`
- [x] 创建 root span
- [x] 注入 `X-Trace-Id` / `X-Span-Id` 响应 header
- [x] 注入 Sentry tags (通过 request.state)

### T1.3 Log 注入 trace_id

- [x] `TraceLogFilter` 注入 trace_id / span_id
- [x] 测试验证日志格式

### T1.4 编写测试

- [x] tests/test_tracing.py 15/15 通过
- [x] 验证 W3C 格式解析
- [x] 验证 trace 继承
- [x] 验证 span 嵌套
- [x] 验证 middleware 注入

---

## Phase 2: 告警多通道 (P0)

### T2.1 创建 notifier 模块

- [x] `app/monitoring/notifier.py` 新建
- [x] `Notifier` Protocol 接口
- [x] `WebhookNotifier` (JSON POST + 指数退避)
- [x] `SlackNotifier` (Slack 格式 + 颜色)
- [x] `DingTalkNotifier` (钉钉签名)
- [x] `EmailNotifier` (SMTP)
- [x] `CompositeNotifier` (多通道)

### T2.2 配置加载

- [x] 从 `ALERT_*` 环境变量加载
- [x] 失败降级到日志
- [x] 指数退避重试 (max 3)

### T2.3 编写测试

- [x] tests/test_notifier.py 21/21 通过
- [x] 验证 Webhook POST
- [x] 验证 Slack 格式
- [x] 验证钉钉签名
- [x] 验证失败重试

---

## Phase 3: AlertManager Webhook 接收 (P0)

### T3.1 创建 alerts API

- [x] `app/api/v1/alerts.py` 新建
- [x] `POST /api/v1/alerts/webhook` 接收 AlertManager
- [x] `GET /api/v1/alerts/history` 查询历史
- [x] `POST /api/v1/alerts/{id}/ack` 确认告警

### T3.2 AlertEvent 持久化

- [x] 复用 `OperationLog` 表
- [x] action_type: `alert_fired` / `alert_resolved` / `alert_escalated` / `alert_acknowledged`
- [x] detail 存储: rule, severity, payload, fingerprint
- [x] 使用请求 session (修复 v1.33 初版的独立 AsyncSessionLocal 问题)

### T3.3 编写测试

- [x] tests/api/test_alerts_webhook.py 11/11 通过
- [x] 验证 AlertManager payload 解析
- [x] 验证 severity 标准化 (critical→P0, warning→P1, info→P2)
- [x] 验证 OperationLog 写入
- [x] 验证 history 过滤
- [x] 验证 ack 流程

---

## Phase 4: 告警升级 (P1)

### T4.1 升级策略

- [x] `app/monitoring/escalation.py` 新建
- [x] `EscalationPolicy` (10m P1→P0, 30m P0 再次, 1h P0 标记)
- [x] `acknowledge_alert(alert_id)` 通过 API 触发
- [x] 幂等性 (escalation_level 字段)

### T4.2 后台检查

- [x] `escalate_pending_alerts()` 同步入口 (供 Celery beat 调用)
- [x] 升级触发 `CompositeNotifier`
- [x] 升级记录到 OperationLog (alert_escalated)

### T4.3 编写测试

- [x] tests/test_escalation.py 9/9 通过
- [x] 验证 P1 10m 升级
- [x] 验证 P0 30m 重发
- [x] 验证 P0 1h 标记
- [x] 验证 ack 停止升级
- [x] 验证幂等性

---

## Phase 5: 回归测试 (P0)

### T5.1 核心测试组

- [x] tests/test_tracing.py 15/15
- [x] tests/test_notifier.py 21/21
- [x] tests/api/test_alerts_webhook.py 11/11
- [x] tests/test_escalation.py 9/9
- [x] 现有 sentry / metrics / admin_metrics / audit_logs 测试不破坏 (83/83 全过)

---

## 进度统计

- 总任务: 5 phases
- P0: 4 phases
- P1: 1 phase
- 完成: **5/5 (100%)**
- 测试: **56/56 v1.33 新增 (100%) / 83/83 全量回归 (100%)**
