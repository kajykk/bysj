# FINAL_MODEL_CARD — v1.27 最终模型卡

> **生成日期**: 2026-05-02
> **数据来源**: `model_registry.py` + `config.py` + 各版本 DELIVERY_REPORT

---

## 模型总览

| # | 模型 ID | 版本 | Lifecycle | 用途 | 路由场景 |
|:--:|:---|:---|:---|:---|:---|
| 1 | `structured_logistic_regression_v1.20` | v1.20 | **default** | 结构化默认风险模型 | 特征覆盖率 ≥ 80% |
| 2 | `structured_v1.24_adapter` | v1.24 | **limited_active** | 分数迁移平滑 adapter | structured 路由 (shadow) |
| 3 | `mmpsy_lite_model` | v1.25 | **limited_active** | 轻特征风险模型 | GAD-7+文本, 覆盖率<80% |
| 4 | `mmpsy_lite_scaler` | v1.25 | **limited_active** | Lite 模型标准化器 | 伴随 v1.25 lite |
| 5 | `structured_v1.23_external_lr` | v1.23 | **experimental** | 外部临床标签实验模型 | 实验参考 |
| 6 | `structured_v1.21_binary_lr` | v1.21 | **deprecated** | 真实数据二分类 (LR) | 已弃用 |
| 7 | `structured_v1.21_binary_rf` | v1.21 | **deprecated** | 真实数据二分类 (RF) | 已弃用 |
| 8 | `structured_v1.21_multiclass_lr` | v1.21 | **disabled** | 多分类 (LR) | 已禁用 |
| 9 | `structured_v1.21_multiclass_rf` | v1.21 | **disabled** | 多分类 (RF) | 已禁用 |

---

## 模型详情

### 1. v1.20 Structured (default) — 全局默认模型

| 属性 | 值 |
|:---|:---|
| **模型 ID** | `structured_logistic_regression_v1.20` |
| **文件路径** | `models/artifacts/structured_v1.20/structured_model_v1.20.pkl` |
| **模型类型** | LogisticRegression (sklearn) |
| **特征维度** | 12 |
| **特征列表** | age, cgpa, stress_level, sleep_duration, social_support, financial_pressure, family_history, academic_pressure, exercise_frequency, anxiety, panic_attack, treatment_seeking |
| **Class Weight** | balanced |
| **Lifecycle** | `default` |
| **训练日期** | 2026-05-01 |
| **随机种子** | 42 |
| **训练集大小** | 10,000 (synthetic) |
| **Test Accuracy** | 0.9833 |
| **Test F1** | 0.9875 |
| **Test ROC-AUC** | 0.9991 |
| **路由触发条件** | 结构化特征覆盖率 ≥ 80% |
| **置信度** | high (≥90%) / medium (80-90%) |

---

### 2. v1.24 Adapter (limited_active) — 分数迁移安全网

| 属性 | 值 |
|:---|:---|
| **模型 ID** | `structured_v1.24_adapter` |
| **文件路径** | `models/v1.24_adapter/score_adapter.pkl` |
| **类型** | ScoreAdapter (piecewise_monotonic) |
| **Mean Abs Delta** | 4.37 |
| **AUC Loss** | 0.0196 |
| **Clamp Delta** | 20 |
| **Smooth Buffer** | 3 |
| **Lifecycle** | `limited_active` |
| **说明** | 在 structured 路由下与 v1.20 并行运行 (shadow mode)，提供 v1.23→v1.20 分数迁移平滑 |

---

### 3. v1.25 Lite (limited_active) — 轻特征风险模型

