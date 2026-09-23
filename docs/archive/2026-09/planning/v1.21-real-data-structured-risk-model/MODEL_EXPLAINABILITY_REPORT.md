# v1.21 模型解释性报告 (MODEL_EXPLAINABILITY_REPORT)

> **日期**: 2026-05-01
> **迭代**: v1.21-real-data-structured-risk-model

---

## 一、LogisticRegression 特征重要性 (系数分析)

| 排名 | 特征 | 系数 | 方向 | 解释 |
|------|------|------|------|------|
| 1 | **anxiety** | +1.2986 | 🔴 风险 | 焦虑是抑郁的最强预测因子 — 临床高度共病 |
| 2 | **treatment_seeking** | +0.9959 | 🔴 风险 | 已寻求治疗 → 症状已达到临床关注水平 |
| 3 | **panic_attack** | +0.8324 | 🔴 风险 | 惊恐发作 → 严重的焦虑谱系症状 |
| 4 | **sleep_duration** | -0.4997 | 🟢 保护 | 充足睡眠是心理健康的重要保护因子 |
| 5 | **academic_pressure** | +0.2920 | 🔴 风险 | 学业压力与抑郁正相关（但弱） |
| 6 | **social_support** | -0.2043 | 🟢 保护 | 社交支持是保护因子 |
| 7 | **family_history** | +0.1935 | 🔴 风险 | 家族史轻微增加风险 |
| 8 | **study_year** | +0.1656 | 🔴 风险 | 高年级学生风险略高 |
| 9 | **stress_level** | +0.1581 | 🔴 风险 | 压力水平影响微弱（见下文分析） |
| 10 | **cgpa** | -0.0982 | 🟢 保护 | 成绩好轻微保护 |
| 11 | **exercise_frequency** | -0.0604 | 🟢 保护 | 运动有微弱保护作用 |
| 12 | **financial_pressure** | +0.0499 | 🔴 风险 | 经济压力影响极弱 |
| 13 | **gender** | -0.0321 | 🟢 保护 | 性别影响极小（Male=1, Female=0） |
| 14 | **age** | -0.0069 | 🟢 保护 | 年龄影响可忽略 |

---

## 二、RandomForest 特征重要性 (Gini Impurity)

| 排名 | 特征 | 重要性 |
|------|------|--------|
| 1 | anxiety | 0.2319 |
| 2 | treatment_seeking | 0.1653 |
| 3 | sleep_duration | 0.1063 |
| 4 | panic_attack | 0.0849 |
| 5 | cgpa | 0.0848 |
| 6 | age | 0.0608 |
| 7 | stress_level | 0.0583 |
| 8 | social_support | 0.0397 |
| 9 | exercise_frequency | 0.0384 |
| 10 | study_year | 0.0378 |
| 11 | academic_pressure | 0.0326 |
| 12 | financial_pressure | 0.0290 |
| 13 | gender | 0.0162 |
| 14 | family_history | 0.0143 |

### 两种模型的一致性

| 发现 | LR | RF | 一致? |
|------|----|----|-------|
| anxiety 是最重要特征 | ✅ #1 | ✅ #1 | 完全一致 |
| treatment_seeking 第二 | ✅ #2 | ✅ #2 | 完全一致 |
| sleep_duration 第三/四 | ✅ #4 (保护) | ✅ #3 | 一致 |
| panic_attack 重要 | ✅ #3 | ✅ #4 | 一致 |
| 基础特征影响小 | ✅ 系数低 | ✅ 重要性低 | 完全一致 |

---

## 三、核心洞察：基础特征与 Depression 几乎零相关

### 特征 vs Depression 的相关系数

| 特征 | Pearson r | 解读 |
|------|-----------|------|
| Stress_Level | **0.007** | 几乎零相关 ⚠️ |
| Family_History | 0.064 | 极弱 |
| Academic_Pressure | 0.037 | 极弱 |
| Financial_Stress | 0.031 | 极弱 |
| Social_Support | -0.039 | 极弱 |
| Exercise_Frequency | -0.051 | 极弱 |
| Sleep_Hours | -0.058 | 极弱 |

> ⚠️ **关键发现**: 在这个数据集中，压力水平、睡眠时间、社交支持等基础行为/人口学特征与抑郁诊断的相关性接近于零。这意味着仅凭这些"客观"指标无法有效预测抑郁。模型主要依赖 Anxiety + Panic_Attack + Treatment_Seeking 这三个与抑郁高度共病的二元指标来做出预测。

---

## 四、Top Risk Factors & Protective Factors

```json
{
  "top_risk_factors": [
    {"feature": "anxiety", "weight": 1.30, "context": "焦虑与抑郁高度共病 (comorbidity rate ~70%)"},
    {"feature": "treatment_seeking", "weight": 1.00, "context": "主动寻求治疗暗示症状已影响功能"},
    {"feature": "panic_attack", "weight": 0.83, "context": "惊恐发作是严重焦虑的标志"},
    {"feature": "academic_pressure", "weight": 0.29, "context": "学业压力轻微增加风险"},
    {"feature": "family_history", "weight": 0.19, "context": "家族史有弱的预测价值"}
  ],
  "protective_factors": [
    {"feature": "sleep_duration", "weight": -0.50, "context": "充足睡眠是最重要的可改变保护因子"},
    {"feature": "social_support", "weight": -0.20, "context": "社交支持是显著的保护因子"},
    {"feature": "cgpa", "weight": -0.10, "context": "学业表现好轻微保护"},
    {"feature": "exercise_frequency", "weight": -0.06, "context": "规律运动有弱的保护作用"}
  ]
}
```

---

## 五、每级风险的特征画像

| 风险级别 | 样本数 | 平均压力 | 平均睡眠 | 平均社交 | 抑郁率 | 焦虑率 |
|---------|--------|---------|---------|---------|--------|--------|
| 0 (None) | 425 | 4.2 | 6.5h | 3.0/5 | 0% | 0% |
| 1 (Mild) | 273 | 7.3 | 6.5h | 2.9/5 | 0% | 26% |
| 2 (Moderate) | 91 | 5.9 | 6.5h | 3.0/5 | 13% | 34% |
| 3 (High) | 128 | 5.9 | 6.4h | 2.9/5 | 77% | 63% |
| 4 (Critical) | 83 | 6.1 | 6.4h | 2.9/5 | 100% | 78% |

**注意**: 各风险级别的睡眠和社交支持平均值几乎相同（6.4-6.5h, 2.9-3.0/5）。这再次说明基础行为特征无法区分不同的风险等级——区分度完全来自 Depression + Anxiety + Panic_Attack 的组合状态。

---

## 六、实际意义

### 对系统的启示

1. **不要对行为特征的预测能力抱过高期望**：仅凭年龄、性别、CGPA、睡眠时间预测抑郁几乎不可能
2. **Anxiety 是比 Stress 更有价值的信号**：压力水平 (r=0.007) 几乎无用，但焦虑 (coef=+1.30) 是最强预测因子
3. **睡眠是最可操作的保护因子**：每增加1小时睡眠，对数几率降低0.50
4. **需要更丰富的信号源**：文本分析（日记情绪）、生理数据（HRV）可能比单纯的结构化特征更有价值

### 对临床的启示

- 焦虑和抑郁在该人群中高度共病（72%的抑郁者也报告焦虑）
- 应同时对焦虑和抑郁进行筛查，而不是单独筛查
- 基础问卷特征（年龄、性别、成绩等）的筛查价值有限
