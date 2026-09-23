# 项目需求文档 (PRD) - v1.4 深度学习化改造

> **迭代名称**: v1.4-deep-learning-transformation
> **版本**: 2.0 (Round 2 Draft)
> **日期**: 2026-04-28
> **依据文档**: `docs/superpowers/specs/2026-04-28-deep-learning-transformation-design-v2.md`

---

## 1. 项目概述

### 1.1 背景

抑郁症风险评估系统当前采用多模态融合架构，包含结构化数据（CatBoost，F1=0.8725）、文本数据（TF-IDF+LR，F1=0.9681）和生理数据（NumPy MLP，F1=0.7243）三个模态。生理数据模态性能明显低于其他两个模态，成为系统整体性能的瓶颈。此外，融合层当前仅基于4个测试场景，缺乏充分的场景验证。

### 1.2 目标

通过深度学习化改造，提升生理数据模态的预测性能（目标 F1 ≥ 0.78），优化融合层决策机制，建立模型治理与回退体系，确保系统在升级过程中的稳定性与可回退性。

### 1.3 目标用户

- **数据科学家**: 需要标准化的模型评估、对照实验和模型注册流程
- **后端工程师**: 需要统一的模型接口、回退机制和灰度发布支持
- **运维人员**: 需要模型监控、漂移检测和告警机制

---

## 2. 详细功能设计

### 2.1 模块 A: 模型治理与注册 (Model Governance)

#### 2.1.1 模型注册表
**路径**: `backend/app/core/model_registry_v2.py`

**功能需求**:
| 元素名称 | 类型 | 验证规则 | 默认值 | 交互逻辑 | 异常处理 | 权限 |
|---|---|---|---|---|---|---|
| model_id | String | Required, lower_snake_case | - | 唯一标识 | 重复ID报错 | 系统 |
| name | String | Required, Max 100 | - | 模型名称 | - | 系统 |
| version | String | Required, semver | v1.0.0 | 版本号 | 格式错误报错 | 系统 |
| type | Enum | Required | - | xgboost/lightgbm/mlp/catboost/logistic_regression | 非法值报错 | 系统 |
| status | Enum | Required | candidate | candidate/staging/production/retired | 非法值报错 | 系统 |
| fallback_id | String | Required | - | 回退模型ID | 回退模型不存在告警 | 系统 |
| performance_threshold | Dict | - | {} | F1下降>5%触发告警 | - | 系统 |
| metrics | Dict | - | {} | F1/Precision/Recall/ROC-AUC/AUPRC | - | 系统 |
| artifact_path | String | Required | - | 模型文件路径 | 文件不存在告警 | 系统 |
| training_config | Dict | - | {} | 随机种子、超参数、数据划分方式 | - | 系统 |
| created_at | datetime | Required | - | 创建时间 | - | 系统 |
| updated_at | datetime | Required | - | 更新时间 | - | 系统 |

**状态流转**:
```
candidate → staging → production → retired
   ↑___________↓
   (可回滚)
```

**状态晋升条件**:
| 流转 | 条件 | 审批人 |
|---|---|---|
| candidate → staging | 模型训练完成，评估报告通过 | 数据科学家 |
| staging → production | 5-Fold CV F1 ≥ 0.78，McNemar p < 0.05 | 技术负责人 |
| production → retired | 新模型上线，旧模型下线 | 运维人员 |
| production → staging (回滚) | 生产环境性能下降>5% | 自动触发/运维人员 |

#### 2.1.2 模型版本固化
**路径**: `scripts/baseline_freeze.py`

**功能需求**:
- 记录当前所有生产级模型的版本与指标
- 生成基线报告（JSON格式）
- 验证所有模型文件存在且可加载

---

### 2.2 模块 B: 生理数据模型升级 (Physiological Model Upgrade)

#### 2.2.1 数据预处理管道
**路径**: `backend/app/ml/data_loader.py`, `backend/app/ml/data_cleaner.py`

**功能需求**:
| 步骤 | 输入 | 输出 | 约束 |
|---|---|---|---|
| 数据加载 | Depresjon + Kaggle CSV | 合并DataFrame | 列名统一，数据类型一致 |
| 数据清洗 | 原始DataFrame | 清洗后DataFrame | 异常值基于训练集1st/99th百分位裁剪 |
| 特征工程 | 清洗后DataFrame | 13维特征矩阵 | 7原始+6衍生，计算逻辑可复用 |
| 数据划分 | 特征矩阵 | train/val/test | 70/15/15分层划分，random_state=42 |
| 标准化 | 训练集特征 | 标准化特征 | 仅在训练集fit，val/test用相同参数transform |
| SMOTE | 训练集 | 重采样训练集 | 仅在训练集应用，比例≤0.8:1 |

#### 2.2.2 XGBoost 模型训练
**路径**: `scripts/train_physiological_xgboost.py`

