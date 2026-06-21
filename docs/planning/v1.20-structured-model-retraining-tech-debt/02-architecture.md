# 系统架构设计: v1.20 结构化模型重训与迁移技术债清理

## 1. 技术栈 (Tech Stack)

### 1.1 前端
- **框架**: Vue 3.4 + TypeScript
- **UI 库**: Vuetify 3
- **构建工具**: Vite 5
- **状态管理**: Pinia
- **路由**: Vue Router 4

### 1.2 后端
- **Runtime**: Python 3.12
- **框架**: FastAPI 0.115
- **ORM**: SQLAlchemy 2.0 (async)
- **数据库**: SQLite (aiosqlite)
- **迁移工具**: Alembic 1.14
- **模型序列化**: joblib, JSON (numpy-based MLP)

### 1.3 机器学习栈
- **结构化模型**: sklearn LogisticRegression / RandomForest (joblib .pkl)
- **文本模型**: TF-IDF + sklearn (joblib .pkl), BERT (transformers)
- **生理模型**: numpy-based MLP (JSON artifacts)
- **融合模型**: TensorFlow/Keras DNN (.keras)
- **科学计算**: numpy, scipy, SHAP

### 1.4 基础设施
- **部署**: Docker Compose
- **CI/CD**: Shell 脚本 (`ci_backend_verify.sh`, `ci_frontend_verify.sh`)
- **环境**: Windows (开发), Docker/Linux (生产/CI)

## 2. 系统架构概要

```
┌──────────────────────────────────────────────────────────────────┐
│                        FastAPI Application                       │
│                                                                  │
│  ┌─────────────┐  ┌──────────────┐  ┌────────────────────────┐  │
│  │  API Routes │  │  Middleware   │  │  Exception Handlers    │  │
│  │  /api/v1/*  │  │  (Auth/CORS)  │  │  (Global Error Catch)  │  │
│  └──────┬──────┘  └──────────────┘  └────────────────────────┘  │
│         │                                                        │
│  ┌──────▼──────────────────────────────────────────────────────┐ │
│  │                     ModelEngine (Core)                       │ │
│  │  ┌──────────────┐ ┌──────────────┐ ┌─────────────────────┐  │ │
│  │  │ Structured   │ │    Text      │ │  Physiological      │  │ │
│  │  │ Predictor    │ │  Predictor   │ │    Predictor        │  │ │
│  │  │              │ │              │ │ (MLP + Heuristic)   │  │ │
│  │  │ LR + Heuris- │ │ TF-IDF/BERT  │ │                     │  │ │
│  │  │ tic Fallback │ │ + Crisis Det │ │                     │  │ │
│  │  └──────────────┘ └──────────────┘ └─────────────────────┘  │ │
│  │                                                              │ │
│  │  ┌──────────────────────────────────────────────────────────┐ │ │
│  │  │              Fusion Priority Engine                       │ │ │
│  │  │  (加权融合 + 危机覆盖 + 优先级规则)                         │ │ │
│  │  └──────────────────────────────────────────────────────────┘ │ │
│  └──────────────────────────────────────────────────────────────┘ │
│                                                                  │
│  ┌──────────────────────┐  ┌──────────────────────────────────┐  │
│  │   Model Registry     │  │     Model Loader (ml/model_loader) │  │
│  │   (model_registry.py)│  │     load_model / load_scaler / ... │  │
│  └──────────────────────┘  └──────────────────────────────────┘  │
└──────────────────────────────────────────────────────────────────┘
```

## 3. 模型加载与 Fallback 架构 (核心变更点)

### 3.1 当前状态：结构化模型加载链

```
predict_structured(features)
         │
         ▼
_load_model("structured_logistic_regression_quick")
         │
    ┌────┴────┐
    ▼         ▼
  成功      失败 (FileNotFoundError/ValueError)
    │         │
    ▼         ▼
真实模型  _structured_heuristic_fallback(raw)
预测路径  启发式规则计算 risk_score
```

