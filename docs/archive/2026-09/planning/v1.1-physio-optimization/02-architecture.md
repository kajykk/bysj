# 系统架构设计 (System Architecture) - 生理模型优化（深度学习方案）

> **版本**: v3.2.0
> **迭代**: v1.1-physio-optimization
> **日期**: 2026-04-27

## 1. 技术栈

### 1.1 深度学习
- **框架**: PyTorch ≥ 2.2.0
- **模型类型**: MLP (多层感知机) / TabNet / FT-Transformer
- **数据增强**: imbalanced-learn (SMOTE)
- **超参数优化**: Optuna
- **模型序列化**: PyTorch .pth / ONNX
- **可解释性**: SHAP

### 1.2 后端集成
- **Runtime**: Python 3.12
- **框架**: FastAPI (现有)
- **模型加载**: PyTorch torch.load
- **API**: 保持现有 `/api/v1/risk/predict` 接口不变

### 1.3 质量保障
- **模型测试**: pytest + PyTorch 测试工具
- **数据验证**: pandera / 自定义校验
- **回归测试**: 现有测试套件 (136 tests)

## 2. 目录结构

```
/
├── backend/
│   ├── app/
│   │   ├── services/
│   │   │   └── risk_assessment.py          # 融合引擎（修改）
│   │   ├── ml/
│   │   │   ├── __init__.py
│   │   │   ├── model_loader.py             # 模型加载器（扩展）
│   │   │   ├── physiological_predictor.py  # 生理预测器（修改）
│   │   │   └── dl_models.py                # PyTorch 模型定义（新增）
│   │   └── ...
│   └── tests/
│       └── test_ml_physio_dl.py            # 深度学习模型测试（新增）
├── models/
│   └── artifacts/
│       └── physiological/
│           ├── physiological_model_v2_dl.pth    # PyTorch 模型权重
│           ├── physiological_model_v2_dl.onnx   # ONNX 导出（可选）
│           ├── scaler.pkl                        # 特征缩放器
│           ├── feature_names.json                # 特征名列表
│           ├── model_config.json                 # 模型架构配置
│           └── metrics.json                      # 训练指标
├── datasets/
│   └── physiological/
│       └── external/
│           ├── depresjon_processed/              # Depresjon 数据集
│           └── kaggle_wearable/                  # Kaggle 数据集
└── scripts/
    └── train_physiological_dl.py                 # 深度学习训练脚本
```

## 3. 数据模型 (Data Model)

### 3.1 训练数据集
| 字段名 | 类型 | 必填 | 说明 |
|--------|------|------|------|
| sleep_hours | float | 是 | 睡眠时长（小时） |
| sleep_quality | float | 是 | 睡眠质量评分（1-10） |
| exercise_minutes | float | 是 | 运动时长（分钟） |
| heart_rate | float | 是 | 平均心率（BPM） |
| systolic_bp | float | 是 | 收缩压（mmHg） |
| diastolic_bp | float | 是 | 舒张压（mmHg） |
| steps | int | 是 | 每日步数 |
| depression_label | int | 是 | 抑郁标签（0=健康，1=抑郁） |
| phq9_score | float | 否 | PHQ-9 评分（0-27） |

### 3.2 特征工程后数据集（13 维特征）
| 字段名 | 类型 | 说明 |
|--------|------|------|
| sleep_hours | float | 原始特征 |
| sleep_quality | float | 原始特征 |
| exercise_minutes | float | 原始特征 |
| heart_rate | float | 原始特征 |
| systolic_bp | float | 原始特征 |
| diastolic_bp | float | 原始特征 |
| steps | float | 原始特征 |
| sleep_efficiency | float | 派生：sleep_quality / sleep_hours |
| activity_intensity | float | 派生：steps / exercise_minutes |
| cardiovascular_risk | float | 派生：systolic_bp / diastolic_bp |
| hr_sleep_interaction | float | 派生：heart_rate * (10 - sleep_hours) |
| overall_activity | float | 派生：steps * exercise_minutes |
| bp_category | int | 派生：0=正常, 1=前期高血压, 2=高血压 |

## 4. PyTorch 模型定义

