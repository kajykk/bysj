# ML 模型优化工作流设计文档 (V4)

> **文档目的**: 描述 V4 优化计划的工作流架构、状态机、阶段闸门、RACI 责任矩阵。
> **创建时间**: 2026-07-19
> **关联技能**: `mlopt-orchestrator` + 4 个阶段执行器
> **基线文档**: `docs/模型性能综合评估与优化计划_v4.md`

---

## 1. 工作流总览

### 1.1 架构图

```
┌────────────────────────────────────────────────────────────────────┐
│                  mlopt-orchestrator (主编排器)                     │
│  状态机: INIT → PHASE_0_BASELINE → PHASE_1_QUICKFIX                │
│        → PHASE_2_STRUCTURAL → PHASE_3_ARCHITECTURE                 │
│        → PHASE_4_GOVERNANCE → DONE                                 │
│  职责: 阶段调度、关卡验证、进度跟踪、异常处理                       │
└────────────────────────────────────────────────────────────────────┘
         │              │              │              │            │
         ▼              ▼              ▼              ▼            ▼
   ┌──────────┐   ┌──────────┐   ┌──────────┐   ┌──────────┐  ┌──────────┐
   │ Phase 0  │   │ Phase 1  │   │ Phase 2  │   │ Phase 3  │  │ Phase 4  │
   │ Baseline │   │ QuickFix │   │Structural│   │Architect.│  │Governance│
   │          │   │ S-01~05  │   │ M-01~04  │   │ L-01~04  │  │ G-01~08  │
   │ 编排器   │   │ quickfix │   │structural│   │architec. │  │governance│
   │ 自执行   │   │  技能    │   │  技能    │   │  技能    │  │  技能    │
   └──────────┘   └──────────┘   └──────────┘   └──────────┘  └──────────┘
         │              │              │              │            │
         └──────────────┴──────────────┴──────────────┘            │
                                  │                                 │
                                  ▼                                 │
                    ┌─────────────────────────┐                    │
                    │  共享状态与文档          │                    │
                    │  .trae/mlopt/           │                    │
                    │  ├── STATE.md           │ ◄──────────────────┘
                    │  ├── optimization-      │
                    │  │   inventory.md       │
                    │  ├── metrics-baseline.md│
                    │  ├── tasks/             │
                    │  ├── canary-records.md  │
                    │  └── reports/           │
                    └─────────────────────────┘
```

### 1.2 技能清单

| 技能 | 路径 | 角色 |
|------|------|------|
| `mlopt-orchestrator` | `.trae/skills/mlopt-orchestrator/` | 主编排器，5 阶段状态机 |
| `mlopt-quickfix` | `.trae/skills/mlopt-quickfix/` | Phase 1 执行器（S-01 ~ S-05） |
| `mlopt-structural` | `.trae/skills/mlopt-structural/` | Phase 2 执行器（M-01 ~ M-04） |
| `mlopt-architecture` | `.trae/skills/mlopt-architecture/` | Phase 3 执行器（L-01 ~ L-04） |
| `mlopt-governance` | `.trae/skills/mlopt-governance/` | Phase 4 治理与监控（G-01 ~ G-08） |

### 1.3 与现有技能族的关系

```
项目技能生态
├── sysopt-*           (系统优化: 性能/资源/稳定/安全/可维护)
├── audit-beautify-*   (代码审查与美化)
├── remediation-*      (整改协调器)
├── ralph-*            (开发流程)
└── mlopt-*  ← 本次新增 (ML 模型优化)
    ├── mlopt-orchestrator
    ├── mlopt-quickfix
    ├── mlopt-structural
    ├── mlopt-architecture
    └── mlopt-governance
```

**与 sysopt-* 的区别**：
- `sysopt-*`：系统层（API/DB/缓存/前端）优化
- `mlopt-*`：ML 模型层（算法/数据/推理）优化
- 两者可并行运行，状态文件独立（`.trae/sysopt/` vs `.trae/mlopt/`）

---

## 2. 状态机设计

### 2.1 阶段状态机

