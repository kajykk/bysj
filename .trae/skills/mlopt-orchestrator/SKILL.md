---
name: mlopt-orchestrator
description: "Master state machine for 5-phase ML model optimization lifecycle (Baseline → QuickFix → Structural → Architecture → Governance). Invoke when user starts V4 model optimization, asks '下一步做什么', requests phase transition, or needs optimization progress status."
---

# Skill: mlopt-orchestrator

> **ML 优化计划主编排器**：驱动 V4 优化计划 13 个优化项的全生命周期（5 阶段流转 + 5 技能调度）。
> **基线文档**：`docs/模型性能综合评估与优化计划_v4.md`

## 📋 技能描述

这是 ML 模型优化的 **最高指挥官与全生命周期状态管理员**。
你的职责是管理 `.trae/mlopt/STATE.md`，并调度 5 个阶段 (Phase 0~4) 与 13 个优化项 (S-01~S-05 / M-01~M-04 / L-01~L-04) 的流转。

## 使用场景 (Usage)

- 用户启动 V4 模型优化时（指令："启动模型优化"、"start mlopt"、"开始 V4 计划"）
- 需要检查"下一步做什么"时（指令："查看优化进度"、"what's next"）
- 阶段切换时（指令："进入下一阶段"、"phase transition"）
- 需要采集基线、生成问题清单、验证关卡时
- 用户指令："继续优化"、"continue"

## 指令 (Instructions)

### Phase 0: 初始加载协议 (Bootstrap Protocol)

**在开始任何工作之前，必须优先执行以下协议：**

1. **资源定位**:
   - 本 Skill 的标准模板位于 `./assets/` 目录中。
   - 创建任何文档之前，**必须**优先读取该目录下的对应模板文件：
     - `./assets/STATE_TEMPLATE.md` (状态文件模板)
     - `./assets/OPTIMIZATION_INVENTORY_TEMPLATE.md` (优化项清单模板)
     - `./assets/METRICS_BASELINE_TEMPLATE.md` (指标基线模板)

2. **上下文对齐**:
   - 加载规则后的第一步，**立即**读取 `.trae/mlopt/STATE.md`。
   - 如果内部状态与 `STATE.md` 不一致，**必须**废弃内部状态，并根据 `STATE.md` 重建。

3. **工作目录初始化**:
   - 确保以下目录结构存在 (不存在则创建):
   ```
   .trae/mlopt/
   ├── STATE.md
   ├── optimization-inventory.md
   ├── metrics-baseline.md
   ├── tasks/
   │   ├── quickfix.md           # S-01 ~ S-05
   │   ├── structural.md         # M-01 ~ M-04
   │   ├── architecture.md       # L-01 ~ L-04
   │   └── governance.md         # 监控/回归/回滚
   ├── test-plan.md
   ├── canary-records.md
   └── reports/
       ├── phase-0-baseline.md
       ├── phase-1-quickfix.md
       ├── phase-2-structural.md
       ├── phase-3-architecture.md
       └── phase-4-governance.md
   ```

### Phase 1: 状态检查与初始化

1. **读取状态文件**：调用 `Read` 读取 `.trae/mlopt/STATE.md`。
2. **状态判断**：
   - **如果文件不存在**：
     1. 执行 **[初始化协议]** 创建文件。
     2. 初始化为 **PHASE_0_BASELINE / Round 1**。
     3. 输出 "🚀 ML 模型优化流程启动，进入 Phase 0: 基线建立"。
   - **如果文件存在**：
     1. 检查 **阶段进度 (Phase Progress)** 表格。
     2. 找到当前标记为 `🔄 进行中` 的阶段。
     3. 检查 **优化项状态 (Item Status)** 表格，确认各优化项进度。
     4. 报告当前状态与下一步行动。

### Phase 2: 状态流转控制 (State Flow Control)

#### 阶段流转总览

```
INIT → PHASE_0_BASELINE → PHASE_1_QUICKFIX → PHASE_2_STRUCTURAL
     → PHASE_3_ARCHITECTURE → PHASE_4_GOVERNANCE → DONE
```

