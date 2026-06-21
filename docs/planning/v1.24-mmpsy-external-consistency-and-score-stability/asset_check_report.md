# v1.24 Phase 0: Asset Check Report

> Generated: 2026-05-02T04:11:59

| # | Asset | Path | Status | Note |
|---|---|---|---|---|
| 1 | v1.23 model | `backend/models/v1.23_external_lr/model.pkl` | ✅ |  |
| 2 | v1.23 schema | `backend/models/v1.23_external_lr/feature_schema.json` | ✅ |  |
| 3 | v1.23 ext metrics | `backend/models/v1.23_external_lr/external_validation_metrics.json` | ✅ |  |
| 4 | v1.23 metrics | `backend/models/v1.23_external_lr/metrics.json` | ✅ |  |
| 5 | v1.23 delta csv | `backend/models/v1.23_external_lr/model_delta_samples.csv` | ✅ | rows=4318 (OK), cols=19, mean_abs_delta=21.29 (OK) |
| 6 | mmpsy raw data | `data/external/mmpsy_scores.csv` | ✅ |  |
| 7 | v1.20 model | `backend/models/artifacts/structured_v1.20/structured_model_v1.20.pkl` | ✅ |  |
| 8 | model registry | `backend/app/core/model_registry.py` | ✅ |  |
| 9 | model engine | `backend/app/core/model_engine.py` | ✅ |  |

---

**Summary**: 9/9 assets verified.

✅ All assets ready. Safe to proceed to Phase 1.
