# 迁移评估（降级单元）：physio_kaggle

> **样本量先说：n = 10000。** 本单元是**跨数据集压力测试（4/7 原始特征为生产默认常量、3/13 派生特征真实）——下界、非公平基准**，指标只能读作下界/压力测试，不是公平基线。

- 数据集：datasets/physiological/external/kaggle_wearable/mental_health_wearable_data.csv（10000 行；未确证未参与 v2 训练（训练脚本未入库）；标签 = Mental_Health_Condition）
- 判定阈值：`y_score >= 0.5`
- CI：bootstrap 分位（B=10000, seed=42）

| 指标 | 点估计 | 95% CI |
|---|---|---|
| Accuracy | 0.4801 | [0.4701, 0.4898] |
| Precision | 0.4930 | [0.4756, 0.5108] |
| Recall | 0.2883 | [0.2762, 0.3008] |
| F1 | 0.3639 | [0.3507, 0.3771] |
| ROC AUC | 0.5120 | [0.5006, 0.5233] |

混淆矩阵：TP=1487 / FP=1529 / FN=3670 / TN=3314

- 逐样本：`backend/models/artifacts/eval_transfer/transfer_physio_kaggle_predictions.csv`（sha256 `19a22413a3dccbd1…`）
- 复跑：`cd backend && .venv/Scripts/python.exe scripts/modeling/eval/v1_29/02_transfer_eval.py --unit physio_kaggle`
- 复算：`cd backend && .venv/Scripts/python.exe scripts/modeling/eval/v1_29/02_transfer_eval.py --unit physio_kaggle --report-only`
