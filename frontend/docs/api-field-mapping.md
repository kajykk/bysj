# 前后端字段对照表（接口契约统一）

> 目标：消除隐式转换，统一字段命名、分页结构、枚举值。

## 1. 通用响应结构

| 层级 | 字段 | 类型 | 说明 |
|---|---|---|---|
| 顶层 | code | number | 业务状态码 |
| 顶层 | message | string | 提示信息 |
| 顶层 | data | object | 业务数据 |

## 2. 分页结构（统一）

统一为：`items / total / page / page_size`

| 统一字段 | 类型 | 兼容旧字段（前端适配层） |
|---|---|---|
| items | array | list |
| total | number | count |
| page | number | current |
| page_size | number | pageSize / size |

## 3. 预警 Warning

| 前端字段 | 后端字段 | 类型 | 枚举/约束 |
|---|---|---|---|
| id | id | number | 必填 |
| warning_type | warning_type | string | 可选 |
| risk_level | risk_level | string | `low` / `medium` / `high` |
| title | title | string | 可选 |
| content | content | string | 可选 |
| is_read | is_read | boolean | `true` / `false` |
| status | status | string | `pending` / `handled` / `ignored` |
| created_at | created_at | string | ISO 时间 |
| handled_at | handled_at | string | ISO 时间，可选 |
| handled_by | handled_by | string | 可选 |
| handled_note | handled_note | string | 可选 |

## 4. 评估记录 Assessment

| 前端字段 | 后端字段 | 类型 | 枚举/约束 |
|---|---|---|---|
| id | id | number | 必填 |
| assessment_type | assessment_type | string | `structured` / `text` / `physiological` |
| score | score | number | 可选 |
| risk_level | risk_level | string | `low` / `medium` / `high` |
| summary | summary | string | 可选 |
| created_at | created_at | string | ISO 时间 |

## 5. 用户管理 User

| 前端字段 | 后端字段 | 类型 | 枚举/约束 |
|---|---|---|---|
| id | id | number | 必填 |
| username | username | string | 必填 |
| nickname | nickname | string | 可选 |
| email | email | string | 可选 |
| role | role | string | `user` / `counselor` / `admin` |
| status | status | string | `active` / `inactive` / `disabled` |

## 6. 操作日志 OperationLog

| 前端字段 | 后端字段 | 类型 | 枚举/约束 |
|---|---|---|---|
| id | id | number | 必填 |
| action_type | action_type | string | `login` / `logout` / `warning_handle` / `warning_ignore` / `user_update` / `role_update` |
| target_type | target_type | string | 可选 |
| target_id | target_id | number | 可选 |
| created_at | created_at | string | ISO 时间 |
| operator_id | operator_id | number | 可选 |
| detail | detail | object/string | 可选 |

## 7. 模型预测 Model Prediction (v1.16+)

### 7.1 融合预测 FusionPredictResult

| 前端字段 | 后端字段 | 类型 | 说明 |
|---|---|---|---|
| risk_score | risk_score | number | 风险分数 (0-100) |
| risk_level | risk_level | number | 风险等级 (0-4) |
| severity | severity | string | `none` / `mild` / `moderate` / `high` / `critical` |
| model_used | model_used | string[] | 使用的模型列表 |
| fusion_detail | fusion_detail | object | 融合详情（含 modality_scores, weights, gate_weights） |
| intervention_level | intervention_level | string | 干预等级 |
| intervention_actions | intervention_actions | string[] | 干预建议列表 |
| review_required | review_required | boolean | **v1.16 新增** 是否需要人工复核 |
| review_triggers | review_triggers | string[] | **v1.16 新增** 复核触发原因列表 |
| crisis_override | crisis_override | boolean | **v1.16 新增** 是否触发危机覆盖 |
| model_version | model_version | string | **v1.16 新增** 模型版本标识 |
| risk_factors | risk_factors | string[] | **v1.16 新增** 风险因素标签 |
| protective_factors | protective_factors | string[] | **v1.16 新增** 保护因素标签 |

### 7.2 文本预测 TextPredictResult (v1.16+)

| 前端字段 | 后端字段 | 类型 | 说明 |
|---|---|---|---|
| prediction | prediction | number | 预测标签 (0/1) |
| probability | probability | number | 预测概率 |
| sentiment_label | sentiment_label | string | `negative` / `positive` |
| sentiment_score | sentiment_score | number | 情感分数 |
| model_used | model_used | string | 模型名称 |
| distress_score | distress_score | number | **v1.16 新增** 痛苦程度分数 |
| crisis_score | crisis_score | number | **v1.16 新增** 危机程度分数 |
| crisis_detected | crisis_detected | boolean | **v1.16 新增** 是否检测到危机表达 |
| crisis_keywords | crisis_keywords | string[] | **v1.16 新增** 检测到的危机关键词 |
| risk_factors | risk_factors | string[] | **v1.16 新增** 风险因素 |
| protective_factors | protective_factors | string[] | **v1.16 新增** 保护因素 |

### 7.3 生理预测 PhysiologicalPredictResult (v1.16+)

| 前端字段 | 后端字段 | 类型 | 说明 |
|---|---|---|---|
| risk_score | risk_score | number | 风险分数 |
| risk_level | risk_level | number | 风险等级 |
| severity | severity | string | 严重程度 |
| model_used | model_used | string | 模型名称 |
| confidence | confidence | number | **v1.16 新增** 预测置信度 |
| data_quality | data_quality | object | **v1.16 新增** 数据质量信息 |
| calibrated | calibrated | boolean | **v1.16 新增** 是否已校准 |

## 8. 风险报告 RiskReport (v1.16+)

| 前端字段 | 后端字段 | 类型 | 说明 |
|---|---|---|---|
| risk_level | risk_level | number | 风险等级 |
| risk_score | risk_score | number | 风险分数 |
| severity | severity | string | 严重程度 |
| trend | trend | string | `up` / `down` / `stable` |
| main_factors | main_factors | array | 主要风险因子 |
| advice | advice | string[] | 建议列表 |
| assessed_at | assessed_at | string | 评估时间 |
| review_required | review_required | boolean | **v1.16 新增** 是否需要人工复核 |
| review_triggers | review_triggers | string[] | **v1.16 新增** 复核原因 |
| crisis_override | crisis_override | boolean | **v1.16 新增** 危机覆盖标记 |
| risk_factors | risk_factors | string[] | **v1.16 新增** 风险因素 |
| protective_factors | protective_factors | string[] | **v1.16 新增** 保护因素 |

## 9. 错误返回（推荐）

| 字段 | 类型 | 说明 |
|---|---|---|
| detail | string | 统一透传人类可读错误 |
| message | string | 兼容字段（detail 为空时兜底） |
| errors | object | 可选，422 行内错误明细 |
