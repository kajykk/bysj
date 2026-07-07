# dws-improvement-orchestrator Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers-subagent-driven-development or superpowers-executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Create the `dws-improvement-orchestrator` skill — a top-level state-machine orchestrator that drives the DWS 8-week improvement project lifecycle (phases 0-6), dispatches existing skills by work package, and maintains state artifacts.

**Architecture:** A Trae/Ralph-style project skill composed of a core `SKILL.md` (<500 lines) plus progressive-disclosure reference files (`dispatch-registry.md`, `gate-checks.md`, `state-schema.md`) and 6 runtime templates. The orchestrator does not implement code fixes; it manages phase transitions, task lifecycle, priority constraints, artifact consistency, and skill dispatch (instruct the agent to invoke skills via the Skill tool, with manual-mode fallback).

**Tech Stack:** Markdown skill documents; no code runtime. Verification is a document state-machine self-test protocol (no scripts in v1).

**Spec:** `docs/superpowers/specs/2026-07-08-dws-improvement-orchestrator-design.md`

## Global Constraints

- Skill location: `.trae/skills/dws-improvement-orchestrator/` only — no `.cursor/skills/` duplicate (avoid state drift).
- `SKILL.md` must be <500 lines; detailed matrices go in reference files.
- Skill names in `dispatch-registry.md` must match invokable skills (available via Skill tool) or on-disk skills under `.trae/skills/`; planned-but-absent skills marked `(planned)` with manual-mode fallback.
- Runtime artifacts live in `docs/planning/v1.40-improvement/` (separate from `docs/planning/v1.40-audit-beautify/` audit artifacts).
- `dispatch-registry.md`: skill dir = template source; runtime dir = snapshot; deviations recorded in `decisions.md`.
- Phase enum values are exactly: `PHASE_0_INIT | PHASE_1_SECURITY | PHASE_2_UX | PHASE_3_WORKBENCH | PHASE_4_DATA_PILOT | PHASE_5_VERIFICATION | PHASE_6_DELIVERY | CLOSED`.
- `pilot/` has exactly 7 fixed filenames: `event-tracking.md`, `interview-guide.md`, `questionnaire.md`, `privacy-notice.md`, `pilot-plan.md`, `deployment-guide.md`, `rollback-plan.md`.
- Hard constraints from project memory: P0→P1→P2 priority; P0 must clear before P1; phase transition only when closure conditions met; progress quantified X/Y; same-type issues cross-checked; permission/security/data-consistency issues need second-person review; fixes must include regression tests; state docs ignored during audits.

---

## File Structure

```
.trae/skills/dws-improvement-orchestrator/
├── SKILL.md                      # Core: goal, 9 commands, workflow, hard constraints, reference index
├── dispatch-registry.md          # WP1-WP12 → required/supporting skill + fallback + blocking
├── gate-checks.md                # M0-M6 automatic + manual gates + waiver rules
├── state-schema.md               # Task fields + state transition table + phase enum
└── templates/
    ├── STATE.template.md         # Runtime state: phase, task queue, metrics X/Y, manual_confirmations
    ├── backlog.template.md       # Task entries with horizontal-check fields
    ├── acceptance-criteria.template.md
    ├── metrics.template.md       # Metric definitions + current snapshot + gate metrics
    ├── phase-report.template.md
    └── decision-record.template.md  # DEC-YYYY-MM-DD-NNN with expiry/revisit
```

Runtime artifacts (created by `启动改进项目`, not in this plan):
```
docs/planning/v1.40-improvement/
├── STATE.md, backlog.md, acceptance-criteria.md, metrics.md, decisions.md, dispatch-registry.md
├── phases/phase-{0..6}.md
├── reports/
└── pilot/ (7 fixed files)
```

---

## Task 1: Skill scaffold + core SKILL.md

**Files:**
- Create: `.trae/skills/dws-improvement-orchestrator/SKILL.md`

**Interfaces:**
- Produces: the skill entry point; references `dispatch-registry.md`, `gate-checks.md`, `state-schema.md`, `templates/*` (created in later tasks).

- [ ] **Step 1: Create the skill directory and SKILL.md**

Write `.trae/skills/dws-improvement-orchestrator/SKILL.md` with this exact content:

