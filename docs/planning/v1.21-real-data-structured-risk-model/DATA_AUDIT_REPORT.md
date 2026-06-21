# v1.21 数据资产审计报告 (DATA_AUDIT_REPORT)

> **日期**: 2026-05-01
> **迭代**: v1.21-real-data-structured-risk-model
> **审计范围**: `datasets/structured/` 下全部 6 个数据源

---

## 一、v1.20 基准特征集 (14 Features)

```
age, gender, study_year, cgpa, stress_level,
sleep_duration, social_support, financial_pressure,
family_history, academic_pressure, exercise_frequency,
anxiety, panic_attack, treatment_seeking
```

---

## 二、数据源总览

| # | 文件名 | 样本数 | 字段数 | 缺失值 | 重复行 | 可用性评级 |
|---|--------|--------|--------|--------|--------|-----------|
| 1 | `student_mental_health_enhanced.csv` | 1,000 | 15 | 0 | 0 | ⭐⭐⭐ 最佳 |
| 2 | `student_mental_health_robust_features.csv` | 1,000 | 39 | 146 (Risk_Level) | 0 | ⭐⭐ 已有衍生特征 |
| 3 | `student_depression_dataset.csv` | 27,901 | 18 | 0 | 0 | ⭐⭐ 样本量大但特征不完整 |
| 4 | `student_mental_health_original.csv` | 101 (74有效) | 8 | 101 (Year_of_Study全空) | 27 | ⭐ 不可用 |
| 5 | `student_mental_health.csv` | 101 | 11 | 1 (Age) | 0 | ⭐ 不可用 |
| 6 | `enhanced_structured_features.csv` | 10 | 20 | 0 | 0 | ❌ 样本量过小 |

---

## 三、逐文件详细审计

### 3.1 `student_mental_health_enhanced.csv` — ⭐⭐⭐ 推荐主训练集

| 原始字段 | 类型 | v1.20特征映射 | 值范围 | 编码要求 |
|---------|------|-------------|--------|---------|
| Age | int | age | 18-29, mean=23.45 | 可直接用 |
| Gender | object | gender | Female(579), Male(421) | Female→0, Male→1 (与v1.20一致) |
| Year_of_Study | int | study_year | 1-4, mean=2.33 | v1.20期望1-6, 范围有差异但可用 |
| CGPA | float | cgpa | 1.17-4.0, mean=3.21 | 可直接用 |
| Stress_Level | int | stress_level | 1-10, mean=5.56 | 需归一化到0-5: stress/2 或重缩放到0-5 |
| Sleep_Hours | float | sleep_duration | 3.0-10.0, mean=6.49 | 可直接用 |
| Social_Support | int | social_support | 1-5, mean=2.95 | 可直接用 |
| Financial_Stress | object | financial_pressure | Low(288)/Medium(490)/High(222) | Low→1, Medium→3, High→5 |
| Family_History | object | family_history | No(795)/Yes(205) | No→0, Yes→1 |
| Academic_Pressure | object | academic_pressure | Low(206)/Medium(511)/High(283) | Low→1, Medium→3, High→5 |
| Exercise_Frequency | object | exercise_frequency | Never(144)/Rarely(248)/Sometimes(371)/Often(237) | Never→0, Rarely→1, Sometimes→2, Often→3 |
| Depression | object | **目标标签** | No(806)/Yes(194) | No→0, Yes→1 |
| Anxiety | object | anxiety | No(751)/Yes(249) | No→0, Yes→1 |
| Panic_Attack | object | panic_attack | No(853)/Yes(147) | No→0, Yes→1 |
| Treatment_Seek | object | treatment_seeking | No(862)/Yes(138) | No→0, Yes→1 |

**标签分布**:
- Depression=Yes: 194 (19.4%)
- Depression=No: 806 (80.6%)
- **类别不平衡比例**: 约 1:4.15 — 中度不平衡，需 class_weight 或 SMOTE 处理

