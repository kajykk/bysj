# 深度学习化改造最终执行方案（修正版 V2）

- **项目名称**：抑郁症风险评估系统深度学习化改造
- **文档类型**：最终执行方案（修正版）
- **版本**：V2.0
- **日期**：2026-04-28
- **依据文档**：《系统模型性能评估与优化综合报告》、Ralph 执行铁律
- **修正说明**：基于技术严谨性评估，修正原方案中不符合数据现实和技术约束的内容

---

## 1. 文档目的

本方案用于指导抑郁症风险评估系统从"传统模型主导"逐步演进为"深度学习能力覆盖关键模态、传统模型保底兜底"的多模态智能评估系统。

本方案强调以下原则：

1. **数据现实优先**：所有技术选型必须基于当前数据形态（横截面/时序、样本量、特征维度），而非理论假设。
2. **保留现有高性能基线**：避免因架构升级导致整体效果回退。
3. **优先改造最适合且数据支持的模块**：生理数据虽为横截面，但仍有提升空间；融合层需更多场景验证。
4. **所有新模型必须可评估、可灰度、可回退**。
5. **严格遵守 Ralph 规则**：数据泄漏防护、交叉验证规范、统计显著性检验、置信区间报告。

---

## 2. 现状判断（修正）

### 2.1 当前系统模型状态

| 模型 | 类型 | 框架 | 输入 | 输出 | F1-Score | 状态 |
|------|------|------|------|------|----------|------|
| **Structured** | CatBoost | scikit-learn | 14 结构化特征 | 风险分 (0-100) | 0.8725 | ✅ 生产级强基线 |
| **Text** | TF-IDF + LR | scikit-learn | 原始文本 | 情感分 (0-1) | 0.9681 | ✅ 生产级强基线 |
| **Physiological** | MLP (NumPy) | 自定义 | 13 横截面特征 | 生理风险分 | 0.7243 | ⚠️ 可提升 |
| **Fusion** | 加权 + 规则门控 | 自定义 Python | 三模态输出 | 融合风险分 | 100% (4/4) | ⚠️ 场景不足 |

### 2.2 数据现状（关键修正）

| 数据类型 | 样本量 | 数据形态 | 深度学习适用性 |
|---------|--------|---------|---------------|
| **生理数据 (Depresjon)** | 1,029 | 横截面（每人一行统计值） | ⚠️ 仅适合 MLP/树模型 |
| **生理数据 (Kaggle)** | ~1,000 | 横截面 | ⚠️ 同上 |
| **文本数据 (Reddit)** | 7,731 | 非结构化文本 | ✅ 适合 BERT（但基线过高） |
| **结构化数据** | 27,901 | 表格数据 | ✅ 适合树模型（已最优） |
| **融合场景** | 4 | 多模态配对 | ❌ 严重不足 |

### 2.3 关键修正判断

**原方案判断**：生理数据具有时序性，适合 1D-CNN/LSTM
**修正判断**：❌ **错误**。当前生理数据为横截面数据（无时间维度），**严禁使用时序模型**。

**原方案判断**：融合层应升级为可学习门控网络
**修正判断**：⚠️ **需谨慎**。当前规则融合在 4 个场景上准确率 100%，但场景过少。应先扩展场景验证规则上限，再决定是否引入可学习网络。

**原方案判断**：文本模型应引入 BERT 进行对照实验
**修正判断**：✅ **正确**，但切换门槛必须极高（F1 > 0.97 且延迟 < 10ms）。

**原方案判断**：结构化模型应引入 FT-Transformer 对照实验
**修正判断**：⚠️ **优先级最低**。CatBoost 在表格数据上接近 SOTA，FT-Transformer 需要大量数据和调参，预期难以超越。

---

## 3. 改造目标（修正）

### 3.1 总目标

构建一个支持多模态智能推理、融合决策和模型治理的系统，使深度学习在以下环节成为主要能力：

- **生理数据建模**：基于横截面特征的深度/树模型优化
- **多模态融合决策**：规则优化为主，可学习网络为辅（数据充足后）
- **文本语义增强**：BERT 双轨制，高门槛切换
- **结构化特征**：保持 CatBoost，仅做监控

### 3.2 量化目标（修正）

