# 系统优化 Agent 应用 · 设计文档

> 基于《系统优化总体计划》（11 章节）设计的一套 **CodeBuddy Agent 应用**：由「编排 Agent」驱动 4 条工作流，按需调用 12 个专业化技能（Skill），在不影响业务连续性的前提下分阶段完成性能、稳定性、安全与可维护性的综合提升。

---

## 1. 设计目标

把一份「方法论文档」变成一个**可执行的 Agent 系统**：

- 计划里的每个阶段 → 一条 **工作流（Workflow）**
- 计划里的每种优化手段（§4.1–§4.5）→ 一个 **技能（Skill）**
- 计划里的 KPI（§3）/ 验收标准（§9）→ 工作流的 **门禁（Gate）**
- 计划里的优先级（§7）→ 编排 Agent 的 **Backlog 排序算法**

交付物全部位于本目录，可直接装入 CodeBuddy（用户级 `~/.workbuddy/skills/` 或项目级 `.workbuddy/skills/`）。

---

## 2. 系统架构

```
                          ┌─────────────────────────────────────┐
                          │      Orchestrator Agent              │
                          │  (sys-optimization-orchestrator)      │
                          │  · 维护优化 Backlog（问题清单+优先级）│
                          │  · 按 §7 四维排序派发任务             │
                          │  · 按阶段推进 WF-0 → WF-3            │
                          │  · 每阶段结束校验 Gate（KPI/验收）   │
                          └───────────────┬─────────────────────┘
                                          │ 调度（按需 load skill）
        ┌──────────────┬─────────────────┼─────────────────┬──────────────┐
        ▼              ▼                 ▼                 ▼              ▼
   [WF-0 基线评估] [WF-1 快速止血]  [WF-2 结构性优化]  [WF-3 体系化治理]  [跨阶段支撑]
        │              │                 │                 │
   ┌────┴────┐   ┌─────┴─────┐     ┌─────┴─────┐     ┌─────┴─────┐
   │perf     │   │db-optimizer│    │async-     │     │observability│
   │diagnosis│   │cache-opt   │    │decoupling │     │release-    │
   │load-    │   │reliability │    │db-optimizer│     │governance  │
   │testing  │   │security    │    │cache-opt  │     │code-quality│
   │security │   │code-quality│    │resource-  │     │test-gates  │
   │code-    │   │observability│   │tuning     │     │security    │
   │quality  │   │             │    │reliability│     │            │
   └─────────┘   └────────────┘     └──────────┘     └────────────┘

   数据底座（本工程已有的可观测/质量设施）：
   Sentry(Vue) · ruff/import-linter/grimp · trivy · pytest/coverage
   vitest/playwright · lighthouse · alembic · SQLAlchemy
```

---

## 3. 工作流 ↔ 计划章节 映射

| 工作流 | 计划章节 | 阶段 | 核心目标 | 门禁（Gate） |
|---|---|---|---|---|
| **WF-0 基线评估** | §2, §5 阶段0 | 0 | 建立可比基线、输出优先级问题清单 | 现状报告 + 问题清单 + KPI 基线通过评审 |
| **WF-1 快速止血** | §4.1–4.4(高收益项), §5 阶段1 | 1 | 解决 P0/P1 高风险高收益问题 | 高危漏洞清零、P0 闭环、性能前后对比达标 |
| **WF-2 结构性优化** | §4.1–4.2 深度项, §5 阶段2 | 2 | 拆耦合、异步化、DB/缓存/资源深治 | 架构方案评审通过、链路对比达标、资源更平稳 |
| **WF-3 体系化治理** | §4.3–4.5, §5 阶段3, §9 | 3 | 固化监控/安全/质量/发布门禁与机制 | 治理手册、门禁生效、故障演练记录 |

详细步骤见 [`AGENT_WORKFLOWS.md`](./AGENT_WORKFLOWS.md)。

---

## 4. 技能（Skill）总览

12 个技能覆盖计划的全部优化手段，注册表与触发条件见 [`SKILL_CATALOG.md`](./SKILL_CATALOG.md)，每个技能独立定义于 `skills/` 目录。