**优势**:
1. 全部 14 特征可直接映射
2. 0 缺失值
3. 特征分布与 v1.20 假设一致
4. Depression 作为 ground-truth 二元标签天然存在

**风险**:
1. 1,000 样本对 ML 来说偏少（但可接受）
2. Stress_Level 范围 1-10 与 v1.20 期望 0-5 不一致
3. 多个特征需要 ordinal 编码（可能引入偏差）

---

### 3.2 `student_depression_dataset.csv` — ⭐⭐ 大样本辅助集

| 样本量 | 27,901 |
|--------|--------|
| 目标变量 | Depression (0/1) |
| Depression=1 比例 | 58.6% (16,421/27,901) — 较均衡 |

**特征映射分析**:

| 原始字段 | v1.20映射 | 可行性 | 问题 |
|---------|----------|--------|------|
| Age | age | ✅ | 18-59, mean=25.82, 但 v1.20 期望 18-28 |
| Gender | gender | ✅ | 需编码 Female/Male→0/1 |
| CGPA | cgpa | ⚠️ | 范围 0-10, 需归一化到 1-4 (除以2.5) |
| Academic Pressure | academic_pressure | ✅ | 0-5, 可直接用 |
| Sleep Duration | sleep_duration | ⚠️ | 分类值: 'Less than 5 hours'→3, '5-6 hours'→5.5, '7-8 hours'→7.5, 'More than 8 hours'→9, Others→NaN |
| Financial Stress | financial_pressure | ⚠️ | 字符串 "1.0"-"5.0", 需解析 |
| Family History of Mental Illness | family_history | ✅ | Yes/No→1/0 |
| Have you ever had suicidal thoughts ? | (额外) | ✅ | 可用作辅助标签或特征 |
| Depression | (目标标签) | ✅ | 0/1 已编码 |
| Profession | study_year? | ❌ | 不能替代 study_year |
| Work Pressure / Job Satisfaction | — | ❌ | 几乎全部为 0 |

**不可映射的 v1.20 特征**:
- ❌ **study_year** — 数据集中无直接对应字段
- ❌ **stress_level** — 无独立压力等级
- ❌ **social_support** — 无社交支持
- ❌ **exercise_frequency** — 无运动频率
- ❌ **anxiety** — 无焦虑指标
- ❌ **panic_attack** — 无惊恐发作
- ❌ **treatment_seeking** — 无治疗寻求

**结论**: 只能映射 7/14 特征。除非接受缺失特征用 0 或中位数填充（会损失信息），否则不能独立作为训练集。

**潜在价值**: 可作为增强验证集或用于 suicidal thoughts 子任务。

---

### 3.3 `student_mental_health_robust_features.csv` — ⭐⭐ 含衍生特征

- 与 3.1 的 `enhanced` 版本**原始字段完全一致**（相同 15 列基础特征）
- 额外包含 24 个衍生特征:
  - `Mental_Health_Risk_Score` (1-16) — 合成风险总分
  - `Risk_Level` (Low/Medium/High) — 三级风险标签 (但 146 个缺失)
  - `Risk_Level_Encoded` (1-3)
  - 各种交互特征 (Stress_Sleep_Interaction 等)
- 注意: `Financial_Stress_Encoded` 全列为 NaN (1,000 缺失)

**风险**:
1. `Risk_Level` 仅有 Low/Medium/High 三级（需从中派生五级）
2. `Financial_Stress_Encoded` 全缺
3. 衍生特征的计算逻辑未知，存在数据泄漏风险（Risk_Level 可能基于 Depression + Anxiety 构造）

---

### 3.4 其他数据源

| 文件 | 结论 |
|------|------|
| `student_mental_health_original.csv` | Year_of_Study 全空, 27行重复, 不可用 |
| `student_mental_health.csv` | 101样本, 字段为问卷原始格式, 不可用 |
| `enhanced_structured_features.csv` | 仅10行, 不同特征体系, 不可用 |

---

