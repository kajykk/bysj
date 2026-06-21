# 01f-simulation-r2 — v1.36-alert-observability (Round 2 / Step 4)

> **目的**: 基于 Round 2 research, 输出 7 端点最终 schema (含 cached / instance_id) + 工具模块设计 + 性能断言。
> **关联**: [./01e-research-r2.md](./01e-research-r2.md)

---

## 1. 通用响应增强 (新增)

所有 7 端点响应统一格式:

```json
{
  "code": 0,
  "data": {
    "...原内容...": "...",
    "cached": false,
    "cached_at": null,
    "instance_id": "backend-pod-7c5d8-12345"
  }
}
```

| 字段 | 类型 | 说明 |
|:---|:---|:---|
| `cached` | bool | 是否命中缓存 |
| `cached_at` | ISO datetime \| null | 缓存写入时间 (仅 cached=true) |
| `instance_id` | string | 当前实例标识 (hostname-pid) |

---

## 2. 工具模块设计

### 2.1 `app/core/cache.py` (新增)

**接口**:
```python
async def cache_get(key: str) -> Any | None
async def cache_set(key: str, value: Any, ttl: int = 300) -> bool
def make_cache_key(endpoint: str, params: dict) -> str
```

**降级**:
- Redis 不可用 → 静默返回 None / False
- 解析失败 → 视为缓存 miss
- 超时 2s → 视为 miss

**复用性**: 后续 v1.37+ 可用于其他观测端点

### 2.2 `app/core/instance.py` (新增)

**接口**:
```python
def get_instance_id() -> str  # hostname-pid
```

**实现**:
```python
import os
import socket

def get_instance_id() -> str:
    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = "unknown"
    return f"{hostname}-{os.getpid()}"
```

**复用性**: 后续 v1.37+ 跨实例统计时使用

---

## 3. 7 端点最终 Schema

### 3.1 EP-1 趋势

```json
{
  "code": 0,
  "data": {
    "buckets": [
      {"bucket": "2026-06-01T00:00:00Z", "items": [
        {"severity": "P0", "status": "firing", "count": 12}
      ]}
    ],
    "summary": {"total_firing": 145, "total_resolved": 132, "window_hours": 168},
    "cached": false,
    "cached_at": null,
    "instance_id": "backend-pod-7c5d8-12345"
  }
}
```

### 3.2 EP-2 响应时长

```json
{
  "code": 0,
  "data": {
    "groups": [
      {"key": "P0", "total_acknowledged": 42, "total_pending": 8, "stats": {
        "mean_seconds": 120.5, "p50_seconds": 90, "p95_seconds": 480, "p99_seconds": 1200
      }}
    ],
    "summary": {"total_alerts": 50, "acknowledged_rate": 0.84},
    "cached": false,
    "cached_at": null,
    "instance_id": "..."
  }
}
```

### 3.3 EP-3 升级率

```json
{
  "code": 0,
  "data": {
    "total_fired": 150, "total_escalated": 18, "escalation_rate": 0.12,
    "by_level": {"L1": 12, "L2": 4, "L3": 2},
    "by_rule": [{"rule": "HighCPU", "fired": 30, "escalated": 8, "rate": 0.27}],
    "cached": false, "cached_at": null, "instance_id": "..."
  }
}
```

### 3.4 EP-4 通道成功率

```json
{
  "code": 0,
  "data": {
    "channels": [
      {"channel": "webhook", "sent": 145, "failed": 3, "success_rate": 0.98, "avg_duration_ms": 120}
    ],
    "total_sent": 420, "total_failed": 30, "overall_success_rate": 0.93,
    "cached": false, "cached_at": null, "instance_id": "..."
  }
}
```

### 3.5 EP-5 静默命中率

```json
{
  "code": 0,
  "data": {
    "total_alerts": 250, "silenced_alerts": 35, "hit_rate": 0.14,
    "by_matcher": [{"matcher_key": "severity", "matcher_value": "P0", "silenced": 8, "hit_rate": 0.10}],
    "cached": false, "cached_at": null, "instance_id": "..."
  }
}
```

### 3.6 EP-6 AM 同步

```json
{
  "code": 0,
  "data": {
    "total_attempts": 25, "success": 23, "failed": 2, "success_rate": 0.92,
    "recent_failures": [
      {"timestamp": "2026-06-01T10:00:00Z", "local_silence_id": 42, "name": "db-maintenance", "error": "AM timeout after 2s"}
    ],
    "cached": false, "cached_at": null, "instance_id": "..."
  }
}
```

### 3.7 EP-7 锁可观测

```json
{
  "code": 0,
  "data": {
    "instance_id": "backend-pod-7c5d8-12345",
    "current_window": {"acquired": 145, "skipped": 23, "fallback": 2},
    "last_flush": "2026-06-01T10:00:00Z",
    "redis_available": true,
    "cached": false, "cached_at": null
  }
}
```

---

## 4. 端点集成模式 (模板)

