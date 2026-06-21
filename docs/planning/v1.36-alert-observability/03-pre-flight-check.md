# 03-pre-flight-check — v1.36-alert-observability

> **迭代**: v1.36-alert-observability
> **基础**: v1.35-multi-instance-alerting (DELIVERED)

---

## 1. 环境检查 (v1.36 增量)

- [x] **v1.35 已部署**: dedup_lock / am_sync / AlertArchive / archive API
- [x] **OperationLog 表存在**: 启动时自动创建
- [x] **Redis 可用**: v1.35 跨实例去重已使用
- [x] **Celery beat 运行中**: v1.34 升级/归档任务已在调度

---

## 2. 数据库要求

- [x] **MySQL 5.7+** (JSON_EXTRACT 支持) **OR** PostgreSQL 13+ **OR** SQLite 3.38+
  - 用于 severity / channel 等 detail 字段提取
- [x] **复合索引自动创建**: 启动时 Base.metadata
  - `idx_oplog_action_created`
  - `idx_oplog_target_action`

---

## 3. 配置清单

| 项 | 必填 | 默认 | 说明 |
|:---|:---:|:---|:---|
| `REDIS_URL` | ✗ | v1.35 已配 | 复用, 5min cache 仍可用 |
| `ALERTMANAGER_URL` | ✗ | v1.35 已配 | 复用, AM 同步观测需 |
| `OBSERVABILITY_CACHE_TTL` | ✗ | 300 | 5min, 可调整 |

---

## 4. 启动验证

```bash
# 1. 启动后端 (应看到新复合索引)
python -c "from app.core.database import Base, engine; Base.metadata.create_all(engine)"

# 2. 验证 flush 任务注册
celery -A app.core.celery_app:celery_app inspect registered | grep flush_lock_stats
# 期望: app.tasks.observability.flush_lock_stats_task

# 3. 验证 endpoint 可达
curl -H "Authorization: Bearer $ADMIN_TOKEN" http://localhost:8000/api/v1/alerts/observability/silence-hit-rate
# 期望: {"code": 0, "data": {...}}

# 4. 验证索引
psql -c "\d operation_logs" | grep idx_oplog
# 期望: idx_oplog_action_created, idx_oplog_target_action
```

---

## 5. 数据准备

- [x] **历史 OperationLog**: v1.33-v1.35 已积累, 趋势/升级率 API 可直接查询
- [x] **历史告警**: v1.34-v1.35 已记录, 响应时长 API 可直接查询
- [x] **新 action_type**: 启动后开始记录, 通道/AM/锁 观测需等待 1 天积累

---

## 6. 回滚方案

| 改动 | 回滚方式 |
|:---|:---|
| notifier 改造 | revert commit, 告警无影响 |
| am_sync 改造 | revert commit, 静默无影响 |
| dedup_lock 改造 | revert commit, 跨实例去重无影响 |
| 新增 observability API | 移除 router 注册 |
| 复合索引 | DROP INDEX (无数据影响) |
| flush 任务 | 移除 beat schedule |

---

## 7. 检查清单 (执行前)

- [x] 已阅读 v1.35 DELIVERY_REPORT
- [x] 已阅读 v1.36 01-requirements / 02-architecture
- [x] 数据库迁移脚本确认 (自动)
- [x] Celery beat 配置确认
- [x] 测试计划确认
- [ ] **准备启动 v1.36 实施**
