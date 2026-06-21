# 01-requirements — v1.36-alert-observability

> **迭代**: v1.36-alert-observability
> **基础**: v1.35-multi-instance-alerting (DELIVERED)
> **创建**: 2026-06-03
> **类型**: Observability / Visualization / Metrics
> **版本**: **Round 3 终稿** (锁定, 待实施)

---

## 1. 目标

为 v1.34-v1.35 已建成的告警闭环提供"运维视角"的可观测性能力, 让运维/SRE 团队能够:

1. 看到告警趋势 (按 severity/rule/时间)
2. 量化响应时长 (mean/p50/p95/p99)
3. 评估升级率 (避免过度升级)
4. 监控通道成功率 (及时发现通知故障)
5. 评估静默命中率 (规则是否合理)
6. 监控 AM 同步状态
7. 监控 Redis 锁可观测

---

## 2. 范围 (P0 - 7 个只读端点 + 4 个数据改造 + 2 个工具)

### 2.1 7 个观测端点

| # | 端点 | 用途 | 数据源 | 依赖 |
|:--|:---|:---|:---|:---|
| EP-1 | `GET /alerts/observability/trend` | 告警趋势 | alert_fired/resolved | idx_oplog_action_created |
| EP-2 | `GET /alerts/observability/response-time` | 响应时长 | alert_fired + acknowledged 配对 | idx_oplog_target_action |
| EP-3 | `GET /alerts/observability/escalation` | 升级率 | alert_escalated | idx_oplog_action_created |
| EP-4 | `GET /alerts/observability/channel-stats` | 通道成功率 | (新) alert_channel_sent/failed | **T1.1** |
| EP-5 | `GET /alerts/observability/silence-hit-rate` | 静默命中率 | alert_silenced | idx_oplog_action_created |
| EP-6 | `GET /alerts/observability/am-sync` | AM 同步可观测 | (新) am_sync_success/failed | **T1.2** |
| EP-7 | `GET /alerts/observability/lock-stats` | Redis 锁可观测 | 内存 + (新) flush | **T1.3** |

### 2.2 4 个数据源改造

