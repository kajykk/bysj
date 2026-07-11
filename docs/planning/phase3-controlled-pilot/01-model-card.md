# DWS 模型卡（Model Card）

> 本模型卡基于 Mitchell et al. (2019) "Model Cards for Model Reporting" 框架，记录 DWS 心理健康风险评估系统所用模型的用途、性能、限制和变更历史。模型卡应随模型版本更新而同步更新。

---

## 一、模型概述

| 字段 | 值 |
|------|-----|
| 模型名称 | DWS 多模态心理健康风险评估模型 |
| 版本 | v3.1.0 |
| 发布日期 | 2026-07-11 |
| 模型类型 | 多模态融合（结构化 + 文本 + 生理指标） |
| 架构 | LogisticRegression / RandomForestClassifier / CalibratedClassifierCV |
| 许可证 | 仅限教育和研究用途 |

---

## 二、预期用途

### 2.1 预期使用场景

- **用途**：高校学生心理健康风险筛查与预警辅助
- **用户**：高校心理咨询中心、辅导员、学生本人
- **使用方式**：作为心理风险评估的辅助参考，不替代专业诊断
- **适用人群**：18 岁以上高校在读学生

### 2.2 禁用场景

- ❌ 临床诊断或医疗决策
- ❌ 自动触发惩罚性措施（如处分、退学）
- ❌ 强制干预措施（如强制就医）
- ❌ 非"高校学生"人群使用
- ❌ 未经人工复核的高风险结果直接对外披露
- ❌ 替代专业心理咨询师或精神科医生的判断

### 2.3 使用限制

- 模型输出仅为风险概率和风险等级，**不是诊断结论**
- 高风险结果必须进入人工复核流程（ReviewService）
- 危机事件必须立即升级到心理中心（CrisisEventService）
- 模型预测服务可通过暂停开关（kill switch）随时停止

---

## 三、数据描述

### 3.1 训练数据

详见 [02-data-description.md](02-data-description.md)。

| 数据源 | 样本量 | 特征数 | 标签类型 |
|--------|--------|--------|---------|
| 结构化问卷 | - | 多维度 | 4 级风险（0-3） |
| 文本分析 | - | 语言特征 | 4 级风险（0-3） |
| 生理指标 | - | HRV/睡眠等 | 4 级风险（0-3） |

### 3.2 标签定义

风险等级基于标准化心理量表得分映射：

| 风险等级 | 分数范围 | 含义 | 阈值（结构化） |
|---------|---------|------|---------------|
| 0 - 无风险 | 0-24 | 无明显风险 | < 25 |
| 1 - 轻度 | 25-44 | 需关注 | 25-44 |
| 2 - 中度 | 45-64 | 需干预 | 45-64 |
| 3 - 重度 | 65-100 | 高风险 | ≥ 65 |

### 3.3 数据局限

- 训练数据来源于特定高校样本，可能存在选择偏差
- 生理指标数据依赖可穿戴设备，存在设备差异
- 文本分析基于中文语境，其他语言不适用
- 样本中高风险标签占比较低，可能影响 recall

---

## 四、性能指标

### 4.1 结构化模型

| 指标 | 值 | 置信区间 (95%) | 说明 |
|------|-----|---------------|------|
| Sensitivity | 待真实试点 | - | 高风险识别率 |
| Specificity | 待真实试点 | - | 低风险排除率 |
| PPV | 待真实试点 | - | 阳性预测值 |
| NPV | 待真实试点 | - | 阴性预测值 |
| AUROC | 待真实试点 | - | ROC 曲线下面积 |
| Brier Score | 待真实试点 | - | 校准度 |

> 注：试点前指标通过 `POST /api/v1/validation/clinical` 计算，试点后每两周更新。

### 4.2 风险阈值

各模态的风险等级阈值（[risk_thresholds.py](../../backend/app/core/risk_thresholds.py)）：

| 模态 | 轻度 | 中度 | 重度 | 危机 |
|------|------|------|------|------|
| 结构化 | 25 | 45 | 65 | 85 |
| 文本 | 20 | 40 | 60 | 80 |
| 生理 | 35 | 55 | 75 | 90 |
| 融合 | 22 | 42 | 62 | 82 |

