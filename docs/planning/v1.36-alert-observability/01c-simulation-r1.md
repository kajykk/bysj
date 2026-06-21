# 01c-simulation — v1.36-alert-observability (Round 1 / Step 4)

> **目的**: 端点详细规范 / 接口签名 / 数据流 / 失败降级 / 性能预算。
> **关联**: [./01-requirements.md](./01-requirements.md), [./01a-critique-r1.md](./01a-critique-r1.md), [./01b-research-r1.md](./01b-research-r1.md)

---

## 1. 端点详细规范 (P0)

### EP-1: 告警趋势

**端点**: `GET /api/v1/alerts/observability/trend`

**Query 参数**:
| 参数 | 类型 | 默认 | 范围 | 必填 |
|:---|:---|:---|:---|:---:|
| `start_time` | ISO datetime | 7 天前 | - | ✗ |
| `end_time` | ISO datetime | now | - | ✗ |
| `bucket` | enum | `1h` | `1h`, `6h`, `24h`, `7d` | ✗ |
| `severity` | enum | all | `P0`, `P1`, `P2` | ✗ |
| `status` | enum | all | `firing`, `resolved` | ✗ |
| `group_by` | enum | `severity` | `severity`, `rule` | ✗ |

**响应**:
```json
{
  "code": 0,
  "data": {
    "buckets": [
      {
        "bucket": "2026-06-01T00:00:00Z",
        "items": [
          {"severity": "P0", "status": "firing", "count": 12},
          {"severity": "P1", "status": "firing", "count": 25}
        ]
      }
    ],
    "summary": {
      "total_firing": 145,
      "total_resolved": 132,
      "window_hours": 168
    }
  }
}
```

**数据流**:
```
start_time, end_time, bucket, group_by
  → SQL: SELECT date_trunc(bucket, created_at) as bucket,
                detail->>'severity' as severity, action_type,
                count(*)
         FROM operation_logs
         WHERE action_type IN ('alert_fired', 'alert_resolved')
           AND created_at BETWEEN ? AND ?
         GROUP BY 1, 2, 3
  → Python: 格式化 buckets
  → 5min Redis cache (key: trend:{params_hash})
```

**降级**:
- DB 错误 → 返回 500 + 错误详情
- JSON 解析失败 → 跳过该行 (silent skip)

---

### EP-2: 响应时长

**端点**: `GET /api/v1/alerts/observability/response-time`

**Query 参数**:
| 参数 | 类型 | 默认 | 说明 |
|:---|:---|:---|:---|
| `start_time` | ISO datetime | 7 天前 | |
| `end_time` | ISO datetime | now | |
| `severity` | enum | all | |
| `group_by` | enum | `severity` | `severity`, `rule` |

**响应**:
```json
{
  "code": 0,
  "data": {
    "groups": [
      {
        "key": "P0",
        "total_acknowledged": 42,
        "total_pending": 8,
        "stats": {
          "mean_seconds": 120.5,
          "p50_seconds": 90,
          "p95_seconds": 480,
          "p99_seconds": 1200
        }
      }
    ],
    "summary": {
      "total_alerts": 50,
      "acknowledged_rate": 0.84
    }
  }
}
```

**数据流**:
```
SQL: SELECT fired.detail->>'severity' as severity,
             fired.id as fired_id,
             fired.created_at as fired_at,
             ack.created_at as ack_at,
             TIMESTAMPDIFF(SECOND, fired.created_at, ack.created_at) as secs
     FROM operation_logs fired
     LEFT JOIN operation_logs ack
       ON ack.target_id = fired.id
       AND ack.action_type = 'alert_acknowledged'
     WHERE fired.action_type = 'alert_fired'
       AND fired.created_at BETWEEN ? AND ?
  → Python: 计算 mean / percentiles
  → 5min cache
```

**降级**:
- 无 ack 记录 → 不计入 stats, 仅计入 total_pending
- 计算失败 → 跳过该组
- DB 性能风险 → 加 LIMIT 10000 (仅取最近 10K)

---

### EP-3: 升级率

**端点**: `GET /api/v1/alerts/observability/escalation`

**Query 参数**: 同 EP-1

**响应**:
```json
{
  "code": 0,
  "data": {
    "total_fired": 150,
    "total_escalated": 18,
    "escalation_rate": 0.12,
    "by_level": {
      "L1": 12,
      "L2": 4,
      "L3": 2
    },
    "by_rule": [
      {"rule": "HighCPU", "fired": 30, "escalated": 8, "rate": 0.27}
    ]
  }
}
```

**数据流**:
```
SQL: SELECT fired.detail->>'rule' as rule,
             fired.detail->>'severity' as severity,
             count(DISTINCT fired.id) as fired_count,
             count(DISTINCT esc.id) as escalated_count
     FROM operation_logs fired
     LEFT JOIN operation_logs esc
       ON esc.target_id = fired.id
       AND esc.action_type = 'alert_escalated'
     WHERE fired.action_type = 'alert_fired'
       AND fired.created_at BETWEEN ? AND ?
     GROUP BY rule, severity
```

