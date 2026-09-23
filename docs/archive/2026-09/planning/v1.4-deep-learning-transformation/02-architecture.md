# 系统架构设计 - v1.4 深度学习化改造

> **迭代名称**: v1.4-deep-learning-transformation
> **版本**: 2.0 (Round 2 Draft)
> **日期**: 2026-04-28
> **依据文档**: 01-requirements.md, docs/superpowers/specs/2026-04-28-deep-learning-transformation-design-v2.md

---

## 1. 技术栈

### 1.1 后端
- **Runtime**: Python 3.11+
- **框架**: FastAPI
- **ML库**: scikit-learn, XGBoost, LightGBM, PyTorch (可选)
- **数据处理**: pandas, numpy
- **数据库**: SQLite (开发) / PostgreSQL (生产)

### 1.2 基础设施
- **部署**: Docker
- **CI/CD**: GitHub Actions
- **监控**: 日志 + 自定义指标

### 1.3 质量保障
- **后端单元测试**: pytest
- **类型检查**: mypy
- **代码质量**: ruff

---

## 2. 目录结构规范

```
backend/
├── app/
│   ├── api/v1/
│   │   └── model_predict.py          # 预测API
│   ├── core/
│   │   ├── model_engine.py           # 模型推理引擎
│   │   ├── model_registry.py         # 模型注册表 (当前)
│   │   ├── model_registry_v2.py      # 模型注册表 v2 (新增)
│   │   └── risk_thresholds.py        # 风险阈值
│   ├── ml/
│   │   ├── data_loader.py            # 数据加载
│   │   ├── data_cleaner.py           # 数据清洗
│   │   ├── feature_engineering.py    # 特征工程
│   │   ├── data_split.py             # 数据划分
│   │   ├── scaler.py                 # 标准化
│   │   ├── smote.py                  # SMOTE
│   │   ├── model.py                  # NumPy MLP (当前)
│   │   ├── pytorch_mlp.py            # PyTorch MLP (新增)
│   │   ├── trainer.py                # 训练器
│   │   ├── loss.py                   # 损失函数
│   │   ├── evaluation.py             # 评估工具
│   │   ├── cross_validation.py       # 交叉验证
│   │   ├── statistical_tests.py      # 统计检验
│   │   ├── drift_detector.py         # 漂移检测 (新增)
│   │   └── model_loader.py           # 模型加载
│   └── services/
│       └── model_predict_service.py  # 预测服务
├── tests/
│   └── api/
│       └── test_model_predict.py     # 模型预测测试
└── scripts/
    ├── train_physiological_model.py  # 当前训练脚本
    ├── train_physiological_xgboost.py # XGBoost训练 (新增)
    ├── train_physiological_lightgbm.py # LightGBM训练 (新增)
    ├── train_text_bert.py            # BERT训练 (新增)
    ├── evaluation/                   # 评估脚本目录 (新增)
    │   └── evaluate_model.py         # 统一评估
    ├── optimize_fusion_weights.py    # 融合权重优化 (新增)
    └── baseline_freeze.py            # 基线冻结 (新增)
```

---

## 3. 数据模型

### 3.1 模型注册表 (ModelRegistry)

| 字段名 | 类型 | 必填 | 说明 |
|---|---|---|---|
| model_id | str | 是 | 唯一标识，lower_snake_case |
| name | str | 是 | 模型名称 |
| version | str | 是 | 语义化版本 |
| type | Enum | 是 | xgboost/lightgbm/mlp/catboost/logistic_regression |
| status | Enum | 是 | candidate/staging/production/retired |
| fallback_id | str | 是 | 回退模型ID |
| performance_threshold | dict | 否 | F1下降>5%触发告警 |
| metrics | dict | 否 | 评估指标 |
| artifact_path | str | 是 | 模型文件路径 |
| training_config | dict | 否 | 随机种子、超参数、数据划分方式 |
| created_at | datetime | 是 | 创建时间 |
| updated_at | datetime | 是 | 更新时间 |

### 3.2 评估报告 (EvaluationReport)

| 字段名 | 类型 | 说明 |
|---|---|---|
| model_id | str | 模型标识 |
| model_type | str | 模型类型 |
| metrics | dict | F1/Precision/Recall/ROC-AUC/AUPRC |
| confidence_intervals | dict | Bootstrap 95% CI |
| statistical_tests | dict | McNemar检验结果 |
| confusion_matrix | dict | 混淆矩阵 |
| feature_importance | dict | 特征重要性 |
| calibration_curve | dict | 校准曲线 |
| timestamp | datetime | 评估时间 |