每个阶段切换必须通过 **关卡验证 (Gate Validation)**。

#### 阶段调度映射

| 阶段 | 调度技能 | 优化项 | 预计周期 | 关卡条件 |
|------|---------|--------|----------|----------|
| PHASE_0_BASELINE | mlopt-orchestrator | 基线采集 | 1-2 天 | 指标基线已写入 + 13 项清单初始化 |
| PHASE_1_QUICKFIX | mlopt-quickfix | S-01 ~ S-05 | 2-4 周 | 5 项 COMPLETED + 7 天稳定性 |
| PHASE_2_STRUCTURAL | mlopt-structural | M-01 ~ M-04 | 1-3 月 | 4 项 COMPLETED + 14 天稳定性 |
| PHASE_3_ARCHITECTURE | mlopt-architecture | L-01 ~ L-04 | 3-6 月 | 4 项 COMPLETED + 30 天稳定性 |
| PHASE_4_GOVERNANCE | mlopt-governance | 监控/回归 | 持续 | 90 天治理 + V5 报告生成 |

#### 优化项生命周期

每个优化项 (S/M/L-XX) 必须遵循以下状态机：

```
PROPOSED → PLANNING → IMPLEMENTING → VERIFYING → MONITORING → COMPLETED
                ↓           ↓             ↓            ↓
             REJECTED    BLOCKED      FAILED     ROLLED_BACK
```

**状态定义**：
- `PROPOSED`：已在清单中提出，待评估
- `PLANNING`：正在制定实施方案、分配资源
- `IMPLEMENTING`：编码/部署中
- `VERIFYING`：执行回归测试 + 金丝雀验证
- `MONITORING`：金丝雀全量后观察期
- `COMPLETED`：观察期通过，正式上线
- `REJECTED`：评估后不实施
- `BLOCKED`：等待外部依赖（数据、合作方）
- `FAILED`：实施失败，需要重做
- `ROLLED_BACK`：金丝雀期间被自动回滚

### Phase 3: 关卡验证 (Gate Validation)

#### PHASE_0 → PHASE_1 关卡
- [ ] `metrics-baseline.md` 已写入 4 类模型基线指标
- [ ] `optimization-inventory.md` 已初始化 13 个优化项
- [ ] 测试基线：419/421 passed (V4 报告)
- [ ] 性能基线：health<200ms, fusion<100ms, list<500ms

#### PHASE_1 → PHASE_2 关卡
- [ ] S-01 ~ S-05 全部 COMPLETED
- [ ] 7 天稳定性：无 P0 告警
- [ ] 融合 F1 提升 ≥10%（基线 ~0.85 → ≥0.92）
- [ ] 推理缓存命中率 ≥30%
- [ ] 健康检查冷启动 <2s
- [ ] 全量回归测试通过率 100%

#### PHASE_2 → PHASE_3 关卡
- [ ] M-01 ~ M-04 全部 COMPLETED
- [ ] 14 天稳定性：无 P0 告警
- [ ] BERT 文本模型 F1 ≥0.97（长文本场景）
- [ ] 漂移检测覆盖率 100%
- [ ] 生理模型 v2 ECE <0.05

#### PHASE_3 → PHASE_4 关卡
- [ ] L-01 ~ L-04 全部 COMPLETED
- [ ] 30 天稳定性：无 P0 告警
- [ ] Keras 融合 F1 ≥加权融合 F1 +3%
- [ ] 多中心验证 AUC 跨集方差 <0.05
- [ ] 在线学习月度训练管道上线

#### PHASE_4 → DONE 关卡
- [ ] 90 天治理期通过
- [ ] V5 综合评估报告生成
- [ ] 13 个优化项全部 COMPLETED 或 REJECTED（含决策记录）
- [ ] 累计 F1 提升 ≥20%
- [ ] 性能监控机制运行 90 天无中断

### Phase 4: 调度协议 (Dispatch Protocol)

当用户指令"继续优化"或"next"时：

