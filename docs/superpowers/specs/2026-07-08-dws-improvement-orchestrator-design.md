# 设计规格：dws-improvement-orchestrator

- 日期：2026-07-08
- 状态：已批准（待写实现计划）
- 来源：`md/12.md`（DWS 8 周改进项目计划）、`md/13.md`、`md/15.md` 评审
- 关联硬约束：项目 `project_memory.md` 中所有审计/优先级/状态文档规则

## 1. 目标与定位

新增技能 `dws-improvement-orchestrator`，作为 DWS 8 周改进项目的**顶层状态机编排器**。

**职责边界**：
- 负责：阶段流转、任务生命周期、优先级约束、工件状态一致性、技能派发
- 不负责：直接实现代码修复、直接替代专项技能

**触发兼容说明**：
- 本技能是 Trae/Ralph 风格项目技能，由用户显式触发
- 仅放 `.trae/skills/`，不创建 `.cursor/skills/` 副本，避免状态文档分叉
- 未来如需 Cursor 自动发现，再整体迁移

## 2. 状态机

### 2.1 阶段状态枚举

`STATE.md` 仅允许以下枚举值：

```
PHASE_0_INIT | PHASE_1_SECURITY | PHASE_2_UX | PHASE_3_WORKBENCH
| PHASE_4_DATA_PILOT | PHASE_5_VERIFICATION | PHASE_6_DELIVERY | CLOSED
```

**规则**：同一时间只能有一个当前阶段，但阶段内可有多个任务并行；跨阶段任务默认不允许派发，除非 `decisions.md` 有明确豁免。

### 2.2 阶段门禁（自动 / 人工）

完整明细写入 `gate-checks.md`，关键项：

| 阶段流转 | 自动检查 | 人工确认 |
|---|---|---|
| PHASE_0→1 (M0) | backlog/acceptance-criteria/STATE.md 文件存在；测试账号字段非空 | 产品负责人确认范围冻结 |
| PHASE_1→2 (M1) | P0 open count==0；`reports/crisis-chain-report.md` 存在且通过率==100% | 心理专家确认危机提示文案 |
| PHASE_2→3 (M2) | P1 修复率≥85%（自动统计） | 产品+测试确认核心流程可用 |
| PHASE_3→4 (M3) | 三类角色关键路径 E2E 通过 | 产品确认体验达标 |
| PHASE_4→5 (M4) | `pilot/` 下 6 个文件存在；埋点事件覆盖率==100% | 心理专家审核问卷/访谈提纲 |
| PHASE_5→6 (M5) | E2E/性能/安全/a11y 报告存在且达标 | 测试负责人签字 |
| PHASE_6→CLOSED (M6) | 试点版本 tag/部署手册/复盘报告存在 | 干系人确认交付 |

编排器不假装能判断材料质量，人工项必须显式确认后才前进。

### 2.3 门禁豁免规则

**Non-waivable gates**（不可豁免）：
- P0 open count must be 0 for PHASE_1→2 and all later transitions.
- Crisis chain pass rate must be 100% for PHASE_1→2.
- Core E2E must pass before PHASE_6_DELIVERY.
- Missing STATE.md/backlog.md/acceptance-criteria.md cannot be waived.

**Waivable gates**（须 decisions.md 记录）：
- P1 fix rate below 85%: waivable only with a decision record.
- Missing non-critical pilot material: waivable only before PHASE_5, not before CLOSED.
- A11Y/performance non-blocking gaps: waivable if documented with owner and deadline.

`decisions.md` 不得成为任意跳过质量门禁的后门。

### 2.4 任务状态迁移表

| 当前状态 | 允许流向 | 触发命令 |
|---|---|---|
| New | Confirmed / 阻塞 | 派发任务 / 标记阻塞 |
| Confirmed | Fixing / 阻塞 | 派发任务 / 标记阻塞 |
| Fixing | Pending Review / 阻塞 | 提交验收 / 标记阻塞 |
| Pending Review | Closed / Fixing / 阻塞 | 关闭任务 / 验收退回 / 标记阻塞 |
| Closed | 不可回退 | —（回归须新建任务） |
| 阻塞 | Confirmed / Fixing | 解除阻塞 |

