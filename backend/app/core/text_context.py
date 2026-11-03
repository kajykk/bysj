"""关键词命中的上下文裁定：引号、元话语、否定。

纯字符串规则，放在 ``app.core`` 内供危机检测与文本分析共用。
本模块只回答「这处命中是否算数」，不判断风险等级。

三类误报的处置口径：

* **否定**：命中词前同一分句内出现「不是 / 没有 / 不会 / 从未」等标记，
  或紧邻一个「不」，视为否定。``忍不住想死`` / ``控制不住自己想死``
  因为「不」不紧邻命中词，仍算有效命中。
* **元话语（提到词语本身）**：命中词被引号包裹，且引号外紧跟
  「太重 / 太吓人 / 这个词 / 这两个字」等评述，视为在讨论词，不是表达。
  只有引号 + 评述才算；无引号的「绝望太重了」仍按真实表达处理。
* **转述**：``他说「我想死」`` 没有元话语评述，仍算有效命中；
  是否属于用户本人由后续人工复核判断，检测侧不擅自降级。
"""

from __future__ import annotations

import re
from dataclasses import dataclass

QUOTE_PAIRS: tuple[tuple[str, str], ...] = (
    ("「", "」"),
    ("『", "』"),
    ("“", "”"),
    ("‘", "’"),
    ("《", "》"),
    ('"', '"'),
)

CLAUSE_DELIMITERS = "，。；！？,;!?\n\r、…"

#: 裸「不」只在紧邻命中词时生效，避免把「忍不住」「控制不住」当作否定。
NEGATION_MARKERS: tuple[str, ...] = (
    "不是",
    "并不是",
    "并非",
    "并不",
    "并没有",
    "没有",
    "没",
    "不会",
    "不可能",
    "从未",
    "从没",
    "从不",
    "从未有过",
    "不再",
    "谈不上",
    "称不上",
    "算不上",
    "不要",
    "别",
    "不至于",
    "哪有",
    "怎么会",
)

#: 双重否定（不是没有想过自杀）表达的是肯定，不能按否定过滤。
DOUBLE_NEGATION_SUFFIXES: tuple[str, ...] = ("不是没有", "并非没有", "并不是没有")

#: 关键词前出现的「这个词」类提示，说明在讨论词本身。
META_BEFORE_MARKERS: tuple[str, ...] = (
    "这个词",
    "这个字",
    "这两个字",
    "这种说法",
    "这个词眼",
    "所谓",
    "所谓的",
    "叫做",
    "称为",
    "引自",
    "字面意思",
    "字眼",
    "术语",
)

_META_NOUN_RE = re.compile(
    r"^[\s，,、]*(?:这个|那两?个|这种|那种)?(?:词|字|说法|概念|定义|表达|词汇|字眼)"
)
_META_JUDGEMENT_RE = re.compile(
    r"^[\s，,、]*(?:太|很|有点|有些|过于|挺|真)[\s]*"
    r"(?:重|轻|吓人|笼统|抽象|夸张|绝对|刺眼|难听|生硬|正式|严重)"
)

#: 转述标记：仅用于结果留痕，不参与过滤（转述的危机表达仍需人工核实）。
_REPORTED_SPEECH_RE = re.compile(
    r"(?:他|她|他们|她们|有人|朋友|同学|家人|医生|咨询师|同事|室友|网友|书上|网上)?"
    r"(?:说|讲|写|问|告诉|提到|留言|发消息说)"
)

_NEGATION_RE = re.compile("|".join(re.escape(m) for m in NEGATION_MARKERS))

_FIRST_PERSON_MARKERS: tuple[str, ...] = ("我", "本人")
_THIRD_PERSON_MARKERS: tuple[str, ...] = (
    "他们",
    "她们",
    "他",
    "她",
    "朋友",
    "同学",
    "室友",
    "同事",
    "家人",
    "妈妈",
    "爸爸",
    "父母",
    "老师",
    "别人",
    "对方",
    # 第三方消息源：新闻里 / 有人 / 网上等，不能因句中转述而升级本人风险。
    "有人",
    "某人",
    "新闻",
    "报道",
    "网上",
    "电视",
    "微博",
    "热搜",
    "文章",
    "帖子",
    "群里",
    "班群",
)

#: 「我朋友 / 我的同学 / 我妈妈说」里的「我」是第三方领属，不是本人主语。
_THIRD_PARTY_POSSESSIVE_RE = re.compile(
    r"我(?:的)?"
    r"(?:朋友|同学|室友|同事|家人|妈妈|爸爸|父母|老师|亲戚|"
    r"男朋友|女朋友|男友|女友|老公|老婆|孩子|邻居|网友|"
    r"医生|咨询师|导师|领导|老板|哥哥|姐姐|弟弟|妹妹|"
    r"爷爷|奶奶|外公|外婆|表哥|表姐|表弟|表妹)"
)

_NEGATION_WINDOW = 8
_META_AFTER_QUOTE_WINDOW = 12
_META_BEFORE_WINDOW = 12
_META_AFTER_UNQUOTED_WINDOW = 4
_REPORTED_SPEECH_WINDOW = 12
_THIRD_PERSON_WINDOW = 30


@dataclass(frozen=True)
class MatchContext:
    """一处关键词命中的上下文裁定结果。"""

    in_quote: bool
    quote_text: str | None
    negated: bool
    negation_marker: str | None
    meta_mention: bool
    meta_marker: str | None
    reported_speech: bool

    @property
    def suppressed(self) -> bool:
        return self.negated or self.meta_mention

    @property
    def suppress_reason(self) -> str | None:
        if self.negated:
            return "negated"
        if self.meta_mention:
            return "meta_mention"
        return None


