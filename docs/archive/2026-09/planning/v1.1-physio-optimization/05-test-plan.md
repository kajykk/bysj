# 测试计划 (Test Plan) - 深度学习方案

> **生成时间**: 2026-04-27
> **基于文档**: 01-requirements.md, 02-architecture.md
> **测试框架**: pytest (Backend) + PyTorch 测试工具

> **⚠️ 执行铁律**: 必须严格按照列表顺序（从上到下）执行测试用例。严禁跳跃或乱序执行。

---

## 1. 数据预处理测试 (DATA-PREP)

### 1.1 数据加载
- [x] `[TC-DATA-HP-001]` 成功加载 Depresjon 数据集 (1,029 样本) (P0)
- [x] `[TC-DATA-HP-002]` 成功加载 Kaggle Wearable 数据集 (~1,000 样本) (P0)
- [x] `[TC-DATA-HP-003]` 成功合并两个数据集 (P0)
- [x] `[TC-DATA-SP-001]` 数据集文件不存在时返回错误 (P1)
- [x] `[TC-DATA-SP-002]` 数据集缺少必要字段时返回错误 (P1)

### 1.2 数据清洗
- [x] `[TC-DATA-HP-004]` 缺失值被正确填充（中位数）(P0)
- [x] `[TC-DATA-HP-005]` 极端值被正确裁剪 (P0)
- [x] `[TC-DATA-HP-006]` Winsorization 在 1st/99th 百分位生效 (P1)
- [x] `[TC-DATA-SP-003]` 缺失值过多（>30%）的样本被丢弃 (P1)

### 1.3 特征工程
- [x] `[TC-DATA-HP-007]` sleep_efficiency 计算正确 (P0)
- [x] `[TC-DATA-HP-008]` activity_intensity 计算正确 (P0)
- [x] `[TC-DATA-HP-009]` cardiovascular_risk 计算正确 (P0)
- [x] `[TC-DATA-HP-010]` hr_sleep_interaction 计算正确 (P0)
- [x] `[TC-DATA-HP-011]` overall_activity 计算正确 (P0)
- [x] `[TC-DATA-HP-012]` bp_category 分类正确 (P0)
- [x] `[TC-DATA-EC-001]` exercise_minutes=0 时 activity_intensity 处理 (P2)

### 1.4 数据增强（SMOTE - 防泄漏验证）
- [x] `[TC-DATA-HP-013]` SMOTE 增强后样本数增加 (P0)
- [x] `[TC-DATA-HP-014]` SMOTE 后类别分布平衡 (P0)
- [x] `[TC-DATA-HP-015]` SMOTE 仅应用于训练集 (P0)
- [x] `[TC-DATA-SP-004]` 样本数不足时 SMOTE 返回错误 (P1)
- [x] `[TC-DATA-EC-002]` 验证集和测试集保持原始分布 (P0)

### 1.5 PyTorch Dataset
- [x] `[TC-DATA-HP-018]` PhysiologicalDataset 初始化成功 (P0)
- [x] `[TC-DATA-HP-019]` DataLoader 生成正确批次 (P0)
- [x] `[TC-DATA-HP-020]` Tensor 形状为 (batch_size, 13) (P0)

---

## 2. 深度学习模型测试 (DL-MODEL)

### 2.1 模型架构
- [x] `[TC-DL-HP-001]` PhysiologicalMLP 初始化成功 (P0)
- [x] `[TC-DL-HP-002]` forward() 输出形状正确 (batch_size, 1) (P0)
- [x] `[TC-DL-HP-003]` predict_proba() 返回概率值 [0, 1] (P0)
- [x] `[TC-DL-HP-004]` 模型参数可训练 (P1)

### 2.2 Focal Loss
- [x] `[TC-DL-HP-005]` FocalLoss 计算正确 (P0)
- [x] `[TC-DL-HP-006]` alpha/gamma 参数生效 (P1)

### 2.3 训练流程
- [x] `[TC-DL-HP-007]` train_epoch() 运行无错误 (P0)
- [x] `[TC-DL-HP-008]` validate_epoch() 返回正确指标 (P0)
- [x] `[TC-DL-HP-009]` Early Stopping 在 patience 后触发 (P1)
- [x] `[TC-DL-HP-010]` 模型检查点保存正确 (P1)

### 2.4 超参数调优
- [x] `[TC-DL-HP-011]` Optuna study 创建成功 (P0)
- [x] `[TC-DL-HP-012]` 50 trials 完成无错误 (P0)
- [x] `[TC-DL-HP-013]` 最佳参数被正确记录 (P0)

---

## 3. 模型评估测试 (MODEL-EVAL)