```
                                  ┌─────────────┐
                                  │     INIT    │
                                  └──────┬──────┘
                                         │ 用户启动
                                         ▼
                                  ┌─────────────┐
                                  │   PHASE_0   │  基线建立
                  ┌───────────────│  BASELINE   │  1-2 天
                  │               └──────┬──────┘
                  │ 关卡 0→1             │ 通过
                  │ 未通过               │
                  │                      ▼
                  │               ┌─────────────┐
                  │               │   PHASE_1   │  短期优化
                  │      ┌────────│  QUICKFIX   │  2-4 周
                  │      │        └──────┬──────┘
                  │      │ 关卡 1→2      │ 通过
                  │      │ 未通过        │
                  │      │               ▼
                  │      │        ┌─────────────┐
                  │      │        │   PHASE_2   │  中期优化
                  │      │  ┌─────│ STRUCTURAL  │  1-3 月
                  │      │  │     └──────┬──────┘
                  │      │  │ 关卡 2→3   │ 通过
                  │      │  │ 未通过     │
                  │      │  │            ▼
                  │      │  │     ┌─────────────┐
                  │      │  │     │   PHASE_3   │  长期架构
                  │      │  │  ┌──│ARCHITECTURE │  3-6 月
                  │      │  │  │  └──────┬──────┘
                  │      │  │  │ 关卡 3→4│ 通过
                  │      │  │  │ 未通过  │
                  │      │  │  │         ▼
                  │      │  │  │  ┌─────────────┐
                  │      │  │  │  │   PHASE_4   │  治理与监控
                  │      │  │  │  │ GOVERNANCE  │  90 天
                  │      │  │  │  └──────┬──────┘
                  │      │  │  │         │ 通过
                  │      │  │  │         ▼
                  │      │  │  │  ┌─────────────┐
                  │      │  │  │  │    DONE     │
                  │      │  │  │  └─────────────┘
                  │      │  │  │
                  └──────┴──┴──┴──── 阻塞时回到当前阶段继续
```

### 2.2 优化项状态机

每个优化项（S/M/L-XX）独立维护状态：

```
                ┌──────────┐
                │ PROPOSED │ ← 初始状态
                └────┬─────┘
                     │ 开始规划
                     ▼
                ┌──────────┐
        ┌───────│ PLANNING │
        │       └────┬─────┘
        │            │ 规划完成
        │            ▼
        │       ┌──────────────┐
        │       │ IMPLEMENTING │
        │       └──────┬───────┘
        │              │ 实施完成
        │              ▼
        │       ┌──────────────┐
        │       │  VERIFYING   │
        │       └──────┬───────┘
        │              │ 验证通过
        │              ▼
        │       ┌──────────────┐
        │       │  MONITORING  │ ← 金丝雀期
        │       └──────┬───────┘
        │              │ 监控期通过 (7/14/30 天)
        │              ▼
        │       ┌──────────────┐
        │       │  COMPLETED   │
        │       └──────────────┘
        │
        │ 失败路径
        ▼
   ┌──────────┐  评估拒绝   ┌──────────┐
   │ REJECTED │ ◄────────── │ PLANNING │
   └──────────┘             └──────────┘
   ┌──────────┐  等待依赖   ┌──────────────┐
   │ BLOCKED  │ ◄────────── │IMPLEMENTING │
   └──────────┘             └──────────────┘
   ┌──────────┐  实施失败   ┌──────────────┐
   │  FAILED  │ ◄────────── │IMPLEMENTING │
   └──────────┘             └──────────────┘
   ┌────────────┐  金丝雀回滚 ┌──────────────┐
   │ROLLED_BACK │ ◄──────────│  MONITORING  │
   └────────────┘            └──────────────┘
```

### 2.3 状态转换规则

| 当前状态 | 触发条件 | 新状态 | 责任人 |
|---------|---------|--------|--------|
| PROPOSED | 开始规划 | PLANNING | ML 工程师 |
| PLANNING | 方案就绪 | IMPLEMENTING | ML 工程师 |
| PLANNING | 评估不实施 | REJECTED | 决策者 |
| IMPLEMENTING | 编码完成 | VERIFYING | ML 工程师 |
| IMPLEMENTING | 依赖阻塞 | BLOCKED | 协调者 |
| IMPLEMENTING | 编码失败 | FAILED | ML 工程师 |
| VERIFYING | 测试通过 | MONITORING | QA |
| VERIFYING | 测试失败 | FAILED | ML 工程师 |
| MONITORING | 稳定期通过 | COMPLETED | 治理 |
| MONITORING | 金丝雀回滚 | ROLLED_BACK | 自动 |
| BLOCKED | 依赖就绪 | PLANNING | 协调者 |
| FAILED | 重新规划 | PLANNING | ML 工程师 |
| ROLLED_BACK | 根因分析后 | PLANNING | ML 工程师 |

