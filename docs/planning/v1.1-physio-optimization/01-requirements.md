# 产品需求文档 (PRD) - 生理模型优化（深度学习方案）

> **项目名称**: 抑郁症预警系统 (Depression Warning System)
> **版本**: v3.2.0
> **迭代**: v1.1-physio-optimization
> **日期**: 2026-04-27
> **目标**: 用深度学习模型替换启发式生理模型，提升生理数据预测准确率

## 1. 项目概述

### 1.1 背景
当前系统的生理模型使用启发式规则（基于睡眠时长、运动量的简单阈值判断），导致：
- F1-Score 仅 0.6667
- 准确率仅 0.5000（所有低风险样本被误分类为高风险）
- 召回率 1.0000（过度预测）

通过引入 Depresjon 数据集（1,029 样本）和 Kaggle Wearable 数据集（~1,000 样本），可以训练专用的深度学习生理预测模型。

### 1.2 目标
将生理模型从启发式规则升级为深度学习模型，实现：
- **F1-Score ≥ 0.80**（当前 0.6667）
- **Accuracy ≥ 0.75**（当前 0.5000）
- **Precision ≥ 0.70**（当前 0.5000）
- **Recall ≥ 0.80**（当前 1.0000，需更平衡）
- **ROC-AUC ≥ 0.85**（新增指标）
- **Latency < 50 ms**（当前 0.01 ms，可接受适度增加）

### 1.3 目标用户
- **系统用户**: 获得更准确的生理风险评估
- **咨询师**: 接收更可靠的预警通知
- **管理员**: 通过模型管理界面查看新模型状态

## 2. 功能需求详解

### 2.1 数据预处理模块 (Data Preprocessing)

#### 2.1.1 数据加载与合并
- **输入**: Depresjon 数据集 + Kaggle Wearable 数据集
- **处理**:
  - 标准化列名映射到系统字段
  - 单位统一（小时、BPM、步数）
  - 缺失值处理（中位数填充）
- **输出**: 统一格式的合并数据集

#### 2.1.2 特征工程
- **新特征创建**:
  | 特征名 | 公式 | 说明 |
  |--------|------|------|
  | sleep_efficiency | sleep_quality / sleep_hours | 每小时睡眠质量 |
  | activity_intensity | steps / (exercise_minutes + 1e-6) | 每分钟运动步数（除零保护） |
  | cardiovascular_risk | systolic_bp / diastolic_bp | 脉压比代理 |
  | hr_sleep_interaction | heart_rate * (10 - sleep_hours) | 睡眠不足压力指标 |
  | overall_activity | steps * exercise_minutes | 总活动量 |
  | bp_category | 分类（正常/前期高血压/高血压） | 临床解释 |

#### 2.1.3 数据清洗与增强
- 异常值裁剪（HR > 200, sleep > 12h）
- Winsorization（1st/99th 百分位）
- 标准化/归一化（StandardScaler）
- **数据增强**: SMOTE 处理类别不平衡（35% 抑郁 vs 65% 健康）
- **时序特征**: 若数据包含时间戳，构建滑动窗口特征

### 2.2 深度学习模型训练模块 (Deep Learning Model Training)

#### 2.2.1 模型候选
| 模型 | 优先级 | 说明 | 适用场景 |
|------|--------|------|----------|
| **MLP (多层感知机)** | 🥇 Primary | 全连接网络，适合结构化特征 | 基线深度学习模型 |
| **TabNet** | 🥈 Secondary | 专为表格数据设计的深度学习 | 自动特征选择 |
| **FT-Transformer** | 🥉 Alternative | Transformer 架构处理表格数据 | 特征交互复杂 |
| **ResNet (1D-CNN)** | Alternative | 一维卷积处理时序生理信号 | 含时序数据时 |

#### 2.2.2 MLP 架构设计（主选）
> **科学约束**: 鉴于 ~2,000 样本的小数据集，模型必须轻量以防止过拟合。

```
输入层 (13 features)
    ↓
BatchNorm1d
    ↓
Dense(64) + ReLU + BatchNorm1d
    ↓
Dropout(0.4)
    ↓
Dense(32) + ReLU
    ↓
Dropout(0.3)
    ↓
Dense(16) + ReLU
    ↓
Dense(1) + Sigmoid
```

**参数规模**: ~3,500 参数（轻量级，适合小数据集）

#### 2.2.3 训练流程（严格防止数据泄漏）
> **⚠️ 关键科学约束**: SMOTE 必须在数据划分后仅应用于训练集，严禁在划分前使用！

