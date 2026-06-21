# v1.24 Round 1 经验记录 (Learnings)

> **日期**: 2026-05-02
> **来源**: Round 1 (草稿 → 自查 → 调研 → 推演 → 锁定)

---

## 一、Round 1 自查发现的问题

| # | 问题 | 严重程度 |
|---|------|----------|
| 1 | mmpsy 数据资产信息缺失（路径、规模、字段清单） | 🔴 |
| 2 | v1.23 Feature Schema 未显式引用（仅说"12 个特征"） | 🔴 |
| 3 | Delta 分析与 Score Adapter 的依赖关系未声明 | 🟡 |
| 4 | 外部验证 Ground Truth 定义模糊 | 🟡 |
| 5 | 监控落地方案不具体（存储/告警渠道） | 🟠 |
| 6 | 3.5(监控) 和 3.6(注册表) 缺交付物和验收标准 | 🟠 |
| 7 | mmpsy 验证失败后策略不完整 | 🔵 |
| 8 | Phase 0 未作为独立前置步骤 | ⚪ |

---

## 二、调研关键发现

### 2.1 mmpsy 数据现状
- 路径: `data/external/mmpsy_scores.csv`
- 样本量: **1275**
- 仅 9 个字段: user_id, phq9_score, phq9_level, phq9_binary, gad7_score, gad7_level, gad7_binary, audio_count, audio_transcript
- PHQ-9 均值 6.7, 阳性率 20%; GAD-7 均值 3.8, 阳性率 11%
- `external_validation_metrics.json` 已明确标注 `model_inference_possible: false`

### 2.2 v1.23 Feature Schema (12 特征)
- age, gender, cgpa, stress_level, sleep_duration, social_support, financial_pressure, family_history, academic_pressure, exercise_frequency, anxiety, panic_attack
- 预处理: SimpleImputer(median) + StandardScaler

### 2.3 mmpsy 字段映射现实
- **0 个字段可直接映射**
- 3 个可规则派生（stress_level ← phq9_score, anxiety ← gad7_score, panic_attack ← crisis keyword）
- 3 个可从音频文本低置信度提取
- 6 个完全不可映射（仅能 median 填充）
- 预估覆盖率: **30-50%**

### 2.4 现有代码基础设施
- `model_engine.py` L565-604: v1.23 实验路径（已有）
- `model_engine.py` L624-636: Delta 监控计数器（已有）
- `model_registry.py`: v1.21 multiclass 已 disabled，但缺少 lifecycle 五态枚举
- `model_engine.py` L530: v1.21 binary LR 实验路径硬编码引用

### 2.5 监控现状
- 全部在内存中 (`monitoring_counters` dict)
- `get_metrics_snapshot()` 可 API 查询
- 无持久化、无告警、重启丢失

---

## 三、推演核心发现

### 3.1 mmpsy 覆盖率矛盾 ⚠️ 最重要
mmpsy 特征覆盖率几乎不可能达到 80%。v1.24 的实际交付应为：
1. 证明 mmpsy 不能做完整外部验证的原因
2. 给出"受限验证"的最佳结果
3. 通过 delta 分析和 Score Adapter 证明评分稳定性可控

### 3.2 回归到均值风险
大量特征用中位数填充 → 模型把样本推向"平均风险" → 高风险被低估、低风险被高估。需在验证报告中单独分析。

### 3.3 分段边界不连续
分段单调映射在区间边界可能跳变。解决: 在分段点 ±3 分缓冲区线性插值过渡。

### 3.4 监控重启丢失
决策依赖"连续监控周期稳定"，但重启后基线从零开始。解决: 增加 `uptime_seconds`。

### 3.5 注册表影响 model_engine
v1.21 实验路径 (L530) 硬编码引用，需先修改 model_engine 再做注册表清理。

### 3.6 Phase 1 和 Phase 3 可并行
mmpsy 特征构建 与 Delta 分层分析 互不依赖，可并行执行。

---

## 四、Round 2 修订方向建议

### 必须修正 (绑定到 Round 2 Draft)
1. **mmpsy 覆盖率预期**: 从 80% → 30-50%，验收标准改为"受限验证"而非"完整验证"
2. **Phase 0 独立前置**: 资产审计必须在特征构建之前
3. **Delta → Adapter 依赖**: 显式声明在依赖关系图中
4. **监控持久化方案**: 60s JSON 快照

### 建议深化 (Round 2 自查重点)
5. Score Adapter 分段点是否可以通过 delta 分析数据自动推导（而非手动设定 5 区间）
6. 是否需要单独设计 mmpsy 的"受限验证报告模板"（标准化受限声明的措辞）
7. 注册表 lifecycle 枚举是否会影响现有 API 或前端逻辑（需在 Round 2 调研中检查）

### 风险项 (Round 2 推演重点)
8. 如果 mmpsy AUC < 0.65 且覆盖率 < 30%，v1.24 的 P0 交付是否还有意义？
9. 如果 Score Adapter 的 Pareto 前沿显示 AUC 损失 > 0.05 才能让 Mean Abs Delta < 15，是否接受？

---

## 五、Round 2 重点关注领域

| 优先级 | 领域 | 当前状态 |
|--------|------|----------|
| P0 | mmpsy 受限验证的"可接受下限"定义 | Round 1 已提出三级降级，需精确定义 |
| P0 | Score Adapter 分段点的自动化推导 | 当前为手动 5 区间，Round 2 考虑数据驱动 |
| P1 | 前端现有实验分数展示代码的审计 | 未调研，Round 2 需补充 |
| P1 | 注册表 lifecycle 对现有 API 的影响分析 | 未调研，Round 2 需补充 |

---

> **状态**: Round 1 完成 | 下一步: Round 2