### 4.1 MLP 模型（主选）- 轻量级设计
> **科学约束**: ~2,000 样本的小数据集，模型参数量必须 < 5,000 以防止过拟合。

```
输入层 (13 features)
    ↓
BatchNorm1d
    ↓
Dense(64) + ReLU + BatchNorm1d
    ↓
Dropout(0.4)  ← 动态递减: 0.4 * (1 - 0.2 * layer_index)
    ↓
Dense(32) + ReLU
    ↓
Dropout(0.32) ← 第二层递减后
    ↓
Dense(16) + ReLU
    ↓
Dropout(0.24) ← 第三层递减后 (最低 0.1)
    ↓
Dense(1) + Sigmoid
```

```python
import torch
import torch.nn as nn

class PhysiologicalMLP(nn.Module):
    def __init__(self, input_dim=13, hidden_dims=[64, 32, 16], dropout_rate=0.4):
        super(PhysiologicalMLP, self).__init__()
        
        layers = []
        prev_dim = input_dim
        
        for i, hidden_dim in enumerate(hidden_dims):
            layers.append(nn.Linear(prev_dim, hidden_dim))
            layers.append(nn.BatchNorm1d(hidden_dim))
            layers.append(nn.ReLU())
            # 逐层递减 dropout
            drop_rate = dropout_rate * (1.0 - 0.2 * i)
            layers.append(nn.Dropout(max(0.1, drop_rate)))
            prev_dim = hidden_dim
        
        self.feature_extractor = nn.Sequential(*layers)
        self.classifier = nn.Linear(prev_dim, 1)
        
        # 初始化权重（He 初始化）
        self._init_weights()
        
    def _init_weights(self):
        for m in self.modules():
            if isinstance(m, nn.Linear):
                nn.init.kaiming_normal_(m.weight, mode='fan_out', nonlinearity='relu')
                if m.bias is not None:
                    nn.init.constant_(m.bias, 0)
            elif isinstance(m, nn.BatchNorm1d):
                nn.init.constant_(m.weight, 1)
                nn.init.constant_(m.bias, 0)
        
    def forward(self, x):
        features = self.feature_extractor(x)
        logits = self.classifier(features)
        return logits
    
    def predict_proba(self, x):
        """返回概率值"""
        self.eval()
        with torch.no_grad():
            logits = self.forward(x)
            probs = torch.sigmoid(logits)
        return probs
    
    def count_parameters(self):
        """统计可训练参数数量"""
        return sum(p.numel() for p in self.parameters() if p.requires_grad)
```

**参数统计**: input(13) → 64(896) → 32(2080) → 16(528) → 1(17) = **~3,521 参数**

### 4.2 Focal Loss（处理类别不平衡）
> **注意**: `alpha=0.75` 用于增加正类（抑郁，少数类）的权重。当抑郁样本比例约 35% 时，给予更高权重以平衡类别。

```python
class FocalLoss(nn.Module):
    def __init__(self, alpha=0.75, gamma=2.0):
        super(FocalLoss, self).__init__()
        self.alpha = alpha
        self.gamma = gamma
        
    def forward(self, inputs, targets):
        bce = nn.functional.binary_cross_entropy_with_logits(inputs, targets, reduction='none')
        probs = torch.sigmoid(inputs)
        p_t = (probs * targets) + ((1 - probs) * (1 - targets))
        alpha_t = self.alpha * targets + (1 - self.alpha) * (1 - targets)
        loss = alpha_t * (1.0 - p_t) ** self.gamma * bce
        return loss.mean()
```

## 5. API 接口定义

### 5.1 现有接口（保持不变）

#### 5.1.1 生理数据预测
- **URL**: `POST /api/v1/risk/predict`
- **Auth**: Bearer Token

**Request Body**:
```json
{
  "physiological": {
    "sleep_hours": 6.5,
    "sleep_quality": 7.0,
    "exercise_minutes": 30.0,
    "heart_rate": 72.0,
    "systolic_bp": 120.0,
    "diastolic_bp": 80.0,
    "steps": 8000
  }
}
```