规则：
- `Closed` 不可重开；回归新建任务
- P0 回归插队到当前阶段最前

## 3. 操作命令（9 个）

| 命令 | 动作 |
|---|---|
| `启动改进项目` | 初始化工件，进入 PHASE_0_INIT |
| `继续改进` | 读取状态，派发下一个就绪任务 |
| `查看进度` | 输出阶段/任务/指标 X/Y/阻塞 |
| `确认阶段` | 校验门禁（自动+人工），通过则前进 |
| `派发任务` | 按 dispatch-registry 派发 |
| `提交验收` | 置 Pending Review，必须附回归用例 |
| `关闭任务` | 验收通过置 Closed，更新 metrics |
| `标记阻塞` | 记录阻塞原因/依赖任务/解除条件，跳过 |
| `解除阻塞` | 依赖满足后恢复状态，重新入队 |

**每个命令规定最小输出格式**，以 `查看进度` 为例：

```
## 查看进度 output
- Current phase:
- Open tasks:
- P0/P1/P2 X/Y:
- Blocked tasks:
- Next recommended action:
```

## 4. 技能派发

### 4.1 派发语义

**提示式调度**：编排器不调用技能 API，而是输出指令要求当前 Agent 读取并遵守对应 SKILL.md：

```
When dispatching WP1, instruct the agent to read and follow:
- .trae/skills/remediation-orchestrator/SKILL.md
- .trae/skills/sysopt-security/SKILL.md (if security review needed)
```

### 4.2 派发注册表

独立文件 `dispatch-registry.md`，规则写入头部：

```markdown
Skill names must match invokable skill names. If a skill is planned but not present, mark it with (planned) and fallback to manual-mode.
```

| WP | Required skill | Conditional supporting skill | fallback | blocking |
|---|---|---|---|---|
| WP1 危机链路 | remediation-orchestrator | sysopt-security | manual-mode | true (M1) |
| WP2 角色边界 | sysopt-maintainability | ralph-task-executor | manual-mode | true (M1) |
| WP3 安全一致性 | sysopt-security | sysopt-stability | manual-mode | true (M1) |
| WP4 评估流程 | ralph-web-routine | superpowers-test-driven-development, design-taste-frontend | manual-mode | true (M2) |
| WP5 历史/内容/干预 | ralph-web-routine | superpowers-test-driven-development | manual-mode | true (M2) |
| WP6 交互一致性 | sysopt-maintainability | superpowers-test-driven-development | manual-mode | true (M2) |
| WP7 咨询师工作台 | ralph-web-routine | sysopt-performance | manual-mode | true (M3) |
| WP8 管理端驾驶舱 | ralph-web-routine | sysopt-performance | manual-mode | true (M3) |
| WP9 行为埋点 | ralph-web-requirement | event-tracking-generator *(planned)* | manual-mode | true (M4) |
| WP10 用户研究/试点 | ralph-web-requirement | pilot-material-generator *(planned)* | manual-mode | true (M4) |
| WP11 测试验证 | ralph-test-executor | sysopt-stability, sysopt-security | manual-mode | true (M5) |
| WP12 交付 | ralph-state-manager | delivery-pack-assembler *(planned)* | manual-mode | true (M6) |

### 4.3 fallback 规则

目标技能不存在 → 回退 manual-mode → STATE.md 记录（缺失技能名/受影响 WP/替代方式/是否阻塞门禁）→ 不让整个编排器不可用。

## 5. 新增子技能（两步落地）

3 个薄模板生成器**第一版不强制作为依赖**：
- `event-tracking-generator` *(planned)*
- `pilot-material-generator` *(planned)*
- `delivery-pack-assembler` *(planned)*

- 第一步：仅在 dispatch-registry 标注为"计划依赖"，缺失时 fallback 到 manual-mode
- 第二步：编排器跑通 PHASE_0→PHASE_1 后再创建这 3 个子技能
- 理由：WP9/WP10/WP12 是中后期任务，不阻塞前两阶段；过早创建增加维护成本