1. 读取当前阶段（PHASE_X）
2. 读取该阶段对应技能的待办项
3. 按优先级调度（P0 → P1 → P2 → P3）
4. 对应技能被调用时，传递以下上下文：
   - 当前阶段
   - 待办优化项 ID
   - 历史决策记录
   - 关卡验证清单
5. 子技能返回结果后，更新 `STATE.md` 与 `optimization-inventory.md`
6. 检查是否触发阶段切换条件

### Phase 5: 进度报告 (Progress Report)

进度必须以 **X/Y 量化格式** 输出，禁止模糊描述。

**示例**：
- ✅ "Phase 1: 3/5 完成（S-01, S-02, S-04），2/5 进行中（S-03 PLANNING, S-05 IMPLEMENTING）"
- ❌ "Phase 1 进展顺利"（禁止）

报告模板：
```
## ML 优化进度 - {日期}

**当前阶段**: PHASE_{X}_{NAME}
**总进度**: {已完成项}/{总项数} ({百分比}%)
**预计完成**: {日期}

### 各优化项状态
| ID | 优先级 | 状态 | 进度 | 负责人 | 预计完成 |
|----|--------|------|------|--------|----------|
| S-01 | P0 | COMPLETED | 100% | - | 2026-07-25 |
| S-02 | P0 | MONITORING | 90% | - | 2026-07-28 |
...

### 关卡状态
- [x] Phase 0 → 1 关卡: 通过
- [ ] Phase 1 → 2 关卡: 3/5 条件满足

### 风险与阻塞
- {风险描述}
```

### Phase 6: 异常处理 (Exception Handling)

1. **金丝雀回滚触发**：
   - 立即将对应优化项状态置为 `ROLLED_BACK`
   - 调用 `mlopt-governance` 执行根因分析
   - 在 `canary-records.md` 记录事件
   - 不允许跳过该项继续推进，必须修复后重新进入 PLANNING

2. **P0 告警触发**：
   - 暂停当前阶段所有 IMPLEMENTING 状态的优化项
   - 优先处理 P0 告警
   - 处理完毕后恢复

3. **依赖阻塞**：
   - 将优化项状态置为 `BLOCKED`
   - 记录阻塞原因与依赖方
   - 可继续推进无依赖的其他项

4. **阶段超时**：
   - PHASE_1 超时阈值：6 周（计划 2-4 周 × 1.5）
   - PHASE_2 超时阈值：5 个月（计划 1-3 月 × 1.5）
   - PHASE_3 超时阈值：9 个月（计划 3-6 月 × 1.5）
   - 超时后必须生成阶段总结报告并请求用户决策

### Phase 7: 文档与状态文件维护

**STATE.md 必须包含**：
- 当前阶段与 Round
- 阶段进度表
- 13 个优化项状态表
- 关卡验证清单
- 决策记录（含日期、原因、决策者）
- 风险登记册

**更新时机**：
- 每次优化项状态变更
- 每次阶段切换
- 每次金丝雀事件
- 每次关卡验证
- 每周一次进度快照

---

## 🚫 严禁事项 (Prohibited Actions)

1. **严禁跳过阶段**：必须按 PHASE_0 → 1 → 2 → 3 → 4 顺序
2. **严禁跳过关卡验证**：阶段切换前必须完成所有关卡条件
3. **严禁模糊进度**：必须用 X/Y 量化
4. **严禁私自降级阈值**：关卡条件修改需用户明确同意
5. **严禁未记录的状态变更**：所有变更必须写入 STATE.md
6. **严禁跳过回滚分析**：ROLLED_BACK 状态必须有根因报告

---

## 🔗 关联技能 (Related Skills)

- `mlopt-quickfix`：Phase 1 短期优化执行器
- `mlopt-structural`：Phase 2 中期结构优化执行器
- `mlopt-architecture`：Phase 3 长期架构优化执行器
- `mlopt-governance`：Phase 4 治理与持续监控
- `sysopt-orchestrator`：系统层优化（独立但可并行）
- `audit-beautify-orchestrator`：代码审查（独立）
