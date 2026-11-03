# 当前推理链模型性能验证报告

- 生成时间: 2026-09-07T21:44:14.316985+00:00

## 汇总指标

| 模型 | 数据集 | N | 正例率 | Acc | BalAcc | Prec | Recall | Spec | F1 | AUC | Brier |
|------|--------|---|---|-----|--------|------|--------|------|-----|-----|-------|
| structured_v1.20 | data/external/aligned_features.csv (label_binary 全量) | 28552 | 58.2% | 0.8022 | 0.7832 | 0.7906 | 0.8983 | 0.6681 | 0.8410 | 0.8798 | 0.1835 |
| structured_v1.23_external | data/processed/v1_23_external/test.csv | 4318 | 58.1% | 0.8333 | 0.8255 | 0.8450 | 0.8733 | 0.7777 | 0.8589 | 0.9131 | 0.1152 |
| text_depression_classifier[en] | depression_dataset_reddit_cleaned | 7649 | 49.2% | 0.9736 | 0.9739 | 0.9566 | 0.9912 | 0.9565 | 0.9736 | 0.9975 | 0.0291 |
| text_improved_bilingual[en] | depression_dataset_reddit_cleaned | 7649 | 49.2% | 0.9729 | 0.9730 | 0.9691 | 0.9761 | 0.9699 | 0.9726 | 0.9957 | 0.0484 |
| text_depression_classifier | chinese_depression_corpus_v2_clean.csv (仅 original, sibling-leaked 口径) | 1275 | 20.2% | 0.7827 | 0.4936 | 0.0870 | 0.0078 | 0.9794 | 0.0142 | 0.4957 | 0.1807 |
| text_improved_bilingual | chinese_depression_corpus_v2_clean.csv (仅 original, sibling-leaked 口径) | 1275 | 20.2% | 0.9890 | 0.9729 | 1.0000 | 0.9457 | 1.0000 | 0.9721 | 0.9960 | 0.0346 |
| mmpsy_lite_lr | data/processed/lite_features.csv (test 15%, seed 42) | 192 | 20.3% | 0.9062 | 0.8170 | 0.8387 | 0.6667 | 0.9673 | 0.7429 | 0.9380 | 0.0710 |
| mmpsy_lite_gbdt | data/processed/lite_features.csv (test 15%, seed 42) | 192 | 20.3% | 0.9115 | 0.8585 | 0.7895 | 0.7692 | 0.9477 | 0.7792 | 0.9019 | 0.0778 |
| physiological_v2_dl | depresjon_physiological.csv (n=1029 全量) | 1029 | 34.9% | 0.8290 | 0.7575 | 0.9791 | 0.5209 | 0.9940 | 0.6800 | 0.9624 | 0.1462 |

## 口径说明（文本模态，勿把 0.996 当真实指标）

> 文本模态的 AUC/F1 **不得直接当作泛化性能引用**。
> `text_improved_bilingual` 在 `chinese_depression_corpus_v2_clean`
> （仅 original）上的 AUC 0.9960 是 **sibling-leaked 文本级口径**：
> 同一原文的回译/同义改写变体同时出现在训练集与评估集，属于兄弟样本泄漏，
> 不是外部或跨域指标，只用于口径对照。
>
> 去泄漏口径（v1.27 按用户分组 `StratifiedGroupKFold`，无兄弟交叠）：
> **AUC 0.8437 / F1 0.5864**（Precision 0.6450 / Recall 0.5375）。
> 依据：`scripts/modeling/v1_27/groupwise_eval_results.json`、
> `scripts/modeling/v1_27/groupwise_eval_report.md`。
> 对外引用文本模态时一律使用组级口径。

## 口径说明（生理模态，勿把 0.96 当真实生理性能）

> `physiological_v2_dl` 的训练表 `depresjon_physiological.csv` 中，
> `heart_rate`/`sleep_hours`/`sleep_quality`/`systolic_bp`/`diastolic_bp`
> 由真实队列标签的分组均值生成，`phq9_score` 也是标签的噪声副本；
> 仅 `steps`/`exercise_minutes` 来自真实 actigraphy 汇总。
> 仅真实列 5 折 OOF AUC 为 0.6443，合成列可达 0.9898。
> 因此本表生理行只能作生产管线回归读数，**不得**作为真实生理信号性能引用。
> 依据：`docs/model-evaluation/PHYSIO_DATA_PROVENANCE_AUDIT.md`。

## 混淆矩阵

- **structured_v1.20**: TN=7966 FP=3957 FN=1692 TP=14937
- **structured_v1.23_external**: TN=1406 FP=402 FN=318 TP=2192
- **text_depression_classifier[en]**: TN=3720 FP=169 FN=33 TP=3727
- **text_improved_bilingual[en]**: TN=3772 FP=117 FN=90 TP=3670
- **text_depression_classifier**: TN=996 FP=21 FN=256 TP=2
- **text_improved_bilingual**: TN=1017 FP=0 FN=14 TP=244
- **mmpsy_lite_lr**: TN=148 FP=5 FN=13 TP=26
- **mmpsy_lite_gbdt**: TN=145 FP=8 FN=9 TP=30
- **physiological_v2_dl**: TN=666 FP=4 FN=172 TP=187

## V2 注册表 PRODUCTION 训练产物

(无 PRODUCTION 训练产物接入推理链, resolve_model_path 全部走静态路径)