# 详细设计文档 — v1.16-risk-calibration-safety

## 1. 危机检测模块设计 (Crisis Detector)

### 1.1 类设计

```python
# backend/app/core/crisis_detector.py

from __future__ import annotations

import logging
import re
from typing import Any

logger = logging.getLogger(__name__)


class CrisisDetector:
    """文本危机表达检测器。

    负责扫描用户输入文本，检测是否包含自杀、自伤、极端绝望等危机表达。
    即使 ML 模型分数不高，命中危机关键词也应触发 critical 等级。
    """

    CRISIS_KEYWORDS: dict[str, list[str]] = {
        "suicide": [
            "自杀", "不想活", "结束生命", "想死", "活着没意义",
            "死了算了", "不想活了", "了结", "轻生",
        ],
        "self_harm": [
            "伤害自己", "割腕", "跳楼", "遗书", "自残",
            "把自己弄伤", "想流血", "想从楼上",
        ],
        "despair": [
            "没救了", "撑不下去了", "一切都完了", "绝望",
            "没有希望", "放弃一切", "彻底崩溃",
        ],
    }

    # 口语化过滤：排除明显非真实的宣泄表达
    CASUAL_EXPRESSIONS: list[str] = [
        "累死了", "烦死了", "饿死了", "笑死了",
        "困死了", "忙死了", "气死了", "热死了",
    ]

    def __init__(self) -> None:
        """初始化危机检测器，编译正则表达式。"""
        self._compiled_patterns: dict[str, list[re.Pattern]] = {}
        for category, keywords in self.CRISIS_KEYWORDS.items():
            self._compiled_patterns[category] = [
                re.compile(re.escape(kw), re.IGNORECASE) for kw in keywords
            ]
        self._casual_patterns = [
            re.compile(re.escape(expr), re.IGNORECASE)
            for expr in self.CASUAL_EXPRESSIONS
        ]

    def scan(self, text: str) -> dict[str, Any]:
        """扫描文本，返回危机检测结果。

        Args:
            text: 用户输入文本。

        Returns:
            {
                "crisis_detected": bool,
                "crisis_score": float (0-100),
                "matched_keywords": list[str],
                "category": str | None,
                "is_casual": bool,
            }
        """
        if not text or len(text.strip()) < 2:
            return {
                "crisis_detected": False,
                "crisis_score": 0.0,
                "matched_keywords": [],
                "category": None,
                "is_casual": False,
            }

        # 先检查是否是口语化表达
        is_casual = self._is_casual_expression(text)

        matched_keywords: list[str] = []
        detected_category: str | None = None
        max_severity = 0

        for category, patterns in self._compiled_patterns.items():
            for pattern in patterns:
                if pattern.search(text):
                    keyword = pattern.pattern.replace("\\", "")
                    matched_keywords.append(keyword)
                    if detected_category is None:
                        detected_category = category
                    # suicide/self_harm = 100, despair = 80
                    severity = 100 if category in ("suicide", "self_harm") else 80
                    max_severity = max(max_severity, severity)

        crisis_detected = len(matched_keywords) > 0 and not is_casual
        crisis_score = max_severity if crisis_detected else 0.0

        if crisis_detected:
            logger.warning(
                "Crisis detected in text: category=%s, keywords=%s",
                detected_category,
                matched_keywords,
            )

        return {
            "crisis_detected": crisis_detected,
            "crisis_score": crisis_score,
            "matched_keywords": matched_keywords,
            "category": detected_category,
            "is_casual": is_casual,
        }

    def _is_casual_expression(self, text: str) -> bool:
        """判断文本是否仅为口语化宣泄，非真实危机表达。"""
        # 如果文本很短（<15字）且只包含口语化表达，认为是 casual
        if len(text) < 15:
            for pattern in self._casual_patterns:
                if pattern.search(text):
                    return True
        return False

    def get_crisis_score(self, text: str) -> float:
        """计算危机分数 0-100。"""
        result = self.scan(text)
        return result["crisis_score"]
```

### 1.2 集成点

在 `model_engine.predict_text()` 中，在 ML 预测之前先调用 `CrisisDetector.scan()`：

```python
async def predict_text(self, text: str) -> dict[str, Any]:
    async with self._timed_async("predict", "text"):
        # 1. 危机检测 (新增)
        crisis_result = self.crisis_detector.scan(text)

        # 2. ML 模型预测 (已有)
        bert_result = await self._predict_text_bert(text)
        if bert_result is not None:
            ml_result = bert_result
        else:
            # ... TF-IDF 预测逻辑
            ml_result = {...}

        # 3. 文本风险分析 (新增)
        text_analysis = self.text_analyzer.analyze(text)

        # 4. 合并结果
        result = {
            **ml_result,
            "distress_score": round(ml_result.get("sentiment_score", 0) * 100, 2),
            "crisis_score": crisis_result["crisis_score"],
            "risk_factors": text_analysis["risk_factors"],
            "protective_factors": text_analysis["protective_factors"],
            "crisis_detected": crisis_result["crisis_detected"],
            "crisis_keywords": crisis_result["matched_keywords"],
        }

        # 5. 如果检测到危机，覆盖 risk_level
        if crisis_result["crisis_detected"]:
            result["risk_level"] = 4  # critical
            result["crisis_override"] = True

        return result
```

