# 04-ralph-tasks — v1.34-alerting-complete

> **执行原则**: 按物理顺序执行。每完成标记 `[x]`。

---

## Phase 1: 告警去重 (P0)

### T1.1 创建 dedup 模块

- [ ] `app/monitoring/dedup.py` 新建
- [ ] `should_send(alert, db)` 函数
- [ ] 检查 fingerprint + created_at > 5min 阈值
- [ ] 单元测试

### T1.2 集成到 webhook

- [ ] `alerts.py::alertmanager_webhook` 应用 dedup
- [ ] 单元测试 (5min 内同 fingerprint 不发)

---

## Phase 2: 静默窗口 (P0)

### T2.1 创建 AlertSilence 模型

- [ ] `app/models/admin.py` 新增 `AlertSilence`
- [ ] 字段: id, name, matcher(JSON), starts_at, ends_at, created_by, created_at, comment
- [ ] Alembic 迁移 (or metadata sync)

### T2.2 静默匹配逻辑

- [ ] `app/monitoring/silence.py::is_silenced(alert, db)` 函数
- [ ] 支持按 alertname/severity 匹配
- [ ] 时间窗口检查

### T2.3 静默规则 API

- [ ] `POST /api/v1/alerts/silences` 创建
- [ ] `GET /api/v1/alerts/silences` 列表
- [ ] `DELETE /api/v1/alerts/silences/{id}` 取消
- [ ] `GET /api/v1/alerts/silences/active` 当前生效
- [ ] admin 角色要求
- [ ] 单元测试

### T2.4 webhook 集成

- [ ] 静默期内只持久化不发送
- [ ] 记录到 OperationLog (alert_silenced action)

---

## Phase 3: Celery 升级调度 (P0)

### T3.1 创建 Celery 任务

- [ ] `app/tasks/alerts.py` 新建
- [ ] `escalate_pending_alerts_task` 任务
- [ ] 复用 v1.33 `escalation.py::escalate_pending_alerts`
- [ ] 失败重试 + 错误日志

### T3.2 注册到 beat

- [ ] `celery_app.py::beat_schedule` 添加
- [ ] 每分钟执行
- [ ] 仅在生产启用 (test 环境 skip)

### T3.3 编写测试

- [ ] 验证任务可执行
- [ ] 验证失败重试

---

## Phase 4: 告警归档 (P1)

### T4.1 创建 AlertArchive 模型

- [ ] `app/models/admin.py` 新增 `AlertArchive`
- [ ] 字段: id, original_id, rule, severity, status, message, labels, annotations, fingerprint, original_created_at, archived_at

### T4.2 归档任务

- [ ] `app/tasks/alerts.py::archive_old_alerts_task`
- [ ] 90 天前 alert_fired/alert_resolved 移到 AlertArchive
- [ ] Celery beat: 每日 03:00

### T4.3 编写测试

- [ ] 验证归档逻辑
- [ ] 验证 90 天边界

---

## Phase 5: 回归测试 (P0)

### T5.1 核心测试组

- [ ] tests/test_dedup.py 全过
- [ ] tests/test_silence.py 全过
- [ ] tests/api/test_silences_api.py 全过
- [ ] tests/test_alert_tasks.py 全过
- [ ] 现有 sentry / metrics / admin_metrics / audit_logs / alerts_webhook / escalation 不破坏

---

## 进度统计

- 总任务: 5 phases
- P0: 4 phases
- P1: 1 phase
- 完成: 0/5 (0%)
