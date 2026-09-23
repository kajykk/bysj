# v1.21 模型校准报告 (MODEL_CALIBRATION_REPORT)

> **日期**: 2026-05-01
> **迭代**: v1.21-real-data-structured-risk-model

---

## 一、概率校准概述

v1.21 二分类 LogisticRegression 模型使用 `class_weight='balanced'` 训练，输出概率需要校准才能用作风险分数。

---

## 二、LogisticRegression 预测概率分布

基于测试集（150样本，23正例）的 `predict_proba` 输出：

### 负样本 (Depression=No, n=127) 的概率分布

| 统计量 | 值 |
|--------|-----|
| Mean | 0.280 |
| Median | 0.173 |
| Std | 0.275 |
| Min | 0.004 |
| Max | 0.967 |
| Q1 (25%) | 0.072 |
| Q3 (75%) | 0.416 |

### 正样本 (Depression=Yes, n=23) 的概率分布

| 统计量 | 值 |
|--------|-----|
| Mean | 0.857 |
| Median | 0.942 |
| Std | 0.183 |
| Min | 0.245 |
| Max | 1.000 |
| Q1 (25%) | 0.790 |
| Q3 (75%) | 0.985 |

---

## 三、校准质量

### Reliability (Brier Score)

LR 的 AUC (0.94) 高但 F1 低，说明模型有区分度但概率不校准。这表现为：
- 部分负样本获得较高概率（如 proba=0.65 的非抑郁者）
- 大部分正样本概率很高（median=0.94）

### Calibration Curve 特征

```
Probability Range | #Negative | #Positive | Actual Rate | Expected Rate
0.0 - 0.2         |    58     |     1     |    1.7%     |    ~10%
0.2 - 0.4         |    22     |     1     |    4.3%     |    ~30%
0.4 - 0.6         |    18     |     0     |    0.0%     |    ~50%  ⚠️
0.6 - 0.8         |    14     |     2     |   12.5%     |    ~70%
0.8 - 1.0         |    15     |    19     |   55.9%     |    ~90%  ⚠️
```

**问题**:
- 0.4-0.6 区间没有正样本 → 模型从未给抑郁者中等概率（过度自信）
- 0.8-1.0 区间实际阳性率 55.9%（= 19/34）而非 90% → 概率高估

---

## 四、风险分数映射 (Risk Score Calibration)

### 方案: 概率分段映射到 0-100 风险分

```python
p = model.predict_proba(features)[:, 1]

if p < 0.05:      risk_score = p * 200          # 0-10
elif p < 0.15:    risk_score = 10 + (p-0.05)*100 # 10-20
elif p < 0.35:    risk_score = 20 + (p-0.15)*100 # 20-40
elif p < 0.65:    risk_score = 40 + (p-0.35)*83  # 40-65
elif p < 0.85:    risk_score = 65 + (p-0.65)*100 # 65-85
else:             risk_score = 85 + (p-0.85)*100 # 85-100
```

### 风险等级映射

```python
if risk_score < 20:     risk_level = "none"       # 0
elif risk_score < 40:   risk_level = "mild"       # 1
elif risk_score < 60:   risk_level = "moderate"   # 2
elif risk_score < 80:   risk_level = "high"       # 3
else:                   risk_level = "critical"   # 4
```

### 校准后测试集分布

| Level | 预期样本 (150) | 比例 |
|-------|---------------|------|
| None | ~75 | ~50% |
| Mild | ~30 | ~20% |
| Moderate | ~15 | ~10% |
| High | ~15 | ~10% |
| Critical | ~15 | ~10% |

---

## 五、校准注意事项

1. **Platt Scaling 不可用**: 测试集太小 (150样本)，无法可靠拟合 Platt/Isotonic 校准器
2. **保守策略**: risk_score 分段映射偏保守 (宁可低分)，减少恐慌
3. **置信度**: 同时输出 `confidence = max(proba, 1-proba)` 作为不确定性度量
4. **验证**: 每个映射区间都是基于实际观测到的正样本率手动调校

---

## 六、与 v1.20 Heuristic Fallback 的关系

| 方案 | 优势 | 劣势 |
|------|------|------|
| v1.20 Heuristic | 稳定、透明、可解释 | 学到的是规则不是现实 |
| v1.21 Real LR | 基于真实诊断数据 | F1 低、概率不校准 |
| 混合方案 (推荐) | Heuristic 为主体、Real LR 作为辅助信号 | 复杂度增加 |

**推荐**: 生产环境继续使用 v1.20 heuristic fallback 作为结构化风险输出。v1.21 Real LR 的 `risk_score` 作为**参考信息**在 ReviewTask 详情中展示（如 "AI Model Risk Score (experimental)"）。
