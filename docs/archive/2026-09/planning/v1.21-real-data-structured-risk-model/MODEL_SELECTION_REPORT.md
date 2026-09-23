# v1.21 模型选择报告 (MODEL_SELECTION_REPORT)

> **日期**: 2026-05-01
> **迭代**: v1.21-real-data-structured-risk-model

---

## 一、候选模型总览

| 模型 | 类型 | 数据 | 特征数 | 状态 |
|------|------|------|--------|------|
| v1.20 Synthetic LR | Binary LogisticRegression | 10,000 合成数据 | 14 | ✅ 当前默认 |
| v1.21 Real Binary LR | Binary LogisticRegression | 1,000 真实数据 | 14 | ⚠️ Conditional Go |
| v1.21 Real Binary RF | Binary RandomForest | 1,000 真实数据 | 14 | ❌ No-Go |
| v1.21 Multiclass LR | 5-Class LogisticRegression | 1,000 真实数据 | 10 | ❌ No-Go |
| v1.21 Multiclass RF | 5-Class RandomForest | 1,000 真实数据 | 10 | ❌ No-Go |

---

## 二、关键指标对比

### 二分类模型

| Metric | v1.20 Synth LR | v1.21 Real LR | v1.21 Real RF |
|--------|---------------|--------------|--------------|
| Accuracy | 0.9813 | 0.8133 | 0.9133 |
| F1 | 0.9875 | 0.6000 | 0.6829 |
| Precision | ~0.98 | 0.4468 | 0.7778 |
| Recall | ~0.99 | 0.9130 | 0.6087 |
| ROC-AUC | 0.9991 | 0.9401 | 0.8956 |
| AUPRC | — | 0.7914 | 0.7623 |

### 五级模型

| Metric | LR-Multinomial | RandomForest |
|--------|---------------|-------------|
| Accuracy | 0.1333 | 0.3200 |
| F1 Macro | 0.1365 | 0.1921 |
| High/Critical Recall | 0.6154 | 0.1154 |

---

## 三、推荐策略

### 默认模型: **v1.20 Synthetic LR** ✅

**理由**:
1. v1.21 Real Binary LR F1=0.60，远低于 0.85 阈值
2. v1.21 五级模型不可用（accuracy 13%-32%）
3. v1.20 合成模型虽然本质上学到 heuristic 规则，但经过 v1.20 完整校准和回归验证
4. 在心理健康风险预警场景中，"稳定可靠 > 新颖但不达标"

### 可选/实验模型: **v1.21 Real Binary LR** ⚠️

**定位**: 实验性 artifact，不替代默认模型
**启用方式**: 配置 `STRUCTURED_MODEL_VERSION=v1.21_real_binary_lr`

**适用场景**:
- 研究对比（真实数据 vs 合成数据的行为差异）
- 未来数据扩充后的基准参照
- 推动真实数据采集和标注的论据

---

## 四、风险等级映射方案

由于五级独立模型不可行，采用 **二分类概率 + 阈值映射** 方案：

```
二分类模型输出概率 → 多阈值分档 → 五级风险

p_depression < 0.15     → Level 0 (None)
0.15 ≤ p < 0.35         → Level 1 (Mild)
0.35 ≤ p < 0.65         → Level 2 (Moderate)
0.65 ≤ p < 0.85         → Level 3 (High)
p ≥ 0.85                → Level 4 (Critical)
```

此方案同时适用于 v1.20 和 v1.21 二分类模型。

---

## 五、模型版本配置

```text
# .env 配置
STRUCTURED_MODEL_VERSION=v1.20_synthetic_lr   # 默认（推荐）
# STRUCTURED_MODEL_VERSION=v1.21_real_binary_lr  # 实验性
STRUCTURED_MODEL_MODE=primary                   # primary 或 fallback
```

当 `STRUCTURED_MODEL_MODE=fallback` 时，强制使用 heuristic 规则（不依赖任何模型文件）。

---

## 六、最终判定

| 判定项 | 结论 |
|--------|------|
| v1.21 是否替代 v1.20 | ❌ 不替代 |
| v1.21 模型是否可用 | ⚠️ 实验性可用（配置开关） |
| 线上默认模型 | v1.20 Synthetic LR |
| 五级风险方案 | 二分类概率 + 阈值分档 |
| Go / No-Go | **Conditional Go** |

### 总结

v1.21 的核心价值不在于产出更好的模型，而在于**验证了一个关键假设**:
> 真实世界中的抑郁预测远难于合成数据场景。

这份发现比一个高指标的合成模型更有价值。它揭示了当前数据策略的上限，并为 v1.22 的数据扩充/标注计划提供了坚实的论据基础。
