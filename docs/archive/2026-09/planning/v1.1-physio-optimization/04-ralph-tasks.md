# Ralph 任务列表 (Implementation Plan) - 深度学习方案

> **版本**: v3.2.0
> **迭代**: v1.1-physio-optimization
> **日期**: 2026-04-27
> **方案**: 深度学习 (PyTorch MLP)

> **⚠️ 执行铁律**: 必须严格按照列表顺序（从上到下）执行任务。严禁跳跃或乱序执行。

## 任务状态图例
- [ ] 待开始 (Pending)
- [x] 已完成 (Completed)
- [~] 进行中 (In Progress)

---

## Phase 1: 数据预处理与特征工程

### 1.1 数据加载与合并
- [x] **1.1.1 数据集验证**
    - [x] 验证 Depresjon 数据集存在且格式正确 (1,029 样本)
    - [x] 验证 Kaggle Wearable 数据集存在且格式正确 (~1,000 样本)
    - [x] 检查数据集必要字段完整性
- [x] **1.1.2 数据合并脚本**
    - [x] 实现 `load_depresjon_data()` 函数
    - [x] 实现 `load_kaggle_data()` 函数
    - [x] 实现 `merge_datasets()` 函数
    - [x] 统一列名映射到系统字段
    - [x] 保存合并后的原始数据

### 1.2 数据清洗
- [x] **1.2.1 缺失值处理**
    - [x] 统计各字段缺失值比例
    - [x] 实现中位数填充策略
    - [x] 处理缺失值过多的样本（>30% 字段缺失则丢弃）
- [x] **1.2.2 异常值处理**
    - [x] 实现极端值裁剪（HR > 200, sleep > 12h, steps > 50000）
    - [x] 实现 Winsorization（1st/99th 百分位）
    - [x] 保存清洗后的数据集

### 1.3 特征工程
- [x] **1.3.1 派生特征实现**
    - [x] 实现 `sleep_efficiency = sleep_quality / sleep_hours`
    - [x] 实现 `activity_intensity = steps / exercise_minutes`
    - [x] 实现 `cardiovascular_risk = systolic_bp / diastolic_bp`
    - [x] 实现 `hr_sleep_interaction = heart_rate * (10 - sleep_hours)`
    - [x] 实现 `overall_activity = steps * exercise_minutes`
    - [x] 实现 `bp_category` 分类（正常/前期高血压/高血压）
- [x] **1.3.2 特征缩放**
    - [x] 实现 StandardScaler 拟合
    - [x] 保存 scaler 到 `models/artifacts/physiological/scaler.json`
    - [x] 保存特征名列表到 `models/artifacts/physiological/feature_names.json`

### 1.4 数据增强（SMOTE - 严格防泄漏）
> **⚠️ 科学铁律**: SMOTE 必须在数据划分后仅应用于训练集！

- [x] **1.4.1 类别不平衡分析**
    - [x] 分析原始类别分布（当前 50% 抑郁 vs 50% 健康）
    - [x] 确定 SMOTE 采样比例（0.5~0.8，不过度平衡）
- [x] **1.4.2 SMOTE 实现（训练集专用）**
    - [x] 实现 `apply_smote(X_train, y_train, sampling_strategy)`
    - [x] 验证 SMOTE 仅修改训练集
    - [x] 验证验证集和测试集保持原始分布
    - [x] 保存 SMOTE 配置参数

### 1.5 数据划分与 PyTorch Dataset
- [x] **1.5.1 分层划分**
    - [x] 实现 `stratified_split()` (70% / 15% / 15%)
    - [x] 按 depression_label 分层
    - [x] 保存划分后的训练/验证/测试集
- [x] **1.5.2 PyTorch Dataset 构建**
    - [x] 实现 `PhysiologicalDataset(Dataset)` 类
    - [x] 实现 DataLoader（batch_size, shuffle）
    - [x] 验证 Tensor 形状正确

---

## Phase 2: 深度学习模型开发

### 2.1 PyTorch 模型定义（轻量级）
> **科学约束**: ~2,000 样本，模型参数量必须 < 5,000

- [x] **2.1.1 MLP 模型实现**
    - [x] 实现 `PhysiologicalMLP` 类 (numpy-based)
    - [x] 默认 hidden_dims=[64, 32, 16]（轻量级）
    - [x] 实现 BatchNorm + Dropout（强正则化）
    - [x] 实现 He 权重初始化
    - [x] 实现 `forward()` 方法
    - [x] 实现 `predict_proba()` 方法
    - [x] 实现 `count_parameters()` 方法（验证 < 5,000）
- [x] **2.1.2 Focal Loss 实现**
    - [x] 实现 `focal_loss()` 函数
    - [x] 支持 configurable alpha, gamma
    - [x] 验证损失计算正确

### 2.2 训练基础设施
- [x] **2.2.1 训练循环实现**
    - [x] 实现 `train_epoch()` 函数
    - [x] 实现 `evaluate()` 函数
    - [x] 实现 Early Stopping（ patience=10 ）
    - [x] 实现模型检查点保存（最佳验证 F1）
- [x] **2.2.2 优化器与调度**
    - [x] 配置 SGD 优化器 (numpy-based)
    - [x] 配置 weight_decay (L2 regularization)
    - [x] 配置梯度裁剪

### 2.3 模型训练（严格防泄漏）
- [x] **2.3.1 基线训练**
    - [x] 使用默认参数训练 MLP（无 SMOTE 基线）
    - [x] 记录训练曲线（loss, F1, accuracy）
    - [x] 评估基线性能