```markdown
---
description: Orchestrates the 8-week DWS improvement lifecycle across phases 0-6. Use when the user says 启动改进项目, 继续改进, 查看进度, 确认阶段, 派发任务, 提交验收, 关闭任务, 标记阻塞, 解除阻塞, or asks to manage DWS improvement work. Maintains STATE.md/backlog/metrics, enforces P0→P1→P2 priority, regression tests, horizontal checks, gate checks, and dispatches existing skills by work package.
---

# dws-improvement-orchestrator

Top-level state-machine orchestrator for the DWS 8-week improvement project (per `md/12.md`). Drives phases 0-6, manages task lifecycle, enforces priority/gate/regression constraints, and dispatches existing skills by work package.

**职责边界**: 负责 阶段流转 / 任务生命周期 / 优先级约束 / 工件状态一致性 / 技能派发。**不直接实现代码修复、不替代专项技能。**

**触发兼容**: 本技能是 Trae/Ralph 风格项目技能，由用户显式触发。仅放 `.trae/skills/`，不创建 `.cursor/skills/` 副本。未来如需 Cursor 自动发现，再整体迁移。

## When to read which reference file

| 需要查阅 | 读取 |
|---|---|
| WP→技能映射、fallback、blocking | `dispatch-registry.md` |
| 阶段门禁 M0-M6（自动+人工）、豁免规则 | `gate-checks.md` |
| 任务字段、状态迁移表、阶段枚举 | `state-schema.md` |
| 初始化运行时工件 | `templates/STATE.template.md` 等 6 个模板 |

## 阶段状态枚举

`STATE.md` 仅允许: `PHASE_0_INIT | PHASE_1_SECURITY | PHASE_2_UX | PHASE_3_WORKBENCH | PHASE_4_DATA_PILOT | PHASE_5_VERIFICATION | PHASE_6_DELIVERY | CLOSED`

规则: 同一时间只能有一个当前阶段；阶段内可有多个任务并行；跨阶段任务默认不允许派发，除非 `decisions.md` 豁免。

## 操作命令（9 个）

| 命令 | 动作 |
|---|---|
| `启动改进项目` | 初始化工件，进入 `PHASE_0_INIT` |
| `继续改进` | 读取状态，派发下一个就绪任务 |
| `查看进度` | 输出阶段/任务/指标 X/Y/阻塞 |
| `确认阶段` | 校验门禁（自动+人工），通过则前进 |
| `派发任务` | 按 `dispatch-registry.md` 派发 |
| `提交验收` | 置 Pending Review，必须附回归用例 |
| `关闭任务` | 验收通过置 Closed，更新 metrics |
| `标记阻塞` | 记录阻塞原因/依赖任务/解除条件，跳过 |
| `解除阻塞` | 依赖满足后恢复状态，重新入队 |

### 命令规则

- **`启动改进项目` 初始化范围**: 创建或校验 `STATE.md`/`backlog.md`/`acceptance-criteria.md`/`metrics.md`/`decisions.md`/`dispatch-registry.md`/`phases/phase-0.md`…`phase-6.md`/`reports/`/`pilot/`。**若文件已存在，不覆盖**；先读取校验结构，缺失区块提示用户确认是否补齐。
- **`提交验收` 回归用例规则**: 缺少回归用例必须拒绝；若无法自动化，必须提供人工验证步骤与验收证据，并在 `decisions.md` 记录原因。
- **`查看进度` 最小输出格式**:
  ```
  - Current phase:
  - Open tasks:
  - P0/P1/P2 X/Y:
  - Blocked tasks:
  - Next recommended action:
  ```

## 工作流

1. 用户触发 `启动改进项目` → 校验/创建工件 → 写入 `STATE.md` (phase=`PHASE_0_INIT`) → 提示下一步。
2. `继续改进` → 读 `STATE.md` 的 `current_task_queue` → 选下一个 `Ready=true` 任务 → 按 `dispatch-registry.md` 派发。
3. **派发语义（提示式调度）**: 编排器不进行程序化技能调用，输出指令要求当前 Agent 执行:
   1. 若技能在可用技能注册表（Skill 工具可调用）中 → 指示 Agent 通过 Skill 工具调用该技能
   2. 否则若 `.trae/skills/<name>/SKILL.md` 存在 → 指示 Agent 读取并遵守该 SKILL.md
   3. 否则 → fallback `manual-mode`，在 `STATE.md` 记录缺失技能/受影响 WP/替代方式/blocking
4. 任务完成 → `提交验收`（校验回归用例）→ `关闭任务`（更新 metrics）。
5. 阶段末 → `确认阶段` → 按 `gate-checks.md` 校验: 自动项 → 人工确认已填写 → 证据存在 → 通过则前进，否则输出未满足清单。
6. 任务受阻 → `标记阻塞`；依赖满足 → `解除阻塞`。

## 任务状态迁移

见 `state-schema.md`。要点: `Closed` 不可重开（回归新建任务）；P0 回归插队到当前阶段最前。

## 阻塞与门禁关系

当任务阻塞且 `blocking=true` 且属于当前阶段门禁路径时，阶段不能确认通过；只有 `blocking=false` 或 `decisions.md` 有人工豁免时才允许继续。

## 硬约束

- 修复按 P0→P1→P2 优先级；P0 必须在 P1 前修复。
- 阶段流转仅在关闭条件满足时允许。
- 进度以 X/Y 量化（口径见运行时 `metrics.md`）。
- 同类型问题派发前强制横向排查，记录排查范围与结论。
- 权限/安全/数据一致性问题需第二人复核。
- 修复提交须附回归用例。
- 所有状态文档（STATE/backlog/metrics/decisions）在代码审计时显式忽略（任务字段 `审计忽略` 仅排除流程状态文档，不得跳过代码/安全/功能/测试审查）。
- 不可豁免门禁: P0 open count==0 (PHASE_1_SECURITY→PHASE_2_UX 及之后); 危机链路通过率==100% (PHASE_1_SECURITY→PHASE_2_UX); 核心 E2E 通过 (PHASE_6_DELIVERY 前); 缺失 STATE/backlog/acceptance-criteria 不可豁免。

## 自测协议

见 `gate-checks.md` 末尾的 Self-test protocol。第一版用文档状态机测试，不引入脚本。
```

