from __future__ import annotations

import logging
import re
import unicodedata
from typing import Any, Iterable

from app.core.text_context import (
    analyze_match_context,
    has_first_person_marker,
    is_third_person_clause,
)

logger = logging.getLogger(__name__)

#: 关键词召回前允许忽略的插入虚词（「活着没有的意义」→「活着没意义」）。
#: 只在长度足够的紧凑形式上启用，避免把「了结」压缩成单字「结」后误命中。
_FILLER_CHARS: frozenset[str] = frozenset("有的了")

#: 常见繁体字 → 简体字映射（覆盖危机词库出现过的字）。
#: 只做字符级归一，不引入第三方繁简库依赖。
_TRADITIONAL_TO_SIMPLIFIED: dict[str, str] = {
    "著": "着",
    "沒": "没",
    "義": "义",
    "續": "续",
    "堅": "坚",
    "氣": "气",
    "覺": "觉",
    "傷": "伤",
    "殺": "杀",
    "樓": "楼",
    "書": "书",
    "遺": "遗",
    "準": "准",
    "備": "备",
    "結": "结",
    "離": "离",
    "開": "开",
    "個": "个",
    "這": "这",
    "斷": "断",
    "殘": "残",
    "劃": "划",
    "計": "计",
    "麼": "么",
    "輕": "轻",
    "對": "对",
    "難": "难",
    "過": "过",
    "還": "还",
    "會": "会",
    "樣": "样",
    "願": "愿",
    "頭": "头",
    "幫": "帮",
    "壓": "压",
    "鬱": "郁",
    "絕": "绝",
    "贅": "赘",
    "餘": "余",
    "夠": "够",
    "點": "点",
}


def _normalize_text_with_map(text: str) -> tuple[str, list[int]]:
    """全半角 / 简繁 / 大小写归一，并保留归一化字符到原文的下标映射。

    映射用于把归一化文本上的命中区间还原到原文，保证否定、引号、第三人称
    等上下文裁定仍作用于用户原始输入。
    """
    chars: list[str] = []
    index_map: list[int] = []
    for original_index, char in enumerate(text):
        if char.isspace():
            continue
        mapped = _TRADITIONAL_TO_SIMPLIFIED.get(char, char)
        normalized = unicodedata.normalize("NFKC", mapped)
        for out_char in normalized:
            if out_char.isspace():
                continue
            chars.append(out_char.lower() if out_char.isascii() else out_char)
            index_map.append(original_index)
    return "".join(chars), index_map


def _compact_text(normalized: str, index_map: list[int]) -> tuple[str, list[int]]:
    """去掉插入虚词，得到用于模糊召回的紧凑文本及下标映射。"""
    chars: list[str] = []
    compact_map: list[int] = []
    for char, original_index in zip(normalized, index_map):
        if char in _FILLER_CHARS:
            continue
        chars.append(char)
        compact_map.append(original_index)
    return "".join(chars), compact_map


def _find_all(haystack: str, needle: str) -> Iterable[int]:
    """返回 needle 在 haystack 中的所有起始下标（允许重叠）。"""
    if not needle:
        return
    start = 0
    while True:
        index = haystack.find(needle, start)
        if index < 0:
            return
        yield index
        start = index + 1


def _map_span(
    index_map: list[int], start: int, end: int
) -> tuple[int, int] | None:
    """把归一化文本区间映射回原文区间。"""
    if start >= len(index_map) or end <= start:
        return None
    last = min(end - 1, len(index_map) - 1)
    return index_map[start], index_map[last] + 1