| 目标 | 原方案 | 修正后 | 理由 |
|------|--------|--------|------|
| 生理模型 F1 提升 | ≥ 5% (从 0.72 → 0.77) | **≥ 8% (从 0.72 → 0.78)** | 采用 XGBoost/改进 MLP 更现实 |
| 融合层 | 可学习门控网络 | **规则优化 + 置信度加权** | 数据不足，规则仍有提升空间 |
| 文本模型 | BERT 对照实验 | **BERT 双轨制，F1>0.97 且延迟<10ms 才切换** | 基线过高，收益不确定 |
| 结构化模型 | FT-Transformer 对照 | **暂缓，保持 CatBoost** | 树模型在表格数据上 SOTA |
| 新系统能力 | 统一版本管理、监控、灰度、回退 | **同上** | ✅ 不变 |

---

## 4. 改造范围（修正）

### 4.1 纳入范围（按优先级排序）

| 优先级 | 模块 | 改造内容 | 预期收益 |
|--------|------|---------|---------|
| **P0** | 生理数据模型 | XGBoost/改进 MLP 替代当前 NumPy MLP | F1 0.72 → 0.78 |
| **P1** | 融合层 | 扩展测试场景 + 规则权重优化 + 置信度加权 | 更稳健的融合决策 |
| **P2** | 文本模型 | BERT 双轨制对照实验 | 潜在语义增强 |
| **P3** | 结构化模型 | 监控与漂移检测 | 保持现状 |
| **P4** | 数据收集 | 时序生理数据、多模态配对数据 | 为未来深度学习奠基 |

### 4.2 暂不纳入范围

- 前端界面重构
- 大语言模型作为主风险判断引擎
- 全量历史采集链路改造
- 大规模分布式训练平台建设
- **时序深度模型（1D-CNN/LSTM/Transformer）**：当前数据不支持

---

## 5. 总体执行策略（修正）

本方案采用"四步推进"策略：

1. **冻结现有基线**：保留 CatBoost、TF-IDF+LR、当前 MLP 和融合引擎作为稳定参照。
2. **优先生理模型升级**：从当前 NumPy MLP 演进为 **XGBoost** 或 **改进的 PyTorch 轻量 MLP**（基于横截面特征）。
3. **融合层规则优化**：扩展测试场景，优化权重分配，引入置信度加权。
4. **扩展文本与结构化对照实验**：BERT 双轨制高门槛切换，结构化保持现状。

---

## 6. 数据与模型对应关系（修正）

### 6.1 文本数据

适用数据集：

- `datasets/text/depression_dataset_reddit_cleaned.csv` (7,731 条)
- `datasets/text/final_depression_dataset_1.csv`
- `datasets/text/augmented_text_dataset.csv`
- `datasets/text/standardized_text_dataset.csv`
- `datasets/text/mental_health_twitter.csv`

**使用策略**：双轨制，BERT 仅作为候选模型。

### 6.2 结构化数据

适用数据集：

- `datasets/structured/student_depression_dataset.csv` (27,901 条)
- `datasets/structured/student_mental_health.csv`
- `datasets/structured/student_mental_health_enhanced.csv`

**使用策略**：保持 CatBoost，不做替换。

### 6.3 生理数据（修正：横截面）

适用数据集：

- `datasets/physiological/external/depresjon_processed/depresjon_physiological.csv` (1,029 条，**横截面**)
- `datasets/physiological/external/kaggle_wearable/mental_health_wearable_data.csv` (~1,000 条，**横截面**)

**关键修正**：
- 数据形态为 **(n_samples, n_features)**，非时序
- **严禁使用 1D-CNN/LSTM/GRU/Transformer**
- 适用模型：XGBoost、LightGBM、浅层 MLP、TabNet

### 6.4 融合与综合数据

适用数据集：

- `datasets/fusion/fusion_test_scenarios.json` (4 条，**严重不足**)
- `datasets/combined/combined_data.csv`

**关键修正**：
- 融合场景必须从 4 条扩展到 **50-100 条**
- 在场景充足前，融合层保持规则驱动

---

## 7. 具体模型选型（修正）

### 7.1 生理数据模型（第一优先级，重大修正）

#### 原方案（已废弃）

- ~~1D-CNN + MLP~~ ❌ 数据非时序
- ~~LSTM + MLP~~ ❌ 数据非时序
- ~~GRU + MLP~~ ❌ 数据非时序
- ~~Transformer Encoder for Time Series~~ ❌ 数据非时序