- [ ] **Step 2: Verify line count is under 500**

Run: `powershell -Command "(Get-Content .trae/skills/dws-improvement-orchestrator/SKILL.md | Measure-Object -Line).Lines"`
Expected: a number < 500 (the content above is ~110 lines).

- [ ] **Step 3: Commit**

```bash
git add .trae/skills/dws-improvement-orchestrator/SKILL.md
git commit -m "feat(orchestrator): add dws-improvement-orchestrator SKILL.md core"
```

---

## Task 2: dispatch-registry.md

**Files:**
- Create: `.trae/skills/dws-improvement-orchestrator/dispatch-registry.md`

**Interfaces:**
- Consumes: WP→skill mapping from spec §4.2.
- Produces: the dispatch table referenced by `派发任务` and `继续改进`.

- [ ] **Step 1: Write dispatch-registry.md**

```markdown
# Dispatch Registry

Skill names must match invokable skills (available via Skill tool) or on-disk skills under `.trae/skills/`. Before dispatch, verify the skill is invokable; if not, mark it with `(planned)` and fallback to `manual-mode`.

## Source of truth

- `.trae/skills/dws-improvement-orchestrator/dispatch-registry.md` (this file) = **template source**
- `docs/planning/v1.40-improvement/dispatch-registry.md` = **runtime snapshot**
- `启动改进项目` copies this file to the runtime snapshot; later project-specific adjustments use the runtime snapshot as authority, with deviations recorded in `decisions.md`.

## WP → Skill mapping

| WP | Required skill | Conditional supporting skill | fallback | blocking |
|---|---|---|---|---|
| WP1 危机链路 (T1-1~T1-3) | remediation-orchestrator | sysopt-security | manual-mode | true (M1) |
| WP2 角色边界 (T1-4~T1-5) | sysopt-maintainability | ralph-task-executor | manual-mode | true (M1) |
| WP3 安全一致性 (T1-6~T1-7) | sysopt-security | sysopt-stability | manual-mode | true (M1) |
| WP4 评估流程 (T2-1~T2-3) | ralph-web-routine | superpowers-test-driven-development, design-taste-frontend | manual-mode | true (M2) |
| WP5 历史/内容/干预 (T2-4~T2-6) | ralph-web-routine | superpowers-test-driven-development | manual-mode | true (M2) |
| WP6 交互一致性 (T2-7) | sysopt-maintainability | superpowers-test-driven-development | manual-mode | true (M2) |
| WP7 咨询师工作台 (T3-1~T3-2) | ralph-web-routine | sysopt-performance | manual-mode | true (M3) |
| WP8 管理端驾驶舱 (T3-3~T3-4) | ralph-web-routine | sysopt-performance | manual-mode | true (M3) |
| WP9 行为埋点 (T4-1~T4-2) | ralph-web-requirement | event-tracking-generator *(planned)* | manual-mode | true (M4) |
| WP10 用户研究/试点 (T4-3~T4-4) | ralph-web-requirement | pilot-material-generator *(planned)* | manual-mode | true (M4) |
| WP11 测试验证 (T5-1~T5-4) | ralph-test-executor | sysopt-stability, sysopt-security | manual-mode | true (M5) |
| WP12 交付 (T6-1~T6-2) | ralph-state-manager | delivery-pack-assembler *(planned)* | manual-mode | true (M6) |

## Dispatch instruction template

When dispatching WPx, instruct the agent to:
- invoke `<required-skill>` via the Skill tool
- invoke `<conditional-supporting-skill>` via the Skill tool if its condition applies
- if a skill is not invokable, enter `manual-mode` and record in `STATE.md`: missing skill name / affected WP / substitute / blocking status

## Planned sub-skills (not created in v1)

- `event-tracking-generator` — WP9; create after PHASE_0→PHASE_1 proven
- `pilot-material-generator` — WP10; create after PHASE_0→PHASE_1 proven
- `delivery-pack-assembler` — WP12; create after PHASE_0→PHASE_1 proven

Rationale: WP9/WP10/WP12 are mid-late tasks; early creation adds maintenance cost. First version falls back to manual-mode.
```

