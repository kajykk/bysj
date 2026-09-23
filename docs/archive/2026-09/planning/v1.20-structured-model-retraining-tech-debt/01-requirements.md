# 项目需求文档 (PRD): v1.20 结构化模型重训与迁移技术债清理

## 1. 项目概述

### 1.1 背景
v1.19 已通过用户验收并达到上线 GO 决策。但系统中存在以下非阻塞但影响长期质量的技术债：

1. **结构化模型依赖 heuristic fallback**：自 v1.18 结构化模型损坏后，系统通过 `_structured_heuristic_fallback` 保证功能不崩溃，但启发式规则的预测质量远低于真实机器学习模型。
2. **Alembic 双 head 分支**：`alembic upgrade head` 存在歧义，必须显式指定 revision，对后续生产迁移构成长期风险。
3. **前端 circular chunk warning**：非阻塞但对构建质量有影响。

v1.19 的 `STRUCTURED_MODEL_RETRAIN_PLAN.md` 已确认重训条件（训练脚本存在、数据完整、依赖可用），推荐作为 v1.20 专项执行。

### 1.2 目标
将结构化模型从 heuristic fallback 恢复为真实机器学习模型优先，同时清理 Alembic 双 head 迁移技术债，提升系统长期可维护性和预测质量。

### 1.3 目标用户
- **系统开发者**：需要清晰的迁移路径和可回滚的模型部署方案
- **系统运维者**：需要稳定的数据库迁移策略和无歧义的升级命令
- **终端用户（间接）**：受益于更准确的抑郁风险预测结果

## 2. 详细功能设计 (Detailed Design)

### 2.1 模块 A: 结构化模型重训 (Structured Model Retraining)

#### 2.1.1 训练脚本修复与标准化
**目标**: 确保 `backend/train_baseline.py` 可稳定重复执行。

| 元素名称 | 类型 | 验证规则 | 默认值 | 交互逻辑 | 异常处理 |
|---|---|---|---|---|---|
| 随机种子 | Config | 固定整数值 | 42 | 全局设置确保可复现 | 配置缺失时报错 |
| 数据路径 | Config | 有效文件路径 | `data/` 目录下 | 脚本启动时检查路径存在 | FileNotFoundError 时终止并提示 |
| 输出路径 | Config | 可写目录 | `models/artifacts/` | 自动创建不存在的目录 | 权限不足时终止并提示 |
| Train/Val/Test Split | Config | 比例和为1.0 | 0.7/0.15/0.15 | 分层采样保持标签分布 | 样本不足时降级为简单随机 |
| 标签字段 | Config | 列存在于数据中 | - | 训练前校验 | 列缺失时终止并列出可用列 |
| 训练脚本 | Script | `backend/train_baseline.py` | - | Docker/Linux 环境执行 | 环境不兼容时标记为阻塞 |

**⚠️ 注意**: `train_baseline.py` 当前训练的是 PhysiologicalMLP（生理模型），v1.20 需确定是否修改它来训练结构化 LogisticRegression，或使用 v1.18 之前的训练方式重新生成 `best_model.pkl`。该决策将在 Phase 2 训练脚本审计中确定。

**逻辑流程**:
1. 加载原始数据集
2. 检查数据 schema（列名、类型、缺失值）
3. 按固定随机种子进行 train/val/test split
4. 在训练集上拟合 scaler，应用于全部数据
5. 训练模型并记录超参数
6. 在测试集上评估并输出 metrics
7. 保存所有 artifact（model, scaler, feature_names, metrics, manifest）

#### 2.1.2 模型 Artifact 版本化
**目标**: 所有产出物带版本标签，支持追溯和回滚。

| 元素名称 | 类型 | 验证规则 | 默认值 |
|---|---|---|---|
| 模型文件 | File | `.pkl` 格式 | `structured_model_v1.20.pkl` |
| Scaler 文件 | File | `.pkl` 格式 | `structured_scaler_v1.20.pkl` |
| Feature Names | File | `.json` 格式 | `structured_feature_names_v1.20.json` |
| Metrics | File | `.json` 格式 | `structured_metrics_v1.20.json` |
| Manifest | File | `.json` 格式 | `structured_manifest_v1.20.json` |

**Manifest 结构**:
```json
{
  "model_name": "structured_depression_model",
  "version": "v1.20",
  "created_at": "2026-05-01",
  "features": ["phq9_score", "gad7_score", "sleep_quality", ...],
  "metrics": {"accuracy": 0.xx, "f1": 0.xx, "roc_auc": 0.xx},
  "fallback": "heuristic"
}
```

#### 2.1.3 模型加载与 Fallback 集成
**目标**: 后端优先加载真实模型，失败时自动切换 fallback。