## 四、特征映射汇总矩阵

| v1.20特征 | enhanced | robust | depression_dataset |
|-----------|----------|--------|-------------------|
| age | ✅ Age | ✅ Age | ✅ Age |
| gender | ✅ Gender | ✅ Gender | ✅ Gender |
| study_year | ✅ Year_of_Study | ✅ Year_of_Study | ❌ |
| cgpa | ✅ CGPA | ✅ CGPA | ⚠️ 需归一化 |
| stress_level | ⚠️ Stress_Level (1-10) | ⚠️ Stress_Level (1-10) | ❌ |
| sleep_duration | ✅ Sleep_Hours | ✅ Sleep_Hours | ⚠️ 分类转数值 |
| social_support | ✅ Social_Support | ✅ Social_Support | ❌ |
| financial_pressure | ⚠️ 3级序数 | ⚠️ 3级序数 | ⚠️ 字符串解析 |
| family_history | ✅ Family_History | ✅ Family_History | ✅ Family History |
| academic_pressure | ⚠️ 3级序数 | ⚠️ 3级序数 | ✅ Academic Pressure |
| exercise_frequency | ⚠️ 4级序数 | ⚠️ 4级序数 | ❌ |
| anxiety | ✅ Anxiety | ✅ Anxiety | ❌ |
| panic_attack | ✅ Panic_Attack | ✅ Panic_Attack | ❌ |
| treatment_seeking | ✅ Treatment_Seek | ✅ Treatment_Seek | ❌ |
| **可直接映射** | 7/14 | 7/14 | 1/14 |
| **需编码后映射** | 7/14 | 7/14 | 4/14 |
| **不可映射** | 0/14 | 0/14 | 9/14 |

---

## 五、数据泄漏风险评估

### 5.1 `student_mental_health_enhanced.csv`
- Anxiety、Panic_Attack、Treatment_Seek 与 Depression **高度相关但非泄漏** — 它们在真实场景中确实与抑郁共现
- 这些特征是输入特征而非标签，不存在泄漏
- **风险评估**: ✅ 无泄漏风险

### 5.2 `student_mental_health_robust_features.csv`
- `Mental_Health_Risk_Score` / `Risk_Level` 可能基于 Depression + Anxiety 构造
- 如果 Risk_Level 的计算使用了 Depression，那么用它作为目标标签会造成**目标泄漏**
- **风险评估**: ⚠️ 如果使用 Risk_Level 作为标签，必须先验证其与 Depression 的独立性

### 5.3 `student_depression_dataset.csv`
- suicidal thoughts 可能被用于构造 Depression 标签？不太可能（Depression可能是独立的临床标记）
- **风险评估**: ✅ 低风险

---

## 六、审计结论与建议

### 核心结论

| 结论 | 详情 |
|------|------|
| **推荐主训练集** | `student_mental_health_enhanced.csv` (1,000样本, 14特征全覆盖) |
| **目标标签 (二分类)** | Depression (Yes/No) — 天然 ground-truth |
| **目标标签 (五级)** | 需从 Depression + Anxiety + Panic_Attack + Stress_Level 派生 |
| **数据是否足够** | 1,000样本偏少但可接受，F1 ≥ 0.85 为挑战性目标 |
| **需要额外数据吗** | 如果 1,000 样本模型不达标，需考虑 `student_depression_dataset` 的 27,901 样本（含 suicidal thoughts） |

### 操作建议

1. **Phase 2 使用 `student_mental_health_enhanced.csv` 作为唯一训练数据源**
2. **编码策略**:
   - Stress_Level: `value / 2` 映射到 0-5 或保留 1-10 用 StandardScaler
   - 序数特征: 统一映射到 v1.20 的值范围
   - 二元特征: Yes→1, No→0
3. **五级标签派生规则**: 见 `LABEL_DEFINITION.md`
4. **`student_depression_dataset.csv`**: 保留作为 Phase 3 的额外验证集（使用可映射的 7 特征子集）