#### 修正后方案

**推荐方案 A：XGBoost/LightGBM（首选）**

```python
# 推荐配置
import xgboost as xgb

model = xgb.XGBClassifier(
    n_estimators=200,
    max_depth=5,
    learning_rate=0.05,
    subsample=0.8,
    colsample_bytree=0.8,
    scale_pos_weight=1.5,  # 处理类别不平衡
    random_state=42,
    eval_metric="logloss",
)
```

**优势**：
- 在表格数据上表现优异
- 自动特征重要性
- 不易过拟合（小数据集）
- 推理速度快（< 10ms）
- 可解释性强

**推荐方案 B：改进的 PyTorch 轻量 MLP（备选）**

```python
import torch
import torch.nn as nn

class PhysiologicalMLP_v2(nn.Module):
    def __init__(self, input_dim=13):
        super().__init__()
        self.net = nn.Sequential(
            nn.Linear(input_dim, 32),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(32, 16),
            nn.ReLU(),
            nn.Dropout(0.3),
            nn.Linear(16, 1),
            nn.Sigmoid(),
        )
        
    def forward(self, x):
        return self.net(x)
```

**约束**：
- 参数量 < 5,000（Ralph 规则）
- 2-3 层隐藏层
- 必须使用 Dropout + L2 + BatchNorm
- 早停 patience=10

**不推荐方案**：
- ~~TabNet~~：超参敏感，小数据集不稳定
- ~~FT-Transformer~~：参数量过大，数据不足

#### 特征工程（保持不变）

```python
# 13 个特征（7 原始 + 6 衍生）
ORIGINAL_FEATURES = [
    "sleep_hours", "sleep_quality", "exercise_minutes",
    "heart_rate", "systolic_bp", "diastolic_bp", "steps",
]

DERIVED_FEATURES = [
    "sleep_efficiency",      # sleep_quality / sleep_hours
    "activity_intensity",    # steps / exercise_minutes
    "cardiovascular_risk",   # systolic_bp / diastolic_bp
    "hr_sleep_interaction",  # heart_rate * (10 - sleep_hours)
    "overall_activity",      # steps * exercise_minutes
    "bp_category",           # 血压分类（0/1/2）
]
```

#### 数据预处理（严格遵守 Ralph 规则）

```python
# 正确流程：划分 -> 拟合 -> 转换
from sklearn.model_selection import train_test_split
from sklearn.preprocessing import StandardScaler

# Step 1: 划分（必须先划分！）
X_train, X_temp, y_train, y_temp = train_test_split(X, y, test_size=0.3, stratify=y, random_state=42)
X_val, X_test, y_val, y_test = train_test_split(X_temp, y_temp, test_size=0.5, stratify=y_temp, random_state=42)

# Step 2: 标准化（仅在训练集上 fit）
scaler = StandardScaler()
X_train_scaled = scaler.fit_transform(X_train)
X_val_scaled = scaler.transform(X_val)      # 用训练集的参数 transform
X_test_scaled = scaler.transform(X_test)    # 用训练集的参数 transform

# Step 3: SMOTE（仅在训练集上）
from imblearn.over_sampling import SMOTE
smote = SMOTE(sampling_strategy=0.8, random_state=42)  # 不超过 0.8:1（Ralph 规则）
X_train_resampled, y_train_resampled = smote.fit_resample(X_train_scaled, y_train)
```

#### 评估协议（严格遵守 Ralph 规则）

```python
from sklearn.model_selection import StratifiedKFold
from sklearn.metrics import f1_score, precision_score, recall_score, roc_auc_score
import numpy as np

# 5-Fold 交叉验证（每折独立预处理）
cv = StratifiedKFold(n_splits=5, shuffle=True, random_state=42)

f1_scores = []
for fold, (train_idx, val_idx) in enumerate(cv.split(X, y)):
    X_train_fold, X_val_fold = X[train_idx], X[val_idx]
    y_train_fold, y_val_fold = y[train_idx], y[val_idx]
    
    # 每折独立标准化
    scaler_fold = StandardScaler()
    X_train_fold_scaled = scaler_fold.fit_transform(X_train_fold)
    X_val_fold_scaled = scaler_fold.transform(X_val_fold)
    
    # 训练
    model_fold = xgb.XGBClassifier(**params)
    model_fold.fit(X_train_fold_scaled, y_train_fold)
    
    # 评估
    y_pred = model_fold.predict(X_val_fold_scaled)
    f1 = f1_score(y_val_fold, y_pred)
    f1_scores.append(f1)

# 报告均值 + 95% 置信区间（Bootstrap）
f1_mean = np.mean(f1_scores)
f1_ci = np.percentile(f1_scores, [2.5, 97.5])
print(f"F1: {f1_mean:.4f} (95% CI: {f1_ci[0]:.4f} - {f1_ci[1]:.4f})")
```

