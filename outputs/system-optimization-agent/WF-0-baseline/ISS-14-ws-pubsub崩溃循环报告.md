# ISS-14 ws.py pubsub 订阅器崩溃重启循环 · 根因分析与修复报告

> 生成：2026-07-15 | 阶段：WF-0 基线评估与问题诊断（问题治理） | 项目：抑郁预警系统（FastAPI + Vue3）
> 处理技能：`sys-reliability` | 优先级：P2 | 关联阶段：WF-3 | 状态：**已修复**
> 关联问题：ISS-12（长尾延迟根因复测时附带发现，经验证与长尾无关、为独立可靠性缺陷）

---

## 1. 摘要

`app/core/ws.py` 的后台 Redis pubsub 订阅循环 `_pubsub_loop` 复用**共享缓存 Redis 客户端**（其 `socket_timeout=2`），对空闲频道做阻塞读（`pubsub.listen()`）。当频道空闲超过 2 秒无任何消息时，底层 socket 读超时抛 `redis.exceptions.TimeoutError`，被 `except Exception` 捕获后 `sleep(1)` 重启，形成**每秒一次**的崩溃重启死循环。

修复方式为引入**订阅专用 Redis 客户端单例** `get_redis_pubsub_client()`，独立连接池 + `socket_timeout=None`（订阅是长空闲阻塞读，本就不应有读超时），并配合 `socket_keepalive` / `health_check_interval=30` / `retry_on_timeout` 兜底静默断线检测。该客户端与普通缓存读写隔离，互不干扰。

实测：修复前 `_uvicorn.log` 含 **956 次** `pubsub loop crashed`；修复后重启实例（`postgres+redis`）**35s 空闲实测 0 崩溃 / 0 TimeoutError**，pubsub 循环稳定存活；单元测试 `tests/test_ws_pubsub.py` **17 passed**。

---

## 2. 现象（修复前证据）

- 旧实例（PID 39080，`postgres+redis` 忠实部署）运行日志 `backend/_uvicorn.log` 中大量刷屏：
  ```
  WebSocket pubsub loop crashed, restarting in 1s
  ```
  grep 计数：**956 次**。
- 日志尾部堆栈关键行：
  ```
  redis.exceptions.TimeoutError: Timeout reading from localhost:6379
    File ".../redis/connection.py", line 744, in read_response
  ```
- `redis-cli PING` 返回正常 → Redis 服务本身健康，问题在 asyncio pubsub 的 socket 超时配置。
- 影响：日志刷屏淹没真实告警、Redis 连接因超时风暴频繁重建抖动、崩溃循环持续占用事件循环协程（ISS-06 资源基线中观测到的「53 线程偏高」部分源于此）。

---

## 3. 根因

### 3.1 共享客户端被设置了过短的读超时（致命）

`app/core/cache.py` 的共享缓存客户端在 `_get_redis_client()` 中以 `socket_timeout=2` 创建（`cache.py:130-135`）：

```python
_redis_client = aioredis.from_url(
    url,
    decode_responses=True,
    socket_connect_timeout=2,
    socket_timeout=2,          # ← 普通缓存请求够用，但对长空闲 pubsub 阻塞读是致命的
)
```

该超时保护普通缓存请求（每次请求毫秒级往返）完全合理，但被用于 pubsub 订阅后就出问题。

### 3.2 `_pubsub_loop` 复用了该共享客户端做空闲阻塞读

`app/core/ws.py` 的 `_pubsub_loop`（`ws.py:207-247`）原本调用 `get_redis_client()` 拿到的就是上面的共享客户端，然后进入 `while True` + `pubsub.listen()` 阻塞读：

```python
async def _pubsub_loop(self) -> None:
    from app.core.cache import get_redis_client
    ...
    while True:
        try:
            client = await get_redis_client()          # ← 拿到 socket_timeout=2 的共享客户端
            pubsub = client.pubsub()
            await pubsub.psubscribe(f"{WS_PUBSUB_CHANNEL_PREFIX}*")
            async for message in pubsub.listen():        # ← 阻塞读：频道空闲 >2s 无消息
                ...                                      #    即触发 socket 读超时
        except Exception:
            logger.exception("WebSocket pubsub loop crashed, restarting in 1s")
            await asyncio.sleep(1.0)                     # ← 1s 后重启 → 永久崩溃循环
```

**因果链**：空闲频道（无 WS 消息推送时常态）→ `pubsub.listen()` 阻塞读超过 2s → `redis.exceptions.TimeoutError: Timeout reading from localhost:6379` → 被 `except Exception` 捕获 → `sleep(1)` → 重新进入循环 → 再次空闲超时 → 死循环（实测约每秒一次，日志累计 956 次）。

> 注：`_pubsub_loop` 的「崩溃即重启」容错逻辑本身是对的（应对 Redis 真实宕机），问题出在**把带读超时的共享客户端用于长空闲订阅**这一错误复用，把正常的空闲静默误判成了需要重启的故障。