**功能需求**:
| 参数 | 默认值 | 范围 | 说明 |
|---|---|---|---|
| n_estimators | 200 | 100-500 | 树的数量 |
| max_depth | 5 | 3-10 | 树的最大深度 |
| learning_rate | 0.05 | 0.01-0.3 | 学习率 |
| subsample | 0.8 | 0.5-1.0 | 样本采样比例 |
| colsample_bytree | 0.8 | 0.5-1.0 | 特征采样比例 |
| scale_pos_weight | auto | 1.0-3.0 | 类别不平衡权重，auto=多数类/少数类 |
| random_state | 42 | - | 随机种子 |

**参数量估算**:
- 13维输入 → 32隐藏层: 13×32 + 32 = 448
- 32 → 16: 32×16 + 16 = 528
- 16 → 1: 16×1 + 1 = 17
- **总参数量: 993 < 5,000** ✅

**评估协议**:
- 5-Fold 交叉验证（每折独立预处理）
- Bootstrap 95% CI
- 特征重要性输出
- 与当前MLP的McNemar检验

#### 2.2.3 LightGBM 对照实验
**路径**: `scripts/train_physiological_lightgbm.py`

**功能需求**:
- 与XGBoost相同的评估协议
- 统计显著性检验（McNemar）
- 延迟对比

#### 2.2.4 PyTorch 轻量 MLP
**路径**: `backend/app/ml/pytorch_mlp.py`

**架构要求**:
```
Input(13) → Linear(32) → BatchNorm → ReLU → Dropout(0.3) →
Linear(16) → BatchNorm → ReLU → Dropout(0.3) →
Linear(1) → Sigmoid
```

**约束**:
- 参数量 < 5,000
- 必须包含 Dropout + BatchNorm + L2
- 早停 patience=10
- 学习率衰减（ReduceLROnPlateau）
- 梯度裁剪 max_norm=1.0

---

### 2.3 模块 C: 融合层优化 (Fusion Layer Optimization)

#### 2.3.1 规则权重优化
**路径**: `scripts/optimize_fusion_weights.py`

**功能需求**:
- 在83个测试场景上搜索最优权重
- 基础权重范围: structured [0.3-0.6], text [0.2-0.4], physiological [0.1-0.3]
- **目标: 最大化融合 F1-Score**（非 Accuracy，因数据不平衡）
- 搜索策略: 网格搜索 + 交叉验证
- 输出: 最优权重组合 + 置信区间

#### 2.3.2 置信度加权机制
**路径**: `backend/app/core/model_engine.py`

**功能需求**:
| 元素名称 | 类型 | 说明 |
|---|---|---|
| base_weights | Dict | 基础权重 (structured/text/physiological) |
| confidence | Dict | 各模态置信度分数 [0, 1] |
| dynamic_weights | Dict | 动态权重 = 基础权重 × 置信度，再归一化 |

**置信度计算方法**:
| 模态 | 置信度计算方式 | 说明 |
|---|---|---|
| structured | `confidence = max(proba, 1-proba)` | 预测概率的确定性 |
| text | `confidence = max(proba, 1-proba)` | 预测概率的确定性 |
| physiological | `confidence = max(proba, 1-proba)` | 预测概率的确定性 |

**动态权重公式**:
```
dynamic_weight_i = base_weight_i × confidence_i
normalized_weight_i = dynamic_weight_i / Σ(dynamic_weight_j)
```

#### 2.3.3 模态缺失处理
**路径**: `backend/app/core/model_engine.py`

**功能需求**:
| 场景 | 处理策略 |
|---|---|
| 单模态输入 | 该模态权重=1.0，直接输出 |
| 双模态输入 | 两模态权重重新归一化 |
| 全部缺失 | 返回默认中等风险 (score=50) |

---

### 2.4 模块 D: 文本模型双轨制 (Text Model Dual-Track)

#### 2.4.1 BERT 候选模型
**路径**: `scripts/train_text_bert.py`

**功能需求**:
| 参数 | 值 | 说明 |
|---|---|---|
| model_name | bert-base-chinese | 预训练模型 |
| epochs | 3 | 训练轮数 |
| batch_size | 16 | 批次大小 |
| learning_rate | 2e-5 | 学习率 |
| max_length | 256 | 最大序列长度 |

#### 2.4.2 切换决策
**路径**: `backend/app/core/model_engine.py`

**切换门槛**:
- F1 > 0.97（当前基线 0.9681 + 0.005）
- 延迟 < 10ms
- 模型大小 < 50MB

---

### 2.5 模块 E: 结构化模型监控 (Structured Model Monitoring)

#### 2.5.1 漂移检测
**路径**: `backend/app/ml/drift_detector.py`

**功能需求**:
| 检测类型 | 方法 | 阈值 | 告警条件 |
|---|---|---|---|
| 特征漂移 | KS检验 | p < 0.05 | 特征分布显著变化 |
| 预测漂移 | PSI | PSI > 0.2 | 预测分布显著变化 |
| 性能下降 | 定期评估 | F1下降>5% | 模型性能退化 |

**触发机制**:
| 触发方式 | 频率 | 说明 |
|---|---|---|
| 定时任务 | 每日 02:00 UTC | 批量检测前一日预测数据 |
| 实时检测 | 每 100 次预测 | 滑动窗口检测预测分布 |
| 手动触发 | 按需 | 运维人员手动执行 |