| 属性 | 值 |
|:---|:---|
| **模型 ID** | `mmpsy_lite_model` |
| **文件路径** | `models/v1.25_mmpsy_lite/mmpsy_lite_model.pkl` |
| **Scaler 路径** | `models/v1.25_mmpsy_lite/mmpsy_lite_scaler.pkl` |
| **GBDT 备选** | `models/v1.25_mmpsy_lite/mmpsy_lite_model_gbdt.pkl` |
| **模型类型** | CalibratedClassifierCV(LogisticRegression) |
| **特征维度** | 17 |
| **核心特征** | gad7_score, total_keywords, unique_categories, age, gender, cgpa, text_length, chinese_ratio, text_quality_flag, coverage_density, kw_* (7 categories) |
| **排除输入** | phq9_score |
| **标签** | phq9_binary |
| **Lifecycle** | `limited_active` |
| **训练数据** | mmpsy 数据集 (1,275 samples) |
| **正样本比例** | 20.2% |
| **决策阈值 (v1.26)** | **0.40** |
| **路由触发条件** | 特征覆盖率 < 80%, GAD-7 有值, 文本 ≥ 20 字符 |
| **置信度** | medium |

#### v1.26 性能指标

| 指标 | 值 | 要求 | 状态 |
|:---|---:|----:|:--:|
| AUC | 0.9380 | ≥ 0.88 | ✅ |
| Recall | 0.7692 | ≥ 0.75 | ✅ |
| Specificity | 0.9542 | ≥ 0.65 | ✅ |
| F1 | 0.7895 | — | — |
| Brier | 0.0710 | ≤ 0.12 | ✅ |

---

### 4. v1.23 External (experimental) — 外部临床标签模型

| 属性 | 值 |
|:---|:---|
| **模型 ID** | `structured_v1.23_external_lr` |
| **文件路径** | `models/v1.23_external_lr/model.pkl` |
| **模型类型** | LogisticRegression (sklearn) |
| **特征维度** | 12 |
| **Lifecycle** | `experimental` |
| **训练数据** | 外部 Kaggle+Mendeley (19,916 samples) |
| **Mendeley 权重** | 5.0x |
| **Test AUC** | 0.9131 |
| **Test F1** | 0.8589 |
| **Test Recall** | 0.8733 |
| **PHQ-9 Pearson r** | 0.6826 |

---

### 5. v1.21 Binary (deprecated) — 真实数据二分类

| 属性 | LR | RF |
|:---|:---|:---|
| **模型 ID** | `structured_v1.21_binary_lr` | `structured_v1.21_binary_rf` |
| **Lifecycle** | `deprecated` | `deprecated` |
| **特征维度** | 14 | 14 |
| **训练数据** | real (1,000) | real (1,000) |
| **Test F1** | 0.6000 | 0.6829 |
| **Test Recall** | 0.9130 | 0.6087 |
| **Test ROC-AUC** | 0.9401 | — |

---

### 6. v1.21 Multiclass (disabled) — 多分类模型

| 属性 | LR | RF |
|:---|:---|:---|
| **模型 ID** | `structured_v1.21_multiclass_lr` | `structured_v1.21_multiclass_rf` |
| **Lifecycle** | `disabled` | `disabled` |
| **Enabled** | `False` | `False` |
| **特征维度** | 10 | 10 |
| **Test Accuracy** | 0.1333 | 0.3200 |

---

## Lifecycle 状态分布

| Lifecycle | 数量 | 模型 |
|:---|---:|:---|
| `default` | 1 | v1.20 structured |
| `limited_active` | 3 | v1.24 adapter, v1.25 lite model, v1.25 lite scaler |
| `experimental` | 1 | v1.23 external |
| `deprecated` | 2 | v1.21 binary LR, v1.21 binary RF |
| `disabled` | 2 | v1.21 multiclass LR, v1.21 multiclass RF |

---

## 路由架构总结

```
输入特征
    │
    ├─ feature_coverage ≥ 0.80
    │   └─ → v1.20 structured (default)
    │        └─ [shadow] v1.24 adapter (分数迁移)
    │
    └─ feature_coverage < 0.80
        ├─ GAD-7 + text ≥ 20 chars
        │   └─ → v1.25 lite (limited_active)
        │        └─ threshold = 0.40 (v1.26)
        │        └─ crisis safety check
        │
        ├─ 仅 GAD-7
        │   └─ → anxiety_only (fallback)
        │
        └─ 无 GAD-7
            └─ → insufficient
```

---

> **模型卡结论**: 项目共管理 **9 个注册模型**，其中 **4 个活跃使用** (1 default + 3 limited_active)，实验/弃用/禁用模型已妥善治理。