---

## 2. 文本风险分析模块设计 (Text Analyzer)

### 2.1 类设计

```python
# backend/app/ml/text_analyzer.py

from __future__ import annotations

import re
from typing import Any


class TextAnalyzer:
    """文本风险分析器，提取 risk_factors 和 protective_factors。"""

    RISK_KEYWORDS: dict[str, list[str]] = {
        "interest_loss": ["没兴趣", "不想做", "没意思", "没动力", "不想动"],
        "sleep_problem": ["睡不着", "失眠", "睡不好", "早醒", "多梦"],
        "low_mood": ["难过", "低落", "沮丧", "郁闷", "痛苦", "空虚"],
        "anxiety": ["焦虑", "担心", "紧张", "不安", "心慌", "害怕"],
        "social_withdrawal": ["不想见人", "不想出门", "孤立", "独处"],
        "fatigue": ["累", "疲惫", "没力气", "乏力", "精疲力尽"],
    }

    PROTECTIVE_KEYWORDS: dict[str, list[str]] = {
        "help_seeking": ["想求助", "需要帮助", "想聊聊", "想咨询", "谁能帮帮我"],
        "social_support": ["朋友", "家人", "陪伴", "支持", "关心我的人"],
        "positive_coping": ["运动", "听音乐", "散步", "放松", "深呼吸"],
        "future_oriented": ["想变好", "会好的", "坚持", "努力", "希望"],
    }

    def __init__(self) -> None:
        """初始化分析器，编译正则表达式。"""
        self._risk_patterns: dict[str, list[re.Pattern]] = {}
        for category, keywords in self.RISK_KEYWORDS.items():
            self._risk_patterns[category] = [
                re.compile(re.escape(kw), re.IGNORECASE) for kw in keywords
            ]

        self._protective_patterns: dict[str, list[re.Pattern]] = {}
        for category, keywords in self.PROTECTIVE_KEYWORDS.items():
            self._protective_patterns[category] = [
                re.compile(re.escape(kw), re.IGNORECASE) for kw in keywords
            ]

    def analyze(self, text: str) -> dict[str, Any]:
        """分析文本，返回风险因素和保护因素。

        Args:
            text: 用户输入文本。

        Returns:
            {
                "risk_factors": list[str],
                "protective_factors": list[str],
                "risk_factor_scores": dict[str, float],
                "protective_factor_scores": dict[str, float],
            }
        """
        risk_factors: list[str] = []
        risk_factor_scores: dict[str, float] = {}

        for category, patterns in self._risk_patterns.items():
            match_count = 0
            for pattern in patterns:
                match_count += len(pattern.findall(text))
            if match_count > 0:
                risk_factors.append(self._translate_category(category))
                # 分数基于匹配次数，最多 100
                risk_factor_scores[category] = min(100.0, match_count * 25.0)

        protective_factors: list[str] = []
        protective_factor_scores: dict[str, float] = {}

        for category, patterns in self._protective_patterns.items():
            match_count = 0
            for pattern in patterns:
                match_count += len(pattern.findall(text))
            if match_count > 0:
                protective_factors.append(self._translate_category(category))
                protective_factor_scores[category] = min(100.0, match_count * 25.0)

        return {
            "risk_factors": risk_factors,
            "protective_factors": protective_factors,
            "risk_factor_scores": risk_factor_scores,
            "protective_factor_scores": protective_factor_scores,
        }

    @staticmethod
    def _translate_category(category: str) -> str:
        """将类别代码翻译为中文。"""
        translations = {
            "interest_loss": "兴趣下降",
            "sleep_problem": "睡眠问题",
            "low_mood": "持续低落",
            "anxiety": "焦虑情绪",
            "social_withdrawal": "社交退缩",
            "fatigue": "疲劳乏力",
            "help_seeking": "求助意愿",
            "social_support": "社会支持",
            "positive_coping": "积极应对",
            "future_oriented": "未来导向",
        }
        return translations.get(category, category)
```

---

## 3. 融合模型优先级规则设计

### 3.1 规则引擎

