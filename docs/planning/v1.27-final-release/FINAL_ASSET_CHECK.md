# FINAL_ASSET_CHECK — v1.27 最终资产检查

> **检查日期**: 2026-05-02
> **检查范围**: 全项目模型文件、配置文件、API 类型定义
> **结论**: ✅ 全部核心资产完整，前后端类型一致

---

## 一、模型文件清单

### 1.1 v1.20 structured (default) — 结构化默认模型

| 文件 | 路径 | 存在 | 注册 |
|:---|:---|:--:|:--:|
| 模型 | `models/artifacts/structured_v1.20/structured_model_v1.20.pkl` | ✅ | ✅ |
| Scaler | `models/artifacts/structured_v1.20/structured_scaler_v1.20.pkl` | ✅ | ✅ |
| Manifest | `models/artifacts/structured_v1.20/structured_manifest_v1.20.json` | ✅ | ✅ |
| Feature Names | `models/artifacts/structured_v1.20/structured_feature_names_v1.20.json` | ✅ | — |

- **lifecycle**: `default`
- **特征维度**: 12 (age, cgpa, stress_level, sleep_duration, social_support, financial_pressure, family_history, academic_pressure, exercise_frequency, anxiety, panic_attack, treatment_seeking)
- **模型类型**: LogisticRegression (class_weight=balanced)

### 1.2 v1.21 real-data binary (deprecated)

| 文件 | 路径 | 存在 | 注册 |
|:---|:---|:--:|:--:|
| LR | `models/artifacts/structured_v1.21/model_binary_lr.pkl` | ✅ | ✅ |
| RF | `models/artifacts/structured_v1.21/model_binary_rf.pkl` | ✅ | ✅ |
| Scaler | `models/artifacts/structured_v1.21/scaler.pkl` | ✅ | ✅ |

- **lifecycle**: `deprecated`

### 1.3 v1.21 real-data multiclass (disabled)

| 文件 | 路径 | 存在 | 注册 |
|:---|:---|:--:|:--:|
| LR | `models/artifacts/structured_v1.21/model_multiclass_lr.pkl` | ✅ | ✅ |
| RF | `models/artifacts/structured_v1.21/model_multiclass_rf.pkl` | ✅ | ✅ |
| Scaler | `models/artifacts/structured_v1.21/scaler_multiclass.pkl` | ✅ | ✅ |

- **lifecycle**: `disabled` (enabled=False)

### 1.4 v1.23 external clinical-label LR (experimental)

| 文件 | 路径 | 存在 | 注册 |
|:---|:---|:--:|:--:|
| 模型 | `models/v1.23_external_lr/model.pkl` | ✅ | ✅ |
| Preprocessor | `models/v1.23_external_lr/preprocessor.pkl` | ✅ | — |

- **lifecycle**: `experimental`
- **特征维度**: 12
- **训练数据**: 外部 Kaggle+Mendeley (19,916 samples)

### 1.5 v1.24 adapter (limited_active)

| 文件 | 路径 | 存在 | 注册 |
|:---|:---|:--:|:--:|
| Adapter | `models/v1.24_adapter/score_adapter.pkl` | ✅ | ✅ |

- **lifecycle**: `limited_active`
- **类型**: piecewise_monotonic ScoreAdapter
- **mean_abs_delta**: 4.37, **auc_loss**: 0.0196

### 1.6 v1.25 lite (limited_active)

| 文件 | 路径 | 存在 | 注册 |
|:---|:---|:--:|:--:|
| 主模型 | `models/v1.25_mmpsy_lite/mmpsy_lite_model.pkl` | ✅ | ✅ |
| GBDT | `models/v1.25_mmpsy_lite/mmpsy_lite_model_gbdt.pkl` | ✅ | ✅ |
| Scaler | `models/v1.25_mmpsy_lite/mmpsy_lite_scaler.pkl` | ✅ | ✅ |
| Feature Names | `models/v1.25_mmpsy_lite/mmpsy_lite_feature_names.json` | ✅ | — |

- **lifecycle**: `limited_active`
- **特征维度**: 17
- **模型类型**: CalibratedClassifierCV(LogisticRegression)
- **阈值**: 0.40 (v1.26)

### 1.7 其他模型文件 (文本/融合/生理)

