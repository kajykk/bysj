# v1.23 交付报告 (DELIVERY_REPORT)

> **版本**: v1.23-external-risk-model-upgrade
> **日期**: 2026-05-02
> **状态**: ✅ 全部交付

---

## 一、交付概览

| 阶段 | 名称 | 状态 |
|------|------|------|
| Phase 0 | 资产检查 | ✅ |
| Phase 1 | 数据准备 | ✅ |
| Phase 2 | 模型训练 | ✅ |
| Phase 3 | 模型评估 | ✅ |
| Phase 4 | 校准与阈值 | ✅ |
| Phase 5 | 外部验证 | ✅ |
| Phase 6 | 三模型对比 | ✅ |
| Phase 7 | 模型产物导出 | ✅ |
| Phase 8 | 后端实验接入 | ✅ |
| Phase 9 | 前端展示接入 | ✅ |
| Phase 10 | 上线决策 | ✅ |

---

## 二、交付物清单

### 2.1 模型产物 (`backend/models/v1.23_external_lr/`)

| 文件 | 说明 |
|------|------|
| `model.pkl` | v1.23 External LR Pipeline |
| `preprocessor.pkl` | ColumnTransformer (SimpleImputer + StandardScaler) |
| `metrics_train.json` | 训练/验证集指标 (AUC=0.9165, F1=0.871) |
| `metrics_eval.json` | 测试集指标 (AUC=0.9131, F1=0.8589) |
| `metrics.json` | 聚合指标 (训练+评估+对比+外部验证+校准) |
| `confusion_matrix.json` | 测试集混淆矩阵 |
| `threshold_config.json` | 风险等级阈值 (PHQ-9 对齐策略: 18/35/55/72) |
| `calibration_config.json` | 校准参数 (Brier=0.1121, ECE=0.0319) |
| `feature_schema.json` | 特征 Schema 定义 (12 个数值特征) |
| `feature_coefficients.csv` | LR 特征系数 |
| `roc_curve.csv` | ROC 曲线点 (fpr/tpr) |
| `pr_curve.csv` | PR 曲线点 (precision/recall) |
| `calibration_curve.csv` | 校准曲线点 |
| `score_distribution_histogram.csv` | 风险分分布直方图 (10 bins) |
| `comparison_metrics.json` | 三模型对比结果 |
| `external_validation_metrics.json` | 外部验证指标 (含 GAD-7) |
| `model_delta_samples.csv` | Delta 分析样本 (三模型风险分) |
| `model_card.md` | 模型卡 |

### 2.2 训练脚本 (`backend/scripts/modeling/v1_23/`)

| 文件 | 说明 |
|------|------|
| `01_prepare_external_dataset.py` | Phase 1: 数据准备 |
| `02_train_external_lr.py` | Phase 2: 模型训练 (3 种设置) |
| `03_evaluate_external_lr.py` | Phase 3: 模型评估 |
| `04_compare_with_existing_models.py` | Phase 6: 三模型对比 |
| `05_calibrate_thresholds.py` | Phase 4: 校准与阈值 |
| `05_external_validation.py` | Phase 5: 外部验证 |
| `06_export_model_artifacts.py` | Phase 7: 产物导出 |
| `07_generate_reports.py` | 报告聚合与完整性校验 |
| `08_patch_delivery_gaps.py` | 补丁: 补齐缺失产物 |

### 2.3 处理后的数据 (`data/processed/v1_23_external/`)

| 文件 | 说明 |
|------|------|
| `train.csv` | 训练集 (19,916 条) |
| `validation.csv` | 验证集 (4,318 条) |
| `test.csv` | 测试集 (4,318 条) |
| `external_mmpsy.csv` | mmpsy 外部数据 (1,275 条, 量表分+空结构化特征) |
| `split_metadata.json` | 划分元信息 |

### 2.4 规划文档 (`docs/planning/v1.23-external-risk-model-upgrade/`)

| 文件 | 说明 |
|------|------|
| `DATA_ASSET_CHECKLIST.md` | 数据资产检查清单 |
| `DATA_PREPARATION_REPORT.md` | 数据准备报告 |
| `TRAINING_REPORT.md` | 训练报告 |
| `MODEL_EVALUATION_REPORT.md` | 模型评估报告 |
| `EXTERNAL_VALIDATION_REPORT.md` | 外部验证报告 |
| `CALIBRATION_REPORT.md` | 校准报告 |
| `MODEL_COMPARISON_REPORT.md` | 模型对比报告 |
| `DEPLOYMENT_DECISION_REPORT.md` | 上线决策报告 |
| `DELIVERY_REPORT.md` | 本交付报告 |
| `NEXT_STEPS.md` | 下一步计划 |
| `V1.23_IMPLEMENTATION_PLAN.md` | 实施计划 |
| `REPORT_AGGREGATION_SUMMARY.md` | 报告聚合摘要 |
| `DELIVERY_INTEGRITY_CHECK.json` | 完整性校验 (41/41) |

### 2.5 后端改动

| 文件 | 改动 |
|------|------|
| `backend/app/core/model_registry.py` | +1 model entry (v1.23_external_lr), +2 path entries |
| `backend/app/core/model_engine.py` | +experimental path in predict_structured(), +monitoring counters, +metrics_snapshot |

### 2.6 前端改动

| 文件 | 改动 |
|------|------|
| `frontend/src/api/modelApi.ts` | +5 fields in ModelPredictResponse |
| `frontend/src/views/user/UserRiskPage.vue` | +experimental reference 2 section, +deltaExternalClass computed |

---

## 三、关键指标摘要

| 类别 | 指标 | 值 |
|------|------|-----|
| 性能 | 测试集 AUC | **0.9131** |
| 性能 | 测试集 F1 | **0.8589** |
| 性能 | 测试集 Recall | 0.8733 |
| 性能 | 测试集 Specificity | 0.7777 |
| 外部验证 | PHQ-9 Pearson r | **0.6826** |
| 外部验证 | PHQ-9 Binary AUC | 0.8672 |
| 校准 | Brier Score | 0.1121 |
| 对比 | vs v1.20 AUC 提升 | +0.0675 |
| 对比 | vs v1.20 Mean Abs Delta | 21.29 |

---

## 四、经验总结

1. **外部多样化数据提升显著**: 引入 Mendeley PHQ-9 标签后 AUC 提升 0.0675
2. **数据源分层验证至关重要**: Kaggle 97.6% 占比，Mendeley 仅 2.4%，加权训练改善有限
3. **mmpsy 外部验证受阻**: 缺少结构化特征是当前架构瓶颈，需在后续版本解决
4. **delta 过大不宜直接默认**: Mean Abs Delta 21.29 说明新旧模型评估倾向存在显著差异
5. **v1.21 的过敏感问题已修复**: v1.23 Specificity=0.7777 远超 v1.21 的 0.0315

---

> **交付确认**: ✅ v1.23 全量交付完成
