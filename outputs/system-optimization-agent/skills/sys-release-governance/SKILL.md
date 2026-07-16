---
name: sys-release-governance
description: >-
  This skill should be used when governing releases and changes — "灰度发布",
  "金丝雀发布", "回滚", "发布评审", "变更审批". It implements §4.3.4 and §9
  of the optimization plan and is mandatory for any online change.
agent_created: true
---

# sys-release-governance

## 用途
建立安全可控的发布与变更治理：灰度/金丝雀、回滚、评审，降低发布风险。

## 何时使用
- 任何上线变更前（WF-1~WF-3 的线上改动）。
- 用户要求「灰度发布」「加回滚」「发布评审」。

## 执行流程
1. **发布评审**：确认目标、范围、灰度与回滚方案、监控指标。
2. **灰度/金丝雀**：小流量验证核心链路，观察 KPI 无异常再放大。
3. **特性开关**：用 feature flag 控制新逻辑，异常可秒级关闭。
4. **回滚预案**：预置回滚（代码 + DB 迁移向后兼容）；演练回滚路径。
5. **变更窗口**：与业务方确认窗口期；核心链路双写/双跑或小流量验证。
6. **上线观察**：持续监控关键 KPI（接入 `sys-observability`）。
7. **复盘**：记录发布与回滚，沉淀到 Runbook。

## 工具与脚本
- CI/CD：GitHub Actions（origin `github.com/kajykk/bysj.git`）。
- 开关：`Unleash` / 自实现 feature flag。
- DB 迁移：Alembic，必须向后兼容（配合 `sys-db-optimizer`）。

## 验收与 KPI（§3 / §9）
- 灰度 + 回滚 100% 覆盖线上变更，发布风险显著下降。
- 发布与回滚记录完整，回滚方案可演练。

## 与本工程栈的对应
- 后端 `Dockerfile` / `docker-compose.yml`；前端 `Dockerfile`、Vite 产物。
- Alembic 迁移须向后兼容，避免回滚卡死。

## 注意事项
- 优化引入的缓存一致性、异步重复消费、性能回退风险，必须先在测试环境验证 + 灰度 + 预置回滚。
- DB 迁移不可破坏旧版本兼容，否则无法回滚。