---

## 4. API 接口定义

### 4.1 模型预测模块

#### 4.1.1 结构化数据预测
- **URL**: `POST /api/v1/model/predict/tabular`
- **Auth**: user.predict.use

**Request Body**:
```json
{
  "features": {
    "age": 22,
    "gender": 1,
    "stress_level": 3,
    "sleep_duration": 7,
    ...
  }
}
```

**Response (200 OK)**:
```json
{
  "prediction": 1,
  "probability": 0.85,
  "risk_score": 85.0,
  "risk_level": 3,
  "model_used": "structured_logistic_regression_quick"
}
```

#### 4.1.2 文本预测
- **URL**: `POST /api/v1/model/predict/text`
- **Auth**: user.predict.use

**Request Body**:
```json
{
  "text": "最近经常失眠，情绪很差"
}
```

**Response (200 OK)**:
```json
{
  "prediction": 1,
  "probability": 0.92,
  "sentiment_label": "negative",
  "sentiment_score": 0.92,
  "model_used": "text_depression_model"
}
```

#### 4.1.3 生理数据预测
- **URL**: `POST /api/v1/model/predict/physiological`
- **Auth**: user.predict.use

**Request Body**:
```json
{
  "physiological": {
    "sleep_hours": 7,
    "sleep_quality": 3,
    "exercise_minutes": 30,
    "heart_rate": 72,
    "systolic_bp": 120,
    "diastolic_bp": 78,
    "steps": 6500
  }
}
```

**Response (200 OK)**:
```json
{
  "prediction": 0,
  "probability": 0.35,
  "risk_score": 35.0,
  "risk_level": 1,
  "model_used": "physiological_risk_model"
}
```

#### 4.1.4 融合预测
- **URL**: `POST /api/v1/model/predict/fusion`
- **Auth**: user.predict.use

**Request Body**:
```json
{
  "features": { ... },
  "text": "最近压力很大",
  "physiological": { ... }
}
```

**Response (200 OK)**:
```json
{
  "risk_score": 62.5,
  "risk_level": 3,
  "severity": "high",
  "model_used": ["structured", "text", "physiological"],
  "fusion_detail": {
    "modality_scores": {
      "structured": {"score": 55, "model": "catboost"},
      "text": {"score": 78, "model": "tfidf_lr"},
      "physiological": {"score": 42, "model": "xgboost"}
    },
    "weights": {"final": 62.5, "scheme": "confidence_weighted"},
    "dominant_modality": "text",
    "modality_quality": {
      "structured": "primary",
      "text": "primary",
      "physiological": "secondary"
    }
  },
  "intervention_level": "high",
  "intervention_actions": ["发送高风险预警", "优先转介人工干预"]
}
```

### 4.2 模型实验模块

#### 4.2.1 导入数据集
- **URL**: `POST /api/v1/model/experiment/import`

#### 4.2.2 训练模型
- **URL**: `POST /api/v1/model/experiment/train`

#### 4.2.3 评估模型
- **URL**: `POST /api/v1/model/experiment/evaluate`

#### 4.2.4 对比模型
- **URL**: `POST /api/v1/model/experiment/compare`

---

## 5. 关键流程设计

### 5.1 生理模型训练流程

```
1. 加载数据 (Depresjon + Kaggle)
   → merge_datasets()

2. 数据清洗
   → clean_dataset()
   → 异常值裁剪 (1st/99th百分位)
   → 缺失值填充 (中位数)

3. 特征工程
   → engineer_features()
   → 13维特征 (7原始+6衍生)

4. 数据划分
   → stratified_split(0.7/0.15/0.15)
   → 验证无数据泄漏

5. 预处理 (训练集 only)
   → scaler.fit_transform(X_train)
   → scaler.transform(X_val/test)
   → SMOTE(X_train, y_train, ratio≤0.8:1)

6. 模型训练
   → 5-Fold CV (每折独立预处理)
   → 早停 (patience=10)
   → 学习率衰减

7. 评估
   → Bootstrap 95% CI
   → McNemar vs 基线
   → 特征重要性
   → 校准曲线

8. 保存产物
   → model.json / model.pkl
   → scaler.json
   → feature_names.json
   → metrics.json
```

### 5.2 融合预测流程

