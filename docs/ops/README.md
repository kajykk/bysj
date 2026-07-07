# 运维 SOP 索引 (Ops SOP Index)

> **关联任务**: SEC-C Secrets 管理 SOP
> **创建日期**: 2026-07-03
> **维护说明**: 本目录索引所有运维相关 SOP (Standard Operating Procedure) 文档

---

## 1. Secrets 管理

| 文档 | 适用范围 | 轮换周期 | 关联脚本 |
|------|---------|---------|---------|
| [secrets-rotation-sop.md](./secrets-rotation-sop.md) | 4 类 Secrets (PII / JWT / Webhook / Metrics Token) 生命周期管理 | 60~90 天 | [backend/scripts/rotate_pii_keys.py](../../backend/scripts/rotate_pii_keys.py) |

---

## 2. 应急响应

| 文档 | 适用场景 | 响应时间 |
|------|---------|---------|
| [../EMERGENCY_RUNBOOK.md](../EMERGENCY_RUNBOOK.md) | 生产环境故障应急处理 | 5~30 分钟 |

---

## 3. 部署与回滚

| 文档 | 适用场景 |
|------|---------|
| [../DEPLOYMENT_GUIDE.md](../DEPLOYMENT_GUIDE.md) | 部署流程与检查清单 |
| [../planning/v1.15-launch-readiness/ROLLBACK_PLAN.md](../planning/v1.15-launch-readiness/ROLLBACK_PLAN.md) | 版本回滚流程 |

---

## 4. 待补充 SOP

> 以下 SOP 计划在后续迭代中补充

- [ ] 数据库备份恢复 SOP (PostgreSQL / SQLite)
- [ ] Celery 任务积压处理 SOP
- [ ] Redis 故障切换 SOP
- [ ] 模型回滚 SOP (关联 `auto_rollback_service.py`)
- [ ] Sentry 告警响应 SOP

---

## 5. 变更日志

| 日期 | 变更内容 | 作者 |
|------|---------|------|
| 2026-07-03 | 初始版本, 创建 ops 目录与索引 | 系统优化团队 |
