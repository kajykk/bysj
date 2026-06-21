# Phase 4 数据集调研报告 — 外部公开数据集补充方案

> **版本**: v1.22 Phase 4
> **日期**: 2026-05-01
> **目的**: 为后续迭代 (v1.23+) 补充 PHQ-9/GAD-7 临床标签，扩大真实样本规模，重新评估真实模型替代默认模型

---

## 八、Phase 4 实施记录 (2026-05-01)

### 8.1 已获取数据集

| 数据集 | 来源 | 路径 | 行数 | Gold Label |
|--------|------|------|:--:|------|
| mmpsy-data | GitHub | `data/external/mmpsy-data/` | 1,275 | PHQ-9 + GAD-7 总分 |
| Mendeley PHQ-9 v5 | Mendeley | `datasets/PHQ-9_Dataset_5th Edition.csv` | 682 | PHQ-9 总分 (0-27) |
| Kaggle Student Depression | Kaggle | `datasets/Student Depression Dataset.csv` | 27,870 (学生) | Depression binary |

### 8.2 特征对齐结果

已将 Kaggle 27k + Mendeley 682 条对齐到 v1.22 特征体系：

| 特征 | Kaggle 27k | Mendeley v5 | 映射方式 |
|------|:--:|:--:|------|
| age | ✅ | ✅ | 直接 |
| gender | ✅ | ✅ | Male→1, Female→0 |
| cgpa | ✅ 10分制 | ❌ (填默认3.0) | /10×4 缩放到4分制 |
| academic_pressure | ✅ (0-5) | ✅ 4级 | /5×4 缩放 |
| financial_pressure | ✅ (1-5) | ✅ 4级 | (-1)/4×4 缩放 |
| sleep_duration | ✅ 分类 | ✅ 4级 | 分类→小时映射 |
| family_history | ✅ Yes/No | ❌ (填0) | Yes→1, No→0 |
| panic_attack | ✅ (自杀念头代理) | ❌ (填0) | Yes→1, No→0 |
| stress_level | ✅ (= academic_pressure) | ✅ (= academic_pressure) | 代理 |
| social_support | ❌ (填2.0) | ❌ (填2.0) | 默认 |
| anxiety | ❌ (填代理) | ❌ (填代理) | 代理 |
| treatment_seeking | ❌ (填0) | ❌ (填0) | 默认 |
| exercise_frequency | ❌ (代理) | ❌ (代理) | 代理 |
| study_year | ❌ (填2) | ❌ (填2) | 默认 |

### 8.3 统一特征文件

- **路径**: `data/external/aligned_features.csv`
- **总行数**: 28,552 (27,870 Kaggle + 682 Mendeley)
- **标签分布**: Kaggle 58.4%阳性 / Mendeley 47.1% PHQ-9≥10
- **待补**: mmpsy 的结构化特征（仅含量表分+转录文本，需额外映射处理）

## 一、核心需求分析

当前盲点：
- v1.21 Real Binary LR 仅在 66 条真实数据上训练，严重过拟合
- 缺乏 PHQ-9 / GAD-7 等标准化临床量表作为 Gold Label
- 无法验证模型在临床意义上的有效性
- 需要至少 500+ 含 PHQ-9/GAD-7 总分的学生样本

## 二、候选数据集清单

### ⭐⭐⭐ 强烈推荐

| # | 名称 | 来源 | 规模 | 标签类型 | 人群 | URL |
|---|------|------|:--:|------|------|-----|
| 1 | **mmpsy-data** | GitHub (shuyeit) | 1,275 | PHQ-9 + GAD-7 总分 + MHT + 音频 | 广东中学生 (真实) | https://github.com/shuyeit/mmpsy-data |
| 2 | **PHQ-9 Student Depression v5** | Mendeley Data | 682 | PHQ-9 总分 (0-27) + 睡眠质量 + 学业压力 + 经济压力 | 大学生 17-26岁 | https://data.mendeley.com/datasets/kkzjk253cy/6 |
| 3 | **Social Media and Mental Health** | UMD BSOS | 3,056 | PHQ-9 + GAD-7 + 诊断史 + 用药/咨询 | 美国大学生 (48州) | https://bsos-data.umd.edu/en/dataset/social-media-and-mental-health |
| 4 | **Student Depression Dataset** | Kaggle | 27,901 | Depression(binary) + Academic Pressure + Sleep + Financial Stress | 印度大学生 | https://www.kaggle.com/datasets (搜索 student depression dataset) |

