# v1.23 训练报告 (TRAINING_REPORT)

> 日期: 2026-05-02
> 模型类型: Logistic Regression
> 特征数: 12
> 特征: age, gender, cgpa, stress_level, sleep_duration, social_support, financial_pressure, family_history, academic_pressure, exercise_frequency, anxiety, panic_attack

## Setting A: 自然比例训练
- Accuracy: 0.8467
- Balanced Acc: 0.84
- Precision: 0.8591
- Recall: 0.881
- F1: 0.8699
- ROC-AUC: 0.9164
- 混淆矩阵: TN=1443, FP=363, FN=299, TP=2213

## Setting B: 数据源加权训练 (推荐候选)
Mendeley 权重: 5.0x
- Accuracy: 0.8476
- Balanced Acc: 0.8404
- Precision: 0.8579
- Recall: 0.8846
- F1: 0.871
- ROC-AUC: 0.9165
- 混淆矩阵: TN=1438, FP=368, FN=290, TP=2222

## Setting C: Mendeley-only 验证基线
- Accuracy: 0.8321
- Balanced Acc: 0.8291
- Precision: 0.8621
- Recall: 0.7692
- F1: 0.813
- ROC-AUC: 0.9003
- 混淆矩阵: TN=64, FP=8, FN=15, TP=50

## 特征系数 (Setting B — 推荐候选)
- `panic_attack`: +1.1549
- `stress_level`: +0.8991
- `academic_pressure`: +0.8991
- `financial_pressure`: +0.8232
- `anxiety`: -0.6275
- `age`: -0.5439
- `exercise_frequency`: -0.4374
- `sleep_duration`: -0.2362
- `cgpa`: +0.0855
- `family_history`: +0.0823
- `gender`: +0.0221
- `social_support`: +0.0000

## 训练可复现命令
```bash
python backend/scripts/modeling/v1_23/01_prepare_external_dataset.py --random-state 42
python backend/scripts/modeling/v1_23/02_train_external_lr.py --random-state 42 --setting weighted
```