- [ ] **Step 2: Verify skill names exist on disk**

Run: `powershell -Command "Get-ChildItem .trae/skills -Directory | Select-Object -ExpandProperty Name"`
Expected output includes: `remediation-orchestrator`, `sysopt-security`, `sysopt-maintainability`, `sysopt-stability`, `sysopt-performance`, `ralph-task-executor`, `ralph-web-routine`, `ralph-web-requirement`, `ralph-test-executor`, `ralph-state-manager`. The `(planned)` skills need NOT be present. `superpowers-test-driven-development` and `design-taste-frontend` are invokable via the Skill tool (not required on disk).

- [ ] **Step 3: Commit**

```bash
git add .trae/skills/dws-improvement-orchestrator/dispatch-registry.md
git commit -m "feat(orchestrator): add dispatch-registry.md (WP→skill mapping)"
```

---

## Task 3: gate-checks.md

**Files:**
- Create: `.trae/skills/dws-improvement-orchestrator/gate-checks.md`

**Interfaces:**
- Consumes: gate definitions from spec §2.2, §2.3.
- Produces: the gate table referenced by `确认阶段`; includes the Self-test protocol.

- [ ] **Step 1: Write gate-checks.md**

```markdown
# Gate Checks (M0-M6)

`确认阶段` checks in order: automatic checks → manual confirmations filled → evidence exists.

## Automatic vs manual gates

| Transition | Automatic checks | Manual confirmation |
|---|---|---|
| PHASE_0_INIT → PHASE_1_SECURITY (M0) | backlog/acceptance-criteria/STATE.md exist; test-account field non-empty | 产品负责人确认范围冻结 |
| PHASE_1_SECURITY → PHASE_2_UX (M1) | P0 open count==0; `reports/crisis-chain-report.md` exists and pass rate==100% | 心理专家确认危机提示文案 |
| PHASE_2_UX → PHASE_3_WORKBENCH (M2) | P1 fix rate ≥85% (auto-computed) | 产品+测试确认核心流程可用 |
| PHASE_3_WORKBENCH → PHASE_4_DATA_PILOT (M3) | three-role key-path E2E passes | 产品确认体验达标 |
| PHASE_4_DATA_PILOT → PHASE_5_VERIFICATION (M4) | 7 files under `pilot/` exist; event coverage==100% | 心理专家审核问卷/访谈提纲 |
| PHASE_5_VERIFICATION → PHASE_6_DELIVERY (M5) | E2E/performance/security/a11y reports exist and meet targets | 测试负责人签字 |
| PHASE_6_DELIVERY → CLOSED (M6) | pilot-version tag / deployment handbook / retrospective report exist | 干系人确认交付 |

The orchestrator does not pretend to judge material quality; manual items must be explicitly confirmed before advancing.

## Evidence field check rule

Evidence may be a file path, report path, test-command record, screenshot path, or meeting-notes link. If Evidence looks like a local path, the orchestrator checks the file exists; if it is text or an external link, only check non-empty and require manual confirmation.

## Waiver rules

**Non-waivable gates** (不可豁免):
- P0 open count must be 0 for PHASE_1_SECURITY → PHASE_2_UX and all later transitions.
- Crisis chain pass rate must be 100% for PHASE_1_SECURITY → PHASE_2_UX.
- Core E2E must pass before PHASE_6_DELIVERY.
- Missing STATE.md/backlog.md/acceptance-criteria.md cannot be waived.

**Waivable gates** (须 decisions.md 记录):
- P1 fix rate below 85%: waivable only with a decision record.
- Missing non-critical pilot material: waivable only before PHASE_5_VERIFICATION, not before CLOSED.
- A11Y/performance non-blocking gaps: waivable if documented with owner and deadline.

`decisions.md` must not become a backdoor to arbitrarily skip quality gates. All open P1 default-blocks M2 unless waived in `decisions.md`; phase-unrelated new P1 must also be waived or they count toward M2.

## P1 fix-rate statistics

P1 fix rate = Closed P1 tasks / all P1 tasks, computed live from `backlog.md`. New P1 enters the denominator. All open P1 default-block M2 unless waived in `decisions.md`.

## Self-test protocol (document state-machine test, v1 — no scripts)

1. Create mock `STATE.md` / `backlog.md`.
2. Mark PHASE_0_INIT gate checks satisfied (automatic items + simulated manual confirmation).
3. Run `确认阶段` → verify state changes to `PHASE_1_SECURITY`.
4. Repeat through `PHASE_6_DELIVERY`.
5. Verify final state becomes `CLOSED`.
6. **Counterexample A**: with P0 not cleared, `确认阶段` for PHASE_1_SECURITY → PHASE_2_UX must be rejected with a reason.
7. **Counterexample B**: when a Required skill in dispatch-registry is missing, `派发任务` must NOT fail; it enters `manual-mode` and records in `STATE.md`: missing skill / affected WP / substitute / blocking status.
8. **Counterexample C**: at PHASE_1_SECURITY → PHASE_2_UX, if `manual_confirmations` M1 (心理专家确认) is unfilled, `确认阶段` must be rejected and prompt the pending manual item.
```

