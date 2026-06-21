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

| Metric | Value |
|--------|-------|
| 3-feature 5-fold CV AUC | 0.9993 |
| AUC gap (12f − 3f) | -0.3744 (imputed features may introduce noise → regression-to-mean) |

## Figures

![ROC Curve](mmpsy_roc_curve.png)
![Calibration Curve](mmpsy_calibration_curve.png)
