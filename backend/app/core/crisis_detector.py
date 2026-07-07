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
            "自杀",
            "不想活",
            "结束生命",
            "想死",
            "活着没意义",
            "死了算了",
            "不想活了",
            "了结",
            "轻生",
            "活不下去",
            "离开这个世界",
            "结束自己",
            "自我了断",
        ],
        "self_harm": [
            "伤害自己",
            "割腕",
            "跳楼",
            "遗书",
            "自残",
            "把自己弄伤",
            "想流血",
            "想从楼上",
            "用刀划",
            "割自己",
            "想疼",
        ],
        "despair": [
            "没救了",
            "撑不下去了",
            "一切都完了",
            "绝望",
            "没有希望",
            "放弃一切",
            "彻底崩溃",
            "撑不住了",
            "没意义",
            "没人需要我",
            "没有希望",
        ],
        "internet_slang": [
            "emo到不想活",
            "破防到想死",
            "想一了百了",
            "不想活了真的",
            "活着好累",
        ],
        "planning": [
            "已经准备好了",
            "今晚就结束",
            "留下遗书",
            "准备好了结",
            "计划好了",
            "准备好了",
        ],
        "help_seeking": [
            "救救我",
            "我控制不住自己",
            "我怕我会伤害自己",
            "谁能帮帮我",
            "我需要帮助",
            "我快撑不住了",
        ],
    }

    # 口语化过滤：排除明显非真实的宣泄表达
    CASUAL_EXPRESSIONS: list[str] = [
        "累死了",
        "烦死了",
        "饿死了",
        "笑死了",
        "困死了",
        "忙死了",
        "气死了",
        "热死了",
        "社死了",
        "尴尬死了",
        "冻死了",
        "无聊死了",
    ]

    def __init__(self) -> None:
        """初始化危机检测器，编译正则表达式。"""
        # L-修复：同时保存原始关键词，避免从 pattern.pattern 反推时丢失信息
        self._compiled_patterns: dict[str, list[tuple[re.Pattern, str]]] = {}
        for category, keywords in self.CRISIS_KEYWORDS.items():
            self._compiled_patterns[category] = [
                (re.compile(re.escape(kw), re.IGNORECASE), kw) for kw in keywords
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
            for pattern, keyword in patterns:
                if pattern.search(text):
                    # L-修复：直接使用保存的原始关键词，避免 replace("\\", "") 反推丢失信息
                    matched_keywords.append(keyword)
                    if detected_category is None:
                        detected_category = category
                    if category in ("suicide", "self_harm"):
                        severity = 100
                    elif category == "despair":
                        severity = 80
                    elif category == "help_seeking":
                        severity = 40
                    else:
                        severity = 70
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
        """判断文本是否仅为口语化宣泄，非真实危机表达。

        只有当文本很短（<30字）且只包含口语化表达、不含危机关键词时，
        才认为是 casual。
        """
        # M-Core-5 修复：原阈值 15 字过低，正常口语化表达（>15字）被误判为非危机；
        # 提升到 30 字，避免较长的口语化宣泄被漏判为 casual 而掩盖真实危机。
        if len(text) >= 30:
            return False

        # 先检查是否包含危机关键词
        for patterns in self._compiled_patterns.values():
            for pattern, _keyword in patterns:
                if pattern.search(text):
                    return False

        # 不包含危机关键词，再检查是否是口语化表达
        for pattern in self._casual_patterns:
            if pattern.search(text):
                return True

        return False

    def get_crisis_score(self, text: str) -> float:
        """计算危机分数 0-100。"""
        result = self.scan(text)
        return result["crisis_score"]
