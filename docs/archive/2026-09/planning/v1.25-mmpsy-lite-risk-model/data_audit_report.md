# v1.25 Phase 0: Data Audit Report

> Generated: 2026-05-02T06:28:44

## 1. mmpsy_scores.csv

| Check | Status | Value | Baseline |
|---|---|---|---|
| Row Count | ✅ | row_count | 1275 |
| Columns Match | ✅ | — | 9 specified columns |
| PHQ-9 Range [0-27] | ✅ | — | all in [0, 27] |
| GAD-7 Range [0-21] | ✅ | — | all in [0, 21] |
| Transcript Not Null | ✅ | — | all non-null |
| Label Consistency | ✅ | mismatch=0 | 0 mismatches |
| Positive Ratio | ✅ | 0.2024 | 0.202 ± 0.02 |
| User ID Unique | ✅ | — | 1275 |

**Text length range**: 41 – 3991 characters
**Missing columns**: none
**Extra columns**: none
**Positive samples**: 258 / 1275

## 2. mmpsy_structured_features.csv

| Row Count | ✅ | 1275 | 1275 |
| Source Columns | — | 12 derived/imputed cols | — |
| Derived Cells | — | 7650 | — |
| Imputed Cells | — | 7650 | — |

---

## ✅ Audit Passed

All mmpsy data checks passed. Safe to proceed to Phase 1 (lite feature construction).