---

## 4. 修复

### 4.1 新增订阅专用客户端单例（`cache.py:143-180`）

```python
async def get_redis_pubsub_client() -> "aioredis.Redis | None":
    """ISS-14 修复：获取 pubsub 订阅专用 Redis 客户端 (socket_timeout=None)。

    与 get_redis_client 共享同一 Redis URL, 但独立连接池, 且:
      - socket_timeout=None: 订阅是长空闲阻塞读, 绝不应有读超时;
        若沿用共享客户端的 socket_timeout=2, 空闲 >2s 即抛 TimeoutError (ISS-14)。
      - socket_connect_timeout=2: 连接阶段仍保持短超时, 启动失败快速退出。
      - socket_keepalive=True + health_check_interval=30: 保活, 静默断线时
        周期性 PING 探测, 失败即抛 ConnectionError 触发 _pubsub_loop 重连。
      - retry_on_timeout=True: 超时自动重试 (与 socket_timeout=None 配合, 兜底)。
    """
    global _redis_pubsub_client
    if _redis_pubsub_client is not None:
        return _redis_pubsub_client
    async with _redis_client_lock:
        if _redis_pubsub_client is not None:
            return _redis_pubsub_client
        url = _get_redis_url()
        if not url:
            return None
        try:
            _redis_pubsub_client = aioredis.from_url(
                url,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=None,      # ← 关键：订阅长空闲读不再超时
                socket_keepalive=True,
                health_check_interval=30,
                retry_on_timeout=True,
            )
        except Exception as exc:
            logger.warning("[cache] redis pubsub client init failed: %s", exc)
            _redis_pubsub_client = None
            return None
        return _redis_pubsub_client
```

- 模块级新增单例 `_redis_pubsub_client = None`（`cache.py:100`）。
- `close_redis_client()` 与 `_reset_redis_client()` 同步接管 `_redis_pubsub_client` 的关闭/重置，避免连接泄漏、保证测试隔离复位。

### 4.2 `_pubsub_loop` 改用专用客户端（`ws.py:215-225`）

```python
async def _pubsub_loop(self) -> None:
    """...
    ISS-14 修复: 订阅使用专用 Redis 客户端 (get_redis_pubsub_client,
    socket_timeout=None), 不复用共享缓存客户端 (socket_timeout=2)。
    否则空闲阻塞读超过 2s 会抛 TimeoutError, 触发本循环每秒崩溃重启。
    """
    from app.core.cache import get_redis_pubsub_client
    ...
    client = await get_redis_pubsub_client()   # ← 专用客户端，无读超时
```

发布路径（`_publish_to_redis` / 广播发布，见 `ws.py:138-168`）仍使用共享 `get_redis_client`（短连接、毫秒级往返，2s 超时合理），订阅与发布**连接池隔离**，互不影响。

### 4.3 单元测试对齐（`tests/test_ws_pubsub.py`）

订阅循环测试在 4 处（`TestPubsubLifecycle.test_start_is_idempotent`、`TestCrossProcessMessageFlow.test_celery_notify_reaches_fastapi_worker` / `test_no_loopback_when_same_node_publishes` / `test_broadcast_reaches_other_workers`）增加 `patch("app.core.cache.get_redis_pubsub_client", <fake>)`，与既有 `patch("app.core.cache.get_redis_client", <fake>)` 并列。因测试在运行时 `from app.core.cache import get_redis_pubsub_client` 解析，打同一个 fake 即可重定向订阅路径、不影响发布路径。

---

## 5. 验证

### 5.1 单元测试

```
cd backend && .venv/Scripts/python.exe -m pytest tests/test_ws_pubsub.py -q
```

结果：**`17 passed`**（约 25s）。

> 说明：pytest 退出时仍报 `FAIL Required test coverage of 40% not reached. Total coverage: 21.13%` —— 这是**项目级全局聚合覆盖率门槛**（`.coveragerc` 的 `--cov-fail-under=40`），并非本次测试失败；`test_ws_pubsub.py` 自身 17 用例全绿。该门槛属 ISS-02/覆盖率治理范畴，不在 ISS-14 修复范围内。

### 5.2 运行期验证（端到端）

1. 杀掉旧崩溃实例：`taskkill /F /PID 39080`（956 次崩溃的旧进程）。
2. 启动修复后实例（faithful `postgres+redis` 部署，注意须显式传 `DATABASE_URL` 否则回退 `.env` 的 sqlite 缺表）：
   ```bash
   cd backend
   DATABASE_URL='postgresql://postgres:test@127.0.0.1:5433/testdb' \
   REDIS_URL='redis://localhost:6379/0' \
   uvicorn app.main:app --port 8000 > _uvicorn_iss14.log 2>&1 &
   ```
