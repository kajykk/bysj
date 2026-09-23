# NEXT_STEPS — v1.32 之后

> **下一步建议**: 基于 v1.32-observability-complete (DELIVERED)

---

## 1. v1.33 推荐方向 (P0)

### 1.1 OpenTelemetry 分布式追踪 (P0)

**目标**: 跨服务/跨请求的全链路追踪

- 集成 `opentelemetry-instrumentation-fastapi`
- 集成 `opentelemetry-instrumentation-sqlalchemy`
- 集成 `opentelemetry-instrumentation-redis`
- 导出到 Jaeger / Tempo
- 与 Sentry trace 联动

**预计工作量**: 2-3 天

### 1.2 告警通知集成 (P0)

**目标**: Prometheus AlertManager → Slack/Email/钉钉

- 配置 AlertManager
- Webhook 接收器
- 钉钉/企业微信 适配
- 告警升级策略 (10m → 30m → 1h)

**预计工作量**: 1-2 天

### 1.3 审计日志 Grafana 集成 (P1)

**目标**: 在 Grafana 仪表盘展示 audit_logs

- Postgres → Prometheus exporter
- 按 operator_role 分布图
- 按 action_type 趋势图
- 异常操作 (admin 越权 / 删除) 高亮

**预计工作量**: 1 天

---

## 2. v1.34 候选方向 (P1)

### 2.1 模型漂移检测自动化

- 自动 baseline 训练 (每周)
- PSI / KS 检验自动告警
- 漂移后自动 rollback (参考 v1.20 框架)

### 2.2 A/B 测试框架

- 模型版本灰度
- 流量分配
- 指标对比 (latency / accuracy / business)
- 自动胜出切换

### 2.3 模型版本管理 v2

- MLflow 集成
- 模型注册表 UI
- 模型血缘追踪

---

## 3. 长期规划 (P2)

- **多租户支持**: 机构/学校级别隔离
- **实时协同**: Counselor + User 实时沟通
- **国际化增强**: v1.30 已支持 zh/en, 扩展 ja/ko
- **可穿戴设备集成**: 智能手表/手环数据导入

---

## 4. 当前状态摘要

| 项 | 状态 |
|:---|:---|
| **当前迭代** | v1.32-observability-complete (🟢 DELIVERED) |
| **总测试数** | 43/43 (100%) 可观测性测试 |
| **生产可启动** | ✓ |
| **生产可观测** | ✓ Grafana + Prometheus + Sentry |
| **生产可审计** | ✓ audit-logs + operation-logs |
| **下一步行动** | 等待用户决策: v1.33 / v1.34 / 优化 |

---

> **下一步**: 询问用户方向 (v1.33 追踪+告警 / v1.34 模型治理 / 其他)