```
1. 数据加载与合并
2. 预处理（特征工程 + 清洗）
3. 分层划分（70% / 15% / 15%）
   ├── 训练集 (70%)
   ├── 验证集 (15%)
   └── 测试集 (15%) ← 全程不参与任何训练决策
4. 仅对训练集应用 SMOTE（如启用）
5. PyTorch Dataset / DataLoader 构建
6. 模型定义（MLP）
7. 训练循环（Early Stopping + Learning Rate Scheduling）
   ├── 在训练集上训练
   ├── 在验证集上评估（早停依据）
   └── 测试集全程不参与！
8. 超参数调优（Optuna，50 trials）
   └── 每个 trial 内部执行 5 折交叉验证（每折独立应用 SMOTE）
   └── 以交叉验证的平均 F1 作为 trial 的目标函数值
9. 最终模型在 (训练集+验证集) 上训练，在测试集上评估
10. 模型保存（PyTorch .pth / ONNX）
```

#### 2.2.4 超参数搜索空间
| 参数 | 搜索范围 | 说明 |
|------|----------|------|
| hidden_dims | [[64,32,16], [32,16,8]] | 隐藏层结构（轻量级） |
| dropout_rate | [0.3, 0.5] | Dropout 比率（强正则化） |
| learning_rate | [1e-4, 5e-3] | 学习率（保守范围） |
| batch_size | [16, 32] | 批次大小 |
| epochs | [30, 100] | 训练轮数（早停防止过拟合） |
| weight_decay | [1e-4, 1e-2] | L2 正则化（强正则化） |
| use_smote | [True, False] | 是否使用 SMOTE |
| smote_ratio | [0.5, 0.8] | SMOTE 采样比例（不过度平衡） |

#### 2.2.5 训练策略
- **损失函数**: BCEWithLogitsLoss（基线）+ Focal Loss（对比实验）
- **优化器**: AdamW（weight_decay 强正则化）
- **学习率调度**: ReduceLROnPlateau（patience=5, factor=0.5）
- **早停**: 验证 F1 连续 10 轮不提升则停止（恢复最佳权重）
- **类别权重**: 根据训练集类别比例自动计算（不依赖 SMOTE 后分布）
- **梯度裁剪**: max_norm=1.0（防止梯度爆炸）
- **重采样验证**: 每轮训练前对训练集进行随机打乱

#### 2.2.6 过拟合缓解策略 (Round 2 新增)
鉴于参数/样本比约 1.75，需额外强化正则化：
- **Dropout 递增策略**: 第一层 0.4 → 第二层 0.32 → 第三层 0.24（已实施）
- **权重衰减**: weight_decay ≥ 1e-3（强 L2 正则化）
- **最大 epoch 限制**: 不超过 100 轮，配合早停
- **训练/验证差距监控**: 若差距 > 0.15，自动增加 dropout 或减小模型
- **特征选择**: 训练后检查 VIF，移除 VIF > 10 的冗余特征

#### 2.2.7 特征共线性处理 (Round 2 新增)
- **VIF 检查**: 训练后计算所有特征的方差膨胀因子
- **冗余特征处理**: 若发现高共线性特征对（如 sleep_hours 与 sleep_efficiency），基于验证集性能决定保留哪个特征（保留验证 F1 更高的那个）
- **相关矩阵分析**: 输出特征相关系数热力图，识别高相关特征对

### 2.3 模型评估模块 (Model Evaluation)

#### 2.3.1 评估指标
- F1-Score（主要指标）
- Accuracy
- Precision / Recall
- ROC-AUC
- 混淆矩阵
- **AUPRC**（精确率-召回率曲线下面积，更适合不平衡数据）

#### 2.3.2 验证协议（严格科学标准）
- **5 折分层交叉验证**（每折内部独立预处理，防止数据泄漏）
- **Hold-out 测试集**（15% 未见数据，仅用于最终评估）
- **Bootstrap 置信区间**（1000 次重采样，计算 95% CI）
- **校准曲线**（预测概率 vs 实际概率，评估可靠性）
- **SHAP 解释性分析**（基于背景样本的特征重要性）
- **McNemar 检验**（与启发式模型进行统计显著性比较）
- **Bonferroni 校正**（多重比较校正，控制族错误率）

### 2.4 系统集成模块 (System Integration)

#### 2.4.1 模型替换
```
当前: predict_fusion() -> _predict_physiological() [HEURISTIC]
优化后: predict_fusion() -> _predict_physiological() [DL MODEL v2]
```