```
1. 接收三模态输入
   → features (结构化)
   → text (文本)
   → physiological (生理)

2. 单模态预测
   → structured_score (CatBoost)
   → text_score (TF-IDF+LR / BERT)
   → physio_score (XGBoost / MLP)

3. 置信度计算
   → 各模态输出置信度分数

4. 动态权重
   → weights = base_weights × confidence
   → 归一化

5. 模态缺失处理
   → 缺失模态权重重分配

6. 加权融合
   → fused_score = Σ(score × weight)

7. 风险等级
   → 根据阈值划分等级

8. 干预建议
   → 根据风险等级生成建议
```

### 5.3 回退流程（多级回退）

```
1. 模型加载/预测异常
   → 捕获异常 (FileNotFoundError, ValueError, TimeoutError, etc.)

2. 检查延迟
   → 如果延迟 > 阈值，标记为超时异常

3. 确定回退级别
   → Level 1: 主模型异常 → 次级模型
   → Level 2: 次级模型异常 → 启发式规则
   → Level 3: 超时异常 → 轻量级回退模型

4. 记录日志
   → 原因、时间、输入摘要、回退级别

5. 触发回退
   → 根据模型类型和级别选择回退目标
   → XGBoost → NumPy MLP → 启发式规则
   → BERT → TF-IDF+LR → 启发式规则
   → 融合异常 → 规则融合

6. 返回结果
   → 标注使用回退模型和级别
```

---

## 6. 组件设计

### 6.1 原子组件 (Atomic Components)

| 组件 | 职责 | 输入 | 输出 |
|---|---|---|---|
| SimpleStandardScaler | 标准化 | 特征矩阵 | 标准化矩阵 |
| SimpleSMOTE | 过采样 | 不平衡数据 | 平衡数据 |
| PhysiologicalMLP | NumPy MLP推理 | 特征向量 | 概率 |
| PyTorchMLP | PyTorch MLP推理 | 特征向量 | 概率 |
| XGBoostClassifier | XGBoost推理 | 特征向量 | 概率 |
| LightGBMClassifier | LightGBM推理 | 特征向量 | 概率 |

### 6.2 业务组件 (Business Components)

| 组件 | 职责 | 依赖 |
|---|---|---|
| ModelEngine | 模型推理引擎 | 所有模型组件 |
| ModelRegistryV2 | 模型注册与管理 | 数据库 |
| FusionEngine | 多模态融合 | 单模态预测结果 |
| DriftDetector | 漂移检测 | 历史/当前数据 |
| FallbackManager | 回退管理 | 注册表 |
| CanaryManager | 灰度发布控制 | 注册表、配置中心 |
| TimeoutGuard | 超时检测与回退 | 所有模型组件 |

### 6.3 状态管理

- **ModelRegistry**: 模型元数据状态 (candidate/staging/production/retired)
- **ModelEngine**: 运行时模型缓存
- **DriftDetector**: 漂移告警状态

---

## 7. 安全设计

### 7.1 模型安全
- 模型文件只读权限
- 模型加载时验证文件完整性
- 预测结果范围校验 [0, 100]

### 7.2 回退安全
- 回退自动触发，无需人工干预
- 回退事件必须记录日志
- 所有模型必须具备回退路径

### 7.3 数据安全
- 预处理参数仅在训练集拟合
- 严禁测试集信息泄漏到训练过程
- 交叉验证每折独立预处理

---

## 8. API 错误响应定义

### 8.1 通用错误响应格式

```json
{
  "error": {
    "code": "ERROR_CODE",
    "message": "Human readable message",
    "detail": "Optional detailed description",
    "fallback_used": true,
    "fallback_level": 2,
    "fallback_model": "heuristic_rule"
  }
}
```

### 8.2 错误码定义

| 错误码 | HTTP状态码 | 说明 | 回退策略 |
|---|---|---|---|
| MODEL_NOT_FOUND | 404 | 模型文件不存在 | Level 1 回退 |
| MODEL_CORRUPTED | 422 | 模型文件损坏 | Level 1 回退 |
| MODEL_TIMEOUT | 504 | 模型推理超时 | Level 3 回退 |
| MODEL_PREDICTION_ERROR | 500 | 模型预测异常 | Level 2 回退 |
| FUSION_ERROR | 500 | 融合计算异常 | 规则融合 |
| INVALID_INPUT | 400 | 输入数据格式错误 | 返回默认风险 |
| ALL_MODELS_FAILED | 503 | 所有模型均失败 | 返回默认中等风险 |
