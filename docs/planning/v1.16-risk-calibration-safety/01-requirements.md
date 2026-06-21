# 项目需求文档 (PRD) — v1.16-risk-calibration-safety

## 1. 项目概述

### 1.1 背景

当前系统已具备结构化数据、文本、生理数据三种单模态预测能力，以及融合预测能力。v1.15 完成了上线就绪验证，但模型风险等级与业务预期之间仍存在偏差。心理健康场景对风险识别的准确性、危机响应的及时性有极高要求，漏判危机文本比误报更危险。

### 1.2 目标

提升各模型预测风险等级与业务预期的一致性，并补充心理健康场景下的危机识别和人工复核机制，为上线后的安全运营提供保障。

### 1.3 目标用户

- **学生用户**：接收风险预警和干预建议，需要清晰的风险解释。
- **咨询师**：查看学生风险报告，需要人工复核标记和模型贡献度说明。
- **系统管理员**：监控系统运行，处理高风险案例。

---

## 2. 详细功能设计

### 2.1 模块 A: 文本危机识别 (Crisis Detection)

#### 2.1.1 功能: 危机关键词强规则 (Crisis Override)

**背景**: 即使 ML 模型分数不高，文本中出现强危机表达也应触发 critical 等级。

**危机关键词库**:

| 类别 | 关键词示例 |
| :--- | :--- |
| 自杀表达 | 自杀、不想活、结束生命、想死、活着没意义 |
| 自伤表达 | 伤害自己、割腕、跳楼、遗书 |
| 极端绝望 | 没救了、撑不下去了、一切都完了 |

**规则逻辑**:

```text
如果文本命中危机表达:
  risk_level = critical
  intervention_level = emergency
  必须返回危机干预建议
  必须标记 review_required = true
  必须记录 crisis_override = true
```

**UI 元素清单**:

| 元素名称 | 类型 | 验证规则 | 交互逻辑 | 异常处理 |
| :--- | :--- | :--- | :--- | :--- |
| 危机预警弹窗 | Modal | - | 自动弹出，阻断式提示 | 用户必须确认后才可关闭 |
| 干预建议卡片 | Card | - | 展示紧急求助热线和资源 | - |
| 人工复核标记 | Badge | - | 咨询师端显示红色标记 | - |

#### 2.1.2 功能: 双维度文本评分

**当前问题**: 文本模型只输出一个 sentiment_score，无法区分"情绪宣泄"和"真实高风险"。

**新输出维度**:

```json
{
  "distress_score": 78,
  "crisis_score": 20,
  "risk_factors": ["兴趣下降", "睡眠问题", "持续低落"],
  "protective_factors": ["仍有求助意愿"]
}
```

**字段定义**:

| 字段名 | 类型 | 范围 | 说明 |
| :--- | :--- | :--- | :--- |
| distress_score | float | 0-100 | 情绪困扰程度 |
| crisis_score | float | 0-100 | 危机表达强度 |
| risk_factors | list[str] | - | 检测到的风险因素 |
| protective_factors | list[str] | - | 检测到的保护因素 |

---

### 2.2 模块 B: 结构化模型校准 (Structured Calibration)

#### 2.2.1 功能: 专用阈值校准

**当前问题**: 结构化模型使用默认阈值 (mild=20, moderate=40, high=60, critical=80)，与业务预期不符。

**建议专用阈值**:

| risk_score | 建议等级 |
| :--- | :--- |
| < 25 | none |
| 25 - 44.99 | mild |
| 45 - 64.99 | moderate |
| 65 - 84.99 | high |
| >= 85 | critical |

#### 2.2.2 功能: 特征重要性解释

**输出字段**:

```json
{
  "top_factors": [
    {"feature": "stress_level", "importance": 0.32},
    {"feature": "sleep_duration", "importance": 0.28},
    {"feature": "academic_pressure", "importance": 0.19}
  ],
  "explanation": "本次风险主要由睡眠不足、压力水平较高和学业压力较高导致。"
}
```

#### 2.2.3 功能: 缺失值策略优化

**输出字段**:

```json
{
  "data_quality": {
    "missing_fields": ["sleep_duration", "social_support"],
    "confidence_penalty": 0.15,
    "quality_level": "partial"
  }
}
```

**质量等级定义**:

| 等级 | 条件 |
| :--- | :--- |
| complete | 无缺失字段 |
| partial | 缺失 1-2 个字段 |
| poor | 缺失 3+ 个字段 |

---