- [ ] **Step 2: Verify consistency with SKILL.md gate references**

Read both files; confirm the 7 transition rows match exactly and the enum names are identical to `state-schema.md` (Task 4).

- [ ] **Step 3: Commit**

```bash
git add .trae/skills/dws-improvement-orchestrator/gate-checks.md
git commit -m "feat(orchestrator): add gate-checks.md (M0-M6 gates + waiver + self-test)"
```

---

## Task 4: state-schema.md

**Files:**
- Create: `.trae/skills/dws-improvement-orchestrator/state-schema.md`

**Interfaces:**
- Consumes: task fields and state transitions from spec §2.1, §2.4, §6.
- Produces: the schema referenced by `STATE.md`/`backlog.md` templates and all lifecycle commands.

- [ ] **Step 1: Write state-schema.md**

```markdown
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
```

- [ ] **Step 2: Commit**

```bash
git add .trae/skills/dws-improvement-orchestrator/state-schema.md
git commit -m "feat(orchestrator): add state-schema.md (task fields + transitions)"
```

---

## Task 5: templates/ (6 files)

**Files:**
- Create: `.trae/skills/dws-improvement-orchestrator/templates/STATE.template.md`
- Create: `.trae/skills/dws-improvement-orchestrator/templates/backlog.template.md`
- Create: `.trae/skills/dws-improvement-orchestrator/templates/acceptance-criteria.template.md`
- Create: `.trae/skills/dws-improvement-orchestrator/templates/metrics.template.md`
- Create: `.trae/skills/dws-improvement-orchestrator/templates/phase-report.template.md`
- Create: `.trae/skills/dws-improvement-orchestrator/templates/decision-record.template.md`

