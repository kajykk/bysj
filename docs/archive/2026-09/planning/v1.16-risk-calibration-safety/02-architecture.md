# 系统架构设计 — v1.16-risk-calibration-safety

## 1. 技术栈

### 1.1 前端
- **框架**: React 18 + TypeScript
- **UI 库**: Tailwind CSS + shadcn/ui
- **状态管理**: Zustand

### 1.2 后端
- **Runtime**: Python 3.11
- **框架**: FastAPI
- **数据库**: PostgreSQL (生产) / SQLite (开发)
- **模型服务**: scikit-learn + PyTorch (fallback 到启发式规则)

### 1.3 基础设施
- **部署**: Docker + GitHub Actions
- **监控**: Prometheus + Grafana

---

## 2. 目录结构规范

```
backend/
├── app/
│   ├── api/v1/
│   │   └── model_predict.py          # API 端点 (已有，需扩展)
│   ├── core/
│   │   ├── model_engine.py           # 核心预测引擎 (已有，需修改)
│   │   ├── risk_thresholds.py        # 阈值配置 (已有，需扩展)
│   │   └── crisis_detector.py        # 新增: 危机检测模块
│   ├── ml/
│   │   ├── fusion_engine.py          # 融合引擎 (已有，需修改)
│   │   └── text_analyzer.py          # 新增: 文本风险分析器
│   ├── schemas/
│   │   └── model_predict.py          # Pydantic 模型 (已有，需扩展)
│   └── services/
│       └── model_predict_service.py  # 服务层 (已有，需修改)
├── tests/
│   └── expected_risk/                # 新增: 预期风险样本测试
│       ├── test_structured.py
│       ├── test_text.py
│       ├── test_physiological.py
│       └── test_fusion.py
└── scripts/
    └── calibration/                  # 新增: 校准工具
        └── threshold_tuner.py
```

---

## 3. 数据模型

### 3.1 危机关键词库 (CrisisKeyword)

| 字段名 | 类型 | 必填 | 说明 |
| :--- | :--- | :--- | :--- |
| id | UUID | 是 | 主键 |
| keyword | String | 是 | 关键词 |
| category | Enum | 是 | suicide, self_harm, despair |
| severity | Enum | 是 | high, critical |
| enabled | Boolean | 是 | 是否启用 |

### 3.2 预测结果增强字段

**结构化模型输出**:

```json
{
  "prediction": 1,
  "probability": 0.85,
  "risk_score": 85.0,
  "risk_level": 4,
  "model_used": "structured_logistic_regression_quick",
  "top_factors": [
    {"feature": "stress_level", "importance": 0.32}
  ],
  "explanation": "本次风险主要由压力水平较高导致。",
  "data_quality": {
    "missing_fields": [],
    "confidence_penalty": 0.0,
    "quality_level": "complete"
  }
}
```

**文本模型输出**:

```json
{
  "prediction": 1,
  "probability": 0.78,
  "distress_score": 78.0,
  "crisis_score": 20.0,
  "sentiment_label": "negative",
  "sentiment_score": 0.78,
  "model_used": "text_depression_model",
  "risk_factors": ["兴趣下降", "睡眠问题"],
  "protective_factors": ["仍有求助意愿"],
  "crisis_detected": false,
  "crisis_keywords": []
}
```

**生理模型输出**:

```json
{
  "prediction": 1,
  "probability": 0.72,
  "risk_score": 72.0,
  "risk_level": 3,
  "model_used": "physiological_risk_model",
  "confidence": 0.85,
  "data_quality": "complete",
  "calibrated": true
}
```

**融合模型输出**:

```json
{
  "risk_score": 75.0,
  "risk_level": 3,
  "severity": "high",
  "model_used": ["structured", "text", "physiological"],
  "model_version": "v1.16-risk-calibration",
  "fusion_detail": {
    "modality_scores": {
      "structured": {"score": 61, "weight": 0.3},
      "text": {"score": 82, "weight": 0.5},
      "physiological": {"score": 65, "weight": 0.2}
    },
    "weights": {"final": 75.0, "scheme": "priority_fusion"},
    "dominant_modality": "text",
    "modality_quality": {
      "structured": "primary",
      "text": "primary",
      "physiological": "secondary"
    },
    "intervention_summary": {
      "level": "high",
      "actions": ["发送高风险预警", "优先转介人工干预"]
    }
  },
  "intervention_level": "high",
  "intervention_actions": ["发送高风险预警", "优先转介人工干预"],
  "review_required": true,
  "review_reason": "text_high_risk",
  "review_triggers": ["text_high_risk"],
  "crisis_override": false
}
```

---

## 4. API 接口定义

### 4.1 模块: 模型预测 (已有接口增强)

#### 4.1.1 接口: 文本预测 (增强)

- **URL**: `POST /api/v1/model/predict/text`
- **Auth**: user.predict.use