### 3.2 v1.20 目标状态：增强版加载链

```
predict_structured(features)
         │
         ▼
检查 STRUCTURED_MODEL_MODE 环境变量
         │
    ┌────┼────────────┐
    ▼    ▼            ▼
 primary  fallback    未设置
    │      │           │
    ▼      ▼           ▼
_load_model()  heuristic   _load_model()
    │                      │
    ├── 成功 → 真实模型预测  ├── 成功 → 真实模型预测
    ├── 失败 → heuristic    ├── 失败 → heuristic
    │           + WARNING   │           + WARNING
    │           + fallback   │           + fallback
    │           _reason      │           _reason
```

### 3.3 Artifact 目录结构 (v1.20 新增)

```
models/
├── artifacts/
│   ├── depression_tabular/          # 结构化模型 (现有)
│   │   ├── best_model.pkl           #   当前使用（可能损坏）
│   │   └── metrics.json
│   ├── structured_v1.20/            # v1.20 新增
│   │   ├── structured_model_v1.20.pkl
│   │   ├── structured_scaler_v1.20.pkl
│   │   ├── structured_feature_names_v1.20.json
│   │   ├── structured_metrics_v1.20.json
│   │   └── structured_manifest_v1.20.json
│   ├── physiological/               # 生理模型 (现有)
│   │   ├── model.json
│   │   ├── scaler.json
│   │   ├── feature_names.json
│   │   └── metrics.json
│   └── text_depression_classifier/  # 文本模型 (现有)
│       ├── text_model.pkl
│       └── text_tfidf.pkl
```

### 3.4 Manifest 设计

```json
{
  "model_name": "structured_depression_model",
  "version": "v1.20",
  "created_at": "2026-05-01",
  "framework": "sklearn",
  "sklearn_version": "1.5.0",
  "model_type": "LogisticRegression",
  "random_seed": 42,
  "features": [
    "phq9_score", "gad7_score", "sleep_quality",
    "social_support", "financial_pressure", ...
  ],
  "metrics": {
    "accuracy": 0.xx,
    "f1_score": 0.xx,
    "precision": 0.xx,
    "recall": 0.xx,
    "roc_auc": 0.xx,
    "auprc": 0.xx
  },
  "training_config": {
    "train_size": 0.7,
    "val_size": 0.15,
    "test_size": 0.15,
    "cv_folds": 5,
    "class_weight": "balanced"
  },
  "fallback": "heuristic"
}
```

## 4. 配置管理

### 4.1 新增环境变量

| 变量名 | 类型 | 默认值 | 说明 |
|---|---|---|---|
| `STRUCTURED_MODEL_MODE` | `primary` / `fallback` | `primary` | 控制结构化模型加载策略 |
| `STRUCTURED_MODEL_ARTIFACTS_DIR` | Path | `models/artifacts/structured_v1.20/` | 新模型 artifact 目录 |

### 4.2 Model Registry 更新

在 `model_registry.py` 中新增：

```python
"structured_logistic_regression_v1.20": "models/artifacts/structured_v1.20/structured_model_v1.20.pkl",
"structured_scaler_v1.20": "models/artifacts/structured_v1.20/structured_scaler_v1.20.pkl",
"structured_feature_names_v1.20": "models/artifacts/structured_v1.20/structured_feature_names_v1.20.json",
"structured_manifest_v1.20": "models/artifacts/structured_v1.20/structured_manifest_v1.20.json",
```

## 5. Alembic 迁移架构

### 5.1 当前状态：双 Head 问题

```
Revision Tree (当前):
  eab25055097a (consolidated_initial_schema)
       │
       ├── 5f2c9d3a1b7e (add_refresh_token_sessions)
       │        │
       │        ├── a1b2c3d4e5f6 (add_review_and_crisis_tables)  ← Head 1
       │        │        │
       │        │        └── b1a7c0d9f4e8 (add_schema_model_constraints)
       │        │
       │        └── c3d8e5f6a9b2 (add_monitoring_log_table)      ← Head 2
       │                 │
       │                 ├── d4e9f7a8c3b1 (add_canary_record_table)
       │                 ├── e5f0a8b9d4c2 (add_validation_result_table)
       │                 └── f6a1b9c0e5d3 (add_drift_alert_table)
```

