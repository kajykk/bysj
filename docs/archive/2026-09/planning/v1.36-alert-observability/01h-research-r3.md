# 01h-research-r3 — v1.36-alert-observability (Round 3 / Step 3)

> **目的**: 终稿调研, 复核任务边界和实施可行性。

---

## 1. 关键集成点验证

### 1.1 notifier.send 调用点

- 位置: [alerts.py:236](file:///e:/code/bysj/backend/app/api/v1/alerts.py#L236)
- 调用形式: `notifier.send(alert)` (单参数 AlertPayload)
- 改造: 改为 `notifier.send(alert, db=db)` (新增可选 db 参数)
- ✅ 改造可行 (向后兼容, 默认 None)
- ⚠️ 需保证 db 写入失败不影响通知

### 1.2 am_sync 调用点

- 位置: [silences.py:100-110](file:///e:/code/bysj/backend/app/api/v1/silences.py#L100-L110) (v1.35 集成)
- 现有形式: `push_silence(am_payload)` (无 db)
- 改造: `push_silence(am_payload, db=db)`
- ✅ 改造可行

### 1.3 dedup_lock 调用点

- 位置: [dedup.py:67](file:///e:/code/bysj/backend/app/monitoring/dedup.py#L67) (v1.35 集成)
- 现有形式: `await try_acquire_lock(alert.fingerprint, ttl_seconds=...)`
- 改造: 内部增加 `_stats` 计数
- ✅ 改造可行 (无接口变化)

### 1.4 Celery beat 注册

- 位置: [celery_app.py:31-60](file:///e:/code/bysj/backend/app/core/celery_app.py#L31-L60) (现有 beat_schedule)
- 新增: `"flush-lock-stats": {"task": "app.tasks.observability.flush_lock_stats_task", "schedule": 60.0}`
- ✅ 注册可行 (与 v1.34-v1.35 模式一致)

---

## 2. 工具模块设计复核

### 2.1 cache.py

- ✅ 60 行代码, 极简
- ✅ 复用 aioredis (已有)
- ✅ 失败降级 (返回 None / False)
- ✅ make_cache_key 用 md5 (稳定 + 短)

### 2.2 instance.py

- ✅ 10 行代码
- ✅ socket.gethostname() + os.getpid()
- ✅ 异常降级到 "unknown"

---

## 3. 7 端点实施顺序复核

按依赖关系, 推荐顺序:

| 顺序 | 端点 | 依赖 |
|:---:|:---|:---|
| 1 | EP-5 静默命中率 | 0 (仅 SQL) |
| 2 | EP-1 告警趋势 | 复合索引 |
| 3 | EP-3 升级率 | 复合索引 |
| 4 | EP-4 通道成功率 | **T1.1 notifier** |
| 5 | EP-6 AM 同步 | **T1.2 am_sync** |
| 6 | EP-7 锁可观测 | **T1.3 dedup_lock** |
| 7 | EP-2 响应时长 | 复合索引 + self-JOIN 复杂 |

**理由**: 简单 → 复杂, 0 依赖 → 多依赖, SQL 简单 → self-JOIN

---

## 4. 风险最终评估

| 风险 | 概率 | 影响 | 最终缓解 |
|:---|:---:|:---:|:---|
| notifier 写入失败影响通知 | 低 | 中 | 异步 try/except 包裹, 失败仅日志 |
| am_sync 改造破坏同步 | 低 | 中 | db 默认 None, 旧路径不变 |
| 锁 flush 失败累积 | 低 | 低 | 内存不清零 |
| 复合索引创建慢 | 中 | 中 | 启动 check first |
| 响应时长 self-JOIN 慢 | 中 | 中 | LIMIT 10000 + 索引 |
| API 自身失败无观测 | 低 | 低 | Sentry + logger.error |
| 跨进程锁无法聚合 | 中 | 低 | 接受 (P1 改进) |

**总风险**: 中低, 全部已有缓解。

---

## 5. 性能预算最终验证

| 端点 | 数据规模 | 预算 | 可行性 |
|:---|:---|:---|:---:|
| EP-1 趋势 | 100K rows, 7d, 1h | < 500ms | ✅ 索引覆盖 |
| EP-2 响应时长 | 1K fired, 800 ack | < 300ms | ✅ self-JOIN + LIMIT |
| EP-3 升级率 | 150 fired, 18 esc | < 200ms | ✅ 简单 GROUP BY |
| EP-4 通道成功 | 4 × 100 = 2800 | < 200ms | ✅ 索引覆盖 |
| EP-5 静默命中 | 700 + 50 = 750 | < 100ms | ✅ 简单 count |
| EP-6 AM 同步 | 70 rows | < 100ms | ✅ 简单 count |
| EP-7 锁 stats | 内存 | < 50ms | ✅ 内存读 |

**总性能**: 全部 ✅ 可行

---

## 6. 实施清单 (最终)

### Phase 0 (基础)
- T0.1 cache.py
- T0.2 instance.py

### Phase 1 (数据源)
- T1.1 notifier 改造
- T1.2 am_sync 改造
- T1.3 dedup_lock 改造
- T1.4 复合索引

### Phase 2 (端点)
- T2.1 路由骨架
- T2.2 EP-5 静默命中率
- T2.3 EP-1 趋势
- T2.4 EP-3 升级率
- T2.5 EP-4 通道成功率
- T2.6 EP-6 AM 同步
- T2.7 EP-7 锁可观测
- T2.8 EP-2 响应时长

### Phase 3 (测试)
- T3.1 端到端
- T3.2 性能
- T3.3 工具模块

### Phase 4 (回归)
- T4.1 核心回归

**总任务数**: 17 个 P0 任务

---

## 7. 下一步 (Step 4: 推演)

进入 Step 4 推演 (终稿):
- 验证 04-ralph-tasks.md 与 01-requirements 1:1 对应
- 验证 05-test-plan.md 覆盖 04-ralph-tasks
- 验证 06-learnings.md 反映所有约定
- 最终 lock 决策
