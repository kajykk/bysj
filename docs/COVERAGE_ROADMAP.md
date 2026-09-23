# 测试覆盖率爬坡路线图（P2）— SSOT：本文件

> 实测基线（CI Coverage #316，2026-09-24）：后端全量 **83.31%**，
> 前端门禁 50/50/40/50（`npm run test:coverage` 本地绿）。
> 说明：pr-quality-gates.yml 无独立后端覆盖率门禁（CI-AUDIT-04 已委托给
> coverage.yml），下表“PR 门禁”列为远期目标，当前以后端全量列为准。

## 阈值表（CI 工作流与 pytest/vitest 配置必须与本表一致）

| 阶段 | 后端全量（coverage.yml） | PR 门禁（远期） | 前端（vitest） | 升级条件 |
|---|---|---|---|---|
| T0（已过） | 40% | — | 50/50/40/50 | — |
| T1（已过） | 50% | — | 55/55/45/55 | 实测 83.31% 直接达标 |
| T2（当前） | 60% | 65% | 60/60/50/60 | CI 全绿即升档（2026-09-24） |
| T3 | 70% | 75% | 70/70/60/70 | 全量连续 3 次绿 + 无新增 `--deselect` |
| T4（目标） | 85% | 85% | 80/80/70/80 | 同上 + mypy/ruff-format 已转阻断 |

## 规则

1. 每次只升一档，升级 PR 必须贴出覆盖率前后对比与新增测试清单。
2. 禁止用 `--deselect`/空断言/`# pragma: no cover` 滥用来凑数（已有债务：mypy/ruff-format 非阻断，先转阻断再爬坡）。
3. 测试组织同步治理：`backend/tests/` 根 198 文件按模块/类型迁入
   `tests/unit|integration|contract|degradation|performance`，新测试必须落对应目录。