**Response (200 OK)**:
```json
{
  "physiological": {
    "score": 65.0,
    "level": 2,
    "model_version": "physiological_model_v2_dl"
  },
  "fusion": {
    "score": 58.5,
    "level": 2
  }
}
```

### 5.2 新增接口（模型管理）

#### 5.2.1 获取模型信息
- **URL**: `GET /api/v1/admin/models/physiological`
- **Auth**: Admin

**Response (200 OK)**:
```json
{
  "version": "physiological_model_v2_dl",
  "type": "PyTorch MLP",
  "architecture": {
    "input_dim": 13,
    "hidden_dims": [128, 64, 32],
    "dropout_rate": 0.3
  },
  "training_date": "2026-04-27",
  "metrics": {
    "f1_score": 0.82,
    "accuracy": 0.78,
    "precision": 0.75,
    "recall": 0.85,
    "roc_auc": 0.88,
    "auprc": 0.76
  },
  "feature_importance": {
    "sleep_hours": 0.25,
    "heart_rate": 0.20,
    "steps": 0.15,
    ...
  }
}
```

## 6. 关键流程设计

### 6.1 模型训练流程（严格防止数据泄漏）
> **⚠️ 科学铁律**: SMOTE 必须在数据划分后仅应用于训练集！

```
1. 加载数据
   ├── 读取 Depresjon 数据集
   ├── 读取 Kaggle 数据集
   └── 合并数据集

2. 数据预处理（无泄漏）
   ├── 列名标准化
   ├── 缺失值填充（中位数，基于训练集统计量）
   ├── 异常值裁剪
   ├── 特征工程（6 个新特征）
   └── 保存预处理参数

3. 数据划分（严格隔离）
   └── 分层划分 (70% / 15% / 15%)
       ├── 训练集 (70%) ← 唯一可用于学习的集合
       ├── 验证集 (15%) ← 仅用于超参数选择和早停
       └── 测试集 (15%) ← 全程锁定，仅用于最终报告

4. 训练集增强（可选）
   └── 仅对训练集应用 SMOTE
       ├── 采样比例: 0.5~0.8（不过度平衡）
       └── 验证集和测试集保持原始分布！

5. 标准化拟合（仅训练集）
   └── StandardScaler.fit() 仅在训练集上执行
       └── scaler 保存用于后续变换

6. PyTorch Dataset 构建
   └── 自定义 Dataset + DataLoader

7. 模型训练
   └── MLP（轻量级，< 5,000 参数）

8. 训练循环（严格监控）
   ├── AdamW 优化器（强 weight_decay）
   ├── BCEWithLogitsLoss / Focal Loss
   ├── ReduceLROnPlateau 调度（patience=5）
   ├── Early Stopping（patience=10，恢复最佳权重）
   └── 梯度裁剪（max_norm=1.0）

9. 5 折交叉验证（每折内部独立预处理）
   └── 每折: 划分 → 训练集 SMOTE → 训练 → 评估

10. 超参数调优
    └── Optuna (50 trials，减少计算开销)
        ├── 每 trial 使用交叉验证评估
        └── 最佳参数在验证集上确认

11. 最终模型训练
    └── 使用最佳超参数在 (训练集+验证集) 上训练
        └── 在测试集上进行无偏评估

12. 模型评估（科学标准）
    ├── 测试集性能（主要报告）
    ├── Bootstrap 95% CI
    ├── 校准曲线
    ├── SHAP 解释性分析
    └── McNemar 检验（vs 启发式模型）

13. 模型保存
    ├── PyTorch .pth (权重 + 配置)
    ├── ONNX 导出（可选）
    ├── scaler (.pkl)
    └── 指标 (.json)
```

### 6.2 预测流程（运行时）
```
1. 接收生理数据
   └── [sleep_hours, sleep_quality, exercise_minutes, heart_rate, systolic_bp, diastolic_bp, steps]

2. 特征工程（与训练时一致）
   └── 计算 6 个派生特征

3. 特征缩放
   └── 使用训练时保存的 scaler

4. 转换为 PyTorch Tensor
   └── torch.FloatTensor

5. 模型预测
   ├── 加载 physiological_model_v2_dl.pth
   ├── model.eval() + torch.no_grad()
   ├── 预测概率
   └── 转换为 risk_score (0-100)

6. 回退机制
   ├── 如果模型不存在 -> 启发式规则
   ├── 如果 PyTorch 未安装 -> 启发式规则
   └── 如果预测失败 -> 启发式规则

7. 返回结果
   └── {score, level, model_version}
```