**Interfaces:**
- Consumes: structures from spec §6, §7.1, §7.2, §8.
- Produces: templates copied by `启动改进项目` to `docs/planning/v1.40-improvement/`.

- [ ] **Step 1: Write STATE.template.md**

```markdown
# DWS Improvement — STATE

- Current phase: PHASE_0_INIT
- Last command:
- Last updated:

## Current Task Queue

| Order | Task ID | Priority | WP | Status | Blocking Gate | Ready |
|---:|---|---|---|---|---|---|

## Metrics Snapshot (X/Y)

| Metric | X | Y | Percent | Updated At |
|---|---:|---:|---:|---|

## Blocked Tasks

| Task ID | Reason | Dependent on | Unblock condition |
|---|---|---|---|

## Manual Confirmations

| Gate | Required Confirmation | Confirmed By | Confirmed At | Evidence |
|---|---|---|---|---|
| M0 | 产品负责人确认范围冻结 |  |  |  |
| M1 | 心理专家确认危机提示文案 |  |  |  |
| M2 | 产品+测试确认核心流程可用 |  |  |  |
| M3 | 产品确认体验达标 |  |  |  |
| M4 | 心理专家审核问卷/访谈提纲 |  |  |  |
| M5 | 测试负责人签字 |  |  |  |
| M6 | 干系人确认交付 |  |  |  |

## Missing-skill fallback log

| WP | Missing skill | Substitute | Blocking | Recorded at |
|---|---|---|---|---|
```

- [ ] **Step 2: Write backlog.template.md**

```markdown
# DWS Improvement — Backlog

> 审计忽略：是（本文件为流程状态文档，代码审计时排除；不影响代码/安全/功能/测试审查）

## P0

<!-- task entries per state-schema.md format; ID format DWS-P0-NNN -->

## P1

<!-- ID format DWS-P1-NNN -->

## P2

<!-- ID format DWS-P2-NNN -->

## Task entry format

```markdown
## DWS-Px-NNN [标题]
- 类型：  优先级：  状态：
- 阶段：  工作包：  负责人：
- 计划完成：
- 验收标准：
- 关联测试：
- 横向排查范围：
- 横向排查结论：
- 回归用例：  验收证据：
- 阻塞信息：
- 审计忽略：
```
```

- [ ] **Step 3: Write acceptance-criteria.template.md**

```markdown
# DWS Improvement — Acceptance Criteria

> Source: `md/12.md` §12 验收指标总表

| 分类 | 指标 | 目标 | 当前 | 是否达标 |
|---|---|---|---|---|
| 安全 | 危机关键词触发率 | 100% |  |  |
| 安全 | 危机事件审计完整率 | 100% |  |  |
| 安全 | P0 安全问题 | 0 |  |  |
| 功能 | P0 问题剩余数 | 0 |  |  |
| 功能 | P1 修复率 | ≥85% |  |  |
| 功能 | 核心 E2E 通过率 | 100% |  |  |
| 用户体验 | 学生评估完成率 | ≥80% |  |  |
| 用户体验 | 评估平均耗时 | ≤5 分钟 |  |  |
| 用户体验 | 结果理解正确率 | ≥85% |  |  |
| 咨询师效率 | 单条预警处理耗时下降 | ≥30% |  |  |
| 性能 | 页面加载 P95 | ≤2 秒 |  |  |
| 性能 | 风险评估提交 P95 | ≤2 秒 |  |  |
| 稳定性 | API 错误率 | ≤1% |  |  |
| 数据闭环 | 核心埋点覆盖率 | 100% |  |  |
| 试点准备 | 试点材料完成率 | 100% |  |  |
```