**Request Body** (不变):
```json
{
  "text": "最近压力很大，睡不好。"
}
```

**Response (200 OK)**:
```json
{
  "code": 200,
  "data": {
    "prediction": 1,
    "probability": 0.78,
    "distress_score": 78.0,
    "crisis_score": 20.0,
    "sentiment_label": "negative",
    "sentiment_score": 0.78,
    "model_used": "text_depression_model",
    "risk_factors": ["睡眠问题", "压力表达"],
    "protective_factors": [],
    "crisis_detected": false,
    "crisis_keywords": []
  }
}
```

#### 4.1.2 接口: 融合预测 (增强)

- **URL**: `POST /api/v1/model/predict/fusion`
- **Auth**: user.predict.use

**Response (200 OK)**:
```json
{
  "code": 200,
  "data": {
    "risk_score": 75.0,
    "risk_level": 3,
    "severity": "high",
    "model_used": ["structured", "text"],
    "model_version": "v1.16-risk-calibration",
    "fusion_detail": {
      "modality_scores": {
        "structured": {"score": 61, "weight": 0.3},
        "text": {"score": 82, "weight": 0.5}
      },
      "dominant_modality": "text",
      "intervention_summary": {
        "level": "high",
        "actions": ["发送高风险预警"]
      }
    },
    "intervention_level": "high",
    "intervention_actions": ["发送高风险预警"],
    "review_required": true,
    "review_reason": "text_high_risk",
    "review_triggers": ["text_high_risk"],
    "crisis_override": false
  }
}
```

---

## 5. 关键流程设计

### 5.1 文本危机检测流程

```
用户输入文本
  -> crisis_detector.scan(text)
    -> 命中关键词?
      -> YES: 返回 crisis_detected=true, risk_level=critical
      -> NO: 继续 ML 模型预测
  -> model_engine.predict_text(text)
    -> 返回 distress_score, crisis_score, risk_factors, protective_factors
  -> 合并结果
    -> 如果 crisis_detected: 覆盖 risk_level 为 critical
```

### 5.2 融合模型优先级规则流程

```
收集三模态结果
  -> 检查文本危机标记
    -> crisis_detected=true? -> 直接返回 critical
  -> 检查多模型一致性
    -> >=2 个模型 high? -> 提升融合等级
  -> 检查模型分歧
    -> 差距 >40 分? -> 标记 review_required
  -> 检查置信度
    -> 低置信度 + 高风险? -> 标记 review_required
  -> 正常加权融合
    -> 返回融合结果 + modality_scores + review 标记
```

### 5.3 阈值校准流程

```
加载预期样本集
  -> 对每个样本执行预测
  -> 比较预测等级 vs 预期等级
  -> 计算偏差
  -> 调整阈值 (二分搜索/网格搜索)
  -> 验证新阈值
    -> 所有样本通过? -> 保存阈值
    -> 仍有偏差? -> 继续调整
```

---

## 6. 组件设计

### 6.1 CrisisDetector (新增)

```python
class CrisisDetector:
    """文本危机表达检测器"""

    CRISIS_KEYWORDS = {
        "suicide": ["自杀", "不想活", "结束生命", "想死", "活着没意义"],
        "self_harm": ["伤害自己", "割腕", "跳楼", "遗书"],
        "despair": ["没救了", "撑不下去了", "一切都完了"],
    }

    def scan(self, text: str) -> dict:
        """扫描文本，返回危机检测结果"""
        ...

    def get_crisis_score(self, text: str) -> float:
        """计算危机分数 0-100"""
        ...
```

### 6.2 TextAnalyzer (新增)

```python
class TextAnalyzer:
    """文本风险分析器，提取 risk_factors 和 protective_factors"""

    RISK_KEYWORDS = {
        "interest_loss": ["没兴趣", "不想做", "没意思"],
        "sleep_problem": ["睡不着", "失眠", "睡不好"],
        "low_mood": ["难过", "低落", "沮丧"],
        "anxiety": ["焦虑", "担心", "紧张"],
    }

    PROTECTIVE_KEYWORDS = {
        "help_seeking": ["想求助", "需要帮助", "想聊聊"],
        "social_support": ["朋友", "家人", "陪伴"],
    }

    def analyze(self, text: str) -> dict:
        """分析文本，返回风险因素和保护因素"""
        ...
```

### 6.3 阈值配置 (扩展)

```python
# risk_thresholds.py
MODALITY_RISK_THRESHOLDS = {
    "structured": {
        "mild": 25,
        "moderate": 45,
        "high": 65,
        "critical": 85,
    },
    "text": {
        "mild": 20,
        "moderate": 40,
        "high": 60,
        "critical": 80,
    },
    "physiological": {
        "mild": 35,
        "moderate": 55,
        "high": 75,
        "critical": 90,
    },
    "fusion": {
        "mild": 22,
        "moderate": 42,
        "high": 62,
        "critical": 82,
    },
}
```