```python
# backend/app/ml/fusion_priority_engine.py

from __future__ import annotations

from typing import Any


class FusionPriorityEngine:
    """融合模型优先级规则引擎。

    规则优先级（从高到低）：
    1. 文本危机表达 -> 直接 critical
    2. 多模型一致高风险 -> 提升等级
    3. 模型分歧 -> 标记复核
    4. 低置信度 -> 降低权重
    """

    def apply_priority_rules(
        self,
        structured_result: dict[str, Any] | None,
        text_result: dict[str, Any] | None,
        physio_result: dict[str, Any] | None,
        base_fused_score: float,
        base_risk_level: int,
    ) -> dict[str, Any]:
        """应用优先级规则，返回调整后的结果和复核标记。"""

        review_required = False
        review_triggers: list[str] = []
        crisis_override = False

        # 规则 1: 文本危机表达优先级最高
        if text_result and text_result.get("crisis_detected"):
            base_risk_level = 4  # critical
            base_fused_score = max(base_fused_score, 90.0)
            crisis_override = True
            review_required = True
            review_triggers.append("crisis_override")

        # 规则 2: 多模型一致高风险时提升等级
        high_risk_count = 0
        for result in [structured_result, text_result, physio_result]:
            if result and result.get("risk_level", 0) >= 3:
                high_risk_count += 1
        if high_risk_count >= 2 and base_risk_level < 3:
            base_risk_level = 3  # high
            base_fused_score = max(base_fused_score, 65.0)

        # 规则 3: 单个模型 high，其他 low -> 标记复核
        if high_risk_count == 1:
            review_required = True
            review_triggers.append("single_modality_high_risk")

        # 规则 4: 模型分歧 (>40 分)
        scores = []
        for result in [structured_result, text_result, physio_result]:
            if result:
                scores.append(result.get("risk_score", 0))
        if scores:
            score_range = max(scores) - min(scores)
            if score_range > 40:
                review_required = True
                review_triggers.append(f"model_disagreement_{int(score_range)}_points")

        # 规则 5: 低置信度 + 高风险
        for modality, result in [
            ("structured", structured_result),
            ("text", text_result),
            ("physiological", physio_result),
        ]:
            if result:
                confidence = result.get("confidence", 1.0)
                risk_level = result.get("risk_level", 0)
                if confidence < 0.5 and risk_level >= 3:
                    review_required = True
                    review_triggers.append(f"low_confidence_high_risk_{modality}")

        return {
            "risk_score": round(base_fused_score, 2),
            "risk_level": base_risk_level,
            "review_required": review_required,
            "review_triggers": review_triggers,
            "crisis_override": crisis_override,
        }
```

---

## 4. 阈值配置设计

### 4.1 配置文件

```python
# backend/app/core/risk_thresholds.py

from __future__ import annotations

# v1.16 校准后的阈值
MODALITY_RISK_THRESHOLDS: dict[str, dict[str, int]] = {
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

RISK_LEVEL_LABELS: dict[int, str] = {
    0: "none",
    1: "mild",
    2: "moderate",
    3: "high",
    4: "critical",
}


def get_threshold_by_modality(modality: str) -> dict[str, int]:
    """获取指定模态的阈值配置。"""
    return MODALITY_RISK_THRESHOLDS.get(modality, MODALITY_RISK_THRESHOLDS["structured"])


def score_to_level(score: float, modality: str = "structured") -> int:
    """将风险分数转换为风险等级。"""
    thresholds = get_threshold_by_modality(modality)
    if score >= thresholds["critical"]:
        return 4
    if score >= thresholds["high"]:
        return 3
    if score >= thresholds["moderate"]:
        return 2
    if score >= thresholds["mild"]:
        return 1
    return 0
```

---

## 5. 生理模型输入校验设计

### 5.1 Pydantic Schema

```python
# backend/app/schemas/model_predict.py

from pydantic import BaseModel, Field, field_validator


class PhysiologicalPredictRequest(BaseModel):
    physiological: dict[str, float | int]

    @field_validator("physiological")
    @classmethod
    def validate_ranges(cls, v: dict[str, float | int]) -> dict[str, float | int]:
        """校验生理数据范围。"""
        ranges = {
            "sleep_hours": (0, 16),
            "sleep_quality": (1, 10),
            "exercise_minutes": (0, 300),
            "heart_rate": (35, 220),
            "systolic_bp": (70, 220),
            "diastolic_bp": (40, 140),
            "steps": (0, 50000),
        }

        errors = []
        for field, (min_val, max_val) in ranges.items():
            if field in v:
                val = float(v[field])
                if val < min_val or val > max_val:
                    errors.append(
                        f"{field}={val} 超出有效范围 [{min_val}, {max_val}]"
                    )

        if errors:
            from pydantic import ValidationError
            raise ValueError("; ".join(errors))

        return v
```

---

## 6. 人工复核标记设计

### 6.1 复核原因枚举

