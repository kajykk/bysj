from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass
from typing import Any

from app.core.text_context import analyze_match_context, is_third_person_clause


@dataclass(frozen=True)
class _KeywordHit:
    keyword: str
    start: int
    end: int


class TextAnalyzer:
    """文本风险分析器，提取 risk_factors 和 protective_factors。

    匹配口径（2026-11 修订）：
    * 否定 / 引号内元话语不计入（复用 ``app.core.text_context``）；
    * 症状描述的主语明显是第三人称时不计入用户症状；
    * 同一分句内重叠的关键词只保留最长的一条（``很累`` 不会再额外记一次 ``累``）。

    打分口径（替代原「匹配次数 × 25，最多 100」）：
    * 每个类别按 **去重后的关键词命中数** 计分：1 个 50%、2 个 75%、3 个及以上 100%，
      再乘以类别权重；同一句重复 10 次「难过」不会把分数堆到 100；
    * 类别之间用 noisy-OR 聚合，保护因素最多抵扣 25%，不会掩盖重度症状。
    """

    RISK_KEYWORDS: dict[str, list[str]] = {
        "interest_loss": [
            "没兴趣",
            "提不起兴趣",
            "什么都不想做",
            "不想做",
            "没动力",
            "没意思",
        ],
        "sleep_problem": [
            "睡不着",
            "失眠",
            "睡不好",
            "早醒",
            "多梦",
            "睡眠差",
            "睡得很少",
        ],
        "low_mood": [
            "难过",
            "低落",
            "沮丧",
            "郁闷",
            "痛苦",
            "空虚",
            "心情不好",
            "心情很差",
            "不开心",
            "很烦",
            "烦躁",
            "压抑",
            "难受",
            "崩溃",
            "糟糕",
            "emo",
            "伤心",
            "悲伤",
        ],
        "anxiety": [
            "焦虑",
            "担心",
            "紧张",
            "不安",
            "心慌",
            "害怕",
            "恐惧",
            "压力大",
            "很慌",
            "喘不过气",
        ],
        "social_withdrawal": [
            "不想见人",
            "不想出门",
            "不想社交",
            "不想说话",
            "回避社交",
            "避免社交",
            "没人理解",
            "躲着人",
            "不想联系",
            "孤立",
        ],
        "fatigue": [
            "疲惫",
            "精疲力尽",
            "乏力",
            "没力气",
            "很累",
            "太累了",
            "好累",
            "累",
        ],
        "appetite_change": [
            "不想吃饭",
            "没胃口",
            "吃不下",
            "没食欲",
            "食欲差",
            "不想吃东西",
            "不想吃",
            "体重下降",
            "吃了两口就饱",
        ],
        "psychomotor": [
            "不想起床",
            "起不来",
            "不想动",
            "动作慢",
            "反应慢",
            "什么都做不了",
            "洗漱都困难",
            "连站起来",
            "没有力气做事",
            "行动迟缓",
        ],
        "worthlessness": [
            "我真没用",
            "我很没用",
            "觉得自己没用",
            "一无是处",
            "毫无价值",
            "没有价值",
            "不配",
            "讨厌自己",
            "都是我的错",
            "拖累别人",
            "拖累",
            "自责",
            "不够好",
        ],
        "hopelessness": [
            "绝望",
            "没有希望",
            "看不到希望",
            "毫无希望",
            "活着没意义",
            "没意义",
            "没有出路",
            "看不到出路",
        ],
        "passive_ideation": [
            "不想再继续",
            "不想继续了",
            "不想醒来",
            "不想存在",
            "不想活着",
            "没有出口",
            "看不到出口",
            "不想面对明天",
            "不想再有明天",
            "希望自己没出生",
        ],
    }

    PROTECTIVE_KEYWORDS: dict[str, list[str]] = {
        "help_seeking": [
            "想求助",
            "需要帮助",
            "想聊聊",
            "想咨询",
            "谁能帮帮我",
            "主动求助",
            "寻求帮助",
        ],
        "social_support": [
            "支持我",
            "关心我",
            "陪伴我",
            "有人陪",
            "有人关心",
            "朋友支持",
            "朋友陪",
            "家人支持",
            "家人陪",
            "朋友也在",
            "有朋友",
            "有家人",
            "陪伴",
        ],
        "positive_coping": [
            "运动",
            "听音乐",
            "散步",
            "放松",
            "深呼吸",
            "写日记",
            "冥想",
            "晒太阳",
        ],
        # 裸「努力 / 希望 / 坚持」已移除：
        # 「努力表演」「没有希望」「坚持不下去」都会把这些词变成假保护因素。
        "future_oriented": [
            "想变好",
            "想好起来",
            "会好的",
            "会好起来",
            "还有希望",
            "看到希望",
            "期待未来",
            "对未来有期待",
            "有信心",
            "想试试",
            "想努力好起来",
        ],
    }

    RISK_CATEGORY_WEIGHTS: dict[str, float] = {
        "passive_ideation": 1.0,
        "hopelessness": 0.85,
        "worthlessness": 0.8,
        "psychomotor": 0.7,
        "interest_loss": 0.7,
        "sleep_problem": 0.65,
        "appetite_change": 0.65,
        "social_withdrawal": 0.6,
        "low_mood": 0.6,
        "anxiety": 0.55,
        "fatigue": 0.45,
    }

    PROTECTIVE_CATEGORY_WEIGHTS: dict[str, float] = {
        "help_seeking": 0.9,
        "positive_coping": 0.85,
        "social_support": 0.8,
        "future_oriented": 0.8,
    }

    #: 单个类别对风险总强度的贡献上限（noisy-OR 的单项概率系数）。
    RISK_EVIDENCE_WEIGHT = 0.5
    PROTECTIVE_EVIDENCE_WEIGHT = 0.5
    #: 保护因素最多抵扣 25%，避免「朋友很多」掩盖重度症状。
    PROTECTIVE_MAX_DISCOUNT = 0.25

    def __init__(self) -> None:
        """初始化分析器，编译正则表达式。"""
        self._risk_patterns: dict[str, list[tuple[re.Pattern[str], str]]] = {}
        for category, keywords in self.RISK_KEYWORDS.items():
            self._risk_patterns[category] = [
                (re.compile(re.escape(kw), re.IGNORECASE), kw) for kw in keywords
            ]

        self._protective_patterns: dict[str, list[tuple[re.Pattern[str], str]]] = {}
        for category, keywords in self.PROTECTIVE_KEYWORDS.items():
            self._protective_patterns[category] = [
                (re.compile(re.escape(kw), re.IGNORECASE), kw) for kw in keywords
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
                "risk_evidence": dict[str, list[str]],
                "protective_evidence": dict[str, list[str]],
                "suppressed_matches": list[dict],
                "heuristic_sentiment_score": float,
                "heuristic_sentiment_label": str,
            }
        """
        # H-ML-2 修复：处理 None/非字符串输入，避免 re.findall(text) 抛 TypeError
        # 融合引擎中文本模态缺失时可能传入 None
        if not text or not isinstance(text, str):
            return {
                "risk_factors": [],
                "protective_factors": [],
                "risk_factor_scores": {},
                "protective_factor_scores": {},
                "risk_evidence": {},
                "protective_evidence": {},
                "suppressed_matches": [],
                "heuristic_sentiment_score": 0.0,
                "heuristic_sentiment_label": "positive",
            }

        risk_hits, risk_suppressed = self._collect_hits(
            text, self._risk_patterns, third_person_filter=True
        )
        protective_hits, protective_suppressed = self._collect_hits(
            text, self._protective_patterns
        )

        risk_factor_scores, risk_evidence = self._score_categories(
            risk_hits, self.RISK_CATEGORY_WEIGHTS
        )
        protective_factor_scores, protective_evidence = self._score_categories(
            protective_hits, self.PROTECTIVE_CATEGORY_WEIGHTS
        )

        risk_strength = self._noisy_or(
            self.RISK_EVIDENCE_WEIGHT * score / 100.0
            for score in risk_factor_scores.values()
        )
        protective_strength = self._noisy_or(
            self.PROTECTIVE_EVIDENCE_WEIGHT * score / 100.0
            for score in protective_factor_scores.values()
        )
        heuristic_sentiment_score = max(
            0.0,
            min(
                1.0,
                risk_strength
                * (1.0 - self.PROTECTIVE_MAX_DISCOUNT * protective_strength),
            ),
        )

        return {
            "risk_factors": [
                self._translate_category(category)
                for category in risk_factor_scores
            ],
            "protective_factors": [
                self._translate_category(category)
                for category in protective_factor_scores
            ],
            "risk_factor_scores": risk_factor_scores,
            "protective_factor_scores": protective_factor_scores,
            "risk_evidence": risk_evidence,
            "protective_evidence": protective_evidence,
            "suppressed_matches": (risk_suppressed + protective_suppressed)[:20],
            "heuristic_sentiment_score": round(heuristic_sentiment_score, 4),
            "heuristic_sentiment_label": (
                "negative" if heuristic_sentiment_score >= 0.2 else "positive"
            ),
        }

    def _collect_hits(
        self,
        text: str,
        patterns: dict[str, list[tuple[re.Pattern[str], str]]],
        *,
        third_person_filter: bool = False,
    ) -> tuple[dict[str, list[_KeywordHit]], list[dict[str, Any]]]:
        hits_by_category: dict[str, list[_KeywordHit]] = {}
        suppressed: list[dict[str, Any]] = []

        for category, category_patterns in patterns.items():
            category_hits: list[_KeywordHit] = []
            for pattern, keyword in category_patterns:
                for match in pattern.finditer(text):
                    context = analyze_match_context(text, match.start(), match.end())
                    if context.suppressed:
                        suppressed.append(
                            {
                                "keyword": keyword,
                                "category": category,
                                "reason": context.suppress_reason,
                            }
                        )
                        continue
                    if third_person_filter and is_third_person_clause(
                        text, match.start()
                    ):
                        suppressed.append(
                            {
                                "keyword": keyword,
                                "category": category,
                                "reason": "third_person",
                            }
                        )
                        continue
                    category_hits.append(
                        _KeywordHit(keyword=keyword, start=match.start(), end=match.end())
                    )
            if category_hits:
                hits_by_category[category] = self._drop_overlaps(category_hits)

        return hits_by_category, suppressed

    @staticmethod
    def _drop_overlaps(hits: list[_KeywordHit]) -> list[_KeywordHit]:
        """同一分句内重叠的关键词只保留最长的一条。"""
        ordered = sorted(hits, key=lambda hit: (hit.start, -(hit.end - hit.start)))
        accepted: list[_KeywordHit] = []
        last_end = -1
        for hit in ordered:
            if hit.start < last_end:
                continue
            accepted.append(hit)
            last_end = hit.end
        return accepted

    @staticmethod
    def _score_categories(
        hits_by_category: dict[str, list[_KeywordHit]],
        weights: dict[str, float],
    ) -> tuple[dict[str, float], dict[str, list[str]]]:
        scores: dict[str, float] = {}
        evidence: dict[str, list[str]] = {}
        for category, hits in hits_by_category.items():
            distinct: list[str] = []
            for hit in hits:
                if hit.keyword not in distinct:
                    distinct.append(hit.keyword)
            base = min(100.0, 50.0 + 25.0 * (len(distinct) - 1))
            scores[category] = round(base * weights.get(category, 0.5), 2)
            evidence[category] = distinct
        return scores, evidence

    @staticmethod
    def _noisy_or(probabilities: Iterable[float]) -> float:
        remaining = 1.0
        for probability in probabilities:
            remaining *= 1.0 - max(0.0, min(1.0, float(probability)))
        return 1.0 - remaining

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
            "appetite_change": "食欲改变",
            "psychomotor": "精神运动性迟滞",
            "worthlessness": "自我否定",
            "hopelessness": "无望感",
            "passive_ideation": "被动意念",
            "help_seeking": "求助意愿",
            "social_support": "社会支持",
            "positive_coping": "积极应对",
            "future_oriented": "未来导向",
        }
        return translations.get(category, category)
