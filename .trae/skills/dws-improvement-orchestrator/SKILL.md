---
description: Orchestrates the 8-week DWS improvement lifecycle across phases 0-6. Use when the user says 启动改进项目, 继续改进, 查看进度, 确认阶段, 派发任务, 提交验收, 关闭任务, 验收退回, 标记阻塞, 解除阻塞, or asks to manage DWS improvement work. Maintains STATE.md/backlog/metrics, enforces P0→P1→P2 priority, regression tests, horizontal checks, gate checks, and dispatches existing skills by work package.
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
| 初始化运行时工件 | templates/ (STATE / backlog / acceptance-criteria / metrics / phase-report / decision-record) |

## 阶段状态枚举

`STATE.md` 仅允许: `PHASE_0_INIT | PHASE_1_SECURITY | PHASE_2_UX | PHASE_3_WORKBENCH | PHASE_4_DATA_PILOT | PHASE_5_VERIFICATION | PHASE_6_DELIVERY | CLOSED`

规则: 同一时间只能有一个当前阶段；阶段内可有多个任务并行；跨阶段任务默认不允许派发，除非 `decisions.md` 豁免。

## 操作命令（10 个）

| 命令 | 动作 |
|---|---|
| `启动改进项目` | 初始化工件，进入 `PHASE_0_INIT` |
| `继续改进` | 读取状态，派发下一个就绪任务 |
| `查看进度` | 输出阶段/任务/指标 X/Y/阻塞 |
| `确认阶段` | 校验门禁（自动+人工），通过则前进 |
| `派发任务` | 按 `dispatch-registry.md` 派发 |
| `提交验收` | 置 Pending Review，必须附回归用例 |
| `关闭任务` | 验收通过置 Closed，更新 metrics |
| `验收退回` | 退回 Pending Review 任务到 Fixing，记录退回原因 |
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
- **`启动改进项目` 最小输出格式**:
  ```
  - STATE.md / backlog.md path:
  - Current phase: PHASE_0_INIT
  - Next action: 派发任务
  ```
- **`继续改进` 最小输出格式**:
  ```
  - Current phase:
  - Ready tasks (count):
  - Next action:
  ```
- **`确认阶段` 最小输出格式**:
  ```
  - Gate checks: pass/fail per item
  - Transition: advanced / rejected (reason)
  - Next action:
  ```
- **`派发任务` 最小输出格式**:
  ```
  - Task ID / Assigned WP:
  - Skill invoked:
  - Status: dispatched / manual-mode
  ```
- **`提交验收` 最小输出格式**:
  ```
  - Task ID:
  - Status: → Pending Review
  - Regression evidence:
  ```
- **`关闭任务` 最小输出格式**:
  ```
  - Task ID:
  - Status: Closed
  - Remaining open tasks:
  ```
- **`验收退回` 最小输出格式**:
  ```
  - Task ID:
  - Reason:
  - New status: Fixing
  ```
- **`标记阻塞` 最小输出格式**:
  ```
  - Task ID:
  - Blocker reason:
  - Blocking: true/false
  ```
- **`解除阻塞` 最小输出格式**:
  ```
  - Task ID:
  - New status: Confirmed/Fixing
  - Next action:
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