## 6. 任务字段与 backlog

任务字段在 12.md §9.1 基础上增加：

| 新增字段 | 说明 |
|---|---|
| 横向排查范围 | 同类型代码/页面/API 排查范围 |
| 横向排查结论 | 是否发现同类问题 |
| 回归用例 | 修复必须绑定的测试 |
| 验收证据 | 测试命令/报告路径/截图/日志 |
| 审计忽略 | 是否属状态文档，审计时忽略 |
| 阻塞信息 | 阻塞原因/依赖任务/解除条件 |

任务条目示例（写入 `templates/backlog.template.md`）：

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

## 7. 状态工件目录

```
docs/planning/v1.40-improvement/
├── STATE.md                 # 当前阶段/任务/指标 X/Y/阻塞 + manual_confirmations
├── backlog.md               # P0/P1/P2 整改 Backlog
├── acceptance-criteria.md   # 验收指标表
├── metrics.md               # X/Y 指标 + 统计口径
├── decisions.md             # 阶段流转/范围裁剪/人工豁免/风险接受决策
├── dispatch-registry.md     # WP→技能映射（与技能目录同名文件镜像）
├── phases/phase-{0..6}.md   # 各阶段验收报告
├── reports/                 # 危机链路/E2E/性能/安全/a11y 报告
└── pilot/                   # 试点材料
    ├── interview-guide.md
    ├── questionnaire.md
    ├── privacy-notice.md
    ├── pilot-plan.md
    ├── deployment-guide.md
    └── rollback-plan.md
```

`pilot/` 下 6 个文件名固定，使 M4 自动检查可执行。

### 7.1 STATE.md 的 manual_confirmations 区块

```markdown
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
```

`确认阶段` 检查顺序：自动项 → 人工确认已填写 → 证据存在。

### 7.2 metrics.md 的 X/Y 统计口径

| Metric | Numerator X | Denominator Y | Source |
|---|---|---|---|
| P0 open count | 状态非 Closed 的 P0 任务数 | 全部 P0 任务数 | backlog.md |
| P1 fix rate | Closed 的 P1 任务数 | 全部 P1 任务数 | backlog.md |
| Crisis pass rate | 通过的危机链路测试数 | 全部危机链路测试数 | reports/crisis-chain-report.md |
| E2E pass rate | 通过的 E2E 用例数 | 全部 E2E 用例数 | reports/e2e-report.md |
| Event coverage | 已实现埋点事件数 | 计划埋点事件数 | pilot/event-tracking.md |

## 8. 技能目录结构

```
.trae/skills/dws-improvement-orchestrator/
├── SKILL.md                 # 目标/触发命令/工作流/硬约束/引用索引（<500行）
├── dispatch-registry.md     # WP1-WP12 技能映射
├── gate-checks.md           # M0-M6 自动+人工门禁明细 + 豁免规则
├── state-schema.md          # 任务字段与状态迁移表
└── templates/
    ├── STATE.template.md
    ├── backlog.template.md
    ├── acceptance-criteria.template.md
    ├── metrics.template.md
    ├── phase-report.template.md
    └── decision-record.template.md
```

SKILL.md 只保留核心，详细矩阵拆到引用文件，按需读取（progressive disclosure）。

## 9. 错误处理与阻塞

- 任务阻塞：`标记阻塞` 记录原因/依赖/解除条件，编排器跳过该任务派发下一个就绪项
- 阶段流转被拒：输出未满足门禁清单（区分自动失败 vs 待人工确认）
- 技能派发失败/缺失：fallback manual-mode，STATE.md 标注，不阻塞其他任务
- 新增 P0/P1 回归：插入 backlog，P0 清零才能继续阶段流转
- 同类型问题：派发前强制横向排查，记录排查范围与结论
- **阻塞与门禁关系**：当任务阻塞但 blocking=true 且属于当前阶段门禁路径时，阶段不能确认通过；只有 blocking=false 或 decisions.md 有人工豁免时才允许继续