### 3.1 性能指标（测试集上评估）
- [x] `[TC-EVAL-HP-001]` F1-Score ≥ 0.80 (P0)
- [x] `[TC-EVAL-HP-002]` Accuracy ≥ 0.75 (P0)
- [x] `[TC-EVAL-HP-003]` Precision ≥ 0.70 (P0)
- [x] `[TC-EVAL-HP-004]` Recall ≥ 0.80 (P0)
- [x] `[TC-EVAL-HP-005]` ROC-AUC ≥ 0.85 (P0)
- [x] `[TC-EVAL-HP-006]` AUPRC ≥ 0.75 (P0)

### 3.2 统计检验
- [x] `[TC-EVAL-HP-007]` Bootstrap 95% CI 计算正确 (P1)
- [x] `[TC-EVAL-HP-008]` McNemar 检验 p < 0.05 (vs 启发式) (P1)
- [x] `[TC-EVAL-HP-009]` Bonferroni 校正应用正确 (P1)

### 3.3 高级评估
- [x] `[TC-EVAL-HP-010]` 混淆矩阵生成正确 (P1)
- [x] `[TC-EVAL-HP-011]` ROC 曲线绘制正确 (P1)
- [x] `[TC-EVAL-HP-012]` 校准曲线绘制正确 (P1)
- [x] `[TC-EVAL-HP-013]` SHAP 特征重要性计算正确 (P1)

### 3.4 对比分析
- [x] `[TC-EVAL-HP-014]` DL 模型 F1-Score > 启发式模型 (P0)
- [x] `[TC-EVAL-HP-015]` DL 模型 Accuracy > 启发式模型 (P0)

### 3.5 过拟合监控测试 (Round 2 新增)
- [x] `[TC-EVAL-HP-016]` train/val F1 差距 < 0.15 (P0)
- [x] `[TC-EVAL-HP-017]` 早停正确触发并恢复最佳权重 (P1)

### 3.6 VIF 共线性测试 (Round 2 新增)
- [x] `[TC-EVAL-HP-018]` VIF 计算正确 (P1)
- [x] `[TC-EVAL-HP-019]` 高 VIF 特征被正确标记 (P1)
- [x] `[TC-EVAL-HP-020]` 特征相关系数矩阵生成正确 (P1)

---

## 4. 系统集成测试 (SYS-INT)

### 4.1 PyTorch 模型加载
- [x] `[TC-INT-HP-001]` 模型文件成功加载 (P0)
- [x] `[TC-INT-HP-002]` Scaler 成功加载 (P0)
- [x] `[TC-INT-HP-003]` 特征名列表成功加载 (P0)
- [x] `[TC-INT-SP-001]` 模型文件不存在时回退到启发式 (P0)
- [x] `[TC-INT-SP-002]` PyTorch 未安装时回退到启发式 (P0)
- [x] `[TC-INT-SP-003]` 模型文件损坏时回退到启发式 (P1)

### 4.2 预测接口
- [x] `[TC-INT-HP-004]` 正常输入返回正确 risk_score (P0)
- [x] `[TC-INT-HP-005]` 返回结果包含 model_version (P0)
- [x] `[TC-INT-HP-006]` 预测延迟 < 50ms (P0)
- [x] `[TC-INT-SP-004]` 缺失特征时回退到启发式 (P1)
- [x] `[TC-INT-SP-005]` 异常输入时回退到启发式 (P1)

### 4.3 融合引擎
- [x] `[TC-INT-HP-007]` 融合预测流程完整执行 (P0)
- [x] `[TC-INT-HP-008]` 融合准确率 ≥ 0.90 (P0)
- [x] `[TC-INT-HP-009]` 融合延迟 p95 < 200ms (P0)

---

## 5. 回归测试 (REGRESSION)

### 5.1 现有功能
- [x] `[TC-REG-HP-001]` 结构化数据预测正常 (P0)
- [x] `[TC-REG-HP-002]` 文本情感预测正常 (P0)
- [x] `[TC-REG-HP-003]` 风险报告生成正常 (P0)
- [x] `[TC-REG-HP-004]` 预警触发逻辑正常 (P0)
- [x] `[TC-REG-HP-005]` 干预计划生成正常 (P0)

### 5.2 完整套件
- [x] `[TC-REG-HP-006]` 现有测试套件全部通过 (136 tests) (P0)

---

## 6. 测试执行统计

| 类别 | 总数 | 已通过 | 待执行 |
|------|------|--------|--------|
| 数据预处理 | 19 | 19 | 0 |
| 深度学习模型 | 13 | 13 | 0 |
| 模型评估 | 20 | 20 | 0 |
| 系统集成 | 11 | 11 | 0 |
| 回归测试 | 6 | 6 | 0 |
| **总计** | **69** | **69** | **0** |
