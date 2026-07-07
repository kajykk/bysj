---
name: sysopt-orchestrator
description: "Core state machine for 4-phase system optimization lifecycle (Baseline → QuickFix → Structural → Governance). Invoke when user starts system optimization, asks 'what's next', requests phase transition, or needs optimization progress status."
---

# Skill: sysopt-orchestrator

## 📋 技能描述 (Description)

这是系统优化的 **最高指挥官与全生命周期状态管理员**。
你的职责是管理 `.trae/sysopt/STATE.md`，并调度 4 个阶段 (Phase 0~3) 与 5 个维度 (性能/资源/稳定性/安全/可维护性) 的流转。

## 使用场景 (Usage)

- 用户启动系统优化时 (指令: "开始系统优化", "start optimization")。
- 需要检查 "下一步做什么" 时 (指令: "查看优化进度", "what's next")。
- 阶段切换时 (指令: "进入下一阶段", "phase transition")。
- 需要采集基线、生成问题清单、验证关卡时。
- 用户指令: "继续优化", "continue"。

## 指令 (Instructions)

### Phase 0: 初始加载协议 (Bootstrap Protocol)

**在开始任何工作之前，必须优先执行以下协议：**

1. **资源定位 (Resource Location)**:
   - **重要**: 本 Skill 的标准模板位于 `./assets/` 目录中。
   - 在创建任何文档之前，**必须**优先读取该目录下的对应模板文件：
     - `./assets/STATE_TEMPLATE.md` (状态文件模板)
     - `./assets/PROBLEM_INVENTORY_TEMPLATE.md` (问题清单模板)
     - `./assets/KPI_BASELINE_TEMPLATE.md` (KPI 基线模板)

2. **上下文对齐 (Context Alignment)**:
   - 加载规则后的第一步，**立即**读取 `.trae/sysopt/STATE.md`。
   - 如果内部状态与 `STATE.md` 不一致，**必须**废弃内部状态，并根据 `STATE.md` 重建。

3. **工作目录初始化**:
   - 确保以下目录结构存在 (不存在则创建):
   ```
   .trae/sysopt/
   ├── STATE.md
   ├── problem-inventory.md
   ├── kpi-baseline.md
   ├── tasks/
   │   ├── performance.md
   │   ├── resource.md
   │   ├── stability.md
   │   ├── security.md
   │   └── maintainability.md
   ├── test-plan.md
   └── reports/
   ```

### Phase 1: 状态检查与初始化

1. **读取状态文件**：调用 `Read` 读取 `.trae/sysopt/STATE.md`。
2. **状态判断**：
   - **如果文件不存在**：
     1. 执行 **[初始化协议]** 创建文件。
     2. 初始化为 **PHASE_0_BASELINE / Round 1**。
     3. 输出 "🚀 系统优化流程启动，进入 Phase 0: 基线建立"。
   - **如果文件存在**：
     1. 检查 **阶段进度 (Phase Progress)** 表格。
     2. 找到当前标记为 `🔄 进行中` 的阶段。
     3. 检查 **维度状态 (Dimension Status)** 表格，确认各维度进度。
     4. 报告当前状态与下一步行动。

### Phase 2: 状态流转控制 (State Flow Control)

#### 阶段流转总览

```
INIT → PHASE_0_BASELINE → PHASE_1_QUICKFIX → PHASE_2_STRUCTURAL → PHASE_3_GOVERNANCE → DONE
```

每个阶段切换必须通过 **关卡验证 (Gate Validation)**。

---

#### 1. PHASE_0: 基线建立 (Baseline)

**目标**：获得可比较的基线数据，明确优先级。

**执行内容**：
1. 梳理系统架构图、依赖图、核心链路图。
2. 收集近 30 天监控数据、日志、告警和事故记录。
3. 对核心接口进行压测，形成性能基线。
4. 对高风险模块进行代码与安全扫描。
5. 输出问题清单，按影响面与紧急程度排序。

**调度逻辑**：
- **并行调用** 5 个维度 skill 进行基线评估：
  - 调用 `sysopt-performance` (mode=assess)
  - 调用 `sysopt-resource` (mode=assess)
  - 调用 `sysopt-stability` (mode=assess)
  - 调用 `sysopt-security` (mode=assess)
  - 调用 `sysopt-maintainability` (mode=assess)
- 每个维度 skill 将问题写入 `problem-inventory.md` 对应分区。
- 汇总各维度基线数据到 `kpi-baseline.md`。

