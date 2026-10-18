# mmpsy Constrained External Validation Report

⚠️ This is a **constrained external validation**. Only 6/12 (50.0%) features were rule-derived from mmpsy fields; the remaining 6 were filled with training-set medians.

## Key Metrics

| Metric | Value | Threshold | Status |
|--------|-------|-----------|--------|
| Binary AUC | 0.6249 | ≥ 0.80 | ⚠️ |
| Recall (Sensitivity) | 0.6860 | ≥ 0.70 | ⚠️ |
| Specificity | 0.4887 | ≥ 0.60 | ⚠️ |
| F1 Score | 0.3707 | — | — |
| High-Risk Recall | 0.6860 | ≥ 0.75 | ⚠️ |
| Pearson r (vs PHQ-9) | 0.2151 | ≥ 0.50 | ⚠️ |
| Spearman ρ (vs GAD-7) | 0.1239 | ≥ 0.50 | ⚠️ |

## Confusion Matrix

|  | Predicted Negative | Predicted Positive |
|--|-------------------|-------------------|
| Actual Negative | TN = 497 | FP = 520 |
| Actual Positive | FN = 81 | TP = 177 |

## Subset Baseline (3 derived features only)

> ⚠️ **更正（B.5，2026-10-19）：本节两个数值及其解释均无效，原文仅作历史快照保留。**
>
> **1. `3-feature 5-fold CV AUC = 0.9993` 无效（L4 目标泄漏）。**
> 该 3 特征为 `["stress_level", "anxiety", "panic_attack"]`（`02_validate_mmpsy.py:84`），
> 其中 `stress_level` 是**标签同源特征**：
> `v1_24/01_build_mmpsy_features.py:66` 定义 `derive_stress(phq9) = round(phq9/27.0*5.0, 4)`，
> 而标签 `phq9_binary = (phq9_score >= 10)`。实测 `corr(stress_level, phq9_score) = 1.0`、
> `stress_level` 单特征 **AUC = 1.0000** ⇒ 在 mmpsy 上重训的 LR 只是复述标签，不是预测。
>
> **2. `AUC gap (12f − 3f) = -0.3744` 及其「插补特征引入噪声 → 回归均值」解释无效。**
> 两侧**不在同一口径**，不可相减：
> - 12f 侧（0.6249）是**冻结的 v1.23 pipeline 跨域推理**（`joblib.load` + `predict_proba`）；
> - 3f 侧（0.9993）是**在 mmpsy 域内重新训练**的 `cross_val_score(cv=5)`。
>
> 且 3f 侧本身被 L4 污染。⇒ 该 gap 既不能说明「插补引入噪声」，也不能说明「回归均值」。
>
> **3. 关于 12f 的 0.6249（本节未直接引用，但同报告 §Key Metrics 使用）：**
> 实测判定为**未被 L4 污染**——同款 LR 若在 mmpsy 上重训，12f 会拿到 **0.9997**，
> 而冻结 pipeline 只拿到 0.6249（差 0.375）⇒ 冻结模型**没有吃到泄漏红利**，
> 其权重学自训练域（该域 `stress_level` 为真实测量，`corr(stress_level, phq9_total)=0.5476`）。
> 因此 0.6249 作为「跨域迁移性能」读数仍成立，**go/no-go 的 FAIL 判定方向不变**。
> 但必须记账：**该 12 特征集含 `stress_level`**，任何在 mmpsy 上重训/微调的后续工作都会踩同一坑。
>
> **实测依据（本机复现，2026-10-19）**：mmpsy 上重训 LR（liblinear, 5-fold StratifiedKFold）
> 12f=0.9997｜11f（剔 `stress_level`）=0.9212｜10f（再剔 `anxiety`）=0.6394｜
> 3f=0.9993｜2f（3f 剔 `stress_level`）=0.9197｜1f（`stress_level`）=1.0000。
> 详见 `docs/ML_LEAKAGE_REMEDIATION.md`。

| Metric | Value |
|--------|-------|
| 3-feature 5-fold CV AUC | 0.9993 |
| AUC gap (12f − 3f) | -0.3744 (imputed features may introduce noise → regression-to-mean) |

## Figures

![ROC Curve](mmpsy_roc_curve.png)
![Calibration Curve](mmpsy_calibration_curve.png)
