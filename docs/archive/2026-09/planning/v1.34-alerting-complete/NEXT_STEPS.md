# NEXT_STEPS — v1.34 之后

> **下一步建议**: 基于 v1.34-alerting-complete (DELIVERED)

---

## 1. v1.35 推荐方向 (P0)

### 1.1 跨实例去重 (P0)

**目标**: 多 worker 部署时防 dedup 误抑制

- Redis SETNX 锁 (fingerprint 维度)
- 锁 TTL 5 分钟 (与 dedup 窗口一致)
- 失败降级到 SQL 查询
- 锁监控 + 清理

**预计工作量**: 1 天

### 1.2 AlertArchive 表迁移 (P0)

**目标**: 实际归档 90 天前告警

- DBA 协调创建 AlertArchive 表
- 修改 `_archive_impl()` 真实插入 + 删除
- 归档只读查询 API

**预计工作量**: 1 天 (依赖 DBA)

### 1.3 静默规则 AlertManager 同步 (P1)

**目标**: 与 AlertManager 双向同步 silences

- POST /api/v1/alerts/silences 同步到 AlertManager
- AlertManager webhook 接收 silence 事件
- 双向一致性校验

**预计工作量**: 2 天

---

## 2. v1.36 候选方向 (P1)

### 2.1 OpenTelemetry SDK 升级

- 完整 OTel instrumentation
- 部署 Jaeger 或 Tempo
- Grafana trace 面板
- 与现有 W3C trace 双向兼容

### 2.2 MLflow 集成

- 模型注册表
- 训练/部署追踪
- 模型血缘

### 2.3 告警可视化

- 告警趋势 (按 severity / rule)
- 平均响应时间 (fired → acknowledged)
- 升级率统计
- 通道成功率

---

## 3. 长期规划 (P2)

- **多租户告警**: 机构/学校级别路由
- **告警模板库**: 行业模板 (CPU / 业务指标)
- **AI 告警**: 异常检测自动产生
- **SLO/SLI**: 错误预算管理

---

## 4. 当前状态摘要

| 项 | 状态 |
|:---|:---|
| **当前迭代** | v1.34-alerting-complete (🟢 DELIVERED) |
| **v1.34 新增测试** | 46/46 (100%) |
| **总累计测试** | 129/129 (v1.32 + v1.33 + v1.34) |
| **生产可去重** | ✓ fingerprint 5min 抑制 |
| **生产可静默** | ✓ 4 端点 API + 维护期规则 |
| **生产可升级** | ✓ Celery 60s 自动 |
| **下一步行动** | 等待用户决策: v1.35 / v1.36 / 优化 |

---

> **下一步**: 询问用户方向 (v1.35 跨实例+归档 / v1.36 OTel / MLflow / 优化)