**关卡验证 (Gate 0→1)**：
- [ ] 5 个维度全部完成基线评估
- [ ] 问题清单 (problem-inventory.md) 已生成并按 P0~P3 排序
- [ ] KPI 基线数据已采集 (kpi-baseline.md)
- [ ] 优先级列表已与用户确认

**通过后**：
- 更新 `STATE.md` 阶段状态为 ✅，生成 `reports/phase-0-baseline.md`。
- 切换到 PHASE_1_QUICKFIX，输出 "📊 基线建立完成，进入 Phase 1: 快速止血"。

---

#### 2. PHASE_1: 快速止血 (QuickFix)

**目标**：优先解决影响最大、收益最高的问题。

**执行内容**：
1. 修复高频慢接口与慢 SQL (P0/P1)。
2. 调整缓存策略。
3. 限流、熔断、超时配置补齐。
4. 处理明显的内存泄漏和资源浪费。
5. 修复高危安全漏洞 (P0)。
6. 完善告警阈值与故障通知链路。

**调度逻辑**：
- **严格按优先级**：先处理所有 P0，再处理 P1。
- 维度 skill 以 `mode=quickfix` 调用，仅处理本维度 P0/P1 问题。
- 每个修复必须：
  1. 先在测试环境验证。
  2. 准备回滚方案。
  3. 灰度发布。
  4. 监控指标异常自动告警。

**关卡验证 (Gate 1→2)**：
- [ ] 所有 P0 问题已修复并验证
- [ ] P1 问题已处理或纳入 Phase 2 计划
- [ ] 无性能回退 (回归测试通过)
- [ ] 告警阈值与通知链路已完善

**通过后**：
- 更新 `STATE.md`，生成 `reports/phase-1-quickfix.md` (含优化前后对比)。
- 切换到 PHASE_2_STRUCTURAL，输出 "🔧 快速止血完成，进入 Phase 2: 结构性优化"。

---

#### 3. PHASE_2: 结构性优化 (Structural)

**目标**：针对瓶颈链路和架构问题进行深度治理。

**执行内容**：
1. 拆分高耦合模块。
2. 将耗时任务异步化。
3. 优化数据库结构、索引和查询策略。
4. 引入消息队列与削峰机制。
5. 完善服务降级与故障隔离。
6. 调整资源配额与线程池策略。

**调度逻辑**：
- 维度 skill 以 `mode=structural` 调用，处理 P1/P2 问题。
- **重点关注**：性能维度 (链路/DB/缓存)、稳定性维度 (容错/高可用)。
- 每个结构性变更必须：
  1. 输出架构优化方案 (新旧对比)。
  2. 双写/双跑或小流量验证。
  3. 用数据评估影响，而非感觉。

**关卡验证 (Gate 2→3)**：
- [ ] 高耦合模块拆分完成
- [ ] 耗时任务异步化完成
- [ ] 数据库结构与索引优化完成
- [ ] 服务降级与故障隔离就位
- [ ] KPI 目标达成率 >60%

**通过后**：
- 更新 `STATE.md`，生成 `reports/phase-2-structural.md`。
- 切换到 PHASE_3_GOVERNANCE，输出 "🏗️ 结构性优化完成，进入 Phase 3: 体系化治理"。

---

#### 4. PHASE_3: 体系化治理 (Governance)

**目标**：将优化成果固化为制度和工程机制。

**执行内容**：
1. 建立持续性能监控和容量预测机制。
2. 建立安全扫描与漏洞修复 SLA。
3. 建立代码质量门禁和测试门禁。
4. 建立发布灰度和回滚标准。
5. 完善文档、Runbook 和应急预案。
6. 定期进行稳定性压测与故障演练。

**调度逻辑**：
- 维度 skill 以 `mode=governance` 调用，处理 P2/P3 问题并建立机制。
- **重点关注**：可维护性维度 (文档/测试/架构)、安全维度 (SLA/审计)。

**关卡验证 (Gate 3→DONE)**：
- [ ] 持续性能监控与容量预测机制建立
- [ ] 安全扫描与漏洞修复 SLA 建立
- [ ] 代码质量门禁与测试门禁建立
- [ ] 发布灰度与回滚标准建立
- [ ] 文档/Runbook/应急预案完善

**通过后**：
- 更新 `STATE.md`，生成 `reports/phase-3-governance.md`。
- 标记项目为 "🎉 系统优化完成 (DONE)"。

---

### 初始化协议 (Initialization Protocol)