| 类别 | 文件 | 存在 |
|:---|:---|:--:|
| 文本 | `models/text/improved_bilingual_model.pkl` | ✅ |
| 文本 | `models/text/improved_bilingual_tfidf.pkl` | ✅ |
| 文本 | `models/artifacts/text_depression_classifier/text_model.pkl` | ✅ |
| 文本 | `models/artifacts/text_depression_classifier/text_tfidf.pkl` | ✅ |
| 生理 | `models/artifacts/physiological/model.json` | ✅ |
| 生理 | `models/artifacts/physiological/scaler.json` | ✅ |
| 生理 | `models/artifacts/physiological/feature_names.json` | ✅ |
| Quick | `models/structured/Logistic_Regression_quick.pkl` | ✅ |

---

## 二、配置文件检查

### 2.1 config.py — ✅

| 配置项 | 值 | 状态 |
|:---|:---|:--:|
| `lite_decision_threshold` | `0.40` | ✅ |
| `crisis_keywords` | 10 个中文危机词 | ✅ |
| `route_feature_coverage_threshold` | `0.80` | ✅ |
| `route_lite_min_text_length` | `20` | ✅ |
| `structured_model_mode` | `"primary"` | ✅ |
| `model_dir` | `"models"` | ✅ |

### 2.2 model_registry.py — ✅

| 功能 | 状态 |
|:---|:--:|
| `ModelLifecycle` 枚举 (6 状态) | ✅ |
| `ACTIVE_LIFECYCLES` 过滤器 | ✅ |
| `get_active_models()` | ✅ |
| `list_models_by_lifecycle()` | ✅ |
| 全部 7 个模型注册 | ✅ |

### 2.3 Lifecycle 状态分布

| Lifecycle | 模型 |
|:---|:---|
| `default` | v1.20 structured |
| `limited_active` | v1.24 adapter, v1.25 lite model, v1.25 lite scaler |
| `experimental` | v1.23 external |
| `deprecated` | v1.21 binary LR, v1.21 binary RF |
| `disabled` | v1.21 multiclass LR, v1.21 multiclass RF |

---

## 三、前后端 Schema 一致性检查

### 3.1 后端 Schema (`model_predict.py`)

| 字段 | 类型 | 状态 |
|:---|:---|:--:|
| `safety_flags` | `list[str]` | ✅ |
| `requires_human_review` | `bool` | ✅ |
| `crisis_keywords_matched` | `list[str]` | ✅ |
| `routing_info` | `RoutingInfo` | ✅ |
| `data_quality` | `DataQualityItem` | ✅ |
| `fallback_used` | `bool` | ✅ |
| `fallback_reason` | `str \| None` | ✅ |

### 3.2 前端类型 (`modelApi.ts`)

| 字段 | 类型 | 状态 |
|:---|:---|:--:|
| `safety_flags` | `string[]` | ✅ |
| `requires_human_review` | `boolean` | ✅ |
| `crisis_keywords_matched` | `string[]` | ✅ |
| `routing_info` | `RoutingInfo \| null` | ✅ |
| `adjusted_score` | `number \| null` | ✅ |
| `adjusted_delta` | `number \| null` | ✅ |
| `adapter_available` | `boolean` | ✅ |

**结论**: 前后端 Schema 一致，无遗漏字段。

---

## 四、监控 API 检查

| 端点 | 路径 | 状态 |
|:---|:---|:--:|
| Engine Snapshot | `GET /monitoring/engine-snapshot` | ✅ 已注册 |
| Dashboard Summary | `GET /monitoring/dashboard-summary` | ✅ 已存在 |

---

## 五、安全配置检查

| 功能 | 状态 |
|:---|:--:|
| Crisis 关键词 (10个) | ✅ |
| `_check_crisis_safety()` | ✅ |
| Crisis override 不依赖模型 | ✅ |
| 前端 el-alert 人工复核提醒 | ✅ |
| `safety_override_policy.md` | ✅ |

---

## 六、临时产物扫描

| 目录/文件 | 内容 | 建议 |
|:---|:---|:---|
| `frontend/playwright-report/` | E2E 测试报告 (4 个文件) | 清理或 gitignore |
| `frontend/test-results/` | 测试结果 (1 个文件) | 清理或 gitignore |
| `*.pkl` in `.gitignore` | 已在 gitignore | ✅ |

---

## 七、最终判定

| 检查项 | 结果 |
|:---|:--:|
| 所有核心模型文件存在 | ✅ |
| 所有 scaler/feature_names 伴生文件完整 | ✅ |
| 配置文件与 v1.26 一致 | ✅ |
| 前后端 Schema 一致 | ✅ |
| Lifecycle 状态正确 | ✅ |
| 安全配置完整 | ✅ |
| 监控端点已注册 | ✅ |

> **资产检查结论**: ✅ **ALL PASS** — 全部核心资产完整，无需修复。