```python
@router.get("/trend", response_model=dict)
async def get_trend(
    db: Annotated[AsyncSession, Depends(get_db)],
    _: Annotated[User, Depends(require_role("admin"))],
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    bucket: str = "1h",
    severity: str | None = None,
    status: str | None = None,
) -> dict:
    """v1.36: 告警趋势."""
    # 1. 构造 cache key
    params = {
        "start_time": start_time.isoformat() if start_time else None,
        "end_time": end_time.isoformat() if end_time else None,
        "bucket": bucket,
        "severity": severity,
        "status": status,
    }
    cache_key = make_cache_key("trend", params)
    
    # 2. 试读缓存
    cached = await cache_get(cache_key)
    if cached is not None:
        cached["cached"] = True
        cached["cached_at"] = datetime.now(timezone.utc).isoformat()
        cached["instance_id"] = get_instance_id()
        return ok(cached)
    
    # 3. 实时查询
    try:
        result = await _compute_trend(db, start_time, end_time, bucket, severity, status)
    except Exception as exc:
        logger.error("[observability.trend] failed: %s", exc, exc_info=True)
        raise HTTPException(status_code=500, detail=f"trend query failed: {exc}")
    
    # 4. 写缓存
    await cache_set(cache_key, result, ttl=300)
    
    # 5. 增强响应
    result["cached"] = False
    result["cached_at"] = None
    result["instance_id"] = get_instance_id()
    return ok(result)
```

---

## 5. 性能断言 (具体化)

| 测试 | 数据规模 | 断言 |
|:---|:---|:---|
| `test_trend_7d_under_500ms` | 100K OperationLog, 1h bucket, 7d 窗口 | < 500ms |
| `test_trend_30d_under_1500ms` | 100K OperationLog, 1h bucket, 30d 窗口 | < 1500ms |
| `test_response_time_7d_under_300ms` | 1K fired + 800 acknowledged, 7d | < 300ms |
| `test_response_time_p99_calculation` | 100 rows with 50% ack | mean/p50/p95/p99 正确 |
| `test_channel_stats_7d_under_200ms` | 4 通道 × 100 告警/天 = 2800 行, 7d | < 200ms |
| `test_silence_hit_rate_under_100ms` | 700 fired, 50 silenced | < 100ms |
| `test_am_sync_under_100ms` | 70 rows | < 100ms |
| `test_lock_stats_under_50ms` | 内存读 | < 50ms |

**实施方式**: `time.time()` 简单计时 + 断言

---

## 6. 失败路径详细设计

### 6.1 DB 查询失败

```python
try:
    result = await _compute_trend(...)
except SQLAlchemyError as exc:
    logger.error("[observability.trend] DB error: %s", exc, exc_info=True)
    # Sentry 自动捕获 (v1.13 集成)
    raise HTTPException(status_code=500, detail="trend query failed")
```

### 6.2 JSON 解析失败 (severity 提取)

```python
# 静默 skip
for row in rows:
    try:
        detail = json.loads(row.detail or "{}")
        severity = detail.get("severity", "Unknown")
    except Exception:
        severity = "Unknown"  # 不抛错
    # ...
```

### 6.3 Redis 不可用 (cache 失败)

```python
cached = await cache_get(cache_key)
# 内部已处理: 失败返回 None, 不抛错
if cached is None:
    # 实时查询
    result = await _compute_trend(...)
    # 写缓存 (内部已处理: 失败仅日志)
    await cache_set(cache_key, result)
```

### 6.4 notifier 改造后写 OperationLog 失败

```python
# 在 send() 中 try/except 包裹
try:
    op_log = OperationLog(...)
    db.add(op_log)
    await db.commit()
except Exception as exc:
    await db.rollback()
    logger.error("[notifier] failed to log channel result: %s", exc)
    # 不影响通知返回
```

### 6.5 锁 flush 任务失败

```python
# Celery task 已有 max_retries=2
@celery_app.task(bind=True, max_retries=2, default_retry_delay=30)
def flush_lock_stats_task(self):
    try:
        ...
    except Exception as exc:
        try:
            self.retry(exc=exc)
        except self.MaxRetriesExceededError:
            logger.error("[flush_lock_stats] max retries exceeded")
            # 内存不清零, 下次 beat 再试
```

---

## 7. 端点注册

**新文件**: `app/api/v1/observability.py`

```python
router = APIRouter(prefix="/alerts/observability", tags=["observability"])

# 7 个端点
@router.get("/trend")
@router.get("/response-time")
@router.get("/escalation")
@router.get("/channel-stats")
@router.get("/silence-hit-rate")
@router.get("/am-sync")
@router.get("/lock-stats")
```

**注册**: `app/api/v1/__init__.py`
```python
from app.api.v1 import observability
api_router.include_router(observability.router)
```

---

## 8. 数据流 (增强版)

```
┌─────────────────┐
│ OperationLog    │ ← alert_fired / alert_resolved
│ (truth)         │ ← alert_silenced
│                 │ ← alert_acknowledged
│ + 2 复合索引    │ ← alert_escalated
│                 │ ← (新) alert_channel_sent/failed
└─────────────────┘ ← (新) am_sync_success/failed
        ↑           ← (新) dedup_lock_skipped/fallback (60s flush)
        │
        ├─→ cache.py (5min Redis)
        ├─→ observability.py (7 端点)
        └─→ cache miss → DB query
                ↓
            instance_id + cached 标记
                ↓
            admin (HTTP)
```

---

## 9. 下一步 (Step 5: 锁定)

进入 Step 5: 锁定 Round 2 修订, 准备 Round 3 终稿。
