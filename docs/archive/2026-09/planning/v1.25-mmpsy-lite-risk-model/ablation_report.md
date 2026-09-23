# v1.25 Phase 3: Ablation Study Report

> Generated: 2026-05-02T06:43:00
> CV: 5-Fold Stratified | Random State: 42

## 1. Per-Configuration Metrics (CV Mean ± Std)

| ID | Config | AUC | F1 | Recall | Specificity |
|---|---|---|---|---|---|
| A | PHQ-9 Only (upper bound) | 1.0000±0.0000 | 1.0000±0.0000 | 1.0000±0.0000 | 1.0000±0.0000 |
| B | GAD-7 Only (anxiety baseline) | 0.9195±0.0164 | 0.7241±0.0419 | 0.8101±0.0448 | 0.8909±0.0247 |
| C | Text Keywords Only | 0.6893±0.0340 | 0.4345±0.0291 | 0.4920±0.0365 | 0.8034±0.0285 |
| D | GAD-7 + Text (v1.25 core) | 0.9157±0.0202 | 0.6977±0.0302 | 0.8140±0.0498 | 0.8683±0.0187 |
| E | GAD-7 + Text + Demo (v1.25 full) | 0.9132±0.0206 | 0.7019±0.0353 | 0.8141±0.0509 | 0.8712±0.0280 |

## 2. Pairwise Bootstrap Tests

> α' = 0.005 (Bonferroni: 0.05/4)

| Comparison | p-value | α' | Significant |
|---|---|---|---|
| D vs vs vs B | 0.501 | 0.005 | ❌ |
| E vs vs vs B | 0.506 | 0.005 | ❌ |
| D vs vs vs C | 0.578 | 0.005 | ❌ |
| E vs vs vs C | 0.561 | 0.005 | ❌ |

**Best Config**: A — PHQ-9 Only (upper bound)
**AUC**: 1.0000