### 6.3 集成回退流程
```python
def predict_physiological(data):
    try:
        if dl_model_exists() and pytorch_available():
            return dl_predict(data)
        else:
            return heuristic_predict(data)
    except Exception:
        return heuristic_predict(data)
```

## 7. 模型版本管理

| 版本 | 类型 | 状态 | 路径 |
|------|------|------|------|
| v1 (heuristic) | 启发式规则 | 回退 | 代码内置 |
| v2_dl (PyTorch MLP) | 深度学习 | 主用 | models/artifacts/physiological/ |

## 7.1 训练监控与日志 (Round 2 新增)

### 7.1.1 实时监控指标
```python
training_monitor = {
    "epoch": int,
    "train_loss": float,
    "train_f1": float,
    "val_loss": float,
    "val_f1": float,
    "learning_rate": float,
    "gap": float  # train_f1 - val_f1, 若 > 0.1 则报警
}
```

### 7.1.2 日志输出
- **TensorBoard**: 记录 loss、F1、ROC-AUC 曲线
- **控制台**: 每 10 个 epoch 输出当前指标
- **早停触发**: 记录最佳 epoch 和恢复权重路径

### 7.1.3 VIF 检查流程
> **依赖**: `statsmodels>=0.14.0`（已添加到 requirements.txt）

```python
def check_multicollinearity(X_train, feature_names):
    """检查特征共线性，返回 VIF 数据框。
    
    Args:
        X_train: 训练集特征矩阵 (numpy array 或 pandas DataFrame)
        feature_names: 特征名称列表
    
    Returns:
        pd.DataFrame: 包含 feature 和 VIF 列的数据框
    """
    try:
        from statsmodels.stats.outliers_influence import variance_inflation_factor
        import pandas as pd
        import numpy as np
        
        # 输入验证
        if X_train is None or len(feature_names) == 0:
            logger.warning("Empty input for VIF check")
            return pd.DataFrame(columns=["feature", "VIF"])
        
        # 确保是 numpy array
        if hasattr(X_train, 'values'):
            X_array = X_train.values
        else:
            X_array = np.array(X_train)
        
        # 检查常数列（VIF 需要）
        if np.all(X_array[:, 0] == 1):
            # 已有常数列
            X_vif = X_array
        else:
            # 添加常数列
            X_vif = np.column_stack([np.ones(X_array.shape[0]), X_array])
            feature_names = ["const"] + list(feature_names)
        
        vif_data = pd.DataFrame()
        vif_data["feature"] = feature_names
        vif_data["VIF"] = [variance_inflation_factor(X_vif, i) 
                           for i in range(X_vif.shape[1])]
        
        # 标记 VIF > 10 的特征（排除 const）
        high_vif = vif_data[(vif_data["VIF"] > 10) & (vif_data["feature"] != "const")]
        if len(high_vif) > 0:
            logger.warning(f"High VIF features detected: {high_vif.to_dict('records')}")
        
        return vif_data
        
    except ImportError:
        logger.error("statsmodels not installed. Run: pip install statsmodels>=0.14.0")
        return pd.DataFrame(columns=["feature", "VIF"])
    except Exception as e:
        logger.error(f"VIF calculation failed: {e}")
        return pd.DataFrame(columns=["feature", "VIF"])
```

## 8. 风险评估矩阵

| 风险 | 可能性 | 影响 | 缓解措施 |
|------|--------|------|----------|
| 数据分布不匹配 | 高 | 高 | 仔细预处理；领域适应 |
| 过拟合（小数据集） | 中 | 高 | Dropout + BatchNorm + Early Stopping |
| PyTorch 依赖问题 | 低 | 中 | 保持向后兼容；自动回退 |
| 推理延迟增加 | 低 | 低 | torch.no_grad()；ONNX 加速 |
| 类别不平衡 | 高 | 中 | Focal Loss + SMOTE + 类别权重 |
