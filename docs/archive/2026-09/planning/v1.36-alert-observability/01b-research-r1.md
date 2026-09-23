# 01b-research — v1.36-alert-observability (Round 1 / Step 3)

> **目的**: 验证 critique 中的假设, 探查现有代码以确认数据源和改动点。
> **关联**: [./01-requirements.md](./01-requirements.md), [./01a-critique-r1.md](./01a-critique-r1.md)

---

## 1. OperationLog 表现状

**文件**: [models/admin.py::OperationLog](file:///e:/code/bysj/backend/app/models/admin.py#L33)

```python
class OperationLog(Base):
    __tablename__ = "operation_logs"
    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    operator_id: Mapped[int | None] = mapped_column(ForeignKey("users.id"), nullable=True)
    operator_role: Mapped[str | None] = mapped_column(String(20), nullable=True)
    action_type: Mapped[str] = mapped_column(String(50), nullable=False)  # ← 关键
    target_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    detail: Mapped[str | None] = mapped_column(Text, nullable=True)  # ← JSON 字符串
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now(), index=True)
```

**CheckConstraint**:
- `action_type` ≤ 50 字符 (满足新 action_type 长度)

**索引**:
- `created_at` (单列)
- ❌ **缺失**: `(action_type, created_at)` 复合索引 (影响 v1.36 查询)

---

## 2. 现有 action_type 清单 (v1.33-v1.35 调研)

| action_type | 写入位置 | 用途 | 复用 for v1.36 |
|:---|:---|:---|:---:|
| `alert_fired` | [alerts.py:118](file:///e:/code/bysj/backend/app/api/v1/alerts.py#L118) | webhook 收到 firing 告警 | ✅ 趋势, 升级率分母 |
| `alert_resolved` | [alerts.py:118](file:///e:/code/bysj/backend/app/api/v1/alerts.py#L118) | webhook 收到 resolved 告警 | ✅ 趋势 |
| `alert_silenced` | [alerts.py:198](file:///e:/code/bysj/backend/app/api/v1/alerts.py#L198) | 静默匹配命中 | ✅ 静默命中 |
| `alert_acknowledged` | [alerts.py:347](file:///e:/code/bysj/backend/app/api/v1/alerts.py#L347) | 管理员确认 | ✅ 响应时长 |
| `alert_escalated` | [escalation.py:161](file:///e:/code/bysj/backend/app/monitoring/escalation.py#L161) | 升级事件 | ✅ 升级率 |
| `delete_silence` | [silences.py:191](file:///e:/code/bysj/backend/app/api/v1/silences.py#L191) | 静默取消 | ❌ 无需观测 |

**结论**: 5/6 现有 action_type 均可复用, 仅 1 个 (`delete_silence`) 与 v1.36 无关。

---

## 3. 待新增 action_type (P0)

| action_type | 目标 | 写入位置 | detail 字段建议 |
|:---|:---|:---|:---|
| `alert_channel_sent` | 通道发送成功 | notifier 改 | `{channel, rule, severity, fingerprint, duration_ms}` |
| `alert_channel_failed` | 通道发送失败 | notifier 改 | `{channel, rule, severity, fingerprint, error}` |
| `am_sync_success` | AM 推送成功 | am_sync 改 | `{local_silence_id, am_silence_id, name}` |
| `am_sync_failed` | AM 推送失败 | am_sync 改 | `{local_silence_id, name, error}` |
| `dedup_lock_acquired` | 锁获取成功 | dedup_lock 改 | `{fingerprint, source: redis\|sql}` |
| `dedup_lock_skipped` | 锁被其他实例占用 | dedup_lock 改 | `{fingerprint}` |
| `dedup_lock_fallback` | Redis 不可用降级 | dedup_lock 改 | `{fingerprint, error}` |

**写入频率评估**:
- 通道: 每天告警量 × 通道数 (假设 100 告警 × 4 通道 = 400 条/天)
- AM 同步: 静默规则创建/删除频率 (假设 10/天)
- 锁: 同告警量 (100/天) — 但可能合并到已有 alert_fired 中
- **决策**: 锁可观测用"轻量模式", 仅记录降级 (异常情况), 命中走内存计数

---

## 4. 关键查询可行性验证

### 4.1 告警趋势

```sql
SELECT
  DATE_FORMAT(created_at, '%Y-%m-%d %H:00:00') as bucket,
  action_type,  -- alert_fired / alert_resolved
  severity,     -- 需从 detail JSON 提取
  count(*)
FROM operation_logs
WHERE action_type IN ('alert_fired', 'alert_resolved')
  AND created_at BETWEEN ? AND ?
GROUP BY bucket, action_type
```

**风险**: severity 在 detail JSON 中, MySQL 5.7 不支持 JSON_EXTRACT (需 5.7.13+); PostgreSQL/SQLite 用 `detail->>'severity'`。

**缓解**: 限制数据库版本 (PostgreSQL 13+ 或 MySQL 8+); 应用层 Python parse detail (慢)。

### 4.2 响应时长

```sql
SELECT
  fired.id as fired_id,
  fired.created_at as fired_at,
  ack.created_at as ack_at,
  TIMESTAMPDIFF(SECOND, fired.created_at, ack.created_at) as response_seconds
FROM operation_logs fired
LEFT JOIN operation_logs ack
  ON ack.target_id = fired.id
  AND ack.action_type = 'alert_acknowledged'
WHERE fired.action_type = 'alert_fired'
  AND fired.created_at BETWEEN ? AND ?
  AND ack.id IS NOT NULL
```

**风险**: 自我 JOIN 性能; 需 (target_id, action_type) 索引。

### 4.3 升级率

```sql
SELECT
  count(DISTINCT fired.id) as total_fired,
  count(DISTINCT esc.id) as total_escalated
FROM operation_logs fired
LEFT JOIN operation_logs esc
  ON esc.target_id = fired.id
  AND esc.action_type = 'alert_escalated'
WHERE fired.action_type = 'alert_fired'
  AND fired.created_at BETWEEN ? AND ?
```

**OK**: 数据源完整, 简单 JOIN。

### 4.4 通道成功率 (改 notifier 后)

```sql
SELECT
  JSON_EXTRACT(detail, '$.channel') as channel,
  count(CASE WHEN action_type = 'alert_channel_sent' THEN 1 END) as success,
  count(CASE WHEN action_type = 'alert_channel_failed' THEN 1 END) as failed
FROM operation_logs
WHERE action_type IN ('alert_channel_sent', 'alert_channel_failed')
  AND created_at BETWEEN ? AND ?
GROUP BY channel
```

**OK**: 标准 SQL 模式。

---

## 5. 现有代码改动点

### 5.1 notifier.py 改 (v1.36 必须)

- 文件: [backend/app/monitoring/notifier.py](file:///e:/code/bysj/backend/app/monitoring/notifier.py)
- 位置: `CompositeNotifier.send()` (line 346)
- 改动:
  1. send() 接收 db session (或回调用 db 注入)
  2. 每次 send 成功 → 写 OperationLog `alert_channel_sent`
  3. 每次 send 失败 → 写 OperationLog `alert_channel_failed`
  4. detail 包含 channel 名, 告警 rule/severity/fingerprint, 耗时

**复杂度**: 中 (需重构 send 接口签名)

### 5.2 am_sync.py 改 (v1.36 必须)

- 文件: [backend/app/monitoring/am_sync.py](file:///e:/code/bysj/backend/app/monitoring/am_sync.py)
- 位置: `push_silence()` / `pull_silences()` / `delete_silence()`
- 改动:
  1. 每个函数增加可选参数 `db: AsyncSession | None = None`
  2. 成功/失败时写 OperationLog
  3. 调用方传 db (silences.py 已有 db)

**复杂度**: 低

### 5.3 dedup_lock.py 改 (v1.36 必须)

- 文件: [backend/app/monitoring/dedup_lock.py](file:///e:/code/bysj/backend/app/monitoring/dedup_lock.py)
- 位置: `try_acquire_lock()`
- 改动:
  1. 增加内存计数器 (`_stats: dict[str, int]`)
  2. Redis 不可用 → 计数 `fallback`
  3. 锁被占用 → 计数 `skipped`
  4. 锁成功 → 不计数 (避免高频写 DB)
  5. 周期任务 (60s) flush 到 OperationLog

**复杂度**: 中 (需新增 flush 任务)

### 5.4 alerts.py 现有逻辑 (无需改)

- 已有: alert_fired / alert_resolved / alert_silenced / alert_acknowledged 全部已写
- 已有: archive 查询 API 可复用模式
- ✅ 直接基于现有路径加 endpoint

---

## 6. 索引建议 (v1.36 应新增)

```sql
-- 用于趋势 / 升级率查询
CREATE INDEX idx_oplog_action_created
  ON operation_logs (action_type, created_at);

-- 用于响应时长 JOIN
CREATE INDEX idx_oplog_target_action
  ON operation_logs (target_id, action_type);

-- 用于 AM 同步查询 (新增 action_type 后)
-- 已有 idx_oplog_action_created 覆盖
```

**实现**: 在 `app/models/admin.py::OperationLog.__table_args__` 中声明, 启动时自动创建。

---

## 7. 关键发现总结

| # | 发现 | 影响 |
|:--|:---|:---|
| **F1** | 现有 5 个 action_type 可直接复用 | 趋势/升级率/静默命中 3 个端点 0 数据改动 |
| **F2** | 通道/AM/锁 需新增 7 个 action_type | 需改 notifier / am_sync / dedup_lock |
| **F3** | OperationLog 缺复合索引 | 需新增 `idx_oplog_action_created` |
| **F4** | 响应时长需 self-JOIN | 性能风险, 需索引 + 可能 cache |
| **F5** | detail 存 JSON 字符串 | severity 提取需 JSON_EXTRACT (DB 版本依赖) |
| **F6** | notifier.send() 不知 db session | 需重构接口签名 (中等风险) |
| **F7** | dedup_lock 是高频路径 | 仅记录降级, 避免 DB 写入放大 |

---

## 8. 下一步 (Step 4: 推演)

基于以上调研:
- 已有数据源: 趋势 / 升级率 / 静默命中 (P0 简单)
- 需改模块: notifier / am_sync / dedup_lock (P0 中等)
- 性能风险: 响应时长 (P1, 需索引 + 缓存)
- 跨实例: dedup_lock 需内存+flush 模式

进入 Step 4 推演: 端点详细规范 / 接口签名 / 数据流 / 失败降级。