### ⭐⭐ 可选补充

| # | 名称 | 来源 | 规模 | 标签类型 | 人群 | URL |
|---|------|------|:--:|------|------|-----|
| 5 | **BD-Engg-MDD-Predictors** | Mendeley Data | 803 | PHQ-9 项 (MDD指标) + 生活方式 | 孟加拉工程学生 | https://data.mendeley.com/datasets/bvvpwb9b85/1 |
| 6 | **PHQ-9 Depression Assessment** | Kaggle/Zenodo | 14天 EMA | PHQ-9 9项逐题分 + mood rating | 普通人群 | https://www.kaggle.com/datasets/thedevastator/phq-9-depression-assessment |
| 7 | **Student Depression & Lifestyle 100k** | Kaggle | 100,000 | Depression(bool) + stress + sleep | ⚠️ 合成数据 | https://www.kaggle.com/datasets/aldinwhyudii/student-depression-and-lifestyle-100k-data |
| 8 | **Student Mental Health Dataset** | Kaggle | ~51k | Normal/Depression/Anxiety + 对话文本 | 未知 | https://www.kaggle.com/datasets/ahmadrosyidalfualdi/student-mental-health-dataset |

### ⭐ 学术参考（申请制）

| # | 名称 | 来源 | 规模 | 标签类型 | 人群 |
|---|------|------|:--:|------|------|
| 9 | **CCDRFS 2010** | 中国疾控中心 | 98,370 | PHQ-9 + 人口学 + 12年死亡随访 | 中国成人（18+） |

---

## 三、重点数据集详解

### 3.1 mmpsy-data (GitHub) — 首选 ⭐⭐⭐

```
规模:     1,275 条真实中学生数据
地区:     广东省，中国
标签:     PHQ-9 总分, GAD-7 总分, MHT 总分（三项标准化量表）
附加:     治疗对话音频录音 + 文本转录
许可:     MIT License
状态:     可直接下载
文件:     data/np_data/ 下有经预处理的音频特征和量表分数
```

**为什么首选**:
- 唯一同时含 PHQ-9 + GAD-7 + 中国学生的公开数据集
- 与当前系统用户画像高度匹配（中国学生）
- MIT 许可可自由用于研究
- 含音频数据可支撑多模态扩展

**集成路径**:
1. Clone 仓库，提取量表分数 CSV
2. 映射到现有特征体系（压力、睡眠、社会支持等需从音频/文本中提取或使用量表分替代）
3. 用 PHQ-9 总分作为 Gold Label 重新训练/验证二分类模型
4. 对比 v1.20 Synthetic 和 v1.21 Real 的性能差异

### 3.2 PHQ-9 Student Depression v5 (Mendeley) ⭐⭐⭐

```
规模:     682 条，零缺失值
地区:     国际（孟加拉为主）
标签:     PHQ-9 总分 (0-27), 五级严重度分类
特征:     睡眠质量(4级), 学业压力(4级), 经济压力(4级), 年龄, 性别
许可:     CC BY 4.0
状态:     可直接下载 CSV
```

**亮点**: 专业心理健康人员监督收集，IRB 批准，结构清晰，可直接用于 Logistic Regression 训练。

### 3.3 Social Media and Mental Health (UMD) ⭐⭐⭐

```
规模:     3,056 条
地区:     美国 48 州大学生
标签:     PHQ-9 总分, GAD-7 总分, 诊断史, 用药/咨询
特征:     18 列，含社交媒体使用、健康评分、种族
质量:     96% excellent
许可:     PDDL (Public Domain)
状态:     可直接下载 (mental_health2425v8(in).csv)
```

