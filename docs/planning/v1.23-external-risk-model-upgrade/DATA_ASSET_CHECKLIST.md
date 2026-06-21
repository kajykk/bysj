# v1.23 数据资产检查清单 (DATA_ASSET_CHECKLIST)

> **日期**: 2026-05-02
> **版本**: v1.23-external-risk-model-upgrade
> **阶段**: Phase 0 — 准备与基线确认

---

## 一、外部数据文件

| # | 文件路径 | 状态 | 备注 |
|---|----------|------|------|
| 1 | `data/external/aligned_features.csv` | ✅ 存在 | 28,552 行, 19 列, 含 `source`/`label_binary`/`label_source`/`phq9_total`/`phq9_severity` |
| 2 | `data/external/mmpsy_scores.csv` | ✅ 存在 | 1,275 行, 含 `phq9_score`/`phq9_level`/`phq9_binary`/`gad7_score`/`gad7_level`/`gad7_binary` |
| 3 | `data/external/mmpsy-data/` | ✅ 存在 | 含 `data/wav_select.json`, `data_generation.py`, README |

---

## 二、原始数据集

| # | 文件路径 | 状态 | 备注 |
|---|----------|------|------|
| 4 | `datasets/PHQ-9_Dataset_5th Edition.csv` | ✅ 存在 | Mendeley PHQ-9, 682 条, 含 PHQ-9 总分标签 |
| 5 | `datasets/Student Depression Dataset.csv` | ✅ 存在 | Kaggle Student Depression, 27,870 条, 二分类标签 |

---

## 三、后端核心文件

| # | 文件路径 | 状态 | 备注 |
|---|----------|------|------|
| 6 | `backend/app/core/model_registry.py` | ✅ 存在 | 已有 v1.20 LR + v1.21 Binary/Multiclass 注册项, 223 行 |
| 7 | `backend/app/core/model_engine.py` | ✅ 存在 | `predict_structured()` 已含 v1.22 Phase 2 实验路径 (v1.21 Real Binary LR 并行), 1176 行 |

---

## 四、前端目标文件

| # | 文件路径 | 状态 | 备注 |
|---|----------|------|------|
| 8 | `frontend/src/api/modelApi.ts` | ✅ 存在 | `ModelPredictResponse` 已含 `experimental_real_*` 字段 |
| 9 | `frontend/src/views/user/UserRiskPage.vue` | ✅ 存在 | 已有实验参考区域, 含 `.experiment.test.ts` 测试 |

---

## 五、已有模型产物

| # | 模型 ID | 模型路径 | 版本 | 角色 |
|---|---------|----------|------|------|
| 10 | `structured_logistic_regression_v1.20` | `models/artifacts/structured_v1.20/structured_model_v1.20.pkl` | v1.20 | **默认主模型** (enabled=true) |
| 11 | `structured_v1.21_binary_lr` | `models/artifacts/structured_v1.21/model_binary_lr.pkl` | v1.21 | **实验参考** (enabled=true, experimental) |
| 12 | `structured_v1.21_binary_rf` | `models/artifacts/structured_v1.21/model_binary_rf.pkl` | v1.21 | 实验参考 (enabled=true) |
| 13 | `structured_v1.21_multiclass_lr` | `models/artifacts/structured_v1.21/model_multiclass_lr.pkl` | v1.21 | **已禁用** (enabled=false, No-Go) |

---

## 六、aligned_features.csv 特征字段

| 字段 | 类型 | 说明 |
|------|------|------|
| `source` | str | 数据来源标识 (kaggle / mendeley / mmpsy) |
| `age` | numeric | 年龄 (范围 12-35 合理) |
| `gender` | numeric | 0=Female, 1=Male |
| `cgpa` | numeric | 学业成绩 |
| `stress_level` | numeric | 压力水平 |
| `sleep_duration` | numeric | 睡眠时长 (小时) |
| `social_support` | numeric | 社会支持 (⚠ 部分为默认值 2.0) |
| `financial_pressure` | numeric | 经济压力 |
| `family_history` | numeric | 家族史 (0/1) |
| `academic_pressure` | numeric | 学业压力 |
| `exercise_frequency` | numeric | 运动频率 |
| `anxiety` | numeric | 焦虑 (⚠ 可能为代理特征) |
| `panic_attack` | numeric | 恐慌发作 (0/1) |
| `treatment_seeking` | numeric | 求助意愿 (0/1) |
| `study_year` | numeric | 学年 |
| `label_binary` | numeric | 二分类标签 (0/1) |
| `label_source` | str | 标签来源 |
| `phq9_total` | numeric | PHQ-9 总分 |
| `phq9_severity` | str | PHQ-9 严重程度 |

---

## 七、基线确认结论

1. **所有 v1.23 Phase 0 要求的文件均已存在**，无缺失项。
2. `aligned_features.csv` 已包含 `source` 字段，可按数据源分层。
3. v1.20 模型是当前默认主模型，v1.21 作为实验路径已接入。
4. 后端已预留实验模型扩展机制 (`experimental_real_*` 字段模式可直接复用)。
5. 前端已有实验参考展示区域，可直接扩展。
6. **尚未创建 v1.23 训练脚本目录**（`backend/scripts/modeling/v1_23/`），Phase 1 中创建。

> **结论**: Phase 0 通过 ✅，可进入 Phase 1（数据准备）。

---

> **检查人**: Ralph AI Agent
> **检查日期**: 2026-05-02
