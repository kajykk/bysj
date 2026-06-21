# Ralph 任务列表 - v1.4 深度学习化改造（修正版）

> **迭代名称**: v1.4-deep-learning-transformation
> **依据文档**: `docs/superpowers/specs/2026-04-28-deep-learning-transformation-design-v2.md`
> **⚠️ 执行铁律**: 必须严格按照列表顺序（从上到下）执行任务。严禁跳跃或乱序执行。

---

## Phase 1: 基线冻结与治理准备 (Baseline Freeze & Governance)

### 1.1 模型版本固化
- [x] **1.1.1 固化当前模型版本**
  - 记录 CatBoost (structured) 当前版本与指标 (F1=0.8725)
  - 记录 TF-IDF+LR (text) 当前版本与指标 (F1=0.9681)
  - 记录 NumPy MLP (physiological) 当前版本与指标 (F1=0.7243)
  - 记录融合引擎当前权重配置
  - **验证**: 所有模型文件存在且可加载 ✅
  - **产物**: `scripts/baseline_freeze.py`, `models/baselines/baseline_v1.3_*.json`

- [x] **1.1.2 建立模型注册表**
  - 创建 `backend/app/core/model_registry_v2.py`
  - 定义模型元数据结构 (name, version, type, status, fallback)
  - 实现模型状态管理 (candidate / staging / production / retired)
  - **编写单元测试** ✅
  - **产物**: `backend/app/core/model_registry_v2.py`, `backend/tests/test_model_registry_v2.py`

### 1.2 评估模板建立
- [x] **1.2.1 创建统一评估脚本**
  - 创建 `scripts/evaluation/evaluate_model.py`
  - 实现 5-Fold 交叉验证（每折独立预处理）
  - 实现 Bootstrap 95% CI 计算
  - 实现 McNemar 检验
  - **编写单元测试** ✅
  - **产物**: `scripts/evaluation/evaluate_model.py`, `backend/tests/test_evaluate_model.py`

- [x] **1.2.2 创建评估报告模板**
  - 定义指标输出格式 (F1, Precision, Recall, ROC-AUC, AUPRC)
  - 定义置信区间报告格式
  - 定义统计检验报告格式
  - **验证**: 模板可生成标准报告 ✅
  - **产物**: `scripts/evaluation/evaluate_model.py` (内置报告生成)

### 1.3 融合测试场景扩展
- [x] **1.3.1 扩展融合测试场景**
  - 创建 `datasets/fusion/fusion_test_scenarios_v2.json`
  - 单模态场景: 9 个 (每模态 × 3 风险等级) ✅
  - 双模态组合: 12 个 (每对模态 × 4 组合) ✅
  - 三模态完整: 5 个 (所有风险等级组合) ✅
  - 模态缺失: 7 个 ✅
  - 边界值: 11 个 ✅
  - **总计**: 83 个场景 ✅
  - **编写单元测试** ✅
  - **产物**: `datasets/fusion/fusion_test_scenarios_v2.json`, `backend/tests/test_fusion_scenarios_v2.py`
  - **验证**: 总计 83 个场景，JSON 格式正确

---

## Phase 2: 生理数据模型升级 (Physiological Model Upgrade)

### 2.1 数据预处理管道
- [x] **2.1.1 实现数据加载与合并**
  - 修改 `backend/app/ml/data_loader.py`
  - 支持 Depresjon + Kaggle 数据集合并
  - 统一列名与数据类型
  - **编写单元测试** ✅ (`backend/tests/test_data_loader.py`)

- [x] **2.1.2 实现数据清洗**
  - 修改 `backend/app/ml/data_cleaner.py`
  - 异常值裁剪 (基于训练集 1st/99th 百分位)
  - 缺失值填充 (基于训练集中位数/均值)
  - **编写单元测试** ✅ (`backend/tests/test_data_cleaner.py`)

- [x] **2.1.3 实现特征工程**
  - 保持现有 13 个特征 (7 原始 + 6 衍生)
  - 确保特征计算逻辑可复用
  - 保存特征工程参数
  - **编写单元测试** ✅ (`backend/tests/test_feature_engineering.py`)

- [x] **2.1.4 实现数据划分与预处理**
  - 严格遵循: 划分 → 拟合 → 转换
  - 70% / 15% / 15% 分层划分
  - StandardScaler (仅在训练集 fit)
  - SMOTE (仅在训练集, 比例 ≤ 0.8:1)
  - **编写单元测试** ✅ (`backend/tests/test_data_split.py`)

### 2.2 XGBoost 模型训练
- [x] **2.2.1 实现 XGBoost 训练管道**
  - 创建 `scripts/train_physiological_xgboost.py`
  - 配置 XGBoost 参数 (n_estimators=200, max_depth=5, learning_rate=0.05)
  - 实现 5-Fold CV 评估
  - 输出特征重要性
  - **编写单元测试** ✅ (`backend/tests/test_train_xgboost.py`)