3. 静置约 35s（故意不推送任何 WS 消息，制造空闲订阅条件），检查新日志 `backend/_uvicorn_iss14.log`：
   ```
   2026-07-15 03:37:23 | INFO | app.core.ws | WebSocket pubsub loop started (node_id=9b84...)
   2026-07-15 03:37:23 | INFO | uvicorn.error | Application startup complete.
   ```
   - grep `pubsub loop crashed`：**0 次**。
   - grep `TimeoutError`：**0 次**。
   - pubsub 循环稳定存活，无重启。

**结论**：空闲订阅不再触发读超时，崩溃重启死循环已消除。

---

## 6. 影响与风险评估

- **正向影响**：消除日志刷屏（避免淹没真实告警）、消除 Redis 连接超时风暴式重建抖动、释放被崩溃循环占用的事件循环协程（ISS-06 观测到的线程数偏高问题部分缓解）。
- **剩余风险（已评估、可接受）**：`socket_timeout=None` 意味着一个**真正夯死**的 TCP 连接可能永久阻塞读。缓解措施已就位：
  - `socket_keepalive=True` + `health_check_interval=30`：Redis 客户端每 30s 发 PING 探活，静默断线会被探测到并抛 `ConnectionError` → 触发 `_pubsub_loop` 重连；
  - `retry_on_timeout=True`：兜底超时重试；
  - `_pubsub_loop` 的 `except Exception → sleep(1) → 重启` 容错逻辑保留，应对 Redis 真实宕机。
- **隔离性**：专用客户端独立连接池，与高频缓存读写互不干扰；普通缓存请求的 2s 超时保护保持不变，未引入回归。

---

## 7. 回滚

- 代码回滚：将 `cache.py` 还原（删除 `get_redis_pubsub_client` 及 `_redis_pubsub_client` 单例，撤销 `close_redis_client`/`_reset_redis_client` 相关改动），并将 `ws.py` `_pubsub_loop` 改回 `from app.core.cache import get_redis_client` + `await get_redis_client()`。
- 测试回滚：撤销 `tests/test_ws_pubsub.py` 的 4 处 `get_redis_pubsub_client` patch。
- ⚠️ 回滚会将系统**重新暴露**于每秒崩溃重启循环（即本缺陷），仅应在修复引发严重回归时执行，且需同步根因修复。

---

## 8. 交付物

| 类型 | 文件 | 说明 |
|---|---|---|
| 源码修复 | `backend/app/core/cache.py` | 新增 `get_redis_pubsub_client()`（:143-180）+ `_redis_pubsub_client` 单例（:100）；`close_redis_client`/`_reset_redis_client` 接管 |
| 源码修复 | `backend/app/core/ws.py` | `_pubsub_loop` 改用 `get_redis_pubsub_client`（:215-225） |
| 测试对齐 | `backend/tests/test_ws_pubsub.py` | 4 处订阅路径 patch 增加 `get_redis_pubsub_client` |
| 证据 | `backend/_uvicorn.log` | 修复前日志，**956 次** `pubsub loop crashed`（before） |
| 证据 | `backend/_uvicorn_iss14.log` | 修复后日志，**0 崩溃 / 0 TimeoutError**，启动干净（after） |
| KPI | `outputs/system-optimization-agent/WF-0-baseline/KPI-基线.json` | 新增 `reliability.ws_pubsub_crash_loop: "resolved"`；`latency_tail_fullstack` 注更新 |
| 清单 | `outputs/system-optimization-agent/WF-0-baseline/问题清单与优先级.csv` | ISS-14 状态 → `已修复-...` |
| 报告 | `outputs/system-optimization-agent/WF-0-baseline/系统现状评估报告.md` | §2.3 ISS-14 注改「已修复」；§5 新增第 5 项标记关闭 |
| 本报告 | `outputs/system-optimization-agent/WF-0-baseline/ISS-14-ws-pubsub崩溃循环报告.md` | — |

---

## 9. 复现命令（供审计 / 回归）

```bash
# 1) 单元
cd backend && .venv/Scripts/python.exe -m pytest tests/test_ws_pubsub.py -q

# 2) 运行期（faithful postgres+redis）
docker start ci-postgres dws-redis            # 已含 39 表 + 租户 1
# 修复前（对照）：旧代码 + 旧实例日志 grep "pubsub loop crashed" 应 >> 0
# 修复后：
cd backend
DATABASE_URL='postgresql://postgres:test@127.0.0.1:5433/testdb' \
REDIS_URL='redis://localhost:6379/0' \
uvicorn app.main:app --port 8000 > _uvicorn_iss14.log 2>&1 &
sleep 35
grep -c "pubsub loop crashed" _uvicorn_iss14.log   # 期望 0
grep -c "TimeoutError"      _uvicorn_iss14.log      # 期望 0
```

> 推进原则（与全计划一致）：先数据后决策、先根因后修复、每阶段可量化、伴随监控与回滚。
