# 02-architecture — v1.36-alert-observability

> **迭代**: v1.36-alert-observability
> **基础**: v1.35-multi-instance-alerting (DELIVERED)
> **创建**: 2026-06-03
> **状态**: 🟡 Round 1 锁定 (待 Round 2 修订)

---

## 1. 目标

为 v1.34-v1.35 已建成的告警闭环提供"运维视角"的可观测性能力。提供 7 个只读 API 端点, 不影响现有告警发送路径。

---

## 2. 目录结构

```
backend/app/
├── api/v1/
│   ├── observability.py            # 新增 (v1.36 P0)
│   ├── alerts.py                   # 已有 (v1.34-v1.35)
│   └── silences.py                 # 已有 (v1.34-v1.35)
├── monitoring/
│   ├── notifier.py                 # 改 (v1.36 P0) - 记录 channel 发送
│   ├── am_sync.py                  # 改 (v1.36 P0) - 记录同步结果
│   ├── dedup_lock.py               # 改 (v1.36 P0) - 内存计数 + flush
│   ├── dedup.py                    # 已有 (v1.34-v1.35)
│   ├── escalation.py               # 已有 (v1.33)
│   └── silence.py                  # 已有 (v1.34)
├── models/
│   └── admin.py                    # 改 (v1.36 P0) - OperationLog 复合索引
├── tasks/
│   ├── alerts.py                   # 已有 (v1.34)
│   └── observability.py            # 新增 (v1.36 P0) - 锁统计 flush
└── core/
    └── celery_app.py               # 改 (v1.36 P0) - 新增 flush 调度

tests/
├── test_observability_api.py       # 新增 (v1.36 P0)
├── test_channel_logging.py         # 新增 (v1.36 P0) - notifier 改造测试
├── test_am_sync_logging.py         # 新增 (v1.36 P0) - am_sync 改造测试
├── test_dedup_lock_stats.py        # 新增 (v1.36 P0) - 锁统计测试
└── (回归) test_alerts_webhook.py   # 不破坏
```

---

## 3. 数据模型 (ER 图描述)

### 3.1 OperationLog (现有, 仅添加索引)

```python
class OperationLog(Base):
    __tablename__ = "operation_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    operator_role: Mapped[str | None] = mapped_column(String(20), nullable=True)
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)  # 复用 + 新增
    target_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)  # JSON
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
    
    __table_args__ = (
        Index("idx_oplog_action_created", "action_type", "created_at"),
        Index("idx_oplog_target_action", "target_id", "action_type"),
    )
```

### 3.2 新增 action_type 字典

| action_type | 写入者 | detail 字段 |
|:---|:---|:---|
| `alert_channel_sent` | notifier | `{channel, rule, severity, fingerprint, duration_ms}` |
| `alert_channel_failed` | notifier | `{channel, rule, severity, fingerprint, error}` |
| `am_sync_success` | am_sync | `{local_silence_id, am_silence_id, name}` |
| `am_sync_failed` | am_sync | `{local_silence_id, name, error}` |
| `dedup_lock_skipped` | dedup_lock | `{fingerprint}` (周期 flush) |
| `dedup_lock_fallback` | dedup_lock | `{fingerprint, error}` (周期 flush) |

---

## 4. API 接口规范

### 4.1 端点清单

| Method | Path | 说明 |
|:---|:---|:---|
| GET | `/api/v1/alerts/observability/trend` | 告警趋势 (按时间 bucket) |
| GET | `/api/v1/alerts/observability/response-time` | 响应时长统计 (mean/p50/p95/p99) |
| GET | `/api/v1/alerts/observability/escalation` | 升级率统计 |
| GET | `/api/v1/alerts/observability/channel-stats` | 通道成功率 |
| GET | `/api/v1/alerts/observability/silence-hit-rate` | 静默命中率 |
| GET | `/api/v1/alerts/observability/am-sync` | AM 同步可观测 |
| GET | `/api/v1/alerts/observability/lock-stats` | Redis 锁可观测 |

### 4.2 通用规范

- 权限: 全部 `require_role("admin")`
- 响应格式: `{"code": 0, "data": {...}}`
- 缓存: 5min Redis (key: `obs:{endpoint}:{params_hash}`)
- 时间窗口: max 30 天
- 错误处理: 4xx 参数错误, 5xx 系统错误, 详细错误信息

---

## 5. 关键模块设计

### 5.1 notifier 改造 (中等风险)