def _clause_prefix(text: str, start: int, window: int) -> str:
    prefix = text[max(0, start - window) : start]
    cut = max((prefix.rfind(delim) for delim in CLAUSE_DELIMITERS), default=-1)
    return prefix[cut + 1 :] if cut >= 0 else prefix


def _find_quote_span(text: str, start: int, end: int) -> tuple[int, int] | None:
    """返回包住 [start, end) 的最内层引号区间，找不到返回 None。"""
    best: tuple[int, int] | None = None
    for open_q, close_q in QUOTE_PAIRS:
        if open_q == close_q:
            positions = [i for i, ch in enumerate(text) if ch == open_q]
            for left, right in zip(positions[0::2], positions[1::2]):
                if left < start and end <= right and (best is None or left > best[0]):
                    best = (left, right)
            continue
        open_idx = text.rfind(open_q, 0, start)
        while open_idx != -1:
            if text.find(close_q, open_idx + 1, start) != -1:
                break
            close_idx = text.find(close_q, end)
            if close_idx != -1 and (best is None or open_idx > best[0]):
                best = (open_idx, close_idx)
            break
    return best


def _detect_negation(text: str, start: int) -> str | None:
    prefix = _clause_prefix(text, start, _NEGATION_WINDOW)
    if any(marker in prefix for marker in DOUBLE_NEGATION_SUFFIXES):
        return None
    match = _NEGATION_RE.search(prefix)
    if match:
        return match.group(0)
    if prefix.rstrip().endswith("不"):
        return "不"
    return None


def _detect_meta(
    text: str, start: int, end: int, quote_span: tuple[int, int] | None
) -> str | None:
    if quote_span is not None:
        quote_open, quote_close = quote_span
        before = text[max(0, quote_open - _META_BEFORE_WINDOW) : quote_open]
        for marker in META_BEFORE_MARKERS:
            if marker in before:
                return marker
        after = text[quote_close + 1 : quote_close + 1 + _META_AFTER_QUOTE_WINDOW]
        for pattern in (_META_NOUN_RE, _META_JUDGEMENT_RE):
            match = pattern.match(after)
            if match:
                return match.group(0).strip()
        return None

    after = text[end : end + _META_AFTER_UNQUOTED_WINDOW]
    match = _META_NOUN_RE.match(after)
    if match:
        return match.group(0).strip()
    before = text[max(0, start - _META_BEFORE_WINDOW) : start]
    for marker in META_BEFORE_MARKERS:
        if marker in before:
            return marker
    return None


def analyze_match_context(text: str, start: int, end: int) -> MatchContext:
    """裁定 text[start:end] 这一处关键词命中是否应被上下文过滤。"""
    quote_span = _find_quote_span(text, start, end)
    quote_text = text[quote_span[0] : quote_span[1] + 1] if quote_span else None

    negation_marker = _detect_negation(text, start)
    meta_marker = _detect_meta(text, start, end, quote_span)

    toward = text[max(0, start - _REPORTED_SPEECH_WINDOW) : start]
    if quote_span is not None:
        toward = text[max(0, quote_span[0] - _REPORTED_SPEECH_WINDOW) : quote_span[0]]
    reported_speech = bool(_REPORTED_SPEECH_RE.search(toward))

    return MatchContext(
        in_quote=quote_span is not None,
        quote_text=quote_text,
        negated=negation_marker is not None,
        negation_marker=negation_marker,
        meta_mention=meta_marker is not None,
        meta_marker=meta_marker,
        reported_speech=reported_speech,
    )


def _last_self_first_person_index(text: str) -> int:
    """返回最后一个「本人主语」第一人称的位置，找不到为 -1。

    排除两类伪第一人称：

    - 「自我了断」「自我伤害」里的「我」；
    - 「我朋友 / 我的同学 / 我妈妈说」里的领属「我」（第三方主语）。
    """
    last = -1
    search_from = 0
    while True:
        index = text.find("我", search_from)
        if index < 0:
            break
        search_from = index + 1
        if index > 0 and text[index - 1] == "自":
            continue
        if _THIRD_PARTY_POSSESSIVE_RE.match(text, index):
            continue
        last = index
    if "本人" in text:
        last = max(last, text.rfind("本人"))
    return last


def has_first_person_marker(text: str) -> bool:
    """文本中是否存在本人第一人称表述。

    D4 口径：第三人称 / 引用 / 词语元讨论默认只记录不升级，但**文本同时含
    第一人称表述时按本人处理**，不得因前文出现「他/朋友」而漏掉本人风险。
    「我朋友说…」的领属「我」不算本人第一人称。
    """
    return _last_self_first_person_index(text) >= 0


def _sentence_prefix(text: str, start: int, window: int) -> str:
    """取命中词之前、同一句内的窗口；不按逗号截断，便于继承前一分句的主语。"""
    prefix = text[max(0, start - window) : start]
    cut = max((prefix.rfind(delim) for delim in "。！？!?\n\r"), default=-1)
    return prefix[cut + 1 :] if cut >= 0 else prefix


def is_third_person_clause(text: str, start: int, window: int = _THIRD_PERSON_WINDOW) -> bool:
    """命中词所在分句的主语是否明显是第三人称。

    只用于「症状描述」的归属判断：``我朋友最近很难受`` 不应记为用户症状；
    ``朋友说我很难受`` 中离命中词最近的主语是「我」，仍算用户症状。
    """
    prefix = _sentence_prefix(text, start, window)
    last_first = _last_self_first_person_index(prefix)
    last_third = max((prefix.rfind(marker) for marker in _THIRD_PERSON_MARKERS), default=-1)
    return last_third > last_first and last_third >= 0