如果需要初始化 `STATE.md`：
1. **加载模板**：读取 `./assets/STATE_TEMPLATE.md`。
2. **生成文件**：基于模板内容生成 `.trae/sysopt/STATE.md`，替换 `[PROJECT_NAME]`、`[START_TIME]` 等占位符。
3. **初始化问题清单**：基于 `./assets/PROBLEM_INVENTORY_TEMPLATE.md` 创建 `problem-inventory.md`。
4. **初始化 KPI 基线**：基于 `./assets/KPI_BASELINE_TEMPLATE.md` 创建 `kpi-baseline.md`。
5. **状态设定**：确保仅 PHASE_0 标记为 `🔄 进行中`，其余均为 `⏳ 待定`。

### 优先级铁律 (Priority Iron Rules)

**P0 未清零，禁止处理 P1**。严格遵循优先级顺序：
1. **P0**: 必须立即处理 (高危漏洞、核心服务不可用、严重泄漏、关键链路超时)。
2. **P1**: 高优先级 (关键接口慢、DB 慢查询、告警失效、权限缺失)。
3. **P2**: 中优先级 (非核心性能、文档、测试、局部架构)。
4. **P3**: 低优先级 (体验细节、长期重构、技术债)。

### 状态同步协议 (State Sync Protocol)

每次任务状态变更后，**必须**：
1. **Count**: 重新扫描 `tasks/*.md`，计算 `[x]` 数量与总任务数。
2. **Verify**: 确保 `STATE.md` 中的进度与实际文件一致。不一致则**强制覆盖** `STATE.md`。
3. **Update**: 更新 `STATE.md` 中的维度状态与 KPI 达成率。
4. **Audit**: 检查 `problem-inventory.md` 中对应问题状态是否同步更新。

## 示例 (Examples)

### 示例 1：启动优化
**Input**:
> 用户：开始系统优化

**Output**:
> 🚀 **系统优化流程启动**
> - **Phase**: PHASE_0_BASELINE
> - **Action**: 并行调用 5 个维度 skill 进行基线评估
> - **下一步**: 等待各维度评估结果，汇总问题清单

### 示例 2：检查进度
**Input**:
> 用户：查看优化进度

**Output**:
> 📊 **当前优化状态**:
> - **Phase**: PHASE_1_QUICKFIX (🔄 进行中)
> - **维度进度**: 性能 3/5, 安全 2/4, 稳定性 1/3, 资源 0/2, 可维护性 0/1
> - **P0 问题**: 4/6 已修复
> - **下一步**: 继续修复剩余 2 个 P0 问题 (安全维度)

### 示例 3：阶段切换
**Input**:
> 用户：Phase 1 完成，进入下一阶段

**Output**:
> 🔍 **执行关卡验证 (Gate 1→2)**:
> - [x] 所有 P0 问题已修复
> - [x] P1 问题已处理或纳入 Phase 2
> - [x] 回归测试通过
> - [x] 告警链路已完善
> - ✅ **关卡验证通过**
> - **切换到**: PHASE_2_STRUCTURAL

## 🛡️ 铁律与约束 (Iron Rules & Constraints)

1. **先数据后决策**：任何优化必须有基线数据支撑，禁止凭感觉优化。
2. **优先级铁律**：P0 未清零禁止处理 P1；P1 未处理禁止进入下一阶段。
3. **阶段闭环**：Phase N 未通过关卡验证，禁止进入 Phase N+1。
4. **可回滚原则**：所有变更必须有回滚方案，灰度发布。
5. **量化验收**：进度必须为 `X/Y` 数字格式，KPI 必须有基线/目标/当前/达成率。
6. **监控先行**：优化前先建监控基线，优化后验证指标变化。
7. **单一事实来源**：`tasks/*.md` 和 `problem-inventory.md` 是绝对真理，`STATE.md` 是投影。
8. **禁止伪造**：只有当问题真正修复且验证通过后，才允许标记为 ✅。

## 📂 关联资产 (Related Assets)

- `./assets/STATE_TEMPLATE.md` (状态文件模板)
- `./assets/PROBLEM_INVENTORY_TEMPLATE.md` (问题清单模板)
- `./assets/KPI_BASELINE_TEMPLATE.md` (KPI 基线模板)
- `sysopt-performance/SKILL.md` (性能维度)
- `sysopt-resource/SKILL.md` (资源维度)
- `sysopt-stability/SKILL.md` (稳定性维度)
- `sysopt-security/SKILL.md` (安全维度)
- `sysopt-maintainability/SKILL.md` (可维护性维度)
- `.trae/sysopt/STATE.md` (运行时状态文件)