---

## 3. 阶段闸门设计

### 3.1 闸门总览

| 闸门 | 来源 → 目标 | 关卡条件数 | 关键指标 |
|------|------------|-----------|----------|
| G0→1 | BASELINE → QUICKFIX | 4 | 基线已采集 |
| G1→2 | QUICKFIX → STRUCTURAL | 6 | 融合 F1 +10% |
| G2→3 | STRUCTURAL → ARCHITECTURE | 6 | BERT F1 ≥0.97 |
| G3→4 | ARCHITECTURE → GOVERNANCE | 6 | Keras F1 +3% |
| G4→D | GOVERNANCE → DONE | 6 | 累计 F1 +20% |

### 3.2 闸门验证函数

```python
# 伪代码 - 实际由 mlopt-orchestrator 实现
def validate_gate(from_phase: Phase, to_phase: Phase) -> GateResult:
    """阶段闸门验证"""
    gate_checks = GATES[f"{from_phase}_to_{to_phase}"]
    passed = []
    failed = []
    for check in gate_checks:
        result = check.run()
        if result.passed:
            passed.append(check.name)
        else:
            failed.append((check.name, result.reason))

    if not failed:
        return GateResult(passed=True, message=f"Gate {from_phase}→{to_phase} 通过")
    else:
        return GateResult(
            passed=False,
            message=f"Gate {from_phase}→{to_phase} 未通过: {failed}",
            failed_checks=failed,
        )
```

### 3.3 闸门失败处理

| 失败类型 | 处理策略 |
|---------|---------|
| 优化项未完成 | 留在当前阶段，继续推进 |
| 稳定性不达标 | 延长观察期 7 天 |
| 性能指标退化 | 触发根因分析，可能回滚 |
| 测试未通过 | 修复后重新验证 |
| 资源不足 | 升级到决策者，申请资源 |

---

## 4. RACI 责任矩阵

### 4.1 角色定义

| 角色 | 缩写 | 职责 |
|------|------|------|
| ML 工程师 | ML | 模型训练、评估、部署 |
| 后端工程师 | BE | API、缓存、健康检查 |
| 平台工程师 | PE | GPU 服务器、ML 平台、Airflow |
| QA 工程师 | QA | 测试、回归、验证 |
| ML 主管 | LEAD | 决策、资源分配、阶段切换 |
| 项目经理 | PM | 进度跟踪、风险升级 |
| 决策者 | DM | 重大决策、跨团队协调 |

### 4.2 RACI 矩阵

| 优化项 | ML | BE | PE | QA | LEAD | PM | DM |
|--------|----|----|----|----|------|----|----|
| **S-01** 启用生理 v2 | R | C | I | C | A | I | I |
| **S-02** 切换 v1.23 | R | C | I | C | A | I | I |
| **S-03** 清理 v1.21 | C | R | I | C | A | I | I |
| **S-04** 健康检查拆分 | I | R | I | C | A | I | I |
| **S-05** 推理缓存 | C | R | I | C | A | I | I |
| **M-01** BERT 文本模型 | R | C | C | C | A | I | I |
| **M-02** 漂移检测生产化 | C | R | C | C | A | I | I |
| **M-03** 生理 v2 校准 | R | I | I | C | A | I | I |
| **M-04** 数据集扩展 | R | I | I | C | C | A | C |
| **L-01** Keras 融合 | R | C | R | C | A | I | C |
| **L-02** 在线学习 | R | C | R | C | C | A | C |
| **L-03** 多中心验证 | R | I | I | C | C | A | R |
| **L-04** 可穿戴接入 | C | R | C | C | C | A | C |
| **G-01~08** 治理任务 | C | C | C | R | A | C | I |

**图例**：R=Responsible 执行 / A=Accountable 负责 / C=Consulted 咨询 / I=Informed 知会

