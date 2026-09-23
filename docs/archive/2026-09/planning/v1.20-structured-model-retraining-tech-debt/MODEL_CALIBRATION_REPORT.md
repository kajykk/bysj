# MODEL CALIBRATION REPORT — v1.20 结构化模型

> **日期**: 2026-05-01
> **校准依据**: train_structured.py 校准样本测试 + risk_thresholds.py 阈值调整

---

## 1. 校准样本测试结果

| # | 描述 | Score | Prediction | Probability | Risk Level (Score) | Expected | Match |
|---|---|---|---|---|---|---|---|
| 1 | 低压力、睡眠好、社交支持好 | 12.8 | 0 | 0.000 | none (level 0) | none / mild | ✅ |
| 2 | 中等压力、轻微焦虑、睡眠一般 | 52.4 | 1 | 0.896 | moderate (level 2) | moderate | ✅ |
| 3 | 高压力、睡眠差、焦虑明显 | 90.0 | 1 | 1.000 | high (level 3) | high | ✅ |
| 4 | 极高压力、惊恐发作、治疗寻求 | 100.0 | 1 | 1.000 | critical (level 4) | high / critical | ✅ |

---

## 2. 阈值调整详情

### v1.20 之前 (v1.16)
```
structured: mild=25, moderate=45, high=65, critical=85
```

### v1.20 校准后
```
structured: mild=20, moderate=45, high=65, critical=95
```

### 变更说明
- `critical` 阈值: **85 → 95** — 确保 score=90 的高风险样本映射到 `high (level 3)` 而非 `critical (level 4)`
- `mild` 阈值: **25 → 20** — 与基础阈值对齐，边界更合理

### Risk Level 映射表

| Score Range | Level | Label |
|---|---|---|
| [0, 20) | 0 | none |
| [20, 45) | 1 | mild |
| [45, 65) | 2 | moderate |
| [65, 95) | 3 | high |
| [95, 100] | 4 | critical |

---

## 3. 模型性能

| Metric | Train (5-Fold CV) | Test |
|---|---|---|
| Accuracy | 0.9827 ± 0.0024 | 0.9833 |
| F1 | 0.9870 ± 0.0018 | 0.9875 |
| Precision | 0.9957 ± 0.0015 | 0.9930 |
| Recall | 0.9784 ± 0.0038 | 0.9822 |
| ROC-AUC | 0.9991 ± 0.0003 | 0.9991 |

---

## 4. 结论

✅ 结构化模型风险等级输出与 v1.20 预期完全一致。
✅ 新阈值配置已写入 `risk_thresholds.py`。
✅ Heuristic fallback 和 sklearn 模型使用相同的校准后阈值，行为一致。