| 技能 | 对应计划 | 一句话职责 |
|---|---|---|
| `sys-optimization-orchestrator` | 全局 | 驱动 4 阶段工作流、维护 Backlog、校验门禁 |
| `sys-perf-diagnosis` | §2, §4.1 | 性能与链路诊断、5-Why 根因、瓶颈定位 |
| `sys-db-optimizer` | §4.1.2 | 慢 SQL、索引、事务、分区归档 |
| `sys-cache-optimizer` | §4.1.3 | 多级缓存、穿透/击穿/雪崩防护 |
| `sys-async-decoupling` | §4.1.4 | 异步化、消息队列削峰、幂等 |
| `sys-resource-tuning` | §4.2 | CPU/内存/存储/网络资源调优 |
| `sys-reliability` | §4.3 | 熔断/限流/降级/超时、高可用 |
| `sys-security-hardening` | §4.4 | 漏洞扫描、访问控制、数据保护、审计 |
| `sys-code-quality` | §4.5 | 复杂度/重复率/耦合治理、重构 |
| `sys-observability` | §4.3.3 | 分层监控、告警分级、链路追踪 |
| `sys-load-testing` | §2.1, §5 | 基线/峰值/稳定性压测、KPI 基线 |
| `sys-release-governance` | §4.3.4, §9 | 灰度/金丝雀/回滚、发布评审 |

---

## 5. 与 CodeBuddy SDK 的集成方式

本设计面向 **CodeBuddy Agent SDK**：

1. **编排 Agent** 以 `skills/sys-optimization-orchestrator/SKILL.md` 作为系统指令骨架，结合本目录的 `workflows.json` 作为状态机定义。
2. **专用技能** 通过 SDK 的 skill 加载机制按需注入上下文（progressive disclosure），每个技能自带 `scripts/`（确定性脚本）与 `references/`（参考手册）。
3. **门禁校验** 由编排 Agent 调用技能内的脚本（如 `scripts/check_gate.py`）产出结构化结果，决定进入下一阶段或回退。

最小集成骨架（示意，非运行代码）：

```python
from codebuddy_agent_sdk import Agent, SkillLoader

agent = Agent(
    name="system-optimization-agent",
    system_prompt=open("skills/sys-optimization-orchestrator/SKILL.md").read(),
    skills=SkillLoader.load_dir("skills"),   # 12 个专用技能
    workflow="workflows.json",               # 4 阶段状态机 + 门禁
)
agent.run(goal="按《系统优化总体计划》分阶段提升系统性能/稳定性/安全/可维护性")
```

> 说明：以上为集成范式示意。技能文件本身已可直接被 CodeBuddy 加载使用；若需完整可运行 SDK 工程，可在确认后由 `init-cbc-sdk-web` 类脚手架落地。

---

## 6. 安装与使用

```bash
# 项目级（与团队协作）
cp -r skills/* .workbuddy/skills/

# 或用户级（跨工程复用）
cp -r skills/* ~/.workbuddy/skills/
```

安装后，在对话中描述优化诉求（如「对核心接口做性能诊断」「给数据库慢查询建索引」「按计划做阶段 0 基线评估」），对应技能会被自动触发；提及「按优化计划推进」会激活编排技能。

---

## 7. 目录结构

```
system-optimization-agent/
├── README.md               # 本文：架构与集成说明
├── AGENT_WORKFLOWS.md      # 4 条工作流的详细步骤/门禁/交付物
├── SKILL_CATALOG.md        # 技能注册表（触发/KPI/工具）
├── workflows.json          # 机器可读工作流定义（SDK 可消费）
└── skills/                 # 12 个 CodeBuddy 技能（SKILL.md）
    ├── sys-optimization-orchestrator/
    ├── sys-perf-diagnosis/
    ├── sys-db-optimizer/
    ├── sys-cache-optimizer/
    ├── sys-async-decoupling/
    ├── sys-resource-tuning/
    ├── sys-reliability/
    ├── sys-security-hardening/
    ├── sys-code-quality/
    ├── sys-observability/
    ├── sys-load-testing/
    └── sys-release-governance/
```