- [ ] **Step 4: Write metrics.template.md**

```markdown
# DWS Improvement — Metrics

## Metric Definitions

| Metric | Numerator X | Denominator Y | Source |
|---|---|---|---|
| P0 open count | 状态非 Closed 的 P0 任务数 | 全部 P0 任务数 | backlog.md |
| P1 fix rate | Closed 的 P1 任务数 | 全部 P1 任务数 | backlog.md |
| Crisis pass rate | 通过的危机链路测试数 | 全部危机链路测试数 | reports/crisis-chain-report.md |
| E2E pass rate | 通过的 E2E 用例数 | 全部 E2E 用例数 | reports/e2e-report.md |
| Event coverage | 已实现埋点事件数 | 计划埋点事件数 | pilot/event-tracking.md |

## Current Snapshot

| Metric | X | Y | Percent | Source | Updated At |
|---|---:|---:|---:|---|---|

## Gate Metrics

| Gate | Required Metric | Current | Pass |
|---|---|---|---|

## Notes

P1 fix rate uses live backlog stats; new P1 enters the denominator. All open P1 default-block M2 unless waived in decisions.md.
```

- [ ] **Step 5: Write phase-report.template.md**

```markdown
# Phase Report — [PHASE_X_XXX]

- 阶段：
- 日期：
- 负责人：

## 1. 阶段目标

-

## 2. 交付物清单

| 交付物 | 是否完成 | 链接/位置 |
|---|---|---|

## 3. 验收指标

| 指标 | 目标 | 实际 | 是否通过 |
|---|---:|---:|---|

## 4. 测试结果

| 测试类型 | 结果 | 说明 |
|---|---|---|

## 5. 未完成事项

| 事项 | 原因 | 下一步 |
|---|---|---|

## 6. 是否进入下一阶段

结论：
审批人：
```

- [ ] **Step 6: Write decision-record.template.md**

```markdown
# DWS Improvement — Decisions

> 每条决策带唯一编号与复审日期，避免豁免永久化。

## DEC-YYYY-MM-DD-NNN: [Title]

- Date:
- Related phase:
- Related task:
- Decision type: scope-cut / waiver / risk-acceptance / dispatch-change
- Decision:
- Reason:
- Risk:
- Owner:
- Expiry / revisit date:
- Approved by:
```

- [ ] **Step 7: Commit all templates**

```bash
git add .trae/skills/dws-improvement-orchestrator/templates/
git commit -m "feat(orchestrator): add 6 runtime templates (STATE/backlog/acceptance/metrics/phase-report/decision)"
```

---

## Task 6: Self-test protocol execution

**Files:**
- No new files. Uses the skill's own Self-test protocol from `gate-checks.md` to validate the document state machine.

**Interfaces:**
- Consumes: all files from Tasks 1-5.

- [ ] **Step 1: Run self-test positive path (M0→CLOSED)**

Manually simulate the orchestrator workflow using the templates:
1. Copy `templates/STATE.template.md` to a temp `STATE.md`, set `Current phase: PHASE_0_INIT`.
2. Fill `Manual Confirmations` M0 row (产品负责人确认范围冻结 — Confirmed By: test).
3. Walk through `确认阶段` logic against `gate-checks.md` M0 row: automatic items (assume files exist) + manual filled + evidence.
4. Confirm the logic would advance to `PHASE_1_SECURITY`.
5. Repeat the mental walk-through for M1-M6, confirming each transition's automatic + manual + evidence checks match `gate-checks.md`.
6. Confirm final state reaches `CLOSED`.

Expected: each transition's required checks are present and unambiguous in `gate-checks.md`; no missing gate.

- [ ] **Step 2: Run counterexample A (P0 not cleared)**

Read `gate-checks.md` M1 row. Confirm the rule "P0 open count==0" is listed as automatic and as Non-waivable. Trace: with P0 open count>0, `确认阶段` for PHASE_1_SECURITY → PHASE_2_UX must be rejected.

Expected: the rejection reason is derivable from the gate-checks table.

- [ ] **Step 3: Run counterexample B (missing skill fallback)**