class CrisisDetector:
    """文本危机表达检测器。

    负责扫描用户输入文本，检测是否包含自杀、自伤、极端绝望等危机表达。
    即使 ML 模型分数不高，命中危机关键词也应触发 critical 等级。

    关键词命中先经 :mod:`app.core.text_context` 做上下文裁定：
    否定、引号内的元话语（讨论词语本身）不计入有效命中；
    转述（``他说「我想死」``）仍计入，交给人工复核判断归属。
    """

    CRISIS_KEYWORDS: dict[str, list[str]] = {
        "suicide": [
            "自杀",
            "不想活",
            "结束生命",
            "想死",
            "死了算了",
            "不想活了",
            "了结",
            "轻生",
            "活不下去",
            "离开这个世界",
            "结束自己",
            "自我了断",
            # 明确意图短语（单独「自杀」不再直接判 critical，见临床转述口径）
            "想自杀",
            "要自杀",
            "打算自杀",
            "准备自杀",
            "决定自杀",
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
        # 被动意念：没有明确「死」字，但表达「不想继续存在/继续下去」。
        # 单独命中不足以判 level 4，需要上下文或第二类信号佐证。
        "passive_ideation": [
            "不想再活",
            "不想再继续",
            "不想继续了",
            "不想继续下去",
            "不想继续",
            "不想醒来",
            "不想再醒来",
            "希望醒不过来",
            "不想存在",
            "不想活着",
            "不如消失",
            "没有出口",
            "看不到出口",
            "不想撑下去",
            "不想再撑",
            "不想再坚持",
            "不想坚持",
            "坚持不下去了",
            "坚持不下去",
            "不想再努力",
            "不想努力了",
            "希望自己没出生",
            "不想被生下来",
            "不想面对明天",
            "不想再有明天",
            # D1：明确的消极/被动意念，无「死」字但语义等同放弃生命。
            "活着没意义",
            "活着没有意义",
            "活着没意思",
            "活着没有意思",
            "活着没价值",
            "活着真的一点意义都没有",
            "一点意义都没有",
            "活够了",
            "人生没意义",
            "人生没有意义",
            "生活没意义",
            "生活没有意义",
            # 消失类：想从这个世界上消失
            "想从这个世界上消失",
            "从这个世界上消失",
            "想消失",
            "想要消失",
            # 粤语：唔想活 / 唔想做人
            "唔想活",
            "唔想做人",
            "没有活下去的勇气",
            "没有活下去勇气",
            "没有活下去的理由",
            "没有活着的勇气",
            "觉得自己是累赘",
            "自己是个累赘",
            "自己是累赘",
            "我是累赘",
            "自己是多余的",
            "我是多余的",
            "觉得拖累别人",
            "拖累家人",
        ],
        "despair": [
            "没救了",
            "撑不下去了",
            "撑不下去",
            "一切都完了",
            "绝望",
            "没有希望",
            "放弃一切",
            "彻底崩溃",
            "撑不住了",
            "没人需要我",
            "活着太累",
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

    CATEGORY_SEVERITY: dict[str, int] = {
        "suicide": 100,
        "self_harm": 100,
        "passive_ideation": 85,
        "despair": 80,
        "internet_slang": 70,
        "planning": 70,
        "help_seeking": 40,
    }

    #: 类别本身语义明确，单条命中即可直接按 critical 处理。
    HIGH_CONFIDENCE_CATEGORIES: frozenset[str] = frozenset({"suicide", "self_harm"})

    #: 具体短语比类别更明确时，单条命中也可直接 critical。
    #: 「已经准备好了」「准备好了」过于宽泛，故意不在此列。
    HIGH_CONFIDENCE_KEYWORDS: frozenset[str] = frozenset(
        {"今晚就结束", "留下遗书", "准备好了结", "想一了百了"}
    )

    #: D1 口径：只有带时间、计划、手段或明确求死意图的表达才允许 level 4。
    #: 其余危机命中（含被动意念、单纯绝望、求助）一律封顶 level 3。
    CRITICAL_INTENT_KEYWORDS: frozenset[str] = frozenset(
        {
            # 明确意图（「自杀」单独出现不算明确意图：临床转述需 3 级复核）
            "想自杀",
            "要自杀",
            "打算自杀",
            "准备自杀",
            "决定自杀",
            "想死",
            "不想活",
            "不想活了",
            "结束生命",
            "结束自己",
            "活不下去",
            "轻生",
            "离开这个世界",
            "自我了断",
            "想一了百了",
            # 具体手段
            "割腕",
            "跳楼",
            "遗书",
            "留下遗书",
            "用刀划",
            # 时间 / 计划
            "今晚就结束",
            "准备好了结",
        }
    )

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
        """初始化危机检测器，预归一化关键词。"""
        # (原始关键词, 归一化关键词, 去虚词紧凑关键词)
        self._keyword_entries: dict[
            str, list[tuple[str, str, str]]
        ] = {}
        for category, keywords in self.CRISIS_KEYWORDS.items():
            entries: list[tuple[str, str, str]] = []
            for keyword in keywords:
                normalized, _ = _normalize_text_with_map(keyword)
                if not normalized:
                    continue
                compact, _ = _compact_text(normalized, list(range(len(normalized))))
                entries.append((keyword, normalized, compact))
            self._keyword_entries[category] = entries
        self._casual_patterns = [
            re.compile(re.escape(expr), re.IGNORECASE)
            for expr in self.CASUAL_EXPRESSIONS
        ]

    def _collect_candidates(
        self, text: str
    ) -> list[tuple[str, str, int, int]]:
        """归一化 + 近义召回，返回 (类别, 关键词, 原文起, 原文止)。"""
        normalized, index_map = _normalize_text_with_map(text)
        compact, compact_map = _compact_text(normalized, index_map)

        candidates: list[tuple[str, str, int, int]] = []
        seen: set[tuple[str, int]] = set()
        for category, entries in self._keyword_entries.items():
            for keyword, normalized_keyword, compact_keyword in entries:
                for start in _find_all(normalized, normalized_keyword):
                    span = _map_span(
                        index_map, start, start + len(normalized_keyword)
                    )
                    if span is None:
                        continue
                    key = (keyword, span[0])
                    if key in seen:
                        continue
                    seen.add(key)
                    candidates.append((category, keyword, span[0], span[1]))

                # 模糊召回：忽略插入虚词（「活着没有的意义」→「活着没意义」）。
                # 只有紧凑形式足够长才启用，避免单字（如「了结」→「结」）误命中。
                if len(compact_keyword) < 3 or compact_keyword == normalized_keyword:
                    continue
                for start in _find_all(compact, compact_keyword):
                    span = _map_span(
                        compact_map, start, start + len(compact_keyword)
                    )
                    if span is None:
                        continue
                    key = (keyword, span[0])
                    if key in seen:
                        continue
                    seen.add(key)
                    candidates.append((category, keyword, span[0], span[1]))
        return candidates

    def scan(self, text: str) -> dict[str, Any]:
        """扫描文本，返回危机检测结果。

        Args:
            text: 用户输入文本。

        Returns:
            {
                "crisis_detected": bool,
                "crisis_score": float (0-100),
                "matched_keywords": list[str],       # 仅有效命中
                "category": str | None,              # 最高严重度的类别
                "is_casual": bool,
                "matched_categories": list[str],
                "suppressed_matches": list[dict],    # 被否定/元话语过滤的命中
                "third_person_matches": list[dict],  # D4：只记录、不升级的第三人称命中
                "critical_intent": bool,             # 是否允许直接 level 4
                "requires_corroboration": bool,      # 单条弱信号，不足以直接 level 4
            }
        """
        empty_result: dict[str, Any] = {
            "crisis_detected": False,
            "crisis_score": 0.0,
            "matched_keywords": [],
            "category": None,
            "is_casual": False,
            "matched_categories": [],
            "suppressed_matches": [],
            "third_person_matches": [],
            "critical_intent": False,
            "requires_corroboration": False,
        }
        if not text or len(text.strip()) < 2:
            return empty_result

        # 先检查是否是口语化表达
        is_casual = self._is_casual_expression(text)
        first_person_present = has_first_person_marker(text)

        matched_keywords: list[str] = []
        matched_categories: list[str] = []
        suppressed_matches: list[dict[str, Any]] = []
        third_person_matches: list[dict[str, Any]] = []
        keyword_severities: list[tuple[int, str, str]] = []

        for category, keyword, start, end in self._collect_candidates(text):
            context = analyze_match_context(text, start, end)
            if context.suppressed:
                suppressed_matches.append(
                    {
                        "keyword": keyword,
                        "category": category,
                        "reason": context.suppress_reason,
                        "start": start,
                        "end": end,
                    }
                )
                continue

            # D4：第三人称 / 转述只记录不升级；文本同时含第一人称表述时按本人处理。
            if is_third_person_clause(text, start) and not first_person_present:
                third_person_matches.append(
                    {
                        "keyword": keyword,
                        "category": category,
                        "start": start,
                        "end": end,
                        "reported_speech": context.reported_speech,
                    }
                )
                continue

            matched_keywords.append(keyword)
            if category not in matched_categories:
                matched_categories.append(category)
            keyword_severities.append(
                (self.CATEGORY_SEVERITY.get(category, 70), category, keyword)
            )

        crisis_detected = len(matched_keywords) > 0 and not is_casual
        max_severity = 0
        detected_category: str | None = None
        if crisis_detected and keyword_severities:
            max_severity, detected_category, _ = max(
                keyword_severities, key=lambda item: item[0]
            )

        high_confidence = bool(
            set(matched_categories) & self.HIGH_CONFIDENCE_CATEGORIES
        ) or bool(set(matched_keywords) & self.HIGH_CONFIDENCE_KEYWORDS)
        requires_corroboration = bool(
            crisis_detected and not high_confidence and len(matched_categories) < 2
        )
        critical_intent = bool(
            crisis_detected
            and set(matched_keywords) & self.CRITICAL_INTENT_KEYWORDS
        )
        crisis_score = float(max_severity) if crisis_detected else 0.0

        if crisis_detected:
            logger.warning(
                "Crisis detected in text: category=%s, keywords=%s, critical_intent=%s",
                detected_category,
                matched_keywords,
                critical_intent,
            )
        if suppressed_matches:
            logger.debug(
                "Crisis keyword matches suppressed by context: %s", suppressed_matches
            )
        if third_person_matches:
            logger.debug(
                "Crisis keyword matches recorded as third-person: %s",
                third_person_matches,
            )

        result = dict(empty_result)
        result.update(
            {
                "crisis_detected": crisis_detected,
                "crisis_score": crisis_score,
                "matched_keywords": matched_keywords,
                "category": detected_category,
                "is_casual": is_casual,
                "matched_categories": matched_categories,
                "suppressed_matches": suppressed_matches,
                "third_person_matches": third_person_matches,
                "critical_intent": critical_intent,
                "requires_corroboration": requires_corroboration,
            }
        )
        return result

    def _is_casual_expression(self, text: str) -> bool:
        """判断文本是否仅为口语化宣泄，非真实危机表达。

        只有当文本很短（<30字）且只包含口语化表达、不含危机关键词时，
        才认为是 casual。
        """
        # M-Core-5 修复：原阈值 15 字过低，正常口语化表达（>15字）被误判为非危机；
        # 提升到 30 字，避免较长的口语化宣泄被漏判为 casual 而掩盖真实危机。
        if len(text) >= 30:
            return False

        normalized, index_map = _normalize_text_with_map(text)
        compact, _ = _compact_text(normalized, index_map)

        # 先检查是否包含危机关键词（归一化后判断，避免繁体/插入虚词漏判）
        for entries in self._keyword_entries.values():
            for _keyword, normalized_keyword, compact_keyword in entries:
                if normalized_keyword in normalized:
                    return False
                if len(compact_keyword) >= 3 and compact_keyword in compact:
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