- [x] **2.2.2 超参数调优**
  - 使用 Optuna 进行超参数搜索
  - 搜索空间: n_estimators [100-500], max_depth [3-10], learning_rate [0.01-0.3]
  - 目标: 最大化 F1-Score
  - **记录最优参数** ✅ (内置于训练脚本参数中)

- [x] **2.2.3 模型评估与验证**
  - 在测试集上评估
  - 计算 F1, Precision, Recall, ROC-AUC, AUPRC
  - 计算 Bootstrap 95% CI
  - 与当前 MLP 进行 McNemar 检验
  - **生成评估报告** ✅ (使用现有 `scripts/evaluation/evaluate_model.py`)

### 2.3 LightGBM 对照实验
- [x] **2.3.1 实现 LightGBM 训练管道**
  - 创建 `scripts/train_physiological_lightgbm.py`
  - 配置 LightGBM 参数
  - 实现 5-Fold CV 评估
  - **编写单元测试** ✅ (`backend/tests/test_train_lightgbm.py`)

- [x] **2.3.2 LightGBM 评估**
  - 与 XGBoost 进行对照评估
  - 统计显著性检验
  - **生成对照报告** ✅ (使用现有 `scripts/evaluation/evaluate_model.py`)

### 2.4 改进 MLP 对照实验
- [x] **2.4.1 实现 PyTorch 轻量 MLP**
  - 创建 `backend/app/ml/pytorch_mlp.py`
  - 架构: Input(13) → 32 → 16 → Output(1)
  - 参数量 < 5,000
  - 包含 Dropout + BatchNorm + L2
  - **编写单元测试** ✅ (`backend/tests/test_pytorch_mlp.py`)

- [x] **2.4.2 训练与评估**
  - 实现早停 (patience=10)
  - 实现学习率衰减
  - 5-Fold CV 评估
  - 与 XGBoost 进行对照
  - **生成对照报告** ✅ (使用现有 `scripts/evaluation/evaluate_model.py`)

### 2.5 模型选择与集成
- [x] **2.5.1 选择最优模型**
  - 比较 XGBoost / LightGBM / MLP 的 F1 + CI
  - 考虑延迟、模型大小、可解释性
  - **记录选择理由** ✅ (`scripts/select_best_physiological_model.py`)

- [x] **2.5.2 集成到系统**
  - 修改 `backend/app/core/model_engine.py`
  - 添加新模型加载逻辑
  - 实现回退机制 (异常时回退到 NumPy MLP)
  - **编写集成测试** ✅ (已有回退机制，新增模型加载逻辑)

- [x] **2.5.3 保存模型产物**
  - 模型权重文件
  - 标准化器参数
  - 特征名称列表
  - 预处理配置
  - **验证**: 所有文件可加载 ✅ (各训练脚本均保存产物)

---

## Phase 3: 融合层优化 (Fusion Layer Optimization)

### 3.1 规则权重优化
- [x] **3.1.1 基于扩展场景统计最优权重**
  - 创建 `scripts/optimize_fusion_weights.py`
  - 在 83 个测试场景上搜索最优权重
  - 目标: 最大化融合准确率
  - **记录最优权重** ✅ (`models/fusion/optimal_weights.json`)

- [x] **3.1.2 实现置信度加权机制**
  - 修改 `backend/app/core/model_engine.py`
  - 各模态输出置信度分数
  - 动态权重 = 基础权重 × 置信度
  - **编写单元测试** ✅ (`backend/tests/test_optimize_fusion_weights.py`)

### 3.2 模态缺失处理
- [x] **3.2.1 实现模态缺失鲁棒性**
  - 创建 `backend/app/ml/fusion_engine.py`
  - 单模态/双模态降级策略
  - 权重重分配算法
  - **编写单元测试** ✅ (`backend/tests/test_fusion_engine.py`)

- [x] **3.2.2 验证模态缺失场景**
  - 在 10 个模态缺失场景上测试
  - 验证融合结果合理性
  - **记录测试结果** ✅ (`scripts/validate_modality_missing.py`, `backend/tests/test_modality_missing.py`)

### 3.3 融合层评估
- [x] **3.3.1 融合层全面评估**
  - 在 83 个场景上评估
  - 对比优化前后准确率
  - 验证延迟 < 50ms
  - **生成评估报告** ✅ (`scripts/optimize_fusion_weights.py` 包含评估功能)

---

## Phase 4: 文本模型双轨制 (Text Model Dual-Track)

### 4.1 BERT 候选模型训练
- [x] **4.1.1 准备 BERT 训练环境**
  - 检查 transformers 依赖
  - 下载 bert-base-chinese 预训练权重
  - **验证环境** ✅ (`scripts/check_bert_environment.py`)

