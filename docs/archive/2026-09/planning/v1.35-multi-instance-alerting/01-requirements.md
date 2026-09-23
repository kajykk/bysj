# 01-requirements — v1.35-multi-instance-alerting

> **迭代**: v1.35-multi-instance-alerting
> **基础**: v1.34-alerting-complete (DELIVERED)
> **创建**: 2026-06-03
> **类型**: Multi-Instance / Archival / AM-Sync

---

## 1. 目标

完成告警系统在生产多实例环境的可用性 + 数据治理:

| 维度 | v1.34 | v1.35 目标 |
|:---|:---:|:---:|
| 跨实例去重 | 仅 SQL 查询 | **Redis SETNX 锁** ✅ |
| 告警归档 | 仅记录候选 | **真实移动到 AlertArchive** ✅ |
| 静默同步 | 单向 (内部) | **AlertManager 双向同步** ✅ |
| 归档查询 | 无 | **只读 API** ✅ |
| 锁降级 | 无 | **Redis 不可用 → SQL 回退** ✅ |

---

## 2. 范围

### 2.1 跨实例去重 (P0)

- 路径: `app/monitoring/dedup_lock.py`
- 机制:
  - Redis `SETNX alert:dedup:<fingerprint> <ts>` 锁
  - TTL = 5 分钟 (与 dedup 窗口一致)
  - 获取失败 -> 跳过通知 (其他实例已发送)
  - 锁失败 (Redis down) -> 降级到 SQL 查询
- 集成: `dedup.py::should_send()` 优先 Redis

### 2.2 AlertArchive 模型 + 真实归档 (P0)

- 新模型: `AlertArchive`
- 路径: `app/models/admin.py`
- 字段:
  - `id`, `original_id`, `rule`, `severity`, `status`, `message`
  - `labels`, `annotations`, `fingerprint`
  - `original_created_at`, `archived_at`
  - `detail` (完整 JSON)
- 任务: `_archive_impl()` 改为真实 insert + delete
- 单次批量: 1000 条/批
- 删除: 仅删除 `alert_fired` / `alert_resolved`

### 2.3 静默规则 AlertManager 同步 (P1)

- 路径: `app/monitoring/am_sync.py`
- 机制:
  - 创建静默时, 调用 AlertManager API 创建对应 silence
  - AlertManager 取消 silence 时, webhook 通知我们同步
  - 配置: `ALERTMANAGER_URL` 环境变量
- 失败降级: 静默规则已创建, 仅记录同步失败

### 2.4 归档查询 API (P1)

- 端点: `GET /api/v1/alerts/archive`
- 路径: `app/api/v1/alerts.py` (新增)
- 行为: admin 可查询归档告警
- 过滤: rule, severity, status, start_time, end_time

---

## 3. 非功能需求

- **锁 TTL 安全**: 5 分钟自动过期, 不会死锁
- **归档幂等**: 同 alert_id 重复归档不应重复插入
- **AM 同步失败可恢复**: 同步失败时本地静默仍生效
- **零阻塞**: Redis/AM 调用超时不超过 2s

---

## 4. 不在范围

- AM v2 协议 (silence_id 映射) — 后续
- AM API 鉴权 (bearer token) — 后续
- 归档冷存储 (S3) — 后续
- 跨实例告警合并 — 后续

---

## 5. 关联文档

| 文档 | 路径 |
|:---|:---|
| 上一迭代 | [../v1.34-alerting-complete/RALPH_STATE.md](../v1.34-alerting-complete/RALPH_STATE.md) |
| 告警 v1.34 | [../v1.34-alerting-complete/DELIVERY_REPORT.md](../v1.34-alerting-complete/DELIVERY_REPORT.md) |
