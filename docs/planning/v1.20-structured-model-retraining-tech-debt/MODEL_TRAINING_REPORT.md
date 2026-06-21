# MODEL TRAINING REPORT — v1.20 结构化模型

> **日期**: 2026-05-01
> **训练脚本**: `backend/train_structured.py`
> **随机种子**: 42

---

## 1. 训练方式

由于 `train_baseline.py` 训练的是 PhysiologicalMLP（生理穿戴设备数据），而结构化模型需要人口学/行为特征，v1.20 采用以下创新方案：

1. 从 heuristic fallback 逻辑中提取精确的风险评分公式
2. 在特征空间均匀采样 10,000 个合成样本
3. 使用 heuristic 评分作为标签（≥50 → positive）
4. 训练 sklearn LogisticRegression 学习 heuristic 决策边界

**优势**:
- 产出真实 sklearn 模型 artifact（可序列化、可版本化、可加载）
- 预测行为校准后与业务预期对齐
- 模型可用时优先使用，失败时回退到 heuristic（行为一致）

---

## 2. 数据集

| 属性 | 值 |
|---|---|
| 生成方式 | 特征空间均匀随机采样 |
| 样本数 | 10,000 |
| 特征数 | 12 |
| 正样本 | 6,669 (66.7%) |
| 负样本 | 3,331 (33.3%) |

### 特征列表
`age, cgpa, stress_level, sleep_duration, social_support, financial_pressure, family_history, academic_pressure, exercise_frequency, anxiety, panic_attack, treatment_seeking`

---

## 3. 模型配置

| 参数 | 值 |
|---|---|
| 模型类型 | sklearn LogisticRegression |
| random_state | 42 |
| max_iter | 1000 |
| class_weight | balanced |
| C (正则化) | 1.0 |
| 标准化 | StandardScaler (fit on train only) |

---

## 4. 数据划分

| Split | 比例 | 样本数 |
|---|---|---|
| Train | 70% | 7,000 |
| Validation | 15% | 1,500 |
| Test | 15% | 1,500 |

- 随机排列后分层划分
- Scaler 仅在训练集上拟合

---

## 5. 交叉验证结果 (5-Fold CV)

| Metric | Mean ± Std |
|---|---|
| Accuracy | 0.9827 ± 0.0024 |
| F1 | 0.9870 ± 0.0018 |
| Precision | 0.9957 ± 0.0015 |
| Recall | 0.9784 ± 0.0038 |
| ROC-AUC | 0.9991 ± 0.0003 |

---

## 6. 测试集结果

| Metric | Value |
|---|---|
| Accuracy | 0.9833 |
| F1 | 0.9875 |
| Precision | 0.9930 |
| Recall | 0.9822 |
| ROC-AUC | 0.9991 |
| AUPRC | 0.9996 |

**混淆矩阵**:
```
TN=484, FP=7
FN=18,  TP=991
```

---

## 7. 校准样本测试

| # | 描述 | Heuristic Score | Prediction | Probability | Risk Level | 预期 | 结果 |
|---|---|---|---|---|---|---|---|
| 1 | 低压力、睡眠好、社交支持好 | 12.8 | 0 | 0.000 | none | none/mild | ✅ |
| 2 | 中等压力、轻微焦虑、睡眠一般 | 52.4 | 1 | 0.896 | moderate | moderate | ✅ |
| 3 | 高压力、睡眠差、焦虑明显 | 90.0 | 1 | 1.000 | high | high | ✅ |
| 4 | 极高压力、惊恐发作、治疗寻求 | 100.0 | 1 | 1.000 | critical | high/critical | ✅ |

---

## 8. Risk Level 阈值

| Score 范围 | Risk Level |
|---|---|
| [0, 20) | none |
| [20, 45) | mild |
| [45, 65) | moderate |
| [65, 95) | high |
| [95, 100] | critical |

---

## 9. 产出 Artifact

| 文件 | 路径 |
|---|---|
| 模型 | `models/artifacts/structured_v1.20/structured_model_v1.20.pkl` |
| Scaler | `models/artifacts/structured_v1.20/structured_scaler_v1.20.pkl` |
| 特征名称 | `models/artifacts/structured_v1.20/structured_feature_names_v1.20.json` |
| 指标 | `models/artifacts/structured_v1.20/structured_metrics_v1.20.json` |
| Manifest | `models/artifacts/structured_v1.20/structured_manifest_v1.20.json` |

---

## 10. 可复现性

- ✅ 随机种子固定 (42)
- ✅ 数据生成逻辑确定
- ✅ 超参数记录完整
- ✅ 训练脚本可重新执行并获得相同结果
