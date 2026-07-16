---
name: sys-optimization-orchestrator
description: >-
  This skill should be used when the user wants to run the overall system
  optimization program end-to-end — "按优化计划推进", "开始系统优化",
  "分阶段做性能/稳定性/安全/可维护性优化". It drives the 4-phase workflow
  (baseline → quick-fix → structural → governance), maintains a prioritized
  backlog, dispatches to the 11 specialist skills, and gates each phase by KPI.
agent_created: true
---

# sys-optimization-orchestrator

## 用途
把《系统优化总体计划》作为状态机驱动执行：维护优化 Backlog、按阶段推进
WF-0→WF-1→WF-2→WF-3、按需调用专用技能、用门禁（Gate）决定是否进入下一阶段。

## 何时使用
- 用户提出「按优化计划推进系统优化」「开始执行优化总体计划」等。
- 需要在多阶段、多技能之间做编排与优先级决策时。

## 执行流程
1. **加载工作流定义**：读取 `system-optimization-agent/workflows.json`，获得阶段、任务、依赖、门禁。
2. **初始化 Backlog**：若无既有问题清单，先调度 `sys-perf-diagnosis` / `sys-load-testing` /
   `sys-security-hardening` / `sys-code-quality` 完成 WF-0，产出 `问题清单与优先级.csv` 与 `KPI-基线.json`。
3. **四维排序**：对每个问题按 `impact × risk × cost × benefit` 打 P0–P3（规则见 workflows.json 的 priority_model）。
   - P0：高危漏洞 / 核心不可用 / 严重泄漏 / 关键链路超时。
   - P1：关键接口慢 / 慢查询锁冲突 / 告警失效 / 高风险权限缺失。
4. **顺序推进阶段**：仅当上一阶段 Gate 通过才进入下一阶段；Gate 未过则回到对应任务重做。
   - WF-0 → WF-1（止血）→ WF-2（结构性）→ WF-3（治理）。
5. **派发任务**：每个任务按 `workflows.json` 中声明的 `skills` 字段加载对应专用技能并执行。
6. **核验门禁**：阶段末用技能内脚本或人工评审核验 Gate 指标，记录到交付物。

## 工具与脚本
- 工作流定义：`../workflows.json`（相对于本技能目录）。
- 问题清单模板：`问题清单与优先级.csv`（列：id, 标题, 维度评分, 优先级, 关联阶段, 状态）。
- KPI 基线：`KPI-基线.json`。
- 专用技能：其余 11 个 `sys-*` 技能。

## 验收与门禁（来自 §3 / §9）
- Gate-0：现状报告 + 问题清单 + KPI 基线通过评审。
- Gate-1：高危漏洞清零、P0 闭环、P95↓≥20%、5xx<1%。
- Gate-2：架构方案评审通过、P95 较 WF-1 再↓≥15%、CPU<70%、内存<75%。
- Gate-3：治理手册、CI 门禁生效、≥1 次演练、核心单测≥70%。

## 与本工程栈的对应
- 后端入口 `backend/app/main.py`（FastAPI）；前端 `frontend/`（Vue3+Vite）。
- 已有质量基座：ruff、import-linter/grimp、trivy、pytest/coverage、lighthouse、Sentry。
- 编排时应复用这些既有设施，避免重复造轮子。

## 注意事项
- 严格遵守「先数据后决策、先高收益低成本、每阶段可量化、伴随监控与回滚」。
- 任一线上变更必须经 `sys-release-governance` 灰度 + 回滚。
- 不跳过阶段；不带着未过 Gate 的状态进入下一阶段。
