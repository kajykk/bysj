# v1.21 五级风险模型训练报告 (MULTICLASS_RISK_MODEL_REPORT)

> **日期**: 2026-05-01
> **迭代**: v1.21-real-data-structured-risk-model
> **数据源**: `student_mental_health_enhanced.csv` (1,000 样本)

---

## 一、训练概况

| 项目 | 值 |
|------|-----|
| 特征数 | 10 (排除 Depression, Anxiety, Panic_Attack, Treatment_Seek, Stress_Level) |
| 特征列表 | age, gender, study_year, cgpa, sleep_duration, social_support, financial_pressure, family_history, academic_pressure, exercise_frequency |
| 标签类型 | 五级派生标签 (0=none, 1=mild, 2=moderate, 3=high, 4=critical) |
| 标签构造方法 | 加权评分法 (见 LABEL_DEFINITION.md) |
| 数据划分 | 70% Train / 15% Val / 15% Test |

### 标签分布

| Level | 名称 | Train | Test | 总计 | 比例 |
|-------|------|-------|------|------|------|
| 0 | None | 293 | 65 | 425 | 42.5% |
| 1 | Mild | 193 | 43 | 273 | 27.3% |
| 2 | Moderate | 60 | 16 | 91 | 9.1% |
| 3 | High | 93 | 17 | 128 | 12.8% |
| 4 | Critical | 61 | 9 | 83 | 8.3% |

---

## 二、Multinomial LogisticRegression

### 5-Fold CV

| Metric | Mean ± Std |
|--------|-----------|
| Accuracy | 0.1814 ± 0.0266 |
| F1 Macro | 0.1688 ± 0.0325 |
| F1 Weighted | 0.1928 ± 0.0262 |
| Precision Macro | 0.2007 ± 0.0238 |
| Recall Macro | 0.1979 ± 0.0476 |

### Test Set

| Metric | Value | Target | Pass |
|--------|-------|--------|------|
| Accuracy | 0.1333 | ≥ 0.70 | ❌ |
| F1 Macro | 0.1365 | — | — |
| **High/Critical Recall** | **0.6154** | ≥ 0.85 | ❌ |
| High/Critical Precision | 0.2388 | — | — |

### Per-Class

| Level | Support | Precision | Recall | F1 |
|-------|---------|-----------|--------|-----|
| 0 (None) | 65 | 0.222 | 0.062 | 0.096 |
| 1 (Mild) | 43 | 0.241 | 0.163 | 0.194 |
| 2 (Moderate) | 16 | 0.028 | 0.063 | 0.038 |
| 3 (High) | 17 | 0.182 | 0.235 | 0.205 |
| 4 (Critical) | 9 | 0.089 | 0.444 | 0.148 |

---

## 三、RandomForest

### 5-Fold CV

| Metric | Mean ± Std |
|--------|-----------|
| Accuracy | 0.3229 ± 0.0139 |
| F1 Macro | 0.1848 ± 0.0126 |
| F1 Weighted | 0.3023 ± 0.0132 |

### Test Set

| Metric | Value | Target | Pass |
|--------|-------|--------|------|
| Accuracy | 0.3200 | ≥ 0.70 | ❌ |
| F1 Macro | 0.1921 | — | — |
| **High/Critical Recall** | **0.1154** | ≥ 0.85 | ❌ |
| High/Critical Precision | 0.1304 | — | — |

### Per-Class

| Level | Support | Precision | Recall | F1 |
|-------|---------|-----------|--------|-----|
| 0 (None) | 65 | 0.368 | 0.492 | 0.421 |
| 1 (Mild) | 43 | 0.382 | 0.302 | 0.338 |
| 2 (Moderate) | 16 | 0.167 | 0.063 | 0.091 |
| 3 (High) | 17 | 0.105 | 0.118 | 0.111 |
| 4 (Critical) | 9 | 0.000 | 0.000 | 0.000 |

> ⚠️ RF 对 Level 4 (Critical) 的预测完全失败 (precision=0, recall=0)

---

## 四、模型对比

| Metric | LR-Multinomial | RandomForest | Winner |
|--------|---------------|-------------|--------|
| Accuracy | 0.1333 | 0.3200 | RF |
| F1 Macro | 0.1365 | 0.1921 | RF |
| High/Critical Recall | 0.6154 | 0.1154 | LR |
| High/Critical Precision | 0.2388 | 0.1304 | LR |

---

## 五、校准样本测试

| 样本 | Expected | LR Pred | RF Pred |
|------|----------|---------|---------|
| 完全健康 | none | moderate ❌ | none ✅ |
| 轻度风险(压力高) | mild/moderate | high ❌ | mild ✅ |
| 中度风险 | moderate/high | critical ⚠️ | none ❌ |
| 高风险 | high/critical | critical ✅ | none ❌ |

RF 倾向预测低风险 (过于保守)，LR 倾向预测高风险 (过于激进)。

---

## 六、失败原因分析

### 根本原因

1. **信息瓶颈**: 5 个标签构造列 (Depression, Anxiety, Panic_Attack, Treatment_Seek, Stress_Level) 包含了标签的主要判别信息，但我们为了防泄漏必须排除它们。剩余的 10 个特征 (年龄、性别、CGPA、睡眠等) 与风险等级的关联性较弱。

2. **样本稀疏**: 5 级 × 700 训练样本 = 平均每级 140 样本，但 Moderate (60) 和 Critical (61) 严重不足。

3. **信号弱**: 用"性别、年龄、CGPA"预测"抑郁+焦虑+惊恐"的加权组合本身就缺乏理论基础。这些基础特征对心理健康的预测能力有限。

4. **五级建模 vs 二分类**: 二分类模型 ROC-AUC 可达 0.94 (区分度好)，但五级模型的表现差很多。这说明**把连续风险压缩到5级丢失了信息**。

### 对比 v1.20 合成数据

v1.20 合成模型的高指标是因为 heuristic fallback 生成了标签 → 二分类模型本质上在**自回归**。真实场景中不存在这种完美的信号对应关系。

---

## 七、建议

### 短期
- **不部署五级模型**（No-Go）
- 推荐使用 **v1.20 heuristic + 阈值分档** 或 **v1.21 Binary LR** 作为结构化风险输出
- 五级风险等级由 **二分类概率 + 校准阈值** 映射得到（而非训练专属五级模型）

### 中期
- 如果需要真正的五级分类，需要：
  1. **扩充数据**：≥5,000 样本，每级 ≥ 500 样本
  2. **增强特征**：加入 PHQ-9/GAD-7 分数、行为数据等（不依赖 Depression 标签的特征）
  3. **更丰富的信号**：生理数据（HRV/睡眠质量）、文本数据（日记情绪分析）

### 结论

**No-Go for five-level standalone model** — 当前数据条件下，五级分类模型不可行。风险等级应通过二分类概率 + 阈值方案实现。
