# 01i-simulation-r3 — v1.36-alert-observability (Round 3 / Step 4)

> **目的**: 终稿推演, 端到端模拟实施流程, 验证无遗漏。

---

## 1. 实施流程模拟 (按物理顺序)

### Step 1: T0.1 cache.py

```python
# 创建 app/core/cache.py (60 行)
# 测试 test_cache.py (7 用例)
# 通过 → 标记 [x]
```

**预期**: ~30 分钟, 无依赖

### Step 2: T0.2 instance.py

```python
# 创建 app/core/instance.py (10 行)
# 测试 test_instance.py (2 用例)
# 通过 → 标记 [x]
```

**预期**: ~10 分钟

### Step 3: T1.4 复合索引

```python
# 修改 app/models/admin.py::OperationLog.__table_args__
# 添加 Index("idx_oplog_action_created", ...)
# 添加 Index("idx_oplog_target_action", ...)
# 启动时 Base.metadata.create_all() 自动创建
# 验证: SHOW INDEX FROM operation_logs
```

**预期**: ~15 分钟, 启动时自动验证

### Step 4: T1.1 notifier 改造

```python
# 修改 app/monitoring/notifier.py
# CompositeNotifier.send(payload, *, db=None)
# 每个 notifier.send 后:
#   - 记录 start_time
#   - 调用 self.notifier.send(payload)
#   - 计算 duration_ms
#   - 写 OperationLog (db 不为空时)
# 测试 test_channel_logging.py (5 用例)
```

**预期**: ~1 小时 (中等风险)

### Step 5: T1.2 am_sync 改造

```python
# 修改 app/monitoring/am_sync.py
# push_silence(silence, *, db=None) -> dict | None
# 成功 → db.add(OperationLog(am_sync_success, ...))
# 失败 → db.add(OperationLog(am_sync_failed, ...))
# delete_silence / pull_silences 同理
# 测试 test_am_sync_logging.py (4 用例)
```

**预期**: ~30 分钟

### Step 6: T1.3 dedup_lock 改造

```python
# 修改 app/monitoring/dedup_lock.py
# _stats = {"skipped": 0, "fallback": 0, "last_flush": None}
# try_acquire_lock 内部:
#   if not acquired: _stats["skipped"] += 1
#   if redis_down: _stats["fallback"] += 1
# 新增 async def flush_lock_stats(db) -> None
# 新增 app/tasks/observability.py::flush_lock_stats_task
# 修改 app/core/celery_app.py 添加 beat_schedule
# 测试 test_dedup_lock_stats.py (5 用例)
```

**预期**: ~1 小时

### Step 7: T2.1 路由骨架

```python
# 创建 app/api/v1/observability.py
# 创建 router (prefix="/alerts/observability", tags=["observability"])
# 公共依赖: db, current_user, require_role("admin")
# 注册到 app/api/v1/__init__.py
# 空端点列表 (待 2.2-2.8)
```

**预期**: ~20 分钟

### Step 8: T2.2 EP-5 静默命中率

```python
# @router.get("/silence-hit-rate")
# SQL: count(fired), count(silenced)
# 集成 cache / instance_id
# 测试 test_silence_hit_rate_api.py (4 用例)
```

**预期**: ~30 分钟

### Step 9: T2.3 EP-1 告警趋势

```python
# @router.get("/trend")
# SQL: GROUP BY date_trunc, severity
# 集成 cache / instance_id
# 测试 test_trend_api.py (7 用例, 含 7d_under_500ms)
```

**预期**: ~1 小时

### Step 10: T2.4 EP-3 升级率

```python
# @router.get("/escalation")
# SQL: JOIN fired + escalated
# 集成 cache / instance_id
# 测试 test_escalation_api.py (5 用例)
```

**预期**: ~30 分钟

### Step 11: T2.5 EP-4 通道成功率

```python
# @router.get("/channel-stats")
# SQL: GROUP BY channel (从 detail JSON)
# 集成 cache / instance_id
# 测试 test_channel_stats_api.py (5 用例, 含 7d_under_200ms)
```

