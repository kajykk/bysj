from __future__ import annotations

import pytest

from app.core.model_engine.text_chunking import (
    DEFAULT_CHUNK_SIZE,
    aggregate_chunk_probabilities,
    split_text_chunks,
)


def _long_text(sentences: int = 10, sentence_len: int = 120) -> str:
    # 每句以句号结尾，模拟中文长文本；句子长度大于 _BOUNDARY_LOOKBACK，
    # 保证切块时确实要靠句界回退，而不是恰好整除。
    return "".join("a" * (sentence_len - 1) + "。" for _ in range(sentences))


class TestSplitTextChunks:
    def test_short_text_single_chunk(self):
        text = "今天心情不太好。"
        chunks = split_text_chunks(text)
        assert len(chunks) == 1
        assert chunks[0].text == text
        assert chunks[0].start == 0
        assert chunks[0].end == len(text)

    def test_empty_text_returns_no_chunks(self):
        assert split_text_chunks("") == []
        assert split_text_chunks("   \n\t ") == []

    def test_long_text_is_chunked_with_bounds_and_overlap(self):
        text = _long_text()
        chunks = split_text_chunks(text)

        assert len(chunks) > 1
        assert chunks[0].start == 0
        assert chunks[-1].end == len(text)
        for chunk in chunks:
            assert 0 < len(chunk.text) <= DEFAULT_CHUNK_SIZE
            assert text[chunk.start : chunk.end].strip() == chunk.text
        for previous, current in zip(chunks, chunks[1:]):
            # 相邻块必须有重叠，且没有跳过任何字符
            assert current.start < previous.end
            assert current.start > previous.start

    def test_chunks_prefer_sentence_boundary(self):
        text = _long_text()
        chunks = split_text_chunks(text)
        # 除最后一块外，块文本应以句读结尾（回退到最近的句界）
        for chunk in chunks[:-1]:
            assert chunk.text.endswith("。")

    def test_text_without_delimiters_is_split_by_length(self):
        text = "a" * 1300
        chunks = split_text_chunks(text)
        assert len(chunks) >= 3
        assert all(len(chunk.text) <= DEFAULT_CHUNK_SIZE for chunk in chunks)
        assert chunks[-1].end == len(text)

    @pytest.mark.parametrize(
        ("chunk_size", "overlap"),
        [(0, 0), (-1, 0), (100, 100), (100, 120), (100, -1)],
    )
    def test_invalid_parameters_rejected(self, chunk_size: int, overlap: int):
        with pytest.raises(ValueError):
            split_text_chunks("abc", chunk_size=chunk_size, overlap=overlap)


class TestAggregateChunkProbabilities:
    def test_max_is_used_not_mean(self):
        # 平均分会把 0.9 稀释成 0.5；风险筛查必须保留最高块。
        assert aggregate_chunk_probabilities([0.1, 0.9, 0.5]) == 0.9

    def test_single_value(self):
        assert aggregate_chunk_probabilities([0.37]) == 0.37

    def test_empty_rejected(self):
        with pytest.raises(ValueError):
            aggregate_chunk_probabilities([])
