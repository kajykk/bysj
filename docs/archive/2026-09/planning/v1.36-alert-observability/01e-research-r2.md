# 01e-research-r2 — v1.36-alert-observability (Round 2 / Step 3)

> **目的**: 调研 Round 2 critique 提出的 4 个 P1 建议, 决定是否纳入 Round 3 终稿。
> **关联**: [./01d-critique-r2.md](./01d-critique-r2.md)

---

## 1. P1-1: 缓存命中标记 (`cached: true`)

### 调研发现

- ✅ 无现有 cache 工具函数 (`app/core/cache.py` 不存在)
- ✅ dedup_lock 直接用 `aioredis.from_url` 调用
- ✅ rate_limit 通过 slowapi 间接用 Redis
- ❌ 无统一 cache 模式

### 设计方案

**新文件**: `app/core/cache.py`

```python
"""v1.36: 观测 API 5min 缓存工具."""
import hashlib
import json
import logging
from typing import Any
import redis.asyncio as aioredis
from app.core.config import settings

logger = logging.getLogger(__name__)
DEFAULT_TTL = 300  # 5min

async def cache_get(key: str) -> Any | None:
    """读缓存, 失败返回 None (降级到直接查询)."""
    if not settings.redis_url or not settings.redis_url.startswith("redis"):
        return None
    try:
        client = aioredis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2)
        value = await client.get(key)
        await client.aclose()
        if value:
            return json.loads(value)
    except Exception as exc:
        logger.warning("[cache] get failed: %s", exc)
    return None

async def cache_set(key: str, value: Any, ttl: int = DEFAULT_TTL) -> bool:
    """写缓存, 失败仅日志."""
    if not settings.redis_url or not settings.redis_url.startswith("redis"):
        return False
    try:
        client = aioredis.from_url(settings.redis_url, decode_responses=True, socket_connect_timeout=2, socket_timeout=2)
        await client.set(key, json.dumps(value), ex=ttl)
        await client.aclose()
        return True
    except Exception as exc:
        logger.warning("[cache] set failed: %s", exc)
        return False

def make_cache_key(endpoint: str, params: dict) -> str:
    """生成稳定 cache key."""
    raw = json.dumps(params, sort_keys=True)
    return f"obs:{endpoint}:{hashlib.md5(raw.encode()).hexdigest()[:16]}"
```

**集成模式**:
```python
@router.get("/trend")
async def trend(...):
    cache_key = make_cache_key("trend", {...params})
    cached = await cache_get(cache_key)
    if cached:
        cached["cached"] = True
        cached["cached_at"] = datetime.now().isoformat()
        return ok(cached)
    result = await compute_trend(...)
    await cache_set(cache_key, result)
    result["cached"] = False
    return ok(result)
```

### 评估

- ✅ 简单实现, 60 行
- ✅ 失败降级 (Redis 不可用 → 不缓存, 直接查)
- ⚠️ 多用户并发: 同一 cache key 命中旧数据 (5min 内可接受)
- ✅ 标记 `cached: true` 让前端显示"已缓存"
- **建议**: **纳入 P0** (缓存是性能要求, 标记是低成本增强)

---

## 2. P1-2: instance_id 返回

### 调研发现

- ✅ 无现有 instance_id 概念
- ✅ 可用 `socket.gethostname() + os.getpid()` 组合
- ✅ 多实例部署时, OperationLog 不带 instance 字段

### 设计方案

**新文件**: `app/core/instance.py`

```python
"""v1.36: 实例标识."""
import os
import socket

def get_instance_id() -> str:
    """获取当前实例唯一标识 (hostname-pid)."""
    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = "unknown"
    return f"{hostname}-{os.getpid()}"
```

**集成**:
- 锁 stats 响应带 `instance_id`
- observability API 响应带 `instance_id` (可选, 调试用)

### 评估

- ✅ 极简, 10 行
- ✅ 调试多实例问题时很有用
- ⚠️ 不是核心功能
- **建议**: **纳入 P0** (低成本, 高价值调试能力)

---

## 3. P1-3: observability 自身失败记录

### 调研发现

- ✅ OperationLog 已存在
- ✅ 无现有 "API 调用记录" 机制
- ⚠️ 给 observability API 自己加埋点会自循环 (observability → observability error → observability error...)

### 设计方案

**方案 A: 用普通日志, 不入 OperationLog**
- 失败时 `logger.error("[observability] {endpoint} failed: {error}", exc_info=True)`
- Sentry 自动捕获
- 不引入自循环

**方案 B: 入 OperationLog, 但用独立 action_type**
- `obs_api_error` (action_type)
- 不会自循环, 因为查询 observability 数据时, 不应再次触发观测 API

### 评估

- ✅ 方案 A 简单, Sentry 覆盖
- ⚠️ 方案 B 多一层 (但保留审计)
- **建议**: **方案 A 纳入 P0** (依赖现有 Sentry; 方案 B 为 P1)

---

## 4. P1-4: cache 工具函数

### 评估

- ✅ P1-1 已设计 `app/core/cache.py`
- ✅ 复用性高 (后续 v1.37+ 也可使用)
- **建议**: **纳入 P0** (与 P1-1 同步)

---

## 5. 性能测试具体断言

### Round 1 critique 提到: "未明确性能测试断言"

**建议补充** (进入 04 / 05 任务和测试):
- `test_trend_7d_under_500ms`: 100K 行 OperationLog, 1h bucket, 7 天窗口, 断言 < 500ms
- `test_response_time_7d_under_300ms`: 1K 行 fired + 800 行 acknowledged, self-JOIN, 断言 < 300ms
- `test_channel_stats_7d_under_200ms`: 4 通道 × 100 告警/天, GROUP BY, 断言 < 200ms

**实施**: pytest-benchmark 或 `time.time()` 简单计时

---

## 6. 调研结论

| 建议 | 评估 | 决定 |
|:---|:---:|:---|
| 缓存命中标记 | 低成本高价值 | **纳入 P0** |
| instance_id | 调试有用 | **纳入 P0** |
| API 自身失败 | 用 Sentry 而非自循环 | **纳入 P0** (方案 A) |
| cache 工具 | 复用性高 | **纳入 P0** |
| 性能测试断言 | 明确预算 | **纳入 P0** (04-ralph-tasks) |

**新增 P0 任务**:
- T0.1 新建 `app/core/cache.py` (cache_get / cache_set / make_cache_key)
- T0.2 新建 `app/core/instance.py` (get_instance_id)
- T0.3 性能测试 (补充到 05-test-plan)

**新增 P0 端点增强**:
- 所有 7 端点响应增加 `cached: bool` + `instance_id: str`
- 失败时 Sentry 捕获 + logger.error

---

## 7. 下一步 (Step 4: 推演)

基于调研, 进入 Step 4 推演:
- 7 端点的最终请求/响应 schema (含 cached / instance_id)
- cache 工具函数的接口设计
- 失败降级路径
- 性能测试断言细节