**预期**: ~30 分钟

### Step 12: T2.6 EP-6 AM 同步

```python
# @router.get("/am-sync")
# SQL: count + 最近失败
# 集成 cache / instance_id
# 测试 test_am_sync_api.py (4 用例)
```

**预期**: ~20 分钟

### Step 13: T2.7 EP-7 锁可观测

```python
# @router.get("/lock-stats")
# 读 _stats + last_flush
# 集成 cache / instance_id
# 测试 test_lock_stats_api.py (4 用例)
```

**预期**: ~20 分钟

### Step 14: T2.8 EP-2 响应时长

```python
# @router.get("/response-time")
# SQL: self-JOIN fired + acknowledged
# 计算 mean / p50 / p95 / p99
# LIMIT 10000
# 集成 cache / instance_id
# 测试 test_response_time_api.py (6 用例, 含 p99 正确性)
```

**预期**: ~1 小时 (复杂)

### Step 15: T3 集成 + 性能 + 工具测试

```python
# 端到端测试 (3 用例)
# 性能测试 (8 用例)
# 工具测试 (复用 T0.1/T0.2 测试)
```

**预期**: ~2 小时

### Step 16: T4 回归测试

```bash
# 运行 v1.34-v1.35 全部测试
# 验证无破坏
# 必要时修复
```

**预期**: ~1 小时

**总工时**: ~10-12 小时 (1.5 个工作日)

---

## 2. 关键依赖关系图

```
T0.1 cache ←──┐
T0.2 instance ←┤
              │
T1.4 索引 ────┤
              │
T1.1 notifier ┤
T1.2 am_sync  ├──> T2.1 路由 ──> T2.2-T2.8 (7 端点)
T1.3 dedup    ┤                          │
              │                          ↓
              └─> T3 集成/性能/工具 ──> T4 回归
```

**无循环依赖**, 可严格串行。

---

## 3. 失败模式与回退

| 步骤失败 | 回退方式 |
|:---|:---|
| T0.1 cache | 跳过 (Redis 不可用时已降级) |
| T0.2 instance | 跳过 (不影响功能) |
| T1.4 索引 | 启动时不创建, 后续手动 ALTER |
| T1.1 notifier | revert commit, 告警无影响 |
| T1.2 am_sync | revert commit, 静默无影响 |
| T1.3 dedup | revert commit, 跨实例去重无影响 |
| T2.x 端点 | 移除 router, 不影响其他模块 |
| T3 测试失败 | 修复后重跑 |
| T4 回归失败 | 修复引入的破坏 |

---

## 4. 部署顺序 (生产)

1. **代码部署**: v1.36 全部代码
2. **DB 索引自动创建**: 启动时 `Base.metadata.create_all()`
3. **Celery beat 重启**: 加载新 flush 任务
4. **验证**:
   - `GET /alerts/observability/silence-hit-rate` (无依赖, 立即可用)
   - `GET /alerts/observability/lock-stats` (内存读, 立即可用)
   - `GET /alerts/observability/channel-stats` (需 notifier 触发后, 等 1 天)
   - `GET /alerts/observability/am-sync` (需 am_sync 触发后, 等 1 天)
5. **回滚方案**: revert 代码 + 删除 flush 任务

---

## 5. 风险最终确认

**P0 风险**: 0
- 所有改动都是新增或可选 db 参数
- 现有路径不变 (db=None 时)
- 失败仅日志, 不抛错

**P1 风险**: 2 (复合索引 ALTER / self-JOIN 性能)
- 已有缓解 (启动 check first / LIMIT)

**P2 风险**: 3 (跨进程锁 / API 自身失败 / 跨 DB 不一致)
- 接受, 后续优化

---

## 6. 下一步 (Step 5: Lock)

进入 Step 5: 最终锁定, 生成:
- RALPH_STATE.md 追加 Implementation Phase
- 输出 "🎉 Planning Completed. Initiating Implementation Phase..."
- 调用 ralph-task-executor