**现状**: [notifier.py::CompositeNotifier.send()](file:///e:/code/bysj/backend/app/monitoring/notifier.py#L346)
- 返回 `dict[str, bool]`, 无 DB 写入
- 4 个内置 notifier: Webhook / Slack / DingTalk / Email

**改造**:
- `send(payload, *, db: AsyncSession | None = None) -> dict[str, bool]`
- 每个 notifier.send 后, 如果 db 不为空, 写 OperationLog
- 写入异步 (background task) 避免阻塞 webhook
- detail 包含 channel / duration_ms / error

**集成点**: [alerts.py::alertmanager_webhook](file:///e:/code/bysj/backend/app/api/v1/alerts.py) 调用 send 时传 db

### 5.2 am_sync 改造 (低风险)

**现状**: [am_sync.py::push_silence()](file:///e:/code/bysj/backend/app/monitoring/am_sync.py#L41)
- 返回 `dict | None`, 无 DB 写入
- 由 [silences.py::create_silence](file:///e:/code/bysj/backend/app/api/v1/silences.py) 调用

**改造**:
- `push_silence(silence, *, db: AsyncSession | None = None) -> dict | None`
- 成功/失败时, 如果 db 不为空, 写 OperationLog
- `delete_silence` / `pull_silences` 同理

### 5.3 dedup_lock 改造 (中等风险)

**现状**: [dedup_lock.py::try_acquire_lock()](file:///e:/code/bysj/backend/app/monitoring/dedup_lock.py#L44)
- 无状态, 仅 Redis 调用
- 高频调用 (每次告警)

**改造**:
- 模块级 `_stats: dict[str, int]` 内存计数
- `try_acquire_lock` 返回时增加计数
- 新增 `flush_lock_stats(db) -> None`: 把 stats 写 OperationLog (仅 skipped/fallback)
- 新增 `get_lock_stats() -> dict`: 读内存

**flush 任务**: Celery beat 60s 一次, 调用 `flush_lock_stats`
- 写入 action_type: `dedup_lock_skipped` (sum), `dedup_lock_fallback` (sum)
- 写后清零内存 stats

**风险**: 进程重启丢失内存计数 (可接受, 不阻塞)

### 5.4 observability API 模块 (新增, 低风险)

**新文件**: `app/api/v1/observability.py`
- 7 个端点, 全部只读
- 复用现有 deps (db, current_user, require_role)
- 5min Redis cache
- 注册到 `app/api/v1/__init__.py`

---

## 6. Celery beat 新增

```python
# backend/app/core/celery_app.py
"flush-lock-stats": {
    "task": "app.tasks.observability.flush_lock_stats_task",
    "schedule": 60.0,  # 60s
}
```

---

## 7. 测试策略

### 7.1 单元测试

- `test_observability_api.py`: 7 个端点的成功/失败/参数验证
- `test_channel_logging.py`: notifier 改造后写 OperationLog
- `test_am_sync_logging.py`: am_sync 改造后写 OperationLog
- `test_dedup_lock_stats.py`: 内存计数 + flush 任务

### 7.2 集成测试

- 端到端: 触发告警 → webhook → notifier 写 OperationLog → API 查看到
- 端到端: 创建静默 → am_sync 写 OperationLog → API 查看到

### 7.3 性能测试

- 7 天窗口趋势查询 < 500ms
- 7 天响应时长查询 < 300ms
- (可选) 7 天通道成功率 < 200ms

---

## 8. 部署清单

### 8.1 数据库

```python
# 启动时自动创建 (Base.metadata)
# 复合索引: idx_oplog_action_created, idx_oplog_target_action
```

### 8.2 环境变量

```bash
# 复用 v1.35
REDIS_URL=redis://redis:6379/0
ALERTMANAGER_URL=http://alertmanager:9093
# 新增 (可选): OBSERVABILITY_CACHE_TTL=300
```

### 8.3 Celery

```bash
# 新增 flush 任务
celery -A app.core.celery_app:celery_app worker --loglevel=info
celery -A app.core.celery_app:celery_app beat --loglevel=info
# 应包含: app.tasks.observability.flush_lock_stats_task
```

---

## 9. 风险与缓解

| 风险 | 缓解 |
|:---|:---|
| notifier 改造影响现有告警 | 异步写日志, 失败不影响通知 |
| 复合索引创建慢 | 启动时 check first, 必要时跳过 |
| 内存计数进程重启丢失 | 接受, 不阻塞 |
| 高频写入 OperationLog | 锁 flush 60s 一次, 仅写 skipped/fallback |
| 端点被刷 | Redis 5min cache, admin 限流 |
| JSON_EXTRACT 性能 | 应用层 cache, LIMIT 兜底 |

---

## 10. 关联文档

| 文档 | 路径 |
|:---|:---|
| 需求 | [./01-requirements.md](./01-requirements.md) |
| Critique | [./01a-critique-r1.md](./01a-critique-r1.md) |
| Research | [./01b-research-r1.md](./01b-research-r1.md) |
| Simulation | [./01c-simulation-r1.md](./01c-simulation-r1.md) |
| 任务 | [./04-ralph-tasks.md](./04-ralph-tasks.md) |
| 测试 | [./05-test-plan.md](./05-test-plan.md) |
| 上一迭代 | [../v1.35-multi-instance-alerting/RALPH_STATE.md](../v1.35-multi-instance-alerting/RALPH_STATE.md) |