#### 预期性能

| 指标 | 当前 NumPy MLP | 目标 XGBoost | 改进幅度 |
|------|---------------|-------------|---------|
| F1-Score | 0.7243 | **0.78 - 0.82** | +8% ~ +13% |
| Accuracy | 0.6600 | **0.72 - 0.76** | +9% ~ +15% |
| Precision | 0.6091 | **0.68 - 0.72** | +12% ~ +18% |
| Recall | 0.8933 | **0.85 - 0.90** | -4% ~ +1% |
| ROC-AUC | - | **0.82 - 0.86** | 新增 |
| 推理延迟 | ~5ms | **< 10ms** | 可接受 |

---

### 7.2 文本模型（第二优先级）

#### 选型目标

文本模型当前效果极强（F1=0.9681），因此文本模块不应被"强行替换"，而应建立深度学习候选模型进行验证。

#### 推荐方案：双轨制

```python
# 基线模型（永远保留）
baseline_model = "tfidf_lr"  # F1=0.9681, latency=2ms

# 候选模型（离线评估）
candidate_model = "bert_base"  # 需微调

# 切换决策（必须同时满足）
def should_switch_to_bert(bert_metrics, baseline_metrics):
    return (
        bert_metrics["f1"] > baseline_metrics["f1"] + 0.005  # 至少提升 0.5%
        and bert_metrics["latency_p95"] < 10  # 延迟 < 10ms
        and bert_metrics["model_size_mb"] < 50  # 模型 < 50MB
    )
```

#### BERT 微调配置（如执行）

```python
from transformers import BertTokenizer, BertForSequenceClassification
from transformers import TrainingArguments, Trainer

model_name = "bert-base-chinese"  # 或英文 bert-base-uncased
tokenizer = BertTokenizer.from_pretrained(model_name)
model = BertForSequenceClassification.from_pretrained(model_name, num_labels=2)

training_args = TrainingArguments(
    output_dir="./bert_depression",
    num_train_epochs=3,
    per_device_train_batch_size=16,
    per_device_eval_batch_size=32,
    warmup_ratio=0.1,
    weight_decay=0.01,
    logging_dir="./logs",
    logging_steps=10,
    eval_strategy="epoch",
    save_strategy="epoch",
    load_best_model_at_end=True,
    metric_for_best_model="f1",
    seed=42,
)
```

#### 结论

文本模块采用"双轨制"，即基线模型与深度学习候选模型并行运行，**高门槛切换**。

---

### 7.3 结构化模型（第三优先级，降低）

#### 选型目标

结构化数据属于典型表格数据场景，树模型通常表现极强，因此深度学习在该模块更适合做监控而非替换。

#### 推荐方案：保持 CatBoost + 漂移检测

```python
# 保持现状
structured_model = "catboost"  # F1=0.8725

# 增加监控
from evidently import ColumnMapping
from evidently.report import Report
from evidently.metric_preset import DataDriftPreset

drift_report = Report(metrics=[DataDriftPreset()])
drift_report.run(reference_data=reference_data, current_data=current_data)
```

#### 结论

结构化模块**不建议替换**，除非：
- 数据量增长到 100K+
- 出现明显的非线性模式
- 树模型性能显著下降（漂移）

---

### 7.4 融合层（第二优先级，修正）

#### 原方案（已修正）

- ~~轻量 MLP 融合器~~（数据不足）
- ~~门控融合网络~~（数据不足）
- ~~Attention-based Fusion~~（数据不足）

#### 修正后方案：规则优化 + 置信度加权