| # | 改造 | 路径 | 新 action_type |
|:--|:---|:---|:---|
| T1.1 | notifier 记录通道 | [notifier.py](file:///e:/code/bysj/backend/app/monitoring/notifier.py) | `alert_channel_sent`, `alert_channel_failed` |
| T1.2 | am_sync 记录同步 | [am_sync.py](file:///e:/code/bysj/backend/app/monitoring/am_sync.py) | `am_sync_success`, `am_sync_failed` |
| T1.3 | dedup_lock 内存计数 + flush | [dedup_lock.py](file:///e:/code/bysj/backend/app/monitoring/dedup_lock.py) + 新 tasks/observability.py | `dedup_lock_skipped`, `dedup_lock_fallback` |
| T1.4 | OperationLog 复合索引 | [models/admin.py](file:///e:/code/bysj/backend/app/models/admin.py) | (索引, 不增 action_type) |

### 2.3 2 个工具模块

| # | 模块 | 用途 |
|:--|:---|:---|
| T0.1 | `app/core/cache.py` | 5min Redis cache (cache_get / cache_set / make_cache_key) |
| T0.2 | `app/core/instance.py` | hostname-pid 实例标识 (get_instance_id) |

---

## 3. 通用响应 Schema (7 端点统一)

```json
{
  "code": 0,
  "data": {
    "...endpoint 特定字段...": "...",
    "cached": false,
    "cached_at": null,
    "instance_id": "backend-pod-7c5d8-12345"
  }
}
```

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| `cached` | bool | 是否命中 5min 缓存 |
| `cached_at` | ISO datetime \| null | 缓存写入时间 (仅 cached=true) |
| `instance_id` | string | 当前实例标识 (hostname-pid) |

---

## 4. 端点详细规范

### 4.1 EP-1 告警趋势

**Query**: `start_time`, `end_time`, `bucket` (1h/6h/24h/7d), `severity`, `status`, `group_by` (severity/rule)

**响应**:
```json
{
  "buckets": [
    {"bucket": "2026-06-01T00:00:00Z", "items": [
      {"severity": "P0", "status": "firing", "count": 12}
    ]}
  ],
  "summary": {"total_firing": 145, "total_resolved": 132, "window_hours": 168}
}
```

### 4.2 EP-2 响应时长

**Query**: `start_time`, `end_time`, `severity`, `group_by`

**响应**:
```json
{
  "groups": [
    {"key": "P0", "total_acknowledged": 42, "total_pending": 8, "stats": {
      "mean_seconds": 120.5, "p50_seconds": 90, "p95_seconds": 480, "p99_seconds": 1200
    }}
  ],
  "summary": {"total_alerts": 50, "acknowledged_rate": 0.84}
}
```

**实现**: self-JOIN fired + acknowledged (target_id), LIMIT 10000 兜底

### 4.3 EP-3 升级率

**Query**: `start_time`, `end_time`

**响应**:
```json
{
  "total_fired": 150, "total_escalated": 18, "escalation_rate": 0.12,
  "by_level": {"L1": 12, "L2": 4, "L3": 2},
  "by_rule": [{"rule": "HighCPU", "fired": 30, "escalated": 8, "rate": 0.27}]
}
```

### 4.4 EP-4 通道成功率

**Query**: `start_time`, `end_time`

**响应**:
```json
{
  "channels": [
    {"channel": "webhook", "sent": 145, "failed": 3, "success_rate": 0.98, "avg_duration_ms": 120}
  ],
  "total_sent": 420, "total_failed": 30, "overall_success_rate": 0.93
}
```

### 4.5 EP-5 静默命中率

**Query**: `start_time`, `end_time`

**响应**:
```json
{
  "total_alerts": 250, "silenced_alerts": 35, "hit_rate": 0.14,
  "by_matcher": [{"matcher_key": "severity", "matcher_value": "P0", "silenced": 8, "hit_rate": 0.10}]
}
```

### 4.6 EP-6 AM 同步可观测

**Query**: `start_time`, `end_time`

**响应**:
```json
{
  "total_attempts": 25, "success": 23, "failed": 2, "success_rate": 0.92,
  "recent_failures": [
    {"timestamp": "2026-06-01T10:00:00Z", "local_silence_id": 42, "name": "db-maintenance", "error": "AM timeout after 2s"}
  ]
}
```

### 4.7 EP-7 Redis 锁可观测

**Query**: 无 (内存读)

**响应**:
```json
{
  "instance_id": "backend-pod-7c5d8-12345",
  "current_window": {"acquired": 145, "skipped": 23, "fallback": 2},
  "last_flush": "2026-06-01T10:00:00Z",
  "redis_available": true
}
```

---

## 5. 新增 action_type 详情

| action_type | 写入者 | detail 字段 |
|:---|:---|:---|
| `alert_channel_sent` | notifier | `{channel, rule, severity, fingerprint, duration_ms}` |
| `alert_channel_failed` | notifier | `{channel, rule, severity, fingerprint, duration_ms, error}` |
| `am_sync_success` | am_sync | `{local_silence_id, am_silence_id, name}` |
| `am_sync_failed` | am_sync | `{local_silence_id, name, error}` |
| `dedup_lock_skipped` | dedup_lock flush | `{count, period}` |
| `dedup_lock_fallback` | dedup_lock flush | `{count, period}` |

**总新增**: 6 个 action_type (5 端点依赖 + 1 锁 flush)

---

## 6. 复合索引

```python
# app/models/admin.py::OperationLog.__table_args__
Index("idx_oplog_action_created", "action_type", "created_at"),  # 趋势/升级/静默/通道/AM
Index("idx_oplog_target_action", "target_id", "action_type"),     # 响应时长 self-JOIN
```

启动时 `Base.metadata.create_all()` 自动创建。

---

## 7. 非功能需求

| 维度 | 要求 |
|:---|:---|
| 查询性能 | 7 天窗口 1h bucket < 500ms; 30 天 < 1500ms |
| 缓存 | 5min Redis TTL (`obs:{endpoint}:{params_hash}`) |
| 权限 | 全部 admin (`require_role("admin")`) |
| 零侵入 | 不影响现有告警发送路径 |
| 数据库 | MySQL 5.7.13+ / PostgreSQL 13+ / SQLite 3.38+ (JSON_EXTRACT) |
| 窗口上限 | max 30 天 (防 DOS) |
| Cache 失败 | 降级到直接查询, 不报错 |
| API 自身失败 | Sentry 捕获 + logger.error |

---

## 8. 不在范围 (P1/P2 后续)

- 告警可视化大屏 (P2)
- Prometheus / Grafana 集成 (P2)
- 告警预测 (ML, P2)
- 告警自动根因 (P2)
- 多租户告警视图 (P2)
- 跨进程锁聚合 (P1)
- 预聚合每日 stats 表 (P1)
- AM webhook 接收 (P1)

---

## 9. 验收标准

- [ ] 7 个端点全部可访问, 返回正确 schema (含 cached/instance_id)
- [ ] 单元测试 + 集成测试 + 性能测试 全过
- [ ] 性能测试 7 天窗口 < 500ms
- [ ] notifier / am_sync / dedup_lock 改造不影响现有路径
- [ ] 复合索引启动时自动创建
- [ ] Celery beat flush 任务已注册
- [ ] 回归测试 v1.34-v1.35 不破坏

---

## 10. 风险与缓解 (终稿)

| 风险 | 缓解 |
|:---|:---|
| notifier 改造引入额外 DB 写入 | 异步写, 失败不回滚 |
| am_sync 改造影响现有同步 | 失败仅记录, 不抛异常 |
| 锁 flush 失败 | 内存不清零, 下次重试 |
| 复合索引大表 ALTER 慢 | 启动 check first, 必要时警告 |
| 响应时长 self-JOIN 慢 | LIMIT 10000 兜底 + 索引 |
| JSON_EXTRACT 跨 DB 不一致 | 应用层 parse 兜底 (P1) |
| observability API 自身失败 | Sentry + logger.error |
| 锁 stats 进程重启丢失 | 接受 (P1 跨进程聚合) |

---

## 11. 实施顺序 (推荐)

```
T0.1 cache 工具 → T0.2 instance 工具
    ↓
T1.4 复合索引 (启动时建)
    ↓
T1.1 notifier 改造 → T1.2 am_sync 改造 → T1.3 dedup_lock 改造
    ↓
T2.1 路由骨架
    ↓
T2.2-2.8 7 端点 (按顺序, EP-5 → EP-1 → EP-3 → EP-4 → EP-6 → EP-7 → EP-2)
    ↓
T3 集成 + 性能 + 工具测试
    ↓
T4 回归
```

---

## 12. 关联文档

| 文档 | 路径 |
|:---|:---|
| 架构 | [./02-architecture.md](./02-architecture.md) |
| 任务 | [./04-ralph-tasks.md](./04-ralph-tasks.md) |
| 测试 | [./05-test-plan.md](./05-test-plan.md) |
| Learnings | [./06-learnings.md](./06-learnings.md) |
| Round 1 Critique | [./01a-critique-r1.md](./01a-critique-r1.md) |
| Round 1 Research | [./01b-research-r1.md](./01b-research-r1.md) |
| Round 1 Simulation | [./01c-simulation-r1.md](./01c-simulation-r1.md) |
| Round 2 Critique | [./01d-critique-r2.md](./01d-critique-r2.md) |
| Round 2 Research | [./01e-research-r2.md](./01e-research-r2.md) |
| Round 2 Simulation | [./01f-simulation-r2.md](./01f-simulation-r2.md) |
| 上一迭代 | [../v1.35-multi-instance-alerting/RALPH_STATE.md](../v1.35-multi-instance-alerting/RALPH_STATE.md) |

---

> **状态**: 🟡 Round 3 终稿 (待 Lock 后进入实施)