**亮点**: 唯一同时含 PHQ-9 + GAD-7 + 诊断史的数据集，可用于验证模型与临床诊断的一致性。

### 3.4 Student Depression Dataset (Kaggle) ⭐⭐⭐

```
规模:     27,901 条
地区:     印度（多城市）
标签:     Depression (0/1 binary)
特征:     Academic Pressure (0-5), CGPA, Sleep Duration, Financial Stress,
         Suicidal Thoughts, Family History, Dietary Habits
状态:     可直接下载
```

**亮点**: 规模最大，特征与当前系统高度重叠（学业压力、睡眠、经济、CGPA），是迁移学习的理想候选。

---

## 四、适用性评估矩阵

| 评估维度 | mmpsy | Mendeley v5 | UMD | Kaggle 27k |
|----------|:-----:|:-----------:|:---:|:----------:|
| 含 PHQ-9 总分 | ✅ | ✅ | ✅ | ❌ (binary) |
| 含 GAD-7 总分 | ✅ | ❌ | ✅ | ❌ |
| 中国人群 | ✅ | ❌ | ❌ | ❌ |
| 学生群体 | ✅ (中学) | ✅ (大学) | ✅ (大学) | ✅ (大学) |
| 可直接下载 | ✅ | ✅ | ✅ | ✅ |
| 含学业压力特征 | ❌ | ✅ (4级) | ❌ | ✅ (0-5) |
| 含睡眠特征 | ❌ (需提取) | ✅ (4级) | ❌ | ✅ (分类) |
| 含社会支持特征 | ❌ | ❌ | ❌ | ❌ |
| 许可清晰 | MIT | CC BY 4.0 | PDDL | 需确认 |
| **综合推荐度** | **A++** | **A+** | **A+** | **A** |

---

## 五、推荐数据集优先级与集成顺序

### Phase 4a（可立即开始）

| 步骤 | 数据集 | 动作 |
|------|--------|------|
| 1 | Mendeley v5 (682条) | 下载 → 特征对齐 → LR 基准训练 → 与 v1.20/v1.21 对比 |
| 2 | Kaggle 27k | 下载 → 特征映射 → 预训练 → 迁移到 Mendeley 微调 |
| 3 | mmpsy-data (1,275条) | Clone → 提取量表分 → 作为独立验证集 |

### Phase 4b（中期，需额外处理）

| 步骤 | 数据集 | 动作 |
|------|--------|------|
| 4 | UMD 3,056 | 下载 → PHQ-9/GAD-7 提取 → 跨文化验证（中美差异分析） |
| 5 | CCDRFS 2010 | 如可获取 → 大规模验证（98k Chinese） |

---

## 六、风险与局限

1. **mmpsy-data**: 中学生（非大学生），年龄分布与当前系统不匹配；需从音频提取文本特征才能匹配现有 feature set
2. **Mendeley v5**: 孟加拉学生为主，文化背景差异可能影响泛化
3. **UMD**: 美国学生，跨文化迁移需慎重；无学业压力/睡眠等直接映射特征
4. **Kaggle 27k**: 无 PHQ-9 总分，仅有 binary depression label；印度学生
5. **CCDRFS**: 可能需数据申请，获取周期不确定

---

## 七、结论

**可用于 v1.23 的最优数据集组合**:

```
训练层:   Mendeley v5 (682, PHQ-9 金标) + Kaggle 27k (预训练)
验证层:   mmpsy-data (1,275, PHQ-9+GAD-7, Chinese students)
测试层:   UMD 3,056 (PHQ-9+GAD-7+诊断史, 跨文化泛化)
参考层:   CCDRFS 2010 (98k Chinese, 如可获取)
```

**预期效果**: 如果 Mendeley v5 + mmpsy 联合训练能达到 AUC > 0.80 且与 v1.20 的差异 < ±15%，则可正式评估用真实临床标签模型替代 Synthetic 默认模型。