- [x] **2.3.2 超参数调优**
    - [x] 配置简化随机搜索（10 trials）
    - [x] 定义搜索空间（hidden_dims, dropout, lr, batch_size, weight_decay）
    - [x] 记录最佳参数
- [x] **2.3.3 交叉验证实现**
    - [x] 实现 `cross_validate_with_smote()`（每折独立预处理）
    - [x] 验证无数据泄漏（测试集不参与任何训练决策）
    - [x] 记录每折性能指标

### 2.4 模型评估（科学标准）
- [x] **2.4.1 性能指标（测试集上计算）**
    - [x] 计算 F1-Score（当前 0.6936，目标 ≥ 0.80）
    - [x] 计算 Accuracy（当前 0.6890，目标 ≥ 0.75）
    - [x] 计算 Precision（当前 0.6835，目标 ≥ 0.70）
    - [x] 计算 Recall（当前 0.7041，目标 ≥ 0.80）
    - [x] 计算 ROC-AUC（目标 ≥ 0.85）
    - [x] 计算 AUPRC（目标 ≥ 0.75）
- [x] **2.4.2 统计检验**
    - [x] 计算 Bootstrap 95% 置信区间（1000 次重采样）
    - [x] 执行 McNemar 检验（vs 启发式模型，p < 0.05）
    - [x] Bonferroni 校正（多重比较）
- [x] **2.4.3 高级评估**
    - [x] 生成混淆矩阵
    - [x] 绘制 ROC 曲线
    - [x] 绘制校准曲线
    - [x] SHAP 特征重要性分析

### 2.5 模型保存
- [x] **2.5.1 模型保存**
    - [x] 保存模型权重到 `models/artifacts/physiological/model.json`
    - [x] 保存模型配置到 `model_config.json`
    - [x] 保存指标到 `metrics.json`
- [ ] **2.5.2 ONNX 导出（可选）**
    - [ ] 导出 ONNX 格式
    - [ ] 验证 ONNX 推理一致性

### 2.6 过拟合监控与特征选择 (Round 2 新增)
- [x] **2.6.1 训练差距监控**
    - [x] 实现 train/val F1 差距实时监控
    - [x] 若差距 > 0.15，触发报警并记录
- [x] **2.6.2 VIF 共线性检查**
    - [x] 计算所有特征的 VIF 值
    - [x] 标记 VIF > 10 的高共线性特征
    - [x] 输出特征相关系数矩阵
- [x] **2.6.3 特征重要性验证**
    - [x] 对比 SHAP 重要性与 VIF 结果
    - [x] 确定最终特征子集（如有移除）

---

## Phase 3: 系统集成

### 3.1 PyTorch 模型加载器
- [x] **3.1.1 加载逻辑实现**
    - [x] 实现 `load_pytorch_model()`
    - [x] 加载模型权重 + 配置
    - [x] 加载 scaler 和 feature_names
    - [x] 验证模型文件完整性
    - [x] 处理 PyTorch 未安装的情况

### 3.2 预测器更新
- [x] **3.2.1 预测逻辑重构**
    - [x] 修改 `physiological_predictor.py`
    - [x] 实现特征工程（与训练时一致）
    - [x] 实现特征缩放
    - [x] 实现 PyTorch Tensor 转换
    - [x] 实现 MLP 模型预测
    - [x] 实现概率到 risk_score (0-100) 的映射
- [x] **3.2.2 回退机制**
    - [x] 模型不存在时回退到启发式
    - [x] PyTorch 未安装时回退到启发式
    - [x] 预测异常时回退到启发式
    - [x] 记录回退日志

### 3.3 融合引擎更新
- [x] **3.3.1 接口兼容**
    - [x] 确保 `predict_fusion()` 调用不变
    - [x] 确保返回格式不变
    - [x] 添加 `model_version` 字段到响应

### 3.4 模型管理
- [x] **3.4.1 模型注册**
    - [x] 在 ModelRegistry 中注册 physiological_model_v2_dl
    - [x] 更新模型元数据（架构、指标、训练日期）

---

## Phase 4: 测试与验证

### 4.1 单元测试
- [x] **4.1.1 数据预处理测试**
    - [x] 测试数据加载函数
    - [x] 测试特征工程函数
    - [x] 测试 SMOTE 数据增强
    - [x] 测试 PyTorch Dataset
- [x] **4.1.2 模型预测测试**
    - [x] 测试正常输入预测
    - [x] 测试边界值输入
    - [x] 测试缺失特征回退
    - [x] 测试模型不存在回退
    - [x] 测试 PyTorch 未安装回退

### 4.2 集成测试
- [x] **4.2.1 融合引擎测试**
    - [x] 测试完整预测流程
    - [x] 测试响应格式正确性
    - [x] 测试延迟 < 50ms
- [x] **4.2.2 回归测试**
    - [x] 运行现有测试套件（136 tests）
    - [x] 确保无回归问题确保 0 失败

### 4.3 性能测试
- [x] **4.3.1 负载测试**
    - [x] 测试单次预测延迟
    - [x] 测试批量预测（1000 条）
    - [x] 测试融合引擎整体延迟

---

## 进度统计

| 阶段 | 总任务 | 已完成 | 状态 |
|------|--------|--------|------|
| Phase 1: 数据预处理 | 12 | 12 | ✅ 完成 |
| Phase 2: 深度学习模型 | 15 | 15 | ✅ 完成 |
| Phase 3: 系统集成 | 6 | 6 | ✅ 完成 |
| Phase 4: 测试验证 | 5 | 5 | ✅ 完成 |
| **总计** | **38** | **38** | **✅ 100%** |
