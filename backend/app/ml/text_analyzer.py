from __future__ import annotations

import re
from typing import Any


class TextAnalyzer:
    """文本风险分析器，提取 risk_factors 和 protective_factors。"""

    RISK_KEYWORDS: dict[str, list[str]] = {
        "interest_loss": ["没兴趣", "不想做", "没意思", "没动力", "不想动", "提不起兴趣", "什么都不想做"],
        "sleep_problem": ["睡不着", "失眠", "睡不好", "早醒", "多梦", "睡眠差", "睡得很少"],
        "low_mood": [
            "难过", "低落", "沮丧", "郁闷", "痛苦", "空虚", "心情不好", "心情很差", "不开心",
            "很烦", "烦躁", "压抑", "难受", "崩溃", "糟糕", "emo", "伤心", "悲伤",
        ],
        "anxiety": ["焦虑", "担心", "紧张", "不安", "心慌", "害怕", "恐惧", "压力大", "很慌"],
        "social_withdrawal": ["不想见人", "不想出门", "孤立", "独处", "没人理解", "不想说话"],
        "fatigue": ["累", "疲惫", "没力气", "乏力", "精疲力尽", "很累", "太累了"],
    }

    PROTECTIVE_KEYWORDS: dict[str, list[str]] = {
        "help_seeking": ["想求助", "需要帮助", "想聊聊", "想咨询", "谁能帮帮我"],
        "social_support": ["朋友", "家人", "陪伴", "支持", "关心我的人"],
        "positive_coping": ["运动", "听音乐", "散步", "放松", "深呼吸"],
        "future_oriented": ["想变好", "会好的", "坚持", "努力", "希望", "期待", "有信心"],
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

        risk_total = sum(risk_factor_scores.values())
        protective_total = sum(protective_factor_scores.values())
        heuristic_sentiment_score = max(0.0, min(1.0, (risk_total - protective_total * 0.6) / 100.0))

        return {
            "risk_factors": risk_factors,
            "protective_factors": protective_factors,
            "risk_factor_scores": risk_factor_scores,
            "protective_factor_scores": protective_factor_scores,
            "heuristic_sentiment_score": round(heuristic_sentiment_score, 4),
            "heuristic_sentiment_label": "negative" if heuristic_sentiment_score >= 0.2 else "positive",
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