**降级**: 同 EP-1

---

### EP-4: 通道成功率

**端点**: `GET /api/v1/alerts/observability/channel-stats`

**Query 参数**: 同 EP-1

**响应**:
```json
{
  "code": 0,
  "data": {
    "channels": [
      {
        "channel": "webhook",
        "sent": 145,
        "failed": 3,
        "success_rate": 0.98,
        "avg_duration_ms": 120
      },
      {
        "channel": "slack",
        "sent": 130,
        "failed": 18,
        "success_rate": 0.88,
        "avg_duration_ms": 350
      }
    ],
    "total_sent": 420,
    "total_failed": 30,
    "overall_success_rate": 0.93
  }
}
```

**数据流** (依赖 notifier 改):
```
notifier 每次 send 成功 → OperationLog(action_type='alert_channel_sent', detail={channel, duration_ms})
notifier 每次 send 失败 → OperationLog(action_type='alert_channel_failed', detail={channel, error})
↓
SQL: SELECT JSON_EXTRACT(detail, '$.channel') as channel,
             count(CASE WHEN action_type='alert_channel_sent' THEN 1 END) as sent,
             count(CASE WHEN action_type='alert_channel_failed' THEN 1 END) as failed,
             avg(JSON_EXTRACT(detail, '$.duration_ms')) as avg_dur
     FROM operation_logs
     WHERE action_type IN ('alert_channel_sent', 'alert_channel_failed')
       AND created_at BETWEEN ? AND ?
     GROUP BY channel
```

**依赖**: 必须先完成 notifier 改造 (Step 1 任务)

---

### EP-5: 静默命中率

**端点**: `GET /api/v1/alerts/observability/silence-hit-rate`

**Query 参数**: 同 EP-1

**响应**:
```json
{
  "code": 0,
  "data": {
    "total_alerts": 250,
    "silenced_alerts": 35,
    "hit_rate": 0.14,
    "by_matcher": [
      {"matcher_key": "severity", "matcher_value": "P0", "silenced": 8, "hit_rate": 0.10}
    ]
  }
}
```

**数据流**:
```
SQL: SELECT count(*) as total
     FROM operation_logs
     WHERE action_type = 'alert_fired' AND created_at BETWEEN ? AND ?
     -- 2nd query: silenced
     SELECT count(*) as silenced
     FROM operation_logs
     WHERE action_type = 'alert_silenced' AND created_at BETWEEN ? AND ?
```

**降级**: 直接 ratio, 简单计算

---

### EP-6: AM 同步可观测

**端点**: `GET /api/v1/alerts/observability/am-sync`

**Query 参数**:
| 参数 | 类型 | 默认 |
|:---|:---|:---|
| `start_time` | ISO datetime | 7 天前 |
| `end_time` | ISO datetime | now |

**响应**:
```json
{
  "code": 0,
  "data": {
    "total_attempts": 25,
    "success": 23,
    "failed": 2,
    "success_rate": 0.92,
    "recent_failures": [
      {
        "timestamp": "2026-06-01T10:00:00Z",
        "local_silence_id": 42,
        "name": "db-maintenance",
        "error": "AM timeout after 2s"
      }
    ]
  }
}
```

**数据流** (依赖 am_sync 改):
```
am_sync.push_silence() 成功 → OperationLog(action_type='am_sync_success', detail={local_silence_id, am_silence_id, name})
am_sync.push_silence() 失败 → OperationLog(action_type='am_sync_failed', detail={local_silence_id, name, error})
↓
SQL: count + 最近失败
```

**依赖**: 必须先完成 am_sync 改造

---

### EP-7: Redis 锁可观测

**端点**: `GET /api/v1/alerts/observability/lock-stats`

**响应** (per-process 视角, 跨进程需聚合):
```json
{
  "code": 0,
  "data": {
    "instance_id": "hostname-pid",
    "current_window": {
      "acquired": 145,
      "skipped": 23,
      "fallback": 2
    },
    "last_flush": "2026-06-01T10:00:00Z",
    "redis_available": true
  }
}
```

**数据流**:
```
dedup_lock 维护内存 _stats: {acquired, skipped, fallback}
Celery beat 60s 周期任务 → flush 到 OperationLog
↓
查询: 当前进程内存 + 最近 flush
```

**限制**: 跨进程聚合需额外 endpoint `GET /lock-stats/all` (P1)

---

## 2. 接口签名设计

### 2.1 notifier 改造

```python
# 现有: def send(self, payload: AlertPayload) -> bool
# 改造: def send(self, payload: AlertPayload, *, db: AsyncSession | None = None) -> bool
# 增加: send 成功/失败时写 OperationLog (db 不为空时)

# 现有: def send(self, payload: AlertPayload) -> dict[str, bool]
# 改造: 增加 channel_stats 内存缓存 (避免 DB 频繁读)
```