### 4.3 公平性指标

按性别、年级等群体检查偏差（`min_group_size=30` 保护）：

| 群体 | 指标 | 值 | 差异 | 状态 |
|------|------|-----|------|------|
| 性别 | Sensitivity gap | 待试点 | ≤ 0.15 | ⏳ |
| 年级 | Sensitivity gap | 待试点 | ≤ 0.15 | ⏳ |

---

## 五、模型架构与训练

### 5.1 模态子模型

| 模型 ID | 模态 | 算法 | 文件位置 |
|---------|------|------|---------|
| structured_v1.21 | 结构化 | LogisticRegression | `models/artifacts/structured_v1.21/` |
| physiological_optimized | 生理 | CalibratedClassifierCV | `models/artifacts/physiological_optimized/` |
| text_lr | 文本 | LogisticRegression (Multinomial) | - |
| fusion_engine | 融合 | 加权融合 | `app/ml/fusion_engine.py` |

### 5.2 融合策略

- **融合引擎**：[fusion_engine.py](../../backend/app/ml/fusion_engine.py)
- **策略**：加权融合，各模态贡献度可配置
- **危机覆盖**：检测到危机关键词时自动提升风险等级

### 5.3 校准

- **方法**：CalibratedClassifierCV（生理模型）
- **评估**：Brier Score + 校准曲线（`compute_calibration_curve`）
- **目标**：Brier Score ≤ 0.20

---

## 六、运维与监控

### 6.1 模型监控

| 监控项 | 方式 | 频率 | 告警阈值 |
|--------|------|------|---------|
| 预测延迟 | `track_model_inference` | 实时 | P95 > 2s |
| 错误率 | 日志 + 指标 | 实时 | > 5% |
| 数据漂移 | `drift_detector.py` | 每日 | KL 散度 > 0.3 |
| 指标退化 | `model_validation.py` | 每两周 | Sensitivity < 0.50 |

### 6.2 暂停开关

- **端点**：`POST /api/v1/model-kill-switch/activate|deactivate`
- **检查点**：所有 4 个预测端点（tabular/text/physiological/fusion）
- **响应**：暂停时返回 HTTP 503
- **审计**：所有操作记录到 `OperationLog`

### 6.3 版本回滚

- 模型文件存储在 `models/artifacts/` 目录
- 版本切换通过 `ModelRegistry` 表管理
- 回滚操作记录到 `OperationLog`（`action_type="model.version.rollback"`）

---

## 七、变更历史

| 版本 | 日期 | 变更内容 | 变更原因 | 审批人 |
|------|------|---------|---------|--------|
| v3.1.0 | 2026-07-11 | Phase 3 基础设施（模型验证 + 暂停开关） | Phase 3 试点准备 | - |
| v1.40 | - | 审计修复（43 项 P3/P4 + 61 项视觉） | Phase 1 完整性 | - |
| v1.20 | - | 结构化阈值重新校准 | 阈值优化 | - |

> 注：未来版本变更必须记录原因、审批人和回滚方案。

---

## 八、引用与参考

- Mitchell, M., et al. (2019). "Model Cards for Model Reporting." *FAT* 2019.
- Phase 3 计划：[dws产品化优化_9da5f8c0.plan.md](../../md/dws产品化优化_9da5f8c0.plan.md)
- 模型验证 API：[model_validation.py](../../backend/app/ml/model_validation.py)
- 暂停开关：[kill_switch.py](../../backend/app/core/kill_switch.py)

---

## 九、免责声明

本模型仅作为心理健康风险评估的**辅助参考工具**，不构成医疗诊断或治疗建议。模型输出应由具有资质的心理咨询师或精神科医生进行专业解读。对于危机事件，应立即联系专业心理危机干预机构或拨打心理援助热线。

开发者不对因使用本模型而产生的任何直接或间接损失承担责任。使用者应遵守当地法律法规和伦理规范。