### 4.3 关键决策点

| 决策点 | 决策者 | 输入 | 输出 |
|--------|--------|------|------|
| 阶段切换 | LEAD | 闸门验证结果 | 通过/延期/降级 |
| 优化项拒绝 | LEAD | 评估报告 | 接受/拒绝 |
| 资源申请升级 | DM | 资源缺口 | 批准/拒绝 |
| 金丝雀全量 | LEAD | 7 天稳定性数据 | 推进/延长/回滚 |
| 自动回滚 | 自动 | 阈值越线 | 回滚 + 通知 |
| V5 验收 | DM | 90 天治理数据 | 通过/延期 |

---

## 5. 调度协议

### 5.1 调度流程

```
用户指令 "继续优化" / "next"
        │
        ▼
┌──────────────────────────┐
│ 1. 读取 STATE.md          │
│ 2. 确定当前阶段           │
│ 3. 确定当前 Round         │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ 4. 调用对应阶段技能       │
│    PHASE_1 → quickfix    │
│    PHASE_2 → structural  │
│    PHASE_3 → architecture│
│    PHASE_4 → governance  │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ 5. 阶段技能选择优化项     │
│    按 P0→P1→P2→P3 优先级 │
│    一次一项（默认）       │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ 6. 执行优化项             │
│    PLANNING→IMPL→VERIFY  │
│    →MONITOR→COMPLETED    │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ 7. 更新 STATE.md          │
│ 8. 更新 optimization-     │
│    inventory.md           │
│ 9. 检查阶段切换条件       │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ 10. 输出进度报告          │
│     X/Y 量化格式         │
└──────────────────────────┘
```

### 5.2 调度示例

**用户**: "继续优化"

**编排器响应**:
```
📊 ML 优化进度报告 - 2026-07-19

**当前阶段**: PHASE_1_QUICKFIX (Round 1)
**总进度**: 3/13 (23%)
**预计完成**: 2026-08-15

### 当前阶段进度: 2/5
✅ S-01 启用生理 v2 - COMPLETED (2026-07-25)
🔄 S-02 切换 v1.23 - MONITORING (25% 金丝雀, 第 3 天)
⏳ S-03 清理 v1.21 - PROPOSED (依赖 S-02)
⏳ S-04 健康检查拆分 - PROPOSED
⏳ S-05 推理缓存 - PROPOSED

### 下一步行动
1. 等待 S-02 7 天稳定性 (剩余 4 天)
2. 启动 S-04 健康检查拆分 (可并行)

### 关卡状态
- [x] Phase 0 → 1: 通过
- [ ] Phase 1 → 2: 2/6 条件满足

是否启动 S-04?
```

---

## 6. 异常处理流程

### 6.1 金丝雀回滚

```
金丝雀监控检测到异常
        │
        ▼
┌──────────────────────────┐
│ 自动回滚 (流量 100%→0%)  │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ 更新 STATE.md             │
│ 优化项 → ROLLED_BACK      │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ 记录 canary-records.md    │
│ (时间/版本/指标/影响)     │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ 24h 内根因分析            │
│ (mlopt-governance)        │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ 重新进入 PLANNING         │
│ (不跳过)                  │
└──────────────────────────┘
```

### 6.2 P0 告警

```
P0 告警触发
        │
        ▼
┌──────────────────────────┐
│ 暂停当前阶段所有          │
│ IMPLEMENTING 优化项       │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ Slack + 电话通知          │
│ 15 分钟响应               │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ 优先处理 P0               │
│ (回滚/扩容/修复)          │
└──────────┬───────────────┘
           │
           ▼
┌──────────────────────────┐
│ 24h 内事故报告            │
│ 恢复 IMPLEMENTING         │
└──────────────────────────┘
```

### 6.3 阶段超时

| 阶段 | 计划周期 | 超时阈值 | 触发动作 |
|------|---------|---------|---------|
| PHASE_1 | 2-4 周 | 6 周 | 生成总结报告 + 用户决策 |
| PHASE_2 | 1-3 月 | 5 月 | 生成总结报告 + 用户决策 |
| PHASE_3 | 3-6 月 | 9 月 | 生成总结报告 + 用户决策 |
| PHASE_4 | 90 天 | 120 天 | 生成总结报告 + 用户决策 |

