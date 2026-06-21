# v1.23 数据准备报告 (DATA_PREPARATION_REPORT)

> 日期: 2026-05-02
> 输入: data/external/aligned_features.csv
> 总样本: 28552

## 数据源分布
- **kaggle**: 27870 条, 正例=16308 (58.5%), PHQ-9均值=None
- **mendeley**: 682 条, 正例=321 (47.1%), PHQ-9均值=9.9

## 目标标签分布
- `depression_binary=0`: 11923
- `depression_binary=1`: 16629

## 缺失率
- 无缺失值

## 常数特征 (无区分度)
- `social_support` = 2.0

## 异常值处理
- `age`: <=12 的 0 条 (clip), >=35 的 39 条 (clip)

## 使用的特征 (共12个)
- `age`
- `gender`
- `cgpa`
- `stress_level`
- `sleep_duration`
- `social_support`
- `financial_pressure`
- `family_history`
- `academic_pressure`
- `exercise_frequency`
- `anxiety`
- `panic_attack`

## 数据限制说明
- `source` 列 100%% 缺失，改用 `label_source` 推断数据源
- `social_support` 全为 2.0（填充值），保留但标注
- `treatment_seeking` / `study_year` 为常数，已从特征集中移除
- Mendeley PHQ-9 数据仅 682 条，标签由 `phq9_total >= 10` 导出
- Kaggle `label_binary` 语义不等于 PHQ-9 标签，需在报告中区分