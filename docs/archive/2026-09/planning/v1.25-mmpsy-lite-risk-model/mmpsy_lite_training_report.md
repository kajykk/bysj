# v1.25 mmpsy-lite Training Report

> Generated: 2026-05-02T06:33:24

## Model Configuration

- **Model**: CalibratedClassifierCV(LogisticRegression, isotonic)
- **Features**: 17 dimensions (no phq9_score)
- **CV**: 5-Fold Stratified
- **Test Split**: 15% hold-out
- **Random State**: 42
- **Class Weight**: balanced

## Test Set Metrics

| Metric | Value | Threshold | Status |
|---|---|---|---|
| AUC | 0.9380 | ≥ 0.8 | ✅ |
| F1 | 0.7429 | ≥ 0.6 | ✅ |
| RECALL | 0.6667 | ≥ 0.75 | ❌ |
| SPECIFICITY | 0.9673 | ≥ 0.65 | ✅ |
| Brier | 0.0710 | ≤ 0.18 | ✅ |
| Precision | 0.8387 | — | — |

### Confusion Matrix
TN=148  FP=5
FN=13  TP=26

### Correlation with PHQ-9 (reference only)
- Pearson r: 0.7815
- Spearman ρ: 0.7399

### LightGBM (optional)
- AUC: 0.9279
- F1: 0.7778

## Go / No-Go Decision: 🔴 NO-GO