### 2.3 模块 C: 生理模型增强 (Physiological Enhancement)

#### 2.3.1 功能: 输入范围校验

**校验规则**:

| 字段名 | 最小值 | 最大值 | 异常处理 |
| :--- | :--- | :--- | :--- |
| sleep_hours | 0 | 16 | 返回 422 |
| sleep_quality | 1 | 10 | 返回 422 |
| exercise_minutes | 0 | 300 | 返回 422 |
| heart_rate | 35 | 220 | 返回 422 |
| systolic_bp | 70 | 220 | 返回 422 |
| diastolic_bp | 40 | 140 | 返回 422 |
| steps | 0 | 50000 | 返回 422 |

#### 2.3.2 功能: 置信度计算

**输出字段**:

```json
{
  "confidence": 0.72,
  "data_quality": "complete",
  "calibrated": true
}
```

**置信度计算逻辑**:

- 基础置信度: 0.8
- 缺失字段: 每个 -0.1
- 异常值: -0.2
- 边界值: -0.05

---

### 2.4 模块 D: 融合模型优先级规则 (Fusion Priority Rules)

#### 2.4.1 功能: 融合优先级规则

**规则定义**:

| 优先级 | 规则 | 结果 |
| :--- | :--- | :--- |
| P0 | 文本命中危机表达 | 直接 critical |
| P1 | 两个模型为 high | 融合至少 high |
| P2 | 单个模型 high，其他 low | 标记不确定，需复核 |
| P3 | 低置信度模型 | 降低权重 |

#### 2.4.2 功能: 人工复核标记

**输出字段**:

```json
{
  "review_required": true,
  "review_reason": "text_high_risk_or_model_disagreement",
  "review_triggers": ["text_crisis_detected", "model_disagreement_45_points"]
}
```

**复核触发条件**:

| 条件 | review_reason |
| :--- | :--- |
| 文本 high/critical | text_high_risk |
| 任意两个模型差距超过 40 分 | model_disagreement |
| 模型低置信度但风险高 | low_confidence_high_risk |
| 文本命中危机关键词 | crisis_override |

#### 2.4.3 功能: 模型贡献度输出

**输出字段**:

```json
{
  "modality_scores": {
    "structured": {"score": 61, "weight": 0.3},
    "text": {"score": 82, "weight": 0.5},
    "physiological": {"score": 65, "weight": 0.2}
  },
  "dominant_modality": "text",
  "fusion_scheme": "full_three_modality"
}
```

---

### 2.5 模块 E: 预期风险样本测试 (Expected Risk Test Suite)

#### 2.5.1 功能: 固定测试样本集

**结构化模型样本**:

| 样本类型 | 输入特征 | 预期风险 |
| :--- | :--- | :--- |
| 健康状态 | 压力低、睡眠好、社交支持好 | none / mild |
| 中等风险 | 压力中等、睡眠一般、轻度焦虑 | moderate |
| 高风险 | 高压力、睡眠差、焦虑明显、惊恐发作 | high |
| 极高风险 | 高压力、家族史、焦虑严重、寻求治疗 | high / critical |

**文本模型样本**:

| 文本类型 | 示例 | 预期 |
| :--- | :--- | :--- |
| 正常情绪 | "最近有点累，但总体还好。" | none / mild |
| 中度压力 | "最近压力很大，睡不好，学习效率很低。" | moderate |
| 抑郁倾向 | "对什么都没兴趣，整天很难受。" | high |
| 危机表达 | "不想活了，想结束这一切。" | critical |

**融合模型样本**:

| 结构化 | 文本 | 生理 | 融合预期 |
| :--- | :--- | :--- | :--- |
| low | low | low | low |
| moderate | low | low | mild / moderate |
| high | low | low | moderate / high |
| low | high | low | high |
| low | critical 文本 | low | critical |
| high | high | moderate | high / critical |
| low | low | high | moderate / high，需复核 |
| missing | high | missing | high |

---

## 3. 非功能需求

- **性能**: 危机关键词匹配延迟 < 10ms；融合预测延迟 < 200ms
- **安全**: 危机表达检测必须 100% 命中，不允许漏判
- **可解释性**: 所有模型必须返回 risk_factors 和解释文本
- **可维护性**: 阈值配置必须外部化，支持热更新

## 4. 假设与约束

- 不重新训练模型，仅做阈值校准和规则增强
- 危机关键词库需要定期更新，由业务方维护
- 人工复核流程需要与现有咨询师系统对接