---

## 7. 文档与状态管理

### 7.1 状态文件结构

```
.trae/mlopt/
├── STATE.md                       # 主状态文件（编排器维护）
├── optimization-inventory.md      # 13 项优化项详情
├── metrics-baseline.md            # 指标基线
├── tasks/
│   ├── quickfix.md                # Phase 1 任务清单
│   ├── structural.md              # Phase 2 任务清单
│   ├── architecture.md            # Phase 3 任务清单
│   └── governance.md              # Phase 4 任务清单
├── test-plan.md                   # 测试计划
├── canary-records.md              # 金丝雀与回滚记录
└── reports/
    ├── phase-0-baseline.md        # Phase 0 报告
    ├── phase-1-quickfix.md        # Phase 1 报告
    ├── phase-2-structural.md      # Phase 2 报告
    ├── phase-3-architecture.md    # Phase 3 报告
    ├── phase-4-governance.md      # Phase 4 报告
    ├── weekly-{YYYY-Www}.md       # 周报
    └── monthly-{YYYY-MM}.md       # 月报
```

### 7.2 更新时机

| 事件 | 更新文件 | 责任人 |
|------|---------|--------|
| 优化项状态变更 | STATE.md, inventory.md | 阶段技能 |
| 阶段切换 | STATE.md, reports/ | 编排器 |
| 金丝雀事件 | canary-records.md | 治理技能 |
| 关卡验证 | STATE.md | 编排器 |
| 周一快照 | weekly-{week}.md | 治理技能 |
| 每月 1 日 | monthly-{month}.md | 治理技能 |

### 7.3 版本控制

- `.trae/mlopt/` 状态文件本地维护（已 gitignore，不入库），避免运行时状态污染仓库；如需长期归档可手动提交到 `docs/`
- 状态变更仅在本地记录，不强制生成 commit

---

## 8. 与现有项目的集成

### 8.1 与 sysopt-* 的协同

| 场景 | mlopt-* 处理 | sysopt-* 处理 |
|------|-------------|---------------|
| 推理延迟优化 | 模型推理优化 | API/缓存优化 |
| 内存增长 | 模型加载优化 | 进程内存优化 |
| 健康检查 | 模型健康指标 | 系统健康指标 |
| 漂移检测 | 模型分布漂移 | 系统指标漂移 |

**协同规则**：
- 状态文件独立（`.trae/mlopt/` vs `.trae/sysopt/`）
- 同时启动时，并行运行
- 共享 Alertmanager / Grafana 基础设施
- 共享金丝雀与回滚机制

### 8.2 与 audit-beautify-* 的协同

| 阶段 | audit-beautify | mlopt |
|------|---------------|-------|
| 代码审查 | 优化项实施前 | - |
| 性能验证 | - | 优化项验证时 |
| 验收 | - | 阶段闸门时 |

### 8.3 与 ralph-* 的协同

| 场景 | ralph | mlopt |
|------|-------|-------|
| 新功能开发 | 全流程 | - |
| 模型新版本发布 | - | 全流程 |
| Bug 修复 | 全流程 | - |

---

## 9. 启动与使用指南

### 9.1 启动 ML 优化流程

**用户指令**:
```
启动模型优化 / start mlopt / 开始 V4 计划
```

**编排器响应**:
1. 检查 `.trae/mlopt/STATE.md` 是否存在
2. 若不存在 → 初始化为 PHASE_0_BASELINE
3. 采集基线数据（参考 V4 报告）
4. 初始化 optimization-inventory.md
5. 进入 PHASE_1_QUICKFIX

### 9.2 日常使用

| 用户指令 | 编排器响应 |
|---------|----------|
| "继续优化" / "next" | 调度下一项优化 |
| "查看进度" | 输出 X/Y 进度报告 |
| "S-01 状态" | 输出 S-01 详情 |
| "进入下一阶段" | 验证关卡，若通过则切换 |
| "回滚 S-02" | 手动触发回滚流程 |
| "生成 V5 报告" | 进入 V5 报告生成流程 |

### 9.3 异常处理指令

