# RALPH_STATE — v1.35-multi-instance-alerting

> **状态**: 🟢 **DELIVERED**
> **最后更新**: 2026-06-03
> **基础**: v1.34-alerting-complete

---

## 1. 迭代总览

| 项 | 状态 |
|:---|:---|
| **迭代** | v1.35-multi-instance-alerting |
| **类型** | Multi-Instance / Archival / AM-Sync |
| **核心目标** | 跨实例去重 + 真实归档 + AM 双向同步 |
| **状态** | 🟢 DELIVERED |

---

## 2. 阶段进度

| 阶段 | 任务 | 状态 |
|:---|:---:|:---:|
| Phase 1: 跨实例去重 (Redis 锁) | 2/2 | ✅ |
| Phase 2: AlertArchive 模型 | 1/1 | ✅ |
| Phase 3: 实际归档逻辑 + 查询 API | 2/2 | ✅ |
| Phase 4: AlertManager 双向同步 | 3/3 | ✅ |
| Phase 5: 回归测试 | 1/1 | ✅ |

**总进度**: 5/5 phases (100%)

---

## 3. 目标达成

| 目标 | v1.34 | v1.35 |
|:---|:---:|:---:|
| 跨实例去重 | 仅 SQL 查询 | **Redis SETNX 锁 + 降级** ✅ |
| 告警归档 | 仅记录候选 | **真实 insert + delete** ✅ |
| 静默规则同步 | 单向 (内部) | **AlertManager 双向同步** ✅ |
| 归档只读查询 API | 无 | **GET /api/v1/alerts/archive** ✅ |
| Redis 不可用降级 | 无 | **SQL 回退 + 警告日志** ✅ |
| AM 同步失败降级 | 无 | **本地静默生效 + 失败记录** ✅ |

---

## 4. 核心指标

- **v1.35 新增测试**: 详见 05-test-plan.md (全过 100%)
  - test_dedup_lock: 4/4 ✅
  - test_dedup (集成): 3/3 ✅
  - test_am_sync: 7/7 ✅
  - test_alert_archive_api: 4/4 ✅
  - test_alert_tasks (回归): 9/9 ✅
  - test_silences_api (回归): 8/8 ✅
  - test_dedup (回归): 7/7 ✅
  - test_alerts_webhook (回归): 11/11 ✅
  - test_silence (回归): 11/11 ✅
  - test_escalation (回归): 全过 ✅
  - test_metrics / test_tracing / test_notifier (回归): 全过 ✅

- **已知环境限制**: Windows 全量 pytest 偶发 exit -1073741510, 通过分批运行验证

---

## 5. 新增交付物

| 类型 | 路径 |
|:---|:---|
| 跨实例锁模块 | [backend/app/monitoring/dedup_lock.py](../../backend/app/monitoring/dedup_lock.py) |
| AM 同步模块 | [backend/app/monitoring/am_sync.py](../../backend/app/monitoring/am_sync.py) |
| AlertArchive 模型 | [backend/app/models/admin.py](../../backend/app/models/admin.py) |
| 归档查询 API | [backend/app/api/v1/alerts.py](../../backend/app/api/v1/alerts.py) |
| 静默创建 AM 同步 | [backend/app/api/v1/silences.py](../../backend/app/api/v1/silences.py) |
| 实际归档逻辑 | [backend/app/tasks/alerts.py](../../backend/app/tasks/alerts.py) |
| dedup 集成锁 | [backend/app/monitoring/dedup.py](../../backend/app/monitoring/dedup.py) |
| 锁测试 | [backend/tests/test_dedup_lock.py](../../backend/tests/test_dedup_lock.py) |
| AM 同步测试 | [backend/tests/test_am_sync.py](../../backend/tests/test_am_sync.py) |
| 归档 API 测试 | [backend/tests/api/test_alert_archive_api.py](../../backend/tests/api/test_alert_archive_api.py) |

---

## 6. 关键决策

| # | 决策 | 理由 |
|:--|:---|:---|
| **D1** | Redis 锁失败时返回 True (降级到 SQL) | 锁服务不可用时不应阻塞告警 |
| **D2** | Redis 锁 TTL = 5 分钟 (与 dedup 窗口一致) | 锁与去重窗口同步, 避免锁提前失效 |
| **D3** | AlertArchive 用单独表 (非 OperationLog 标记) | 只读表隔离, 不影响 OperationLog 写入性能 |
| **D4** | 归档使用事务 (insert + delete 原子性) | 失败回滚避免数据丢失或重复 |
| **D5** | AM 同步失败不阻塞本地静默 | 静默规则本地立即生效, 同步失败仅记录 |
| **D6** | AM 调用超时 2s | 避免 webhook 阻塞, 异步重试可后续优化 |
| **D7** | 归档单批 1000 条 | 防止大事务导致 DB 锁等待 |

---

## 7. 关联文档

| 文档 | 路径 |
|:---|:---|
| 需求 | [./01-requirements.md](./01-requirements.md) |
| 任务 | [./04-ralph-tasks.md](./04-ralph-tasks.md) |
| 测试 | [./05-test-plan.md](./05-test-plan.md) |
| 交付 | [./DELIVERY_REPORT.md](./DELIVERY_REPORT.md) |
| 下一迭代 | [./NEXT_STEPS.md](./NEXT_STEPS.md) |
| 上一迭代 | [../v1.34-alerting-complete/RALPH_STATE.md](../v1.34-alerting-complete/RALPH_STATE.md) |

---

## 8. 下一迭代候选

- **v1.36 (P0 推荐)**: 告警可视化 + 趋势统计 + 通道成功率
- **v1.36 (P1)**: OpenTelemetry SDK 升级 + Jaeger 部署 + Grafana trace 面板
- **v1.36 (P1)**: MLflow 集成 + 模型漂移自动检测
- **v1.36 (P2)**: AM v2 协议 (silence_id 映射) + AM API 鉴权 (bearer token)
- **v1.36 (P2)**: 归档冷存储 (S3) + 跨实例告警合并

---

> **迭代状态**: 🟢 **DELIVERED**
> **多实例告警生产就绪, 真实归档 + AM 双向同步上线**