**告警方式**:
| 级别 | 条件 | 方式 | 接收人 |
|---|---|---|---|
| WARNING | 单特征漂移 | 日志 + 邮件 | 数据科学家 |
| CRITICAL | 多特征漂移或性能下降>5% | 日志 + 邮件 + SMS | 技术负责人 |

**告警后处理流程**:
1. 记录漂移详情（特征名、漂移程度、时间窗口）
2. 自动触发模型回退评估（检查是否需要回滚）
3. 生成漂移报告（JSON格式）
4. 人工确认后决定是否回滚模型

---

### 2.6 模块 F: 回退与灰度 (Fallback & Canary)

#### 2.6.1 回退机制
**路径**: `backend/app/core/model_engine.py`

**回退策略（多级回退）**:
| 级别 | 模型 | 异常场景 | 回退目标 | 延迟阈值 |
|---|---|---|---|---|
| 1 | 生理 XGBoost | 文件缺失/模型损坏 | NumPy MLP | - |
| 2 | 生理 NumPy MLP | 模型损坏/预测异常 | 启发式规则 | - |
| 3 | 文本 BERT | 加载失败/预测异常 | TF-IDF+LR | - |
| 4 | 文本 TF-IDF+LR | 加载失败 | 启发式规则 (关键词匹配) | - |
| 5 | 融合层 | 计算异常 | 规则加权融合 | - |
| 6 | 所有模型 | 推理延迟 > 200ms | 轻量级回退模型 | 200ms |

**超时回退机制**:
| 模型 | 延迟阈值 | 超时处理 |
|---|---|---|
| 生理 XGBoost | 10ms | 取消当前推理，回退到 NumPy MLP |
| 文本 BERT | 200ms | 取消当前推理，回退到 TF-IDF+LR |
| 融合层 | 50ms | 取消当前融合，使用规则加权融合 |

**回退日志**:
- 原因、时间、输入数据摘要、回退级别
- 日志级别: WARNING (级别1-3), ERROR (级别4-6)
- 所有回退事件必须记录到 `logs/fallback_YYYY-MM-DD.log`

#### 2.6.2 灰度发布
**路径**: `backend/app/core/model_engine.py`

**功能需求**:
- 基于用户ID的流量分配（hash(user_id) % 100 < ratio）
- 新旧模型并行输出
- 结果对比日志

**灰度配置**:
| 参数 | 默认值 | 说明 |
|---|---|---|
| user_id_format | UUID / int | 用户唯一标识 |
| hash_algorithm | sha256(user_id) % 100 | 确定性哈希，保证同一用户始终命中同一模型 |
| canary_ratio | 10 | 流量分配比例 (0-100) |
| session_sticky | True | 会话粘性，同一用户会话内始终使用同一模型 |

**灰度评估标准**:
| 指标 | 阈值 | 评估周期 |
|---|---|---|
| 新模型 F1 | ≥ 旧模型 F1 | 每日 |
| 新模型延迟 | < 旧模型延迟 × 1.2 | 每日 |
| 回退率 | < 1% | 每日 |
| 错误率 | < 0.1% | 每日 |

**全量发布/回滚决策**:
| 条件 | 动作 |
|---|---|
| 连续 3 天所有指标通过 | 自动全量发布 (canary_ratio = 100) |
| 任意指标连续 2 天未通过 | 自动回滚 (canary_ratio = 0) |
| 严重错误 (错误率 > 1%) | 立即回滚 |

**灰度日志**:
- 用户ID、模型版本、预测结果、延迟、时间戳
- 存储位置: `logs/canary_YYYY-MM-DD.log`

---

## 3. 非功能需求

### 3.1 性能
- 生理模型推理延迟 < 10ms（XGBoost）/ < 5ms（NumPy MLP）
- 融合层推理延迟 < 50ms
- 文本模型推理延迟 < 200ms（BERT）/ < 10ms（TF-IDF+LR）
- 回退模型推理延迟 < 5ms（启发式规则）

### 3.2 安全
- 所有模型文件权限设置为只读
- 回退机制必须自动触发，无需人工干预
- 灰度发布不影响现有用户

### 3.3 可维护性
- 所有预处理代码必须注释数据来源、处理逻辑、参数设置
- 模型版本必须遵循 semver
- 评估报告必须包含置信区间和统计检验结果

### 3.4 数据质量
- 严禁数据泄漏：划分 → 拟合 → 转换
- 严禁在验证集/测试集上进行任何预处理拟合
- SMOTE 仅在训练集应用，比例 ≤ 0.8:1

---

## 4. 假设与约束

### 4.1 假设
- Depresjon 和 Kaggle 数据集格式保持不变
- PyTorch / XGBoost / LightGBM 依赖可正常安装
- 当前结构化模型（CatBoost）性能保持稳定

### 4.2 约束
- 生理数据为横截面数据，严禁使用时序模型（1D-CNN/LSTM/Transformer）
- 模型参数量限制：生理模型 < 5,000
- 融合层在场景充足前保持规则驱动，不引入可学习网络
- 所有新模型必须具备回退机制才能上线