```python
class OptimizedFusionEngine:
    def __init__(self):
        # 基础权重（基于更多场景统计优化）
        self.base_weights = {
            "structured": 0.50,
            "text": 0.30,
            "physiological": 0.20,
        }
        
    def fuse(self, structured_score, text_score, physio_score,
             structured_conf=1.0, text_conf=1.0, physio_conf=1.0,
             structured_missing=False, text_missing=False, physio_missing=False):
        """融合三模态输出，支持模态缺失和置信度加权。"""
        
        scores = {}
        confidences = {}
        
        if not structured_missing:
            scores["structured"] = structured_score
            confidences["structured"] = structured_conf
        if not text_missing:
            scores["text"] = text_score
            confidences["text"] = text_conf
        if not physio_missing:
            scores["physiological"] = physio_score
            confidences["physiological"] = physio_conf
            
        if not scores:
            return 50.0  # 默认中等风险
            
        # 动态权重：基础权重 * 置信度
        weights = {}
        for key in scores:
            weights[key] = self.base_weights[key] * confidences[key]
            
        # 归一化
        total_weight = sum(weights.values())
        weights = {k: v / total_weight for k, v in weights.items()}
        
        # 加权融合
        fused_score = sum(scores[k] * weights[k] for k in scores)
        
        return fused_score
```

#### 扩展融合测试场景

必须从 4 个扩展到 **50-100 个**测试场景，覆盖：

| 场景类型 | 数量 | 说明 |
|---------|------|------|
| 单模态输入 | 9 | 仅结构化/仅文本/仅生理（各3个风险等级） |
| 双模态组合 | 27 | 结构化+文本/结构化+生理/文本+生理（各9个组合） |
| 三模态完整 | 27 | 所有风险等级组合 |
| 模态缺失 | 10 | 各种缺失组合 |
| 边界值 | 10 | 临界风险分数 |

#### 结论

融合层应**先扩展场景、优化规则**，在规则明显不足且数据充足后，再考虑可学习网络。

---

## 8. 系统架构调整方案（修正）

### 8.1 目标架构

系统拆分为五层：

1. **数据接入层**：接收结构化问卷、文本描述和生理横截面数据。
2. **特征处理层**：清洗、标准化、缺失值处理、特征工程（严格遵循划分后 fit）。
3. **模型推理层**：分别承载结构化、文本、生理模型推理。
4. **融合决策层**：整合模态输出并生成最终风险等级与干预建议（规则为主）。
5. **模型治理层**：版本管理、灰度发布、监控与回退。

### 8.2 推荐实施方式

#### 第一阶段：单体内模块化（保持）

保持后端服务形态不变，仅将模型逻辑拆分为独立模块，降低耦合度。

**优点**：改造成本低、实施快、便于调试。

#### 第二阶段：逐步微服务化（保持）

待核心模型稳定后，再将文本、生理、融合等模块拆分为独立服务。

**优点**：便于独立部署、扩容与升级。

### 8.3 推荐路径（修正）

先完成单体内模块化，再根据成熟度对关键模块进行微服务化拆分。

**关键修正**：生理模型服务应支持 **XGBoost** 和 **MLP** 双版本，便于 A/B 测试。

---

## 9. 统一接口与治理机制（保持）

### 9.1 模型统一接口

每个模型模块应统一提供以下能力：

- `predict()`
- `predict_proba()`
- `load_model()`
- `get_version()`
- `get_latency()`
- `get_feature_importance()`  # 新增

### 9.2 融合层统一接口

融合层应统一提供：

- `fuse_predictions()`
- `get_risk_level()`
- `get_intervention_plan()`
- `get_modality_contribution()`  # 新增：模态贡献度

### 9.3 模型注册表（保持）

新增模型注册表，记录以下信息：

- 模型名称
- 模型版本
- 模型类型（xgboost / mlp / logistic_regression / catboost）
- 输入要求
- 当前状态（`candidate / staging / production / retired`）
- **回退模型**（必填）

### 9.4 治理目标（保持）

通过统一注册与治理，确保系统具备：

- 多模型并行运行能力
- 快速切换能力
- 灰度验证能力
- 线上回退能力

---

## 10. 训练实施方案（修正）

### 10.1 数据准备（严格遵守 Ralph 规则）

训练前需完成以下步骤：

- [ ] 统一数据格式
- [ ] 清洗异常值（基于训练集 1st/99th 百分位）
- [ ] 处理缺失值（基于训练集中位数/均值填充）
- [ ] **固化特征字典与标签定义**
- [ ] **划分训练集、验证集和测试集（必须先划分！）**
- [ ] **标准化/归一化仅在训练集上 fit**
- [ ] **SMOTE 仅在训练集上应用（比例不超过 0.8:1）**
- [ ] 保存预处理参数（scaler, imputer 等）

