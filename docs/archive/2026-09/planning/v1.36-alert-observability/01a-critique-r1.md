# 01a-critique — v1.36-alert-observability (Round 1 / Step 2)

> **目的**: 对 v1.36 需求草稿进行严格自查, 识别缺口/假设/风险。
> **关联**: [./01-requirements.md](./01-requirements.md) (草稿)

---

## 1. 自查维度

### 1.1 数据源可获得性

| 指标 | 假设数据源 | 实际可用? | 风险 |
|:---|:---|:---:|:---|
| 告警趋势 | OperationLog (alert_fired/resolved) | ✅ 已存在 | 低 |
| 响应时长 | OperationLog fired + acknowledged 配对 | ⚠️ 待验证 | **中** |
| 升级率 | OperationLog (alert_escalated) | ⚠️ 待验证 | **中** |
| 通道成功 | OperationLog (alert_channel_sent/failed) | ❌ **不存在** | **高** |
| 静默命中 | OperationLog (alert_silenced) | ✅ 已存在 | 低 |
| AM 同步 | OperationLog (am_sync_success/failed) | ❌ **不存在** | **高** |
| 锁可观测 | 内存计数器 + 周期 dump | ❌ **未设计** | **高** |

**结论**: 3 个指标需新增 OperationLog action_type 记录, 1 个需设计持久化机制。

### 1.2 端点设计

- ✅ 7 个端点都遵循 RESTful 规范
- ✅ admin 权限统一要求
- ⚠️ 端点命名 `observability/trend` 略长, 可考虑 `metrics/*` 简写
- ⚠️ bucket 参数 1h/6h/24h/7d 需注意: 7d 下数据量可能 > 100K, 需分页

### 1.3 性能

- ⚠️ 7 天窗口 + 1h bucket = 168 个时间片, 1 次查询
- ⚠️ 多维 group by (severity + rule) 在大数据量下可能慢
- ❌ 缺少: 索引建议 (action_type + created_at 联合索引?)

### 1.4 一致性与正确性

- ❌ **响应时长计算**: OperationLog 没有 `acknowledged_at` 字段, 需用 created_at 近似
- ❌ **acknowledged vs resolved 区别**: 已在 v1.33 escalation 中定义, 需对齐
- ⚠️ **跨实例统计**: 多实例时 OperationLog 分散写入, 需全局聚合

### 1.5 安全性

- ✅ admin 权限要求
- ⚠️ 时间窗口过大可能 DOS (需 max window 限制)
- ❌ 缺少: 缓存防刷机制细节 (Redis 5min cache)

### 1.6 可观测性的可观测性

- ⚠️ 可观测性 API 自身的 metrics 未设计
- ⚠️ 查询失败时无法自检 (套娃问题)

---

## 2. 关键缺口

### 缺口 G1: 通道发送 OperationLog 缺失

- 现状: notifier 发送成功/失败未持久化
- 影响: 通道成功率指标无法实现
- 解决: 需在 v1.36 同步修改 notifier, 记录 `alert_channel_sent` / `alert_channel_failed`

### 缺口 G2: AM 同步 OperationLog 缺失

- 现状: am_sync 失败仅日志, 未持久化
- 影响: AM 同步成功率无法统计
- 解决: 需在 v1.36 同步修改 am_sync, 记录 `am_sync_success` / `am_sync_failed`

### 缺口 G3: 锁可观测持久化

- 现状: dedup_lock 仅内存持有
- 影响: 进程重启丢失, 跨进程无法聚合
- 解决: 需设计:
  - 内存计数器 (per-process)
  - 周期 flush 到 OperationLog (30s/60s)
  - 进程启动时初始化
  - 跨进程聚合 API

### 缺口 G4: 响应时长无直接字段

- 现状: OperationLog 无 acknowledged_at
- 影响: 只能查 fired 与 acknowledged 配对, 但 acknowledged 是单独 action_type
- 解决:
  - 接受"配对查询"方案
  - 或新增 AlertEvent 表记录生命周期 (P2)

### 缺口 G5: 索引缺失

- 现状: OperationLog 在 (action_type, created_at) 上可能无最优索引
- 影响: 时间窗口查询慢
- 解决: 启动时创建复合索引 (action_type, created_at, target_type)

---

## 3. 优先级建议

| 优先级 | 项 | 理由 |
|:---|:---|:---|
| **P0** | 告警趋势 API | 数据源完整, 立即可做 |
| **P0** | 静默命中率 API | 数据源完整, 立即可做 |
| **P0** | 通道成功率 (含 G1) | 需先改 notifier |
| **P0** | AM 同步可观测 (含 G2) | 需先改 am_sync |
| **P0** | 锁可观测 (含 G3) | 需先设计持久化 |
| **P1** | 响应时长 (含 G4) | 需配对查询 |
| **P1** | 升级率 | 数据源可能存在, 需验证 |
| **P2** | 缓存防刷 | 安全优化 |

---

## 4. 自查结论

- ✅ 总体目标清晰, 7 个指标覆盖运维视角
- ⚠️ 需补充 5 个缺口 (G1-G5)
- ⚠️ 需在 v1.36 同步修改 notifier / am_sync / dedup_lock
- ❌ 缺少架构文档 (`02-architecture.md`)
- ❌ 缺少任务列表 (`04-ralph-tasks.md`)
- ❌ 缺少测试计划 (`05-test-plan.md`)

**下一步**: 进入 Step 3 (Research) - 调研现有 OperationLog 表结构, 验证假设。
