# 01d-critique-r2 — v1.36-alert-observability (Round 2 / Step 2)

> **目的**: 对 Round 2 修订后的需求进行二次自查, 验证 Round 1 的 5 个缺口是否全部解决。
> **关联**: [./01-requirements.md](./01-requirements.md) (Round 2 修订版)

---

## 1. Round 1 缺口修复验证

| 缺口 | 描述 | Round 2 状态 |
|:---|:---|:---:|
| **G1** | 通道发送 OperationLog 缺失 | ✅ 3.1 节明确 `alert_channel_sent` / `alert_channel_failed` |
| **G2** | AM 同步 OperationLog 缺失 | ✅ 3.2 节明确 `am_sync_success` / `am_sync_failed` |
| **G3** | 锁可观测持久化 | ✅ 3.3 节明确 `dedup_lock_skipped` / `dedup_lock_fallback` + flush 机制 |
| **G4** | 响应时长无直接字段 | ✅ 2.2 节明确 `fired_at` 与 `acknowledged_at` 配对方法 |
| **G5** | 索引缺失 | ✅ 3.4 节明确 2 个复合索引 |

**结论**: 5/5 缺口全部解决 ✅

---

## 2. 新增自查维度 (Round 2)

### 2.1 数据完整性

- ✅ 7 个端点都明确了数据源
- ✅ 7 个新 action_type 全部明确字段
- ✅ detail JSON 字段都有说明
- ⚠️ **未说明**: action_type 写入失败的降级 (写入失败时, 观测数据丢失, 是否告警?)

### 2.2 性能

- ✅ 7 端点都有性能预算
- ✅ 复合索引明确
- ✅ LIMIT 10000 兜底
- ⚠️ **未细化**: 趋势 bucket=7d (1 row 7天) vs bucket=1h (168 rows) 的索引选择性
- ⚠️ **未量化**: self-JOIN 在 100K 行 OperationLog 上的预估耗时

### 2.3 安全性

- ✅ admin 权限
- ✅ max 30 天窗口限制
- ✅ Redis 5min cache 防刷
- ⚠️ **未说明**: 多用户并发查询的隔离 (同一 cache key 可能命中旧数据)

### 2.4 可观测性的可观测性

- ❌ **缺失**: observability API 自身失败时如何排查?
  - 应记录 `obs_api_error` action_type
  - 或返回详细错误信息 (含 SQL)

### 2.5 运维友好

- ✅ 全部 admin 权限 (避免泄露)
- ⚠️ **未明确**: 返回数据是否包含 `instance_id` (多实例部署时)
- ⚠️ **未明确**: 缓存命中时是否带 `cached: true` 标记

### 2.6 测试覆盖

- ✅ 单元测试 + 集成测试 + 性能测试 全列
- ⚠️ **未明确**: 性能测试的具体断言 (如 < 500ms 在 100K 行表上)

---

## 3. 关键风险 (Round 2 新增)

| 风险 | 严重性 | 缓解 |
|:---|:---:|:---|
| notifier 改造引入额外 DB 写入, 写失败不影响通知, 但观测数据丢失 | 中 | 异步写, 失败仅日志 |
| 锁 flush 失败导致内存累积 | 中 | flush 失败不清零, 下次重试 |
| 复合索引在大表上 ALTER 慢 | 高 | 启动时 check first, 必要时警告 |
| 响应时长 self-JOIN 性能差 | 中 | LIMIT 10000 + 索引 |
| observability API 自身失败无观测 | 低 | 返回错误详情 |
| 多实例锁统计无法聚合 | 中 | 接受 (P1 改进) |

---

## 4. 与 v1.35 的兼容性

- ✅ 现有 OperationLog action_type 全部保留
- ✅ 现有端点 (alerts / silences / archive) 不改动
- ✅ 现有告警发送路径不变
- ⚠️ **新依赖**: dedup_lock 改造会改动高频路径, 需充分回归

---

## 5. 优先级再评估

### P0 必做 (不变)
- 7 个端点全部
- 4 个数据源改造
- 2 个复合索引

### P1 (新增建议)
- 缓存命中标记
- instance_id 返回
- observability 自身失败记录

### P2 (后续)
- 跨进程锁聚合
- 预聚合每日 stats 表
- 大屏可视化

---

## 6. 自查结论

- ✅ 5/5 Round 1 缺口已解决
- ✅ 总体设计清晰, 7 端点 + 4 改造 + 2 索引
- ⚠️ 4 个新发现 (P1), 可在 Round 3 决定是否纳入
- ❌ 缺少架构细节 (e.g. cache 工具函数、聚合查询 helper)

**下一步**: Step 3 (Research) - 深入调研 4 个新增 P1 建议的可行性, 决定是否进入 Round 3 终稿。
