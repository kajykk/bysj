# v1.26 Baseline Reproduction Report

- Test samples: 192
- Positive rate: 39/192 = 20.3%

| Metric | v1.25 | v1.26 Reproduced | Delta | Tolerance | Pass |
|--------|-------|-----------------|-------|-----------|------|
| auc | 0.938 | 0.938 | 0.0 | 0.01 | ✅ |
| recall | 0.6667 | 0.6667 | 0.0 | 0.03 | ✅ |
| specificity | 0.9673 | 0.9673 | 0.0 | 0.03 | ✅ |
| f1 | 0.7429 | 0.7429 | 0.0 | 0.05 | ✅ |
| precision | 0.8387 | 0.8387 | 0.0 | 0.05 | ✅ |
| brier | 0.071 | 0.071 | 0.0 | 0.02 | ✅ |

**Overall**: ✅ ALL PASS