| 元素名称 | 类型 | 验证规则 | 默认值 | 交互逻辑 | 异常处理 |
|---|---|---|---|---|---|
| 模型加载路径 | Config | 文件存在检查 | `models/artifacts/` | 服务启动时加载 | 文件缺失→fallback + WARNING log |
| 模型模式开关 | Config/Env | `primary` / `fallback` | `primary` | 可通过环境变量切换 | 无效值时默认 fallback |
| 预测输出字段 | Response | `risk_score`, `risk_level`, `severity`, `confidence`, `model_used`, `fallback_used` | - | 每次预测返回 | 模型异常→fallback + ERROR log |

**逻辑流程**:
```
真实模型可用 → 使用真实模型预测
真实模型缺失/损坏 → 使用 heuristic fallback + WARNING log + 正常响应
```

**绝对禁止行为**:
- 模型损坏 → API 500
- 模型缺失 → API 422

### 2.2 模块 B: 结构化模型风险校准 (Risk Calibration)

#### 2.2.1 校准样本测试
**目标**: 确保模型输出风险等级符合业务预期。

| 样本描述 | 预期 risk_level | 验证方法 |
|---|---|---|
| 低压力、睡眠好、社交支持好 | none / mild | 模型预测匹配预期 |
| 中等压力、轻微焦虑、睡眠一般 | moderate | 模型预测匹配预期 |
| 高压力、睡眠差、焦虑明显 | high | 模型预测匹配预期 |
| 极高压力、惊恐发作、治疗寻求 | high / critical | 模型预测匹配预期 |

#### 2.2.2 阈值调整策略
**目标**: 必要时调整结构化模型专用阈值，确保风险等级分布合理。

| 阈值参数 | 类型 | 调整策略 |
|---|---|---|
| risk_level 分界阈值 | Float[] | 基于校准样本分布调整 |
| confidence 计算方式 | Algorithm | 基于模型概率输出 |
| severity 映射规则 | Mapping | 与 risk_level 对齐 |

### 2.3 模块 C: Alembic 双 Head 合并 (Migration Tech Debt)

#### 2.3.1 迁移合并操作
**目标**: 合并双 head 为单 head，消除 `alembic upgrade head` 歧义。

| 元素名称 | 类型 | 验证规则 | 交互逻辑 |
|---|---|---|---|
| alembic heads 检查 | Command | 输出当前所有 head | `alembic heads` 查看 |
| merge revision | Migration | 自动生成合并脚本 | `alembic merge heads` 创建 |
| upgrade 验证 | Command | 无歧义执行 | `alembic upgrade head` 成功 |
| downgrade 验证 | Command | 可回退或记录不可逆 | `alembic downgrade -1` 验证 |

**逻辑流程**:
1. 执行 `alembic heads` 查看当前双 head
2. 确认两个 head 来源和内容无冲突
3. 创建 merge revision：`alembic merge <head1> <head2> -m "merge dual heads"`
4. 执行 `alembic upgrade head` 验证无歧义
5. 验证核心表结构（review, crisis_events 等）完整
6. 验证 downgrade 策略或记录不可逆说明

### 2.4 模块 D: 模型回滚方案 (Rollback Plan)

#### 2.4.1 配置驱动切换
**目标**: 上线后模型异常时可一键切回 fallback。

| 配置项 | 值 | 效果 |
|---|---|---|
| `STRUCTURED_MODEL_MODE=primary` | 默认 | 优先使用真实模型，失败时 fallback |
| `STRUCTURED_MODEL_MODE=fallback` | 回滚 | 强制使用 heuristic fallback |
| `ENABLE_STRUCTURED_MODEL=false` | 备用 | 等效于 fallback 模式 |

### 2.5 模块 E: 前端 Circular Chunk Warning 清理 (P1)

#### 2.5.1 优化项
**目标**: 减少或记录 circular chunk warning。

| 优化项 | 策略 | 优先级 |
|---|---|---|
| 路由懒加载 | 确保动态 import 无循环引用 | P1 |
| admin/counselor 页面拆包 | 分析依赖图并拆包 | P1 |
| 图表组件异步加载 | 延迟加载重型图表库 | P2 |
| PWA chunk 检查 | 检查 service worker 缓存策略 | P2 |

## 3. 非功能需求 (Non-functional Requirements)

- **可复现性**: 训练必须固定随机种子，完整记录超参数
- **可回滚性**: 模型部署支持一键切换 fallback，无需重启服务
- **科学严谨性**: 遵循数据泄漏防护规范，train/val/test 严格隔离
- **向后兼容**: v1.19 的上线能力全部回归通过
- **日志完整**: 所有模型加载失败和回退事件必须记录日志

## 4. 假设与约束

- **假设**: `backend/train_baseline.py` 可在 Docker/Linux 环境正常执行
- **假设**: 训练数据集格式和标签字段与现有脚本兼容
- **假设**: sklearn 依赖在目标环境中可用且版本兼容
- **约束**: 不升级 BERT 文本模型（后置到 v1.21+）
- **约束**: 不扩展生理模型特征（后置到 v1.21+）
- **约束**: 不引入新数据库表或修改现有表结构（仅合并迁移 head）
- **约束**: Windows 本地 pytest/Vitest 环境限制不阻塞迭代目标
