# NEXT_STEPS — v1.33 之后

> **下一步建议**: 基于 v1.33-distributed-tracing-alerts (DELIVERED)

---

## 1. v1.34 推荐方向 (P0)

### 1.1 告警去重 + 静默窗口 (P0)

**目标**: 防止告警风暴

- fingerprint 抑制 (同 fingerprint 5 分钟内不重复发送)
- 时间窗口静默 (维护窗口期不告警)
- 抑制规则 (AlertManager 同步)
- 静默审计 (记录到 OperationLog)

**预计工作量**: 1-2 天

### 1.2 告警归档自动化 (P0)

**目标**: 90 天前告警自动归档

- Celery beat 任务每日扫描
- 归档到 `alert_archive` 表
- 释放 OperationLog 空间
- 归档查询 API (read-only)

**预计工作量**: 1 天

### 1.3 Celery 任务注册 (P0)

**目标**: escalation 调度自动化

- 注册 `escalate_pending_alerts` 为 Celery task
- beat schedule 每分钟触发
- 失败重试 + 告警通知

**预计工作量**: 0.5 天

---

## 2. v1.35 候选方向 (P1)

### 2.1 OpenTelemetry SDK 升级

- 完整 OTel 集成 (FastAPI/SQLAlchemy/Redis)
- 部署 Jaeger 或 Tempo
- Grafana trace UI
- 与现有 W3C trace 双向兼容

### 2.2 告警可视化

- 告警趋势图 (按 severity / rule)
- 平均响应时间 (fired → acknowledged)
- 升级率统计
- 通道成功率

### 2.3 PagerDuty / OpsGenie

- 标准 incident API
- 升级到 on-call
- 双向 ack 同步

---

## 3. 长期规划 (P2)

- **多租户告警**: 机构/学校级别路由
- **告警模板**: 行业模板库 (CPU / 业务指标)
- **AI 告警**: 异常检测自动产生告警
- **SLO/SLI**: 错误预算管理

---

## 4. 当前状态摘要

| 项 | 状态 |
|:---|:---|
| **当前迭代** | v1.33-distributed-tracing-alerts (🟢 DELIVERED) |
| **总测试数** | 83/83 (100%) |
| **生产可追踪** | ✓ W3C trace_id 全链路 |
| **生产可告警** | ✓ 4 通道 (webhook/slack/dingtalk/email) |
| **生产可升级** | ✓ 10m→30m→1h 三级 |
| **下一步行动** | 等待用户决策: v1.34 告警去重 / v1.35 OTel 升级 / 优化 |

---

> **下一步**: 询问用户方向 (v1.34 告警去重+静默 / v1.35 OTel 升级 / 其他)
