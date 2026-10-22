# 迁移评估（降级单元）：text_ood

> **样本量先说：n = 2523。** 本单元是**域内压力测试（OOD 与训练语料精确去重，但仍是同源 original 的 EDA 改写）——非外迁、非公平基准**，指标只能读作下界/压力测试，不是公平基线。

- 数据集：data/external/ood_test_set_v2.csv（S2_ood_strict 子集）（2523 行；1275 original 全在训练语料、1175 mmpsy_augmented 全在训练增强集（均泄漏）；此处仅保留与训练语料精确不重叠的 2523 条）
- 判定阈值：`y_score >= 0.5`
- CI：bootstrap 分位（B=10000, seed=42）

| 指标 | 点估计 | 95% CI |
|---|---|---|
| Accuracy | 0.9945 | [0.9913, 0.9972] |
| Precision | 1.0000 | [1.0000, 1.0000] |
| Recall | 0.9727 | [0.9574, 0.9862] |
| F1 | 0.9862 | [0.9783, 0.9930] |
| ROC AUC | 0.9986 | [0.9956, 1.0000] |

混淆矩阵：TP=499 / FP=0 / FN=14 / TN=2010

- 逐样本：`backend/models/artifacts/eval_transfer/transfer_text_ood_predictions.csv`（sha256 `06778357a37fd7f7…`）
- 复跑：`cd backend && .venv/Scripts/python.exe scripts/modeling/eval/v1_29/02_transfer_eval.py --unit text_ood`
- 复算：`cd backend && .venv/Scripts/python.exe scripts/modeling/eval/v1_29/02_transfer_eval.py --unit text_ood --report-only`