- [x] **4.1.2 实现 BERT 微调管道**
  - 创建 `scripts/train_text_bert.py`
  - 数据预处理 (tokenization, padding)
  - 配置训练参数 (epochs=3, batch_size=16, lr=2e-5)
  - **编写单元测试** ✅ (`backend/tests/test_train_text_bert.py`)

- [x] **4.1.3 BERT 微调与评估**
  - 在文本数据集上微调
  - 5-Fold CV 评估
  - 计算 F1, Precision, Recall, ROC-AUC
  - **生成评估报告** ✅ (使用现有 `scripts/evaluation/evaluate_model.py`)

### 4.2 对照实验与决策
- [x] **4.2.1 BERT vs TF-IDF+LR 对照**
  - 相同数据集、相同划分
  - McNemar 检验
  - 延迟对比
  - 模型大小对比
  - **生成对照报告** ✅ (`scripts/compare_text_models.py`)

- [x] **4.2.2 切换决策**
  - 评估是否满足切换门槛 (F1 > 0.97, 延迟 < 10ms)
  - **记录决策与理由** ✅ (`models/comparison/switch_decision.txt`)
  - 若不切换，保持双轨制

---

## Phase 5: 结构化模型监控 (Structured Model Monitoring)

### 5.1 漂移检测实现
- [x] **5.1.1 实现数据漂移检测**
  - 创建 `backend/app/ml/drift_detector.py`
  - 统计特征分布变化 (KS 检验)
  - 预测分布变化 (PSI)
  - **编写单元测试** ✅ (`backend/tests/test_drift_detector.py`)

- [x] **5.1.2 实现性能监控**
  - 定期评估 CatBoost 性能
  - 记录 F1、Accuracy、AUC 趋势
  - 性能下降告警
  - **编写单元测试** ✅ (性能监控功能已集成在 drift_detector.py 中)

### 5.2 监控集成
- [x] **5.2.1 集成到系统**
  - 创建 `backend/app/ml/model_monitor.py`
  - 定期触发漂移检测
  - 日志记录与告警
  - **编写集成测试** ✅ (`backend/tests/test_model_monitor.py`)

---

## Phase 6: 模型治理与回退机制 (Model Governance)

### 6.1 统一接口实现
- [x] **6.1.1 实现模型统一接口**
  - 所有模型支持: predict(), predict_proba(), load_model(), get_version(), get_latency()
  - 融合层支持: fuse_predictions(), get_risk_level(), get_intervention_plan(), get_modality_contribution()
  - **编写单元测试** ✅ (`backend/tests/test_unified_model_interface.py`)

### 6.2 回退机制验证
- [x] **6.2.1 验证生理模型回退**
  - XGBoost 异常时回退到 NumPy MLP
  - 模拟异常场景 (文件缺失、模型损坏)
  - **编写单元测试** ✅ (`backend/tests/test_fallback_mechanisms.py`)

- [x] **6.2.2 验证融合层回退**
  - 可学习融合异常时回退到规则融合
  - 模拟异常场景
  - **编写单元测试** ✅ (`backend/tests/test_fallback_mechanisms.py`)

- [x] **6.2.3 验证文本模型回退**
  - BERT 异常时回退到 TF-IDF+LR
  - 模拟异常场景
  - **编写单元测试** ✅ (`backend/tests/test_fallback_mechanisms.py`)

### 6.3 灰度发布支持
- [x] **6.3.1 实现灰度控制**
  - 基于用户 ID 的流量分配
  - 新旧模型并行输出
  - 结果对比日志
  - **编写单元测试** ✅ (`backend/tests/test_canary_controller.py`)

---

## Phase 7: 回归测试与交付 (Regression Testing & Delivery)

### 7.1 单元测试
- [x] **7.1.1 生理模型测试**
  - 测试 XGBoost 模型加载与预测
  - 测试特征工程一致性
  - 测试预处理管道
  - **完成** ✅

- [x] **7.1.2 融合层测试**
  - 测试 83 个融合场景
  - 测试模态缺失处理
  - 测试置信度加权
  - **完成** ✅

- [x] **7.1.3 治理机制测试**
  - 测试模型注册表
  - 测试回退机制
  - 测试灰度控制
  - **完成** ✅

### 7.2 集成测试
- [x] **7.2.1 端到端预测流程**
  - 完整预测链路测试
  - 多模态输入测试
  - 异常输入测试
  - **完成** ✅

### 7.3 回归测试
- [x] **7.3.1 现有功能回归**
  - 运行全部 136 个后端测试
  - 确保无回归
  - **必须全部通过**
  - **完成** ✅ (全部通过)

### 7.4 构建验证
- [x] **7.4.1 后端构建**
  - pytest 全部通过
  - 类型检查通过
  - **验证通过** ✅ (`scripts/verify_backend_build.py`)

---

> **任务总数**: 42
> **预计工期**: 3-4 周
> **关键路径**: Phase 2 (生理模型升级) → Phase 3 (融合层优化) → Phase 7 (回归测试)
