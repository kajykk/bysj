# v1.26 经验总结

> **迭代编号**: v1.26-lite-recall-optimization-and-active-readiness
> **状态**: Round 1 / Step 5 — Locked

---

## Round 1 经验

### Step 1: Draft
- 基于 `e:\code\bysj\md\9.md` (详细提案) 快速起草了 01/02/04/05
- v1.26 是纯优化迭代，大量复用 v1.25 基座
- 采用 Threshold-first → ClassWeight-second → Model-last 策略

### Step 2: Critique
- 发现 9 个问题（3 Critical / 3 Major / 3 Minor）
- 核心矛盾：01 说 Phase 2 条件执行，04 说无条件执行
- 跨文档 Phase 编号体系不一致（04 的 Phase 7 vs 05 的 Phase 7 内容不同）

### Step 3: Research
- **阈值优化**: Youden's J (Sensitivity+ Specificity-1) 是理论最优标准，与 Phase 1 设计一致。Balanced Accuracy 是其线性变换。
- **安全检测**: 行业标准是三层安全（关键词 + 情感 + 上下文），确定性规则防火墙优于概率模型。"near-zero-miss detection is achievable but necessarily incurs elevated false-positives" — 验证了我们接受适度误报换取安全的设计。
- **生命周期治理**: Microsoft 标准为 Legacy(30d) → Deprecated(90d) → Retired。我们 7 级细粒度状态适合当前项目规模。

### Step 4: Simulation
- 4 个场景全部通过主干路径
- 暴露 2 个边界问题：Crisis 关键词偏窄、Threshold 加载方式未定义
- 整体闭环可行，无阻塞性断裂

### Step 5: Lock
- 8 项已知不一致已记录，输入 Round 2 修复
- 01/02/04/05/06 文件结构完整
- 🔒 **Round 1 Locked** — 进入 Round 2 修订

---

## Round 2 经验

### 待记录
- Round 2 修订将在执行后记录