### 10.2 模型训练任务（修正）

#### 生理模型训练（P0）

```python
# 对照实验设计
models = {
    "xgboost": xgb.XGBClassifier(**xgb_params),
    "lightgbm": lgb.LGBMClassifier(**lgb_params),
    "mlp_v2": PhysiologicalMLP_v2(input_dim=13),  # PyTorch 轻量版
}

# 5-Fold 交叉验证（每折独立预处理）
results = {}
for name, model in models.items():
    cv_scores = cross_val_score_with_preprocessing(model, X, y, cv=5)
    results[name] = {
        "f1_mean": np.mean(cv_scores),
        "f1_ci": np.percentile(cv_scores, [2.5, 97.5]),
    }

# 选择最优模型
best_model = max(results, key=lambda k: results[k]["f1_mean"])
```

**必须输出**：
- 5-Fold F1 均值 + 95% CI
- 特征重要性（XGBoost）
- 混淆矩阵
- ROC-AUC
- 校准曲线
- SHAP 值（可解释性）

#### 文本模型训练（P2）

- 训练 `BERT` 微调模型
- 与 `TF-IDF + LR` 做离线对照评估
- **切换门槛**：F1 > 0.97 且延迟 < 10ms

#### 结构化模型训练（P3）

- **暂缓**
- 仅做漂移监控

#### 融合层训练（P1）

- **非训练，而是规则优化**
- 基于 50-100 个测试场景统计最优权重
- 引入置信度加权机制

### 10.3 训练产物（保持）

每次训练必须输出：

- 模型权重文件
- 标准化器和特征配置
- 训练日志
- **指标对比表（含 95% CI）**
- **统计显著性检验（McNemar 检验）**
- 模型版本信息

---

## 11. 评估与验收方案（修正）

### 11.1 指标体系（保持）

必须评估以下指标：

- F1（主指标）
- Precision
- Recall
- ROC-AUC
- **AUPRC（不平衡数据更重要）**
- 延迟
- 模型大小
- 内存占用
- 风险等级稳定性
- 模态缺失下的鲁棒性

### 11.2 对照实验（修正）

必须完成以下实验：

- [ ] 单模态评估（5-Fold CV）
- [ ] 多模态组合评估
- [ ] 模态缺失评估
- [ ] 高风险样本评估
- [ ] 回退路径评估
- [ ] **统计显著性检验（McNemar 检验，p < 0.05）**
- [ ] **Bootstrap 95% CI**

### 11.3 上线门槛（修正）

候选模型进入灰度部署前必须满足：

- [ ] 主指标（F1）**显著优于**现有基线（McNemar 检验 p < 0.05）
- [ ] 推理延迟可接受（< 50ms）
- [ ] 稳定性无明显问题
- [ ] 回退机制已验证
- [ ] **置信区间不包含基线值**

### 11.4 验收标准（修正）

1. [ ] 生理 XGBoost/MLP 模型完成训练，F1 ≥ 0.78，且显著优于当前 MLP
2. [ ] 融合层支持置信度加权和模态缺失处理
3. [ ] 文本 BERT 模型完成对照实验，给出是否切换结论
4. [ ] 结构化模型保持 CatBoost，漂移监控就位
5. [ ] 具备模型注册、版本管理、灰度发布与回退机制
6. [ ] 新方案通过完整离线评估与回归测试（136 个测试全部通过）
7. [ ] **所有预处理代码注释数据来源、处理逻辑、参数设置**

---

## 12. 部署与回退方案（保持）

### 12.1 灰度部署

新模型先进入 `staging` 状态，仅对小比例流量开放，并与现网模型并行输出结果。

### 12.2 监控内容

- 响应时间
- 失败率
- 风险分分布漂移
- 干预等级分布
- 模型输入缺失率
- 预测异常率（NaN、Inf、超出范围）

### 12.3 回退策略（增强）

- 文本深度模型异常时，回退到 `TF-IDF + LR`
- 生理 XGBoost 异常时，回退到当前 NumPy MLP
- 融合层异常时，回退到加权融合或规则门控
- **所有回退事件必须记录到日志，包含原因、时间、输入数据摘要**

