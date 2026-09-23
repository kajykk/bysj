# v1.23 模型评估报告 (MODEL_EVALUATION_REPORT)

> 日期: 2026-05-02
> 模型: v1.23 External LR (Setting B — Source Weighted)

## 测试集总体指标

| 指标 | 值 |
|------|-----|
| 样本数 | 4318 |
| 正例比例 | 58.1% |
| Accuracy | 0.8333 |
| Balanced Accuracy | 0.8255 |
| Precision | 0.8450 |
| Recall (Sensitivity) | 0.8733 |
| Specificity | 0.7777 |
| F1-Score | 0.8589 |
| ROC-AUC | 0.9131 |

## 混淆矩阵

|  | 预测负 | 预测正 |
|------|--------|--------|
| **实际负** | TN=1406 | FP=402 |
| **实际正** | FN=318 | TP=2192 |

## 分数据源评估
### kaggle
- 样本数: 4181
- 正例比例: 58.5%
- Accuracy: 0.8340
- Recall: 0.8778
- Specificity: 0.7723
- F1: 0.8609
- ROC-AUC: 0.9145
### mendeley
- 样本数: 137
- 正例比例: 46.7%
- Accuracy: 0.8102
- Recall: 0.7031
- Specificity: 0.9041
- F1: 0.7759
- ROC-AUC: 0.8672

## 错误样本分析
- FP (假阳性): 402 — 模型误报高风险
- FN (假阴性): 318 — 模型漏报高风险

### 假阳性 (FP) 特征均值 (n=402)
- `age`: 25.34
- `gender`: 0.58
- `cgpa`: 3.07
- `stress_level`: 2.66
- `sleep_duration`: 6.29
- `social_support`: 2.00
- `financial_pressure`: 2.30
- `family_history`: 0.48
- `academic_pressure`: 2.66
- `exercise_frequency`: 1.62
- `anxiety`: 3.03
- `panic_attack`: 0.70

### 假阴性 (FN) 特征均值 (n=318)
- `age`: 26.70
- `gender`: 0.61
- `cgpa`: 3.05
- `stress_level`: 2.02
- `sleep_duration`: 6.50
- `social_support`: 2.00
- `financial_pressure`: 1.67
- `family_history`: 0.42
- `academic_pressure`: 2.02
- `exercise_frequency`: 1.75
- `anxiety`: 2.47
- `panic_attack`: 0.39

## 验收标准对照
| 标准 | 要求 | 实际 | 状态 |
|------|------|------|------|
| AUC | >= 0.75 | 0.9131 | ✅ |
| Recall | >= 0.70 | 0.8733 | ✅ |
| Specificity | >= 0.60 | 0.7777 | ✅ |

## ROC/PR 曲线数据
- ROC: `E:\code\bysj\backend\models\v1.23_external_lr\roc_curve.csv`
- PR: `E:\code\bysj\backend\models\v1.23_external_lr\pr_curve.csv`