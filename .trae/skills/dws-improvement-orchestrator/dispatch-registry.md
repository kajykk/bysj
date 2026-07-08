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