---

## 13. 实施路线图（修正）

### 阶段 1：基线冻结与治理准备（1 周）

- [ ] 固化当前最佳模型版本
- [ ] 建立统一评估模板
- [ ] 建立模型注册机制
- [ ] **扩展融合测试场景到 50-100 个**

### 阶段 2：生理模型升级（2-3 周）

- [ ] 训练 XGBoost、LightGBM、改进 MLP 对照组
- [ ] 5-Fold CV 评估（含 95% CI）
- [ ] McNemar 检验 vs 当前 MLP
- [ ] 特征重要性分析（SHAP）
- [ ] 选择最优方案并集成

### 阶段 3：融合层优化（1-2 周）

- [ ] 基于扩展场景优化规则权重
- [ ] 实现置信度加权机制
- [ ] 模态缺失处理
- [ ] 与现有融合引擎并行评估

### 阶段 4：文本模型增强（2-3 周，可选）

- [ ] 训练 BERT 类候选模型
- [ ] 与 `TF-IDF + LR` 进行离线对比
- [ ] 高门槛切换决策

### 阶段 5：结构化模型监控（持续）

- [ ] 部署漂移检测
- [ ] 定期评估 CatBoost 性能
- [ ] 仅在必要时启动替换评估

### 阶段 6：数据收集与长期优化（持续）

- [ ] 收集时序生理数据（连续 7-14 天）
- [ ] 收集多模态配对数据
- [ ] 定期重训
- [ ] 监控数据与模型漂移

---

## 14. 风险与应对（修正）

### 风险 1：深度模型效果不稳定

**应对**：保留传统模型作为回退方案，先离线验证再上线。

### 风险 2：推理延迟上升

**应对**：优先选择轻量模型（XGBoost < 10ms），必要时采用量化、剪枝或蒸馏。

### 风险 3：数据量不足导致过拟合

**应对**：
- 加强正则化（L2, Dropout）
- 早停策略（patience=10）
- 5-Fold 交叉验证
- **严格限制模型复杂度（参数量 < 5,000）**

### 风险 4：多模型协同复杂度上升

**应对**：统一接口、统一注册、统一监控，降低模块间耦合。

### 风险 5：时序模型误用（新增）

**应对**：
- **明确禁止在当前横截面数据上使用 1D-CNN/LSTM/Transformer**
- 建立数据形态检查机制
- 仅在收集到时序数据后才启动时序模型评估

### 风险 6：数据泄漏（新增）

**应对**：
- **严格执行划分 -> 拟合 -> 转换流程**
- 代码审查预处理逻辑
- 自动化测试验证数据隔离

---

## 15. 结论（修正）

本次深度学习化改造采取**渐进式、数据驱动**的路线：

1. **先升级生理模型**：采用 XGBoost/改进 MLP（基于横截面数据），**严禁使用时序模型**
2. **再优化融合层**：扩展场景、规则权重优化、置信度加权
3. **随后引入文本深度模型**：BERT 双轨制，**高门槛切换**
4. **最后评估结构化模型**：保持 CatBoost，仅做监控

**关键修正总结**：

| 原方案 | 修正后 | 理由 |
|--------|--------|------|
| 生理模型：1D-CNN/LSTM | **XGBoost/改进 MLP** | 数据非时序 |
| 融合层：可学习门控网络 | **规则优化 + 置信度加权** | 场景不足 |
| 文本模型：BERT 对照 | **BERT 双轨制，高门槛切换** | 基线过高 |
| 结构化模型：FT-Transformer | **暂缓，保持 CatBoost** | 树模型 SOTA |
| 数据预处理：未明确 | **严格划分 -> 拟合 -> 转换** | Ralph 规则 |
| 评估标准：未明确统计检验 | **McNemar + Bootstrap CI** | Ralph 规则 |

该方案能够在**控制风险、尊重数据现实**的前提下提升系统性能，并保持现有系统的稳定性、可回退性与可持续演进能力。

---

> **报告附件**：
> - 原方案文档：`2026-04-28-deep-learning-transformation-design.md`
> - 评估依据：《系统模型性能评估与优化综合报告》
> - Ralph 规则：`e:/code/bysj/.trae/rules/Ralph.md`
> - 生理模型代码：`backend/app/ml/model.py`
> - 训练脚本：`scripts/train_physiological_model.py`