Read `dispatch-registry.md` WP9 row (`event-tracking-generator *(planned)*`). Trace `派发任务` for WP9: skill is `(planned)` → not invokable → enter `manual-mode` → record in `STATE.md` Missing-skill fallback log (WP9 / event-tracking-generator / manual-mode / blocking=true (M4) / timestamp).

Expected: the `STATE.template.md` has a "Missing-skill fallback log" section to capture this (verify it exists from Task 5 Step 1).

- [ ] **Step 4: Run counterexample C (manual confirmation missing)**

Read `STATE.template.md` Manual Confirmations M1 row (empty Confirmed By). Trace `确认阶段` for PHASE_1_SECURITY → PHASE_2_UX: automatic items pass, but M1 manual confirmation is unfilled → reject and prompt the pending manual item.

Expected: `gate-checks.md` "确认阶段 checks in order: automatic checks → manual confirmations filled → evidence exists" supports this rejection.

- [ ] **Step 5: Commit self-test record**

Create `.trae/skills/dws-improvement-orchestrator/SELF-TEST.md` recording the walkthrough results:

```markdown
# dws-improvement-orchestrator Self-Test Record

- Date: 2026-07-08
- Result: PASS

## Positive path
- M0→M6 transitions all have defined automatic + manual + evidence checks in gate-checks.md. ✓
- Final state CLOSED reachable. ✓

## Counterexamples
- A (P0 not cleared → reject): supported by Non-waivable rule + M1 automatic check. ✓
- B (missing skill → manual-mode): STATE.template.md has Missing-skill fallback log. ✓
- C (manual confirmation missing → reject): supported by gate-check check order. ✓
```

```bash
git add .trae/skills/dws-improvement-orchestrator/SELF-TEST.md
git commit -m "test(orchestrator): record v1 self-test protocol results (PASS)"
```

---

## Task 7: Final consistency verification

**Files:**
- Reads all files created in Tasks 1-6.

- [ ] **Step 1: Cross-reference consistency check**

Verify these consistencies across files:
1. Phase enum in `SKILL.md`, `state-schema.md`, `gate-checks.md` are identical (8 values).
2. The 9 commands in `SKILL.md` match the command rules section.
3. `dispatch-registry.md` WP rows (12) match spec §4.2 and the workflow table in spec §13.
4. `gate-checks.md` 7 transition rows use full enum names (no `PHASE_0→1` shorthand).
5. `pilot/` 7 filenames referenced in `gate-checks.md` M4 match the runtime artifact list in the plan header.
6. `STATE.template.md` has sections: Current Task Queue / Metrics Snapshot / Blocked Tasks / Manual Confirmations / Missing-skill fallback log.
7. `decision-record.template.md` uses `DEC-YYYY-MM-DD-NNN` format with Expiry/revisit date field.

- [ ] **Step 2: Verify SKILL.md line count**

Run: `powershell -Command "(Get-Content .trae/skills/dws-improvement-orchestrator/SKILL.md | Measure-Object -Line).Lines"`
Expected: < 500.

- [ ] **Step 3: Verify all 10 skill files exist**

Run: `powershell -Command "Get-ChildItem .trae/skills/dws-improvement-orchestrator -Recurse -File | Select-Object -ExpandProperty FullName"`
Expected: 11 files — SKILL.md, dispatch-registry.md, gate-checks.md, state-schema.md, SELF-TEST.md, and 6 templates.

- [ ] **Step 4: Final commit (if any fixes were needed)**

If Steps 1-3 found and fixed any inconsistency, commit:
```bash
git add .trae/skills/dws-improvement-orchestrator/
git commit -m "fix(orchestrator): resolve cross-reference inconsistencies from verification"
```
If no fixes needed, no commit.

---

## Notes

- This plan creates the orchestrator skill **only**. The 3 planned sub-skills (`event-tracking-generator`, `pilot-material-generator`, `delivery-pack-assembler`) are deferred per spec §5 — they will be created after PHASE_0→PHASE_1 is proven on a real WP.
- Runtime artifacts under `docs/planning/v1.40-improvement/` are created by `启动改进项目` at runtime, NOT by this plan.
- Per spec §12 落地顺序, after this plan completes, the next validation is running a real WP1 (危机链路) dispatch end-to-end — that is a separate follow-up, not part of this plan.
