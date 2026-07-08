# State Schema

## Phase enum (only allowed values in STATE.md)

`PHASE_0_INIT | PHASE_1_SECURITY | PHASE_2_UX | PHASE_3_WORKBENCH | PHASE_4_DATA_PILOT | PHASE_5_VERIFICATION | PHASE_6_DELIVERY | CLOSED`

Rule: only one current phase at a time; multiple tasks may run in parallel within a phase; cross-phase tasks are not dispatched unless `decisions.md` waives.

## Task state transition table

| Current state | Allowed transitions | Trigger command |
|---|---|---|
| New | Confirmed / 阻塞 | 派发任务 / 标记阻塞 |
| Confirmed | Fixing / 阻塞 | 派发任务 / 标记阻塞 |
| Fixing | Pending Review / 阻塞 | 提交验收 / 标记阻塞 |
| Pending Review | Closed / Fixing / 阻塞 | 关闭任务 / 验收退回 / 标记阻塞 |
| Closed | (no rollback) | — (regression creates a new task) |
| 阻塞 | Confirmed / Fixing | 解除阻塞 |

Rules:
- `Closed` cannot be reopened; a regression creates a new task.
- P0 regression is inserted at the front of the current phase's queue.

## Task fields (backlog.md entries)

Base fields (from `md/12.md` §9.1): ID / 标题 / 类型 / 优先级 / 阶段 / 负责人 / 状态 / 计划开始 / 计划完成 / 实际完成 / 验收标准 / 关联测试 / 风险 / 备注.

Additional fields:

| Field | Description |
|---|---|
| 横向排查范围 | same-type code/page/API scope to check |
| 横向排查结论 | whether same-type issues found |
| 回归用例 | test(s) the fix must bind to |
| 验收证据 | test command / report path / screenshot / log |
| 审计忽略 | only marks STATE/backlog/metrics/decisions flow-state docs as excluded from code audit; **must not skip code/security/function/test review** |
| 阻塞信息 | blocker reason / dependent task / unblock condition |

## Task entry example

```markdown
## DWS-P0-001 危机文本未统一触发危机对话框
- 类型：安全/UX  优先级：P0  状态：Fixing
- 阶段：PHASE_1_SECURITY  工作包：WP1  负责人：backend/frontend
- 计划完成：2026-07-15
- 验收标准：文本/结构化评估均触发统一危机提示；E2E 危机链路通过
- 关联测试：frontend/tests/e2e/specs/risk-assessment.spec.ts; backend/tests/unit/test_crisis_detector.py
- 横向排查范围：UserRiskPage.vue / crisis_detector.py / api/v1/model_predict/*
- 横向排查结论：待补充
- 回归用例：待补充  验收证据：待补充
- 阻塞信息：无
- 审计忽略：否
```