| 用户指令 | 编排器响应 |
|---------|----------|
| "P0 告警" | 触发 P0 响应流程 |
| "金丝雀失败" | 触发回滚流程 |
| "S-03 阻塞" | 标记 BLOCKED + 记录原因 |
| "阶段超时" | 生成总结报告 + 请求决策 |

---

## 10. 验收与交付

### 10.1 V5 验收清单

- [ ] 13 项优化全部 COMPLETED 或 REJECTED（含决策记录）
- [ ] 90 天治理期通过（无未闭环 P0）
- [ ] 累计 F1 提升 ≥20%
- [ ] 性能监控运行 90 天无中断
- [ ] V5 综合评估报告生成
- [ ] 漂移检测告警噪声 <5/周
- [ ] 用户满意度调研通过

### 10.2 交付物

| 交付物 | 路径 | 责任人 |
|--------|------|--------|
| V5 综合评估报告 | `docs/模型性能综合评估与优化计划_v5.md` | LEAD |
| 13 项优化前后对比 | V5 报告 § 4 | ML |
| 90 天治理数据 | V5 报告 § 9 | 治理 |
| 经验教训 | V5 报告 § 11 | LEAD |
| V6 路线图 | V5 报告 § 12 | LEAD |
| 状态文件归档 | `.trae/mlopt/archive/v4/` | PM |

### 10.3 持续运营

V5 验收后，mlopt-governance 转入持续运营模式：
- KPI 监控持续运行
- 月度全量评估
- 季度 V6 路线图更新
- 年度大版本评估

---

## 附录 A: 技能调用示例

### A.1 启动 ML 优化

```
User: 启动模型优化

→ Skill: mlopt-orchestrator
  → 读取 .trae/mlopt/STATE.md (不存在)
  → 复制 assets/STATE_TEMPLATE.md 到 .trae/mlopt/STATE.md
  → 复制 assets/OPTIMIZATION_INVENTORY_TEMPLATE.md
  → 复制 assets/METRICS_BASELINE_TEMPLATE.md
  → 采集 V4 基线数据
  → 初始化为 PHASE_0_BASELINE / Round 1
  → 输出: 🚀 ML 模型优化流程启动，进入 Phase 0: 基线建立
```

### A.2 执行优化项

```
User: 执行 S-01

→ Skill: mlopt-orchestrator
  → 读取 STATE.md, 确认当前 PHASE_1_QUICKFIX
  → 调度 → Skill: mlopt-quickfix
    → Step 2: S-01 启用生理模型 v2
    → PLANNING → IMPLEMENTING → VERIFYING → MONITORING
    → 返回结果
  → 更新 STATE.md (S-01: COMPLETED)
  → 检查关卡条件
  → 输出进度报告
```

### A.3 处理金丝雀回滚

```
告警: M-01 BERT 金丝雀 fallback_rate=8% > 5%

→ Skill: mlopt-governance
  → Step 4: 金丝雀监控
  → 自动回滚 (流量 100% → 0%)
  → 记录 canary-records.md
  → 通知 mlopt-orchestrator
    → 更新 STATE.md (M-01: ROLLED_BACK)
  → 24h 内根因分析
  → M-01 重新进入 PLANNING
```

---

## 附录 B: 工作流设计原则

### B.1 设计原则

1. **单一职责**：每个技能只负责一个阶段
2. **状态外化**：所有状态写入文件，不依赖内存
3. **量化优先**：所有进度用 X/Y 格式，禁止模糊描述
4. **关卡强约束**：阶段切换必须通过所有关卡条件
5. **失败友好**：失败状态（FAILED/ROLLED_BACK）有明确恢复路径
6. **可观测性**：所有变更记录到 STATE.md 与 reports/
7. **可回滚**：每个优化项都有回滚策略
8. **不跳步**：禁止跳过阶段或跳过关卡

### B.2 与 Superpowers 框架对齐

本工作流遵循 superpowers-using-superpowers 的核心原则：
- **技能优先**：每个阶段都有对应技能
- **流程驱动**：状态机驱动流程推进
- **强约束**：关卡验证保证质量
- **可追溯**：所有决策有记录

---

**文档结束**

> 本工作流设计文档定义了 V4 优化计划的完整执行框架。结合 5 个 mlopt-* 技能，可实现 13 项优化的全生命周期管理。建议从 `mlopt-orchestrator` 启动，按阶段推进。
