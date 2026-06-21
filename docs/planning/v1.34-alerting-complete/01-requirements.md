# 01-requirements — v1.34-alerting-complete

> **迭代**: v1.34-alerting-complete
> **基础**: v1.33-distributed-tracing-alerts (DELIVERED)
> **创建**: 2026-06-03
> **类型**: Alerting / Scheduling

---

## 1. 目标

完成告警系统最后一公里 — 防风暴、防误报、自动化:

| 维度 | v1.33 | v1.34 目标 |
|:---|:---:|:---:|
| 告警去重 | 每次都发送 | **fingerprint 5 分钟抑制** ✅ |
| 静默规则 | 无 | **CRUD API + 时间窗口** ✅ |
| 升级调度 | 手动调用 | **Celery beat 每分钟** ✅ |
| 告警归档 | 永久保留 | **90 天自动归档** ✅ |
| 通道抑制 | 无 | **静默期内仅记录不发** ✅ |

---

## 2. 范围

### 2.1 告警去重 (P0)

- 路径: `app/monitoring/dedup.py`
- 逻辑:
  - 同 fingerprint 5 分钟内仅发送 1 次
  - 5 分钟后再次触发才发送
  - 用 `OperationLog` 中 `alert_fired` 记录时间判定
- 集成到: `alerts.py::alertmanager_webhook`

### 2.2 静默窗口 (P0)

- 新模型: `AlertSilence`
- 路径: `app/models/admin.py` (新增)
- 字段:
  - `id`, `name`, `matcher` (JSON: {alertname, severity, ...})
  - `starts_at`, `ends_at`
  - `created_by`, `created_at`
  - `comment` (说明)
- API:
  - `POST /api/v1/alerts/silences` (admin)
  - `GET /api/v1/alerts/silences` (admin)
  - `DELETE /api/v1/alerts/silences/{id}` (admin)
  - `GET /api/v1/alerts/silences/active` (内部/公开)
- 行为: 静默期内告警仍持久化但不发通知

### 2.3 Celery 升级调度 (P0)

- 新任务: `app.tasks.alerts.escalate_pending_alerts`
- 注册到: `celery_app.conf.beat_schedule` (每分钟)
- 行为:
  - 扫描未确认 firing 告警
  - 应用升级策略 (复用 v1.33 `escalation.py`)
  - 失败重试 + 告警

### 2.4 告警归档 (P1)

- 新模型: `AlertArchive`
- 路径: `app/models/admin.py` (新增)
- 字段: `id`, `original_id`, `rule`, `severity`, `status`, `message`, `labels`, `annotations`, `fingerprint`, `created_at`, `archived_at`
- 任务: `app.tasks.alerts.archive_old_alerts` (每日 03:00)
- 行为:
  - 90 天前 `OperationLog` 中 `alert_fired` / `alert_resolved` 移到 `AlertArchive`
  - 保留主键引用便于审计

---

## 3. 非功能需求

- **去重幂等**: 相同 fingerprint 5min 内重复请求只产生 1 条 firing 记录
- **静默粒度**: 支持按 alertname/severity/labels 匹配
- **归档不阻塞**: Celery 任务在低峰期执行
- **零外部依赖**: 复用现有数据库与缓存

---

## 4. 不在范围

- 跨实例去重 (Redis 锁) — 后续 v1.35
- 静默规则同步 (AlertManager 双向) — 后续
- 告警模板引擎 — 后续

---

## 5. 关联文档

| 文档 | 路径 |
|:---|:---|
| 上一迭代 | [../v1.33-distributed-tracing-alerts/RALPH_STATE.md](../v1.33-distributed-tracing-alerts/RALPH_STATE.md) |
| 告警交付 | [../v1.33-distributed-tracing-alerts/DELIVERY_REPORT.md](../v1.33-distributed-tracing-alerts/DELIVERY_REPORT.md) |
