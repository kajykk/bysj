# v1.22 方案数据审计报告 (DATA_AUDIT_REPORT)

> **日期**: 2026-05-01  
> **迭代**: v1.22-risk-model-scheme  
> **报告类型**: 方案审计版  
> **审计依据**: v1.21 真实数据结构化风险模型报告集

---

## 一、审计目标

v1.22 的数据审计目标不是重新声明 v1.21 已完成的训练结果，而是基于 v1.21 的真实数据发现，明确下一版风险模型方案的数据边界、可用数据源、不可用数据源、标签风险和后续采集要求。

核心问题包括：

1. 当前数据是否足以支撑二分类风险识别；
2. 当前数据是否足以支撑独立五级风险分类；
3. 哪些字段可以作为稳定输入特征；
4. 哪些字段存在标签构造或数据泄漏风险；
5. v1.22 应优先补齐哪些数据资产。

---

## 二、现有数据资产结论

| 数据源 | 样本量 | v1.20/1.21 特征覆盖 | 标签能力 | v1.22 用途建议 |
|--------|--------|--------------------|----------|----------------|
| `student_mental_health_enhanced.csv` | 1,000 | 14/14 | Depression 二分类天然标签；五级标签需派生 | 主基准集，继续作为 v1.22 方案验证基线 |
| `student_mental_health_robust_features.csv` | 1,000 | 14/14 + 衍生特征 | 含 Risk_Level，但存在泄漏风险 | 仅用于特征审计，不直接训练主模型 |
| `student_depression_dataset.csv` | 27,901 | 约 7/14 可映射 | Depression 二分类标签 | 作为大样本迁移/外部验证候选集 |
| `student_mental_health_original.csv` | 101 | 严重缺字段 | 不稳定 | 不纳入 v1.22 建模 |
| `student_mental_health.csv` | 101 | 问卷原始字段，不完整 | 不稳定 | 不纳入 v1.22 建模 |
| `enhanced_structured_features.csv` | 10 | 特征体系不同 | 样本过少 | 不纳入 v1.22 建模 |

---

## 三、v1.22 数据使用边界

### 3.1 主数据集

v1.22 继续以 `student_mental_health_enhanced.csv` 作为方案基准数据集，原因如下：

- 14 个结构化特征完整覆盖；
- 无缺失值、无重复行；
- Depression 字段可作为二分类 ground truth；
- 与 v1.20 线上结构化输入兼容；
- 已在 v1.21 中完成真实模型训练和指标审计。

### 3.2 辅助数据集

`student_depression_dataset.csv` 样本量充足，但字段覆盖不足。v1.22 中建议定位为：

- 外部验证候选；
- 大样本弱监督实验候选；
- 用于检验年龄、性别、CGPA、学业压力、经济压力、睡眠等通用字段的泛化表现；
- 不直接替换主训练集。

### 3.3 禁用数据集

以下数据不进入 v1.22 主方案：

- 样本量过小的数据；
- 字段缺失严重的数据；
- 含有不可解释衍生标签且可能由目标字段构造的数据；
- 与线上结构化特征体系差异过大的数据。

---

## 四、特征审计结论

### 4.1 稳定输入特征

v1.22 继续保留以下 14 个结构化特征作为二分类方案输入：

```text
age, gender, study_year, cgpa, stress_level,
sleep_duration, social_support, financial_pressure,
family_history, academic_pressure, exercise_frequency,
anxiety, panic_attack, treatment_seeking
```

### 4.2 五级风险输入特征

五级风险如果仍使用派生标签，则必须移除标签构造列，建议输入限制为 10 个基础特征：

```text
age, gender, study_year, cgpa, sleep_duration,
social_support, financial_pressure, family_history,
academic_pressure, exercise_frequency
```

但 v1.21 已证明，仅使用这 10 个基础特征无法支撑可靠五级分类。因此 v1.22 不建议训练独立五级模型，而建议采用二分类概率分档。

---

## 五、数据泄漏审计

| 风险点 | 等级 | v1.22 处理策略 |
|--------|------|----------------|
| 使用 Depression 预测 Depression | 高 | 禁止 |
| 使用 Risk_Level / Mental_Health_Risk_Score 训练主模型 | 高 | 禁止，除非明确其构造逻辑 |
| 五级模型使用 Anxiety/Panic/Treatment/Stress 作为输入 | 高 | 禁止，因为这些字段参与五级标签构造 |
| 二分类模型使用 Anxiety/Panic/Treatment | 中 | 允许，前提是实际业务中这些字段可观测 |
| 使用 `student_depression_dataset.csv` 填充缺失字段 | 中 | 仅允许在外部验证或弱监督实验中使用 |

---

## 六、关键数据事实

v1.21 已发现：

1. Depression 二分类标签分布为 806:194，正样本占 19.4%；
2. 二分类任务存在中度类别不平衡；
3. 五级派生标签中 Moderate、Critical 样本较少；
4. 基础人口学/行为特征与 Depression 的相关性极弱；
5. Anxiety、Treatment_Seeking、Panic_Attack 是真实二分类模型的核心有效信号；
6. 独立五级分类的数据基础不足。

---

## 七、v1.22 数据方案建议

### 短期方案

- 继续保留 `student_mental_health_enhanced.csv` 作为基线；
- 不新增独立五级模型训练；
- 使用二分类概率 + 阈值映射生成五级风险；
- 将 v1.21 Real Binary LR 保持为实验参考模型；
- 生产默认仍保持 v1.20 或 heuristic fallback。

### 中期数据补齐

v1.22 后续如要推进真实模型替代，需要补齐：

| 数据项 | 目标 |
|--------|------|
| PHQ-9 | 作为更细粒度抑郁严重程度标签 |
| GAD-7 | 作为焦虑严重程度标签 |
| 睡眠质量 | 替代单一睡眠时长 |
| 行为时间序列 | 提升动态风险识别能力 |
| 文本情绪特征 | 捕获结构化问卷无法覆盖的心理状态 |
| 临床或咨询师复核标签 | 提升标签可信度 |

---

## 八、审计结论

v1.22 的数据基础可以支撑“真实数据二分类风险参考模型 + 阈值分档方案”，但不足以支撑“独立五级风险分类模型上线”。

因此，v1.22 数据策略应从“继续训练更多模型”转向“明确真实数据边界、收敛风险分档方案、建立监控基线、规划高质量标签采集”。