```python
# backend/app/core/review_reasons.py

from enum import Enum


class ReviewReason(str, Enum):
    """人工复核原因枚举。"""

    CRISIS_OVERRIDE = "crisis_override"
    TEXT_HIGH_RISK = "text_high_risk"
    MODEL_DISAGREEMENT = "model_disagreement"
    SINGLE_MODALITY_HIGH_RISK = "single_modality_high_risk"
    LOW_CONFIDENCE_HIGH_RISK = "low_confidence_high_risk"


REVIEW_REASON_LABELS: dict[str, str] = {
    ReviewReason.CRISIS_OVERRIDE: "检测到危机表达",
    ReviewReason.TEXT_HIGH_RISK: "文本高风险",
    ReviewReason.MODEL_DISAGREEMENT: "模型分歧",
    ReviewReason.SINGLE_MODALITY_HIGH_RISK: "单模态高风险",
    ReviewReason.LOW_CONFIDENCE_HIGH_RISK: "低置信度高风险",
}
```

---

## 7. 预期风险样本测试设计

### 7.1 测试结构

```python
# backend/tests/expected_risk/conftest.py

from typing import Any

import pytest

# 结构化模型预期样本
STRUCTURED_TEST_CASES: list[dict[str, Any]] = [
    {
        "name": "健康状态",
        "features": {
            "age": 20,
            "gender": 1,
            "stress_level": 1,
            "sleep_duration": 8,
            "social_support": 5,
            "academic_pressure": 1,
            "anxiety": 1,
            "panic_attack": 0,
            "treatment_seeking": 0,
        },
        "expected_level_range": [0, 1],  # none or mild
    },
    {
        "name": "中等风险",
        "features": {
            "age": 22,
            "gender": 0,
            "stress_level": 3,
            "sleep_duration": 5,
            "social_support": 3,
            "academic_pressure": 3,
            "anxiety": 3,
            "panic_attack": 0,
            "treatment_seeking": 0,
        },
        "expected_level_range": [2],  # moderate
    },
    {
        "name": "高风险",
        "features": {
            "age": 21,
            "gender": 1,
            "stress_level": 5,
            "sleep_duration": 3,
            "social_support": 1,
            "academic_pressure": 5,
            "anxiety": 5,
            "panic_attack": 1,
            "treatment_seeking": 0,
        },
        "expected_level_range": [3],  # high
    },
    {
        "name": "极高风险",
        "features": {
            "age": 23,
            "gender": 0,
            "stress_level": 5,
            "sleep_duration": 2,
            "social_support": 1,
            "academic_pressure": 5,
            "anxiety": 5,
            "panic_attack": 1,
            "treatment_seeking": 1,
            "family_history": 1,
        },
        "expected_level_range": [3, 4],  # high or critical
    },
]

# 文本模型预期样本
TEXT_TEST_CASES: list[dict[str, Any]] = [
    {
        "name": "正常情绪",
        "text": "最近有点累，但总体还好。",
        "expected_level_range": [0, 1],
        "crisis_detected": False,
    },
    {
        "name": "中度压力",
        "text": "最近压力很大，睡不好，学习效率很低。",
        "expected_level_range": [2],
        "crisis_detected": False,
    },
    {
        "name": "抑郁倾向",
        "text": "对什么都没兴趣，整天很难受。",
        "expected_level_range": [3],
        "crisis_detected": False,
    },
    {
        "name": "危机表达",
        "text": "不想活了，想结束这一切。",
        "expected_level_range": [4],
        "crisis_detected": True,
    },
]

# 融合模型预期样本
FUSION_TEST_CASES: list[dict[str, Any]] = [
    {
        "name": "全低",
        "structured": {"risk_level": 0, "risk_score": 10},
        "text": {"risk_level": 0, "risk_score": 15},
        "physiological": {"risk_level": 0, "risk_score": 20},
        "expected_level_range": [0, 1],
    },
    {
        "name": "文本 critical",
        "structured": {"risk_level": 0, "risk_score": 15},
        "text": {"risk_level": 4, "risk_score": 95, "crisis_detected": True},
        "physiological": None,
        "expected_level_range": [4],
        "crisis_detected": True,
    },
]
```

### 7.2 断言辅助函数

```python
# backend/tests/expected_risk/utils.py

def assert_risk_level_in_range(
    actual_level: int,
    expected_range: list[int],
    test_name: str,
) -> None:
    """断言风险等级在预期范围内。"""
    assert actual_level in expected_range, (
        f"测试 '{test_name}' 失败: "
        f"实际风险等级 {actual_level} 不在预期范围 {expected_range} 内"
    )


def assert_crisis_detected(
    actual: bool,
    expected: bool,
    test_name: str,
) -> None:
    """断言危机检测结果。"""
    assert actual == expected, (
        f"测试 '{test_name}' 失败: "
        f"危机检测预期 {expected}，实际 {actual}"
    )
```
