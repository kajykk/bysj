"""长文本分块与聚合（P2）。

TF-IDF + LR 是词袋模型，输入越长，单个风险段落在向量里占比越小：一篇
1300 字的日记里只有一两句话在描述症状，整段送进模型时稀释后的概率可能
低于决策阈值，而这段文字本身是高风险证据。接口允许 5000 字（见
`TextPredictRequest`），模型训练语料却以短文本为主，因此按句子边界切成
不超过 500 字的重叠窗口，逐块推理后按 **max** 聚合：任一段高风险即视为
高风险（安全优先）。

max 聚合是刻意的取舍：平均分会把"一段高危 + 九段日常"稀释成中低风险，
这在风险筛查场景是危险的假阴性。块级概率与偏移一并返回，便于复核人员
定位触发段落。
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass

DEFAULT_CHUNK_SIZE = 500
DEFAULT_CHUNK_OVERLAP = 80
# 只在块尾附近回退找句界，避免把块切得过短。
_BOUNDARY_LOOKBACK = 120
_SENTENCE_DELIMITERS = "。！？!?；;\n\r"


@dataclass(frozen=True)
class TextChunk:
    index: int
    text: str
    start: int
    end: int


def split_text_chunks(
    text: str,
    *,
    chunk_size: int = DEFAULT_CHUNK_SIZE,
    overlap: int = DEFAULT_CHUNK_OVERLAP,
) -> list[TextChunk]:
    """把文本切成不超过 chunk_size 的重叠块（尽量落在句末）。

    不做语义切分，只保证：块长有上界、块间有重叠（跨块句子不会被拦腰截断
    而失去上下文）、单块文本非空。
    """
    if chunk_size <= 0:
        raise ValueError("chunk_size 必须为正整数")
    if overlap < 0 or overlap >= chunk_size:
        raise ValueError("overlap 必须满足 0 <= overlap < chunk_size")
    if not text:
        return []

    if len(text) <= chunk_size:
        stripped = text.strip()
        return [TextChunk(index=0, text=stripped, start=0, end=len(text))] if stripped else []

    chunks: list[TextChunk] = []
    length = len(text)
    pos = 0
    while pos < length:
        end = min(pos + chunk_size, length)
        if end < length:
            search_from = max(pos + chunk_size // 2, end - _BOUNDARY_LOOKBACK)
            boundary = -1
            for delimiter in _SENTENCE_DELIMITERS:
                found = text.rfind(delimiter, search_from, end)
                if found > boundary:
                    boundary = found
            if boundary >= search_from:
                end = boundary + 1

        chunk_text = text[pos:end].strip()
        if chunk_text:
            chunks.append(
                TextChunk(index=len(chunks), text=chunk_text, start=pos, end=end)
            )

        if end >= length:
            break
        next_pos = end - overlap
        if next_pos <= pos:
            next_pos = pos + 1
        while next_pos < end and text[next_pos].isspace():
            next_pos += 1
        pos = next_pos

    return chunks


def aggregate_chunk_probabilities(probabilities: Sequence[float]) -> float:
    """按 max 聚合块级风险概率（安全优先：任何一块高风险即高风险）。"""
    if not probabilities:
        raise ValueError("probabilities 不能为空")
    return max(probabilities)
