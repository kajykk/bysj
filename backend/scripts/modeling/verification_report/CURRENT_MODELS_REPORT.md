# 当前推理链模型性能验证报告

- 生成时间: 2026-08-09T10:09:38.174454+00:00

## 汇总指标

| 模型 | 数据集 | N | 正例率 | Acc | BalAcc | Prec | Recall | Spec | F1 | AUC | Brier |
|------|--------|---|---|-----|--------|------|--------|------|-----|-----|-------|
| structured_v1.20 | data/external/aligned_features.csv (label_binary 全量) | 28552 | 58.2% | 0.8022 | 0.7832 | 0.7906 | 0.8983 | 0.6681 | 0.8410 | 0.8798 | 0.1835 |
| structured_v1.23_external | data/processed/v1_23_external/test.csv | 4318 | 58.1% | 0.8333 | 0.8255 | 0.8450 | 0.8733 | 0.7777 | 0.8589 | 0.9131 | 0.1152 |
| text_depression_classifier[en] | depression_dataset_reddit_cleaned | 7649 | 49.2% | 0.9736 | 0.9739 | 0.9566 | 0.9912 | 0.9565 | 0.9736 | 0.9975 | 0.0291 |
| text_improved_bilingual[en] | depression_dataset_reddit_cleaned | 7649 | 49.2% | 0.9729 | 0.9730 | 0.9691 | 0.9761 | 0.9699 | 0.9726 | 0.9957 | 0.0484 |
| text_depression_classifier | chinese_depression_corpus_v2_clean.csv (仅 original) | 1275 | 20.2% | 0.7827 | 0.4936 | 0.0870 | 0.0078 | 0.9794 | 0.0142 | 0.4957 | 0.1807 |
| text_improved_bilingual | chinese_depression_corpus_v2_clean.csv (仅 original) | 1275 | 20.2% | 0.9890 | 0.9729 | 1.0000 | 0.9457 | 1.0000 | 0.9721 | 0.9960 | 0.0346 |
| text_m2_bert | chinese_depression_corpus_v2_clean (original) | 1275 | 20.2% | 0.9992 | 0.9981 | 1.0000 | 0.9961 | 1.0000 | 0.9981 | 1.0000 | 0.0036 |
| text_m2_bert[ood] | ood_test_set_v2 (去重训练语料) | 2523 | 20.3% | 0.9140 | 0.8771 | 0.7741 | 0.8148 | 0.9393 | 0.7939 | 0.9553 | 0.0728 |
| mmpsy_lite_lr | data/processed/lite_features.csv (test 15%, seed 42) | 192 | 20.3% | 0.9062 | 0.8170 | 0.8387 | 0.6667 | 0.9673 | 0.7429 | 0.9380 | 0.0710 |
| mmpsy_lite_gbdt | data/processed/lite_features.csv (test 15%, seed 42) | 192 | 20.3% | 0.9167 | 0.8426 | 0.8485 | 0.7179 | 0.9673 | 0.7778 | 0.9279 | 0.0693 |
| physiological_v2_dl | depresjon_physiological.csv (n=1029 全量) | 1029 | 34.9% | 0.8290 | 0.7575 | 0.9791 | 0.5209 | 0.9940 | 0.6800 | 0.9624 | 0.1462 |

## 混淆矩阵

- **structured_v1.20**: TN=7966 FP=3957 FN=1692 TP=14937
- **structured_v1.23_external**: TN=1406 FP=402 FN=318 TP=2192
- **text_depression_classifier[en]**: TN=3720 FP=169 FN=33 TP=3727
- **text_improved_bilingual[en]**: TN=3772 FP=117 FN=90 TP=3670
- **text_depression_classifier**: TN=996 FP=21 FN=256 TP=2
- **text_improved_bilingual**: TN=1017 FP=0 FN=14 TP=244
- **text_m2_bert**: TN=1017 FP=0 FN=1 TP=257
- **text_m2_bert[ood]**: TN=1888 FP=122 FN=95 TP=418
- **mmpsy_lite_lr**: TN=148 FP=5 FN=13 TP=26
- **mmpsy_lite_gbdt**: TN=148 FP=5 FN=11 TP=28
- **physiological_v2_dl**: TN=666 FP=4 FN=172 TP=187

## V2 注册表 PRODUCTION 训练产物

(无 PRODUCTION 训练产物接入推理链, resolve_model_path 全部走静态路径)