# v1.21 标签体系定义 (LABEL_DEFINITION)

> **日期**: 2026-05-01
> **迭代**: v1.21-real-data-structured-risk-model
> **数据源**: `student_mental_health_enhanced.csv`

---

## 一、标签来源说明

> ⚠️ **重要声明**: 本数据集的五级风险标签为 **派生标签 (Derived Labels)**，非临床专业标注。
> Ground-truth 仅包含二元 Depression (Yes/No)。五级标签通过 Depression、Anxiety、
> Panic_Attack、Treatment_Seek、Stress_Level 联合规则构造。
>
> 这在报告中已明确说明，符合 v1.21 计划第 4.2 节的要求。

---

## 二、数据字段作为标签来源

| 字段 | 类型 | 角色 |
|------|------|------|
| Depression | Yes/No | **二分类目标标签** |
| Anxiety | Yes/No | 五级标签构造输入 |
| Panic_Attack | Yes/No | 五级标签构造输入 |
| Treatment_Seek | Yes/No | 五级标签构造输入 |
| Stress_Level | 1-10 | 五级标签构造输入 |

---

## 三、二分类标签 (Binary Label)

### 定义

```
0 = 无抑郁 (Depression = "No")
1 = 有抑郁 (Depression = "Yes")
```

### 分布

| 标签 | 含义 | 样本数 | 比例 |
|------|------|--------|------|
| 0 | None/Low Risk | 806 | 80.6% |
| 1 | Risk | 194 | 19.4% |

- **不平衡比例**: 1:4.15 (中度不平衡)
- **处理策略**: `class_weight='balanced'` + 可选 SMOTE (采样比 ≤ 0.8:1)

### 编码

```python
binary_label = 1 if row['Depression'] == 'Yes' else 0
```

---

## 四、五级风险标签 (Five-Level Risk Label)

### 级别定义

| 级别 | 编码 | 名称 | 描述 |
|------|------|------|------|
| Level 0 | 0 | None (无风险) | 无抑郁、无焦虑、无惊恐、压力正常 |
| Level 1 | 1 | Mild (轻度) | 有焦虑或惊恐但无抑郁，或压力偏高 |
| Level 2 | 2 | Moderate (中度) | 轻度抑郁或多种症状叠加 |
| Level 3 | 3 | High (高度) | 确诊抑郁，伴焦虑或治疗 |
| Level 4 | 4 | Critical (极重) | 抑郁 + 惊恐 + 治疗，或多项高危因子叠加 |

### 派生规则 (评分法)

由于数据集没有天然的五级标签，采用 **加权评分 → 阈值映射** 的方式构造：

#### Step 1: 评分

```python
score = 0
if Depression == 'Yes':       score += 2
if Anxiety == 'Yes':          score += 1
if Panic_Attack == 'Yes':     score += 2
if Treatment_Seek == 'Yes':   score += 1
if Stress_Level >= 8:         score += 1   # 高压力加分
```

得分范围: 0-7

#### Step 2: 映射

```python
if score >= 5:      return 4  # Critical
elif score >= 3:    return 3  # High
elif score >= 2:    return 2  # Moderate
elif score >= 1:    return 1  # Mild
else:               return 0  # None
```

### 分布

| 级别 | 编码 | 样本数 | 比例 |
|------|------|--------|------|
| None | 0 | 425 | 42.5% |
| Mild | 1 | 273 | 27.3% |
| Moderate | 2 | 91 | 9.1% |
| High | 3 | 128 | 12.8% |
| Critical | 4 | 83 | 8.3% |

### 权重说明

| 因素 | 权重 | 理由 |
|------|------|------|
| Depression | ×2 | 核心诊断标准，抑郁是主要风险指标 |
| Panic_Attack | ×2 | 惊恐发作是严重心理健康危机的强信号 |
| Anxiety | ×1 | 常见共病，但单独不足以判定高风险 |
| Treatment_Seek | ×1 | 寻求治疗暗示症状已影响日常生活 |
| Stress ≥ 8 | ×1 | 高压力是风险放大器 |

### 典型样本示例

| Depression | Anxiety | Panic | Treatment | Stress | Score | Level |
|------------|---------|-------|-----------|--------|-------|-------|
| No | No | No | No | 3 | 0 | 0 (None) |
| No | Yes | No | No | 5 | 1 | 1 (Mild) |
| No | Yes | Yes | No | 6 | 3 | 3 (High) |
| Yes | No | No | No | 5 | 2 | 2 (Moderate) |
| Yes | Yes | No | No | 7 | 3 | 3 (High) |
| Yes | No | Yes | No | 6 | 4 | 3 (High) |
| Yes | Yes | Yes | No | 8 | 6 | 4 (Critical) |
| Yes | Yes | Yes | Yes | 9 | 7 | 4 (Critical) |

---

## 五、标签关系验证

### Five-Level vs Binary (Cross-Tab)

| Five-Level | Binary=0 (无抑郁) | Binary=1 (有抑郁) |
|------------|------------------|-------------------|
| 0 (None) | 425 | 0 |
| 1 (Mild) | 273 | 0 |
| 2 (Moderate) | 91 | 0 |
| 3 (High) | 17 | 111 |
| 4 (Critical) | 0 | 83 |

> 注: Level 3 中的 17 个非抑郁样本 (No+Yes+Yes 组合)，虽然有焦虑+惊恐但无抑郁

### 一致性检查

- 所有 Depression=Yes 的样本 ≥ Level 2 (符合预期: 抑郁至少是中风险)
- 所有 Level 4 的样本都有 Depression=Yes (符合预期)
- 17 个无抑郁但 Level 3 的样本: 皆因 Anxiety+Panic_Attack 叠加产生 (焦虑+惊恐本身就值得关注)

---

## 六、训练/评估注意事项

### 二分类模型
- **目标**: y ∈ {0, 1}
- **输入**: 14 个结构化特征 (排除 Depression、Anxiety、Panic_Attack、Treatment_Seek 中的标签相关列，仅保留 Anxiety/Panic_Attack/Treatment_Seek 作为特征)
- **注意**: 这里 Anxiety、Panic_Attack、Treatment_Seek **既是特征输入，也是五级标签的构造输入**。对于二分类任务，它们作为特征是合法的（因为它们在实际预测时也是可观测的）

### 五级模型
- **目标**: y ∈ {0, 1, 2, 3, 4}
- **输入**: 仅 10 个基础结构化特征 (排除 5 个标签构造列: Depression, Anxiety, Panic_Attack, Treatment_Seek, Stress_Level)
- ⚠️ **关键**: 五级模型训练时，必须从特征中**移除**用于构造标签的列，否则就是 100% 的数据泄漏！
- 这意味着五级模型只能用 10 个特征训练（题中应有之义: 五级模型应该只基于问卷无法直接回答的行为/生理特征来推断风险）

### 特征分集

```
用于二分类 (14 features):
  age, gender, study_year, cgpa, stress_level, sleep_duration,
  social_support, financial_pressure, family_history, academic_pressure,
  exercise_frequency, anxiety, panic_attack, treatment_seeking

用于五级 (10 features — 排除标签构造列):
  age, gender, study_year, cgpa, sleep_duration,
  social_support, financial_pressure, family_history,
  academic_pressure, exercise_frequency
```