### 5.2 v1.20 目标：合并后单 Head

```
Revision Tree (v1.20 合并后):
  eab25055097a (consolidated_initial_schema)
       │
       └── 5f2c9d3a1b7e (add_refresh_token_sessions)
                │
                ├── a1b2c3d4e5f6 (add_review_and_crisis_tables)
                │        │
                │        └── b1a7c0d9f4e8 (add_schema_model_constraints)
                │
                ├── c3d8e5f6a9b2 (add_monitoring_log_table)
                │        │
                │        ├── d4e9f7a8c3b1 (add_canary_record_table)
                │        ├── e5f0a8b9d4c2 (add_validation_result_table)
                │        └── f6a1b9c0e5d3 (add_drift_alert_table)
                │
                └── <merge_revision> (merge dual heads)          ← New Head
```

**操作**: `alembic merge b1a7c0d9f4e8 f6a1b9c0e5d3 -m "merge dual heads v1.20"`

## 6. API 接口定义

### 6.1 结构化预测接口 (无变更，仅内部行为变化)

- **URL**: `POST /api/v1/model/predict/structured`
- **Auth**: JWT Required

**Response (200 OK)**: v1.20 新增字段
```json
{
  "prediction": 0,
  "probability": 0.1234,
  "risk_score": 12.34,
  "risk_level": 0,
  "model_used": "structured_logistic_regression_v1.20",
  "model_version": "v1.20",
  "fallback_used": false,
  "data_quality": {
    "missing_fields": [],
    "confidence_penalty": 0.0,
    "quality_level": "complete"
  }
}
```

**Fallback 响应 (模型不可用时)**:
```json
{
  "prediction": 0,
  "probability": 0.1500,
  "risk_score": 15.00,
  "risk_level": 0,
  "model_used": "structured_heuristic_fallback",
  "model_version": "v1.20",
  "fallback_used": true,
  "fallback_reason": "model_load_failed: FileNotFoundError",
  "data_quality": { ... }
}
```

## 7. 关键流程设计

### 7.1 模型重训流程

```
1. 环境确认
   └── Docker/Linux 环境 + sklearn 可用 + 数据集可读

2. 数据准备
   └── merge_datasets() → clean_dataset() → engineer_features()
   └── train/val/test split (0.7/0.15/0.15, stratified)
   └── fit_scaler() on train only

3. 模型训练
   └── LogisticRegression / RandomForest
   └── 5-fold CV on train
   └── Record: params, random_seed=42

4. 评估
   └── Test set evaluation
   └── Metrics: accuracy, f1, precision, recall, roc_auc, auprc
   └── Confusion matrix, calibration curve

5. 输出 Artifact
   └── model .pkl, scaler .pkl, feature_names .json, metrics .json, manifest .json
```

### 7.2 模型上线与回滚流程

```
上线:
  artifacts/ 放入 models/artifacts/structured_v1.20/
  → 更新 model_registry.py
  → 设置 STRUCTURED_MODEL_MODE=primary
  → 重启服务 (preload 自动加载)

回滚:
  STRUCTURED_MODEL_MODE=fallback
  → 重启服务 (跳过真实模型，直接使用 heuristic)
  (或: 删除 artifacts 目录，触发自动 fallback)
```

## 8. 数据模型 (不变更)

v1.20 不新增或修改数据库表结构。仅合并 Alembic revision heads。

核心表结构保持不变：
- `users` — 用户认证
- `refresh_token_sessions` — Token 管理
- `review_tasks` — 审核任务
- `crisis_events` — 危机事件
- `monitoring_logs` — 监控日志
- `canary_records` — 灰度记录
- `validation_results` — 校验结果
- `drift_alerts` — 漂移告警