#### 2.4.2 接口兼容
- 保持现有 API 契约不变
- **API 输入**: 7 个原始特征 [sleep_hours, sleep_quality, exercise_minutes, heart_rate, systolic_bp, diastolic_bp, steps]
- **内部处理**: 输入 7 个原始特征后，自动进行特征工程扩展为 13 维（6 个原始 + 6 个派生特征 + 1 个分类特征）
- **输出**: risk_score (0-100)

#### 2.4.3 回退机制
- 如果 DL 模型文件不存在，自动回退到启发式规则
- 如果 DL 模型预测失败，自动回退到启发式规则
- 如果 PyTorch 未安装，自动回退到启发式规则

### 2.5 模型管理模块 (Model Management)

#### 2.5.1 模型注册
- 在 ModelRegistry 中注册新生理模型
- 版本号: physiological_model_v2_dl
- 元数据: 训练日期、数据集来源、性能指标、架构信息

#### 2.5.2 模型切换
- 管理员可通过管理后台切换模型版本
- 支持 A/B 测试（新旧模型对比）

#### 2.5.3 模型信息查询接口
- **URL**: `GET /api/v1/admin/models/physiological`
- **Auth**: Admin
- **功能**: 返回当前生理模型的元数据（版本、架构、训练日期、性能指标、特征重要性）
- **用途**: 管理员在后台查看模型状态和性能

## 3. 非功能需求

### 3.1 性能
- 模型加载时间 < 5 秒
- 单次预测延迟 < 50 ms（PyTorch CPU 推理）
- 批量预测支持（1000 条 < 5 秒）
- 模型文件大小 < 50MB

### 3.2 安全
- 模型文件权限控制（仅服务账户可读取）
- 输入数据验证（防止对抗样本）
- 推理时关闭梯度计算（torch.no_grad()）

### 3.3 可维护性
- 训练脚本可重复执行
- 模型版本控制（与代码版本对应）
- 训练日志完整记录（TensorBoard / wandb）
- 支持导出为 ONNX 格式（跨平台部署）

## 4. 假设与约束

- Depresjon 和 Kaggle 数据集已放置在 `datasets/physiological/external/` 目录
- 系统已安装 PyTorch ≥ 2.2.0、scikit-learn ≥ 1.3.2
- 训练过程可在 CPU 完成（~2,000 样本，小模型）
- 可选 GPU 加速（CUDA 可用时自动切换）
- 新模型文件大小 < 50MB

## 4.1 推演验证 (Simulation Results)

基于设计文档进行的计算推演结果：

| 推演项 | 结论 | 风险等级 |
|--------|------|----------|
| Optuna 50 trials × 5 折 CV 计算开销 | 总训练 250 次，CPU 约 3-30 分钟，可接受 | 🟢 低 |
| ~3,500 参数在 ~2,000 样本上的过拟合 | 参数/样本比 1.75，需强正则化；已配置 BatchNorm + Dropout + Early Stopping + Weight Decay | 🟡 中 |
| PyTorch CPU 推理延迟 | 单次 ~0.8 ms，远 < 50ms 目标；批量 1,000 条约 15 ms | 🟢 低 |
| SMOTE 在 35%/65% 比例下的效果 | sampling_strategy=0.5 推荐，不过度平衡；13 维低维空间合成样本风险可控 | 🟢 低 |
| 13 维特征共线性风险 | sleep_hours/sleep_efficiency、steps/activity_intensity 存在共线性；L2 正则化可缓解；建议训练后检查 VIF | 🟡 中 |

**总体评估**: 设计方案可行，主要风险为过拟合和特征共线性，已通过正则化措施缓解。

## 5. 成功标准

| 指标 | 阈值 | 测量方式 |
|------|------|----------|
| F1-Score | ≥ 0.80 | 5 折交叉验证 |
| Accuracy | ≥ 0.75 | Hold-out 测试集 |
| Precision | ≥ 0.70 | Hold-out 测试集 |
| Recall | ≥ 0.80 | Hold-out 测试集 |
| ROC-AUC | ≥ 0.85 | Hold-out 测试集 |
| AUPRC | ≥ 0.75 | Hold-out 测试集 |
| 融合准确率 | ≥ 0.90 | 现有测试场景 + 新增场景 |
| 融合延迟 p95 | < 200 ms | 负载测试 |
| 回归测试 | 0 失败 | 完整测试套件（136 测试） |