**关键改动**: [notifier.py::CompositeNotifier.send()](file:///e:/code/bysj/backend/app/monitoring/notifier.py#L346)
- 接收 `db: AsyncSession | None = None` 参数
- send 后异步记录 OperationLog (后台 task, 不阻塞通知)
- detail 包含 channel 名, duration_ms, error (失败时)

### 2.2 am_sync 改造

```python
# 现有: def push_silence(silence: dict) -> dict | None
# 改造: def push_silence(silence: dict, *, db: AsyncSession | None = None) -> dict | None
# 增加: 成功/失败时写 OperationLog

# 现有: def pull_silences() -> list | None
# 改造: 增加 db 参数, 记录拉取结果 (P1)
```

**关键改动**: [am_sync.py::push_silence()](file:///e:/code/bysj/backend/app/monitoring/am_sync.py#L41)

### 2.3 dedup_lock 改造

```python
# 现有: async def try_acquire_lock(fingerprint, ttl_seconds=300) -> bool
# 改造: 增加 _stats 内存计数, 增加 flush 接口

# 新增: async def flush_lock_stats(db: AsyncSession) -> None
# 新增: def get_lock_stats() -> dict  # 内存快照
```

**关键改动**: [dedup_lock.py::try_acquire_lock()](file:///e:/code/bysj/backend/app/monitoring/dedup_lock.py#L44)

### 2.4 新增 endpoint 模块

```python
# 新文件: app/api/v1/observability.py
# router = APIRouter(prefix="/alerts/observability", tags=["observability"])

# 端点 (P0): 7 个 (见上)
# 权限: require_role("admin")
# 缓存: Redis 5min
```

---

## 3. 数据流图 (text)

```
┌──────────────┐
│ 告警 webhook │ ─→ alertmanager_webhook()
└──────────────┘         ↓
                  ┌──────────────────┐
                  │  OperationLog    │ ←── alert_fired / alert_resolved
                  │  (source of      │ ←── alert_silenced
                  │   truth)         │ ←── alert_acknowledged
                  └──────────────────┘ ←── alert_escalated
                          ↑               ←── (新) alert_channel_sent/failed
                          │               ←── (新) am_sync_success/failed
                  ┌───────┴────────┐      ←── (新) dedup_lock_*  (周期 flush)
                  │ observability │ 
                  │ API           │ → EP-1~7 → admin
                  │ (read-only)   │
                  └────────────────┘
```

---

## 4. 失败降级矩阵

| 组件 | 失败模式 | 降级 |
|:---|:---|:---|
| **趋势 API** | DB 慢 | 5min cache 减少命中 |
| | JSON 解析失败 | silent skip |
| **响应时长** | 无 ack | total_pending 单列 |
| | 计算超时 | 返回部分 + warning |
| **升级率** | JOIN 慢 | LIMIT 10K 兜底 |
| **通道成功率** | notifier 未改 | 返回 501 + 引导 |
| **AM 同步** | am_sync 未改 | 返回 501 + 引导 |
| **锁可观测** | Redis 不通 | fallback 计数仍有效 |

---

## 5. 性能预算

| 端点 | 数据规模 | 目标延迟 | 实测风险 |
|:---|:---|:---|:---|
| EP-1 趋势 | 7d × 1h bucket × 5 维度 | < 500ms | 中 (group by 维度多) |
| EP-2 响应时长 | 7d × 100 告警/天 = 700 行 | < 300ms | 中 (self-JOIN) |
| EP-3 升级率 | 7d × 50 升级 = 350 行 | < 200ms | 低 |
| EP-4 通道成功 | 7d × 100 告警 × 4 通道 = 2800 行 | < 200ms | 低 |
| EP-5 静默命中 | 7d × 100 告警 = 700 行 | < 100ms | 低 |
| EP-6 AM 同步 | 7d × 10 同步 = 70 行 | < 100ms | 低 |
| EP-7 锁可观测 | 内存读 | < 50ms | 低 |

**优化**:
- Redis 5min cache (key: `obs:{endpoint}:{params_hash}`)
- 预计算: 每日 03:00 Celery 任务预聚合前一天数据到 `alert_stats_daily` 表 (P1)
- LIMIT 10000 兜底

---

## 6. 集成点

| 端点 | 依赖模块 | 依赖新增 | 优先级 |
|:---|:---|:---|:---:|
| EP-1 趋势 | OperationLog (现有) | 复合索引 | P0 |
| EP-2 响应时长 | OperationLog (现有) | 复合索引 + cache | P0 |
| EP-3 升级率 | OperationLog (现有) | 复合索引 | P0 |
| EP-4 通道成功 | **notifier 改** | 2 个 action_type | P0 |
| EP-5 静默命中 | OperationLog (现有) | 无 | P0 |
| EP-6 AM 同步 | **am_sync 改** | 2 个 action_type | P0 |
| EP-7 锁可观测 | **dedup_lock 改** | 3 个 action_type + flush 任务 | P0 |

---

## 7. 下一步 (Step 5: 锁定)

进入 Step 5: 锁定本轮产出, 生成 02-architecture.md / 03-pre-flight-check.md / 04-ralph-tasks.md / 05-test-plan.md / 06-learnings.md 框架, 准备 Round 2 修订。