## 10. 编排器自测（文档状态机测试）

不引入脚本复杂度，第一版用运行手册式测试：

```
1. 创建 mock STATE.md / backlog.md
2. 标记 PHASE_0 门禁满足（自动项 + 模拟人工确认）
3. 运行 确认阶段 → 验证状态变为 PHASE_1_SECURITY
4. 重复至 PHASE_6_DELIVERY
5. 验证终态为 CLOSED
6. 反例A：P0 未清零时 确认阶段 应被拒绝并输出原因
7. 反例B：dispatch-registry 中 Required skill 不存在时，派发任务不应失败；应进入 manual-mode，并在 STATE.md 记录缺失技能/受影响 WP/替代方式/blocking 状态
8. 反例C：PHASE_1→2 时若 manual_confirmations 中 M1 心理专家确认未填写，确认阶段 应被拒绝并提示待人工确认项
```

## 11. description

```yaml
description: Orchestrates the 8-week DWS improvement lifecycle across phases 0-6. Use when the user says 启动改进项目, 继续改进, 查看进度, 确认阶段, 派发任务, 提交验收, 关闭任务, 标记阻塞, 解除阻塞, or asks to manage DWS improvement work. Maintains STATE.md/backlog/metrics, enforces P0→P1→P2 priority, regression tests, horizontal checks, gate checks, and dispatches existing skills by work package.
```

## 12. 落地顺序

1. 创建 `dws-improvement-orchestrator` 技能目录与 `SKILL.md`
2. 创建 `dispatch-registry.md` / `gate-checks.md` / `state-schema.md` / 模板
3. 用 mock 状态跑通 `启动改进项目 → 查看进度 → 确认阶段`
4. 验证两个反例（P0 未清零拒绝；技能缺失进 manual-mode）
5. 跑通真实 WP1 危机链路
6. 再创建 3 个补缺子技能

## 13. 工作流总览（任务序列与依赖）

编排器驱动的工作流序列（角色映射 12.md §4）：

| 阶段 | 工作包序列（依赖序） | 主责角色 | 派发技能 |
|---|---|---|---|
| PHASE_0 | T0-1→T0-2→T0-3→T0-4→T0-5→T0-6 | 产品+技术负责人 | （编排器直管） |
| PHASE_1 | WP1(T1-1→T1-2→T1-3) ∥ WP2(T1-4→T1-5) ∥ WP3(T1-6→T1-7) | 后端+前端+测试 | remediation-orchestrator / sysopt-* |
| PHASE_2 | WP4(T2-1→T2-2→T2-3) → WP5(T2-4→T2-6) ∥ WP6(T2-7) | 前端+后端 | ralph-web-routine / superpowers-test-driven-development |
| PHASE_3 | WP7(T3-1→T3-2) ∥ WP8(T3-3→T3-4) | 前端+后端 | ralph-web-routine / sysopt-performance |
| PHASE_4 | WP9(T4-1→T4-2) ∥ WP10(T4-3→T4-4) | 数据/模型+心理专家 | ralph-web-requirement / *(planned)* |
| PHASE_5 | WP11(T5-1→T5-2→T5-3→T5-4) | 测试+运维 | ralph-test-executor / sysopt-* |
| PHASE_6 | WP12(T6-1→T6-2) | 产品+运维 | ralph-state-manager / *(planned)* |

依赖规则：WP 内任务按编号顺序；WP 间 `∥` 表示可并行；阶段间严格串行，须门禁通过。

## 14. 硬约束对齐

本设计强制遵守 `project_memory.md` 中的硬约束：
- 所有状态文档在审计时显式忽略（任务字段 `审计忽略`）
- 修复按 P0→P1→P2 优先级
- Critical(P0) 必须在 High(P1) 前修复
- 阶段流转仅在关闭条件满足时允许
- 进度以 X/Y 量化
- 同类型问题横向排查
- 权限/安全/数据一致性问题需第二人复核
- 修复提交须附回归用例
