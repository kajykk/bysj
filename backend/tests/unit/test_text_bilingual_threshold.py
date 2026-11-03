from __future__ import annotations

import asyncio
import math
from unittest.mock import patch

import pytest

from app.core.config import settings
from app.core.ml_decision_thresholds import TEXT_DECISION_THRESHOLD_SOURCE
from app.core.model_engine import ModelEngine


class _DummyVectorizer:
    def transform(self, texts):
        return [[0.0]]


class _DummyBinaryModel:
    def __init__(self, prob: float, pred: int | None = None):
        self._prob = prob
        self._pred = int(pred if pred is not None else (prob >= 0.5))

    def predict_proba(self, vector):
        return [[1 - self._prob, self._prob]]

    def predict(self, vector):
        return [self._pred]


class _PerRowVectorizer:
    """每行返回一个特征，保证分块后每块的推理互不影响。"""

    def transform(self, texts):
        return [[1.0] for _ in texts]


class _PerRowModel:
    """按行序号返回预设概率，用于验证聚合口径而不是具体文本。"""

    def __init__(self, probabilities: list[float]):
        self._probabilities = probabilities

    def predict_proba(self, vector):
        rows = []
        for index in range(len(vector)):
            prob = self._probabilities[index]
            rows.append([1 - prob, prob])
        return rows

    def predict(self, vector):
        return [1 if self._probabilities[i] >= 0.5 else 0 for i in range(len(vector))]


def _long_text(sentences: int = 10, sentence_len: int = 120) -> str:
    return "".join("a" * (sentence_len - 1) + "。" for _ in range(sentences))


class TestBilingualTextThreshold:
    @pytest.fixture
    def engine(self) -> ModelEngine:
        return ModelEngine()

    def _run(self, coro):
        return asyncio.run(coro)

    def test_default_threshold_is_030(self):
        assert settings.text_bilingual_decision_threshold == 0.30

    def test_bilingual_prediction_respects_config_threshold(self, engine: ModelEngine):
        async def _load(model_id: str):
            if model_id == "text_improved_bilingual_tfidf":
                return _DummyVectorizer()
            if model_id == "text_improved_bilingual_model":
                return _DummyBinaryModel(0.29, pred=1)
            raise FileNotFoundError(model_id)

        with patch.object(engine, "_load_model_async", side_effect=_load):
            with patch(
                "app.core.model_engine.predict.settings.text_bilingual_decision_threshold",
                0.30,
            ):
                result = self._run(engine._predict_text_ml("I feel awful and hopeless"))

        assert result["model_used"] == "text_improved_bilingual_model"
        assert result["probability"] == 0.29
        assert result["prediction"] == 0
        assert result["sentiment_label"] == "positive"

        async def _load_suspect(model_id: str):
            if model_id == "text_improved_bilingual_tfidf":
                return _DummyVectorizer()
            if model_id == "text_improved_bilingual_model":
                return _DummyBinaryModel(0.31, pred=0)
            raise FileNotFoundError(model_id)

        with patch.object(engine, "_load_model_async", side_effect=_load_suspect):
            with patch(
                "app.core.model_engine.predict.settings.text_bilingual_decision_threshold",
                0.30,
            ):
                result = self._run(engine._predict_text_ml("I feel awful and hopeless"))

        # D2：0.30–0.55 属于「疑似需复核」，不直接判高风险（prediction=0）。
        assert result["prediction"] == 0
        assert result["sentiment_label"] == "positive"
        assert result["probability"] == 0.31
        assert result["text_decision_state"] == "suspect"
        assert result["text_decision_thresholds"] == {
            "suspect_lower": 0.30,
            "high_upper": 0.55,
            "source": TEXT_DECISION_THRESHOLD_SOURCE,
        }

        async def _load_high(model_id: str):
            if model_id == "text_improved_bilingual_tfidf":
                return _DummyVectorizer()
            if model_id == "text_improved_bilingual_model":
                return _DummyBinaryModel(0.56, pred=0)
            raise FileNotFoundError(model_id)

        with patch.object(engine, "_load_model_async", side_effect=_load_high):
            with patch(
                "app.core.model_engine.predict.settings.text_bilingual_decision_threshold",
                0.30,
            ):
                result = self._run(engine._predict_text_ml("I feel awful and hopeless"))

        # D2：>0.55 才直接判高风险。
        assert result["prediction"] == 1
        assert result["sentiment_label"] == "negative"
        assert result["probability"] == 0.56
        assert result["text_decision_state"] == "high_risk"

    def test_bilingual_model_missing_falls_back_to_english_model(self, engine: ModelEngine):
        async def _load(model_id: str):
            if model_id in {"text_improved_bilingual_tfidf", "text_improved_bilingual_model"}:
                raise FileNotFoundError(model_id)
            if model_id == "text_depression_tfidf":
                return _DummyVectorizer()
            if model_id == "text_depression_model":
                return _DummyBinaryModel(0.92, pred=1)
            raise FileNotFoundError(model_id)

        with patch.object(engine, "_load_model_async", side_effect=_load):
            result = self._run(engine._predict_text_ml("I feel awful and hopeless"))

        assert result["model_used"] == "text_depression_model"
        assert result["prediction"] == 1
        assert result["probability"] == 0.92
        assert result["sentiment_label"] == "negative"

    def test_long_text_is_chunked_and_aggregated_by_max(self, engine: ModelEngine):
        """P2：长文本逐块推理，风险集中在一段时不能被其余段落稀释。"""
        model = _PerRowModel([0.85, 0.05, 0.05])

        async def _load(model_id: str):
            if model_id == "text_improved_bilingual_tfidf":
                return _PerRowVectorizer()
            if model_id == "text_improved_bilingual_model":
                return model
            raise FileNotFoundError(model_id)

        with patch.object(engine, "_load_model_async", side_effect=_load):
            with patch(
                "app.core.model_engine.predict.settings.text_bilingual_decision_threshold",
                0.30,
            ):
                result = self._run(engine._predict_text_ml(_long_text()))

        assert result["model_used"] == "text_improved_bilingual_model"
        assert result["probability"] == 0.85
        assert result["prediction"] == 1
        assert result["sentiment_label"] == "negative"
        info = result["chunk_info"]
        assert info["chunk_count"] == 3
        assert info["aggregation"] == "max"
        assert info["chunk_probabilities"] == [0.85, 0.05, 0.05]
        assert len(info["chunk_offsets"]) == 3
        # 平均分是 0.3167，仍在阈值之上；换成分块口径后应取最高块 0.85
        assert result["probability"] != pytest.approx(sum([0.85, 0.05, 0.05]) / 3)

    def test_long_text_primary_model_any_positive_chunk_wins(self, engine: ModelEngine):
        model = _PerRowModel([0.05, 0.9, 0.05])

        async def _load(model_id: str):
            if model_id in {"text_improved_bilingual_tfidf", "text_improved_bilingual_model"}:
                raise FileNotFoundError(model_id)
            if model_id == "text_depression_tfidf":
                return _PerRowVectorizer()
            if model_id == "text_depression_model":
                return model
            raise FileNotFoundError(model_id)

        with patch.object(engine, "_load_model_async", side_effect=_load):
            result = self._run(engine._predict_text_ml(_long_text()))

        assert result["model_used"] == "text_depression_model"
        assert result["probability"] == 0.9
        assert result["prediction"] == 1
        assert result["chunk_info"]["chunk_count"] == 3

    def test_short_text_has_no_chunk_info(self, engine: ModelEngine):
        model = _PerRowModel([0.2])

        async def _load(model_id: str):
            if model_id == "text_improved_bilingual_tfidf":
                return _PerRowVectorizer()
            if model_id == "text_improved_bilingual_model":
                return model
            raise FileNotFoundError(model_id)

        with patch.object(engine, "_load_model_async", side_effect=_load):
            result = self._run(engine._predict_text_ml("我最近有点累"))

        assert result["probability"] == 0.2
        assert result["prediction"] == 0
        assert "chunk_info" not in result

    def test_non_finite_chunk_probability_falls_back(self, engine: ModelEngine):
        """任一块产出 NaN 都代表模型失效，整段回退启发式，不得静默取其余块。"""
        model = _PerRowModel([0.1, float("nan"), 0.1])

        async def _load(model_id: str):
            if model_id == "text_improved_bilingual_tfidf":
                return _PerRowVectorizer()
            if model_id == "text_improved_bilingual_model":
                return model
            raise FileNotFoundError(model_id)

        with patch.object(engine, "_load_model_async", side_effect=_load):
            result = self._run(engine._predict_text_ml(_long_text()))

        assert result["model_used"] == "text_heuristic_fallback"
        assert result["fallback_used"] is True
        assert result["ml_model_used"] == "text_improved_bilingual_model"
        assert "chunk_info" not in result
        assert math.isfinite(result["probability"])

    def test_english_fallback_suspect_requires_human_review(self, engine: ModelEngine):
        """英文回退模型自带 predict=1，也必须被三态收敛为 suspect（不判高风险）。

        回归背景：0.30/0.55 三态此前只覆盖双语主模型，降级到英文模型后
        走模型自带 ``predict`` 的两态，0.31 会被直接判为高风险，悄悄退回单阈值。
        """

        async def _load(model_id: str):
            if model_id in {
                "text_improved_bilingual_tfidf",
                "text_improved_bilingual_model",
            }:
                raise FileNotFoundError(model_id)
            if model_id == "text_depression_tfidf":
                return _DummyVectorizer()
            if model_id == "text_depression_model":
                return _DummyBinaryModel(0.31, pred=1)
            raise FileNotFoundError(model_id)

        with patch.object(engine, "_load_model_async", side_effect=_load):
            with patch(
                "app.core.model_engine.predict.settings.text_bilingual_decision_threshold",
                0.30,
            ):
                result = self._run(engine._predict_text_ml("I feel awful and hopeless"))

        assert result["model_used"] == "text_depression_model"
        assert result["text_decision_state"] == "suspect"
        assert result["prediction"] == 0, "疑似区间不得直接判高风险"
        assert result["requires_human_review"] is True
        assert result["review_reasons"] == ["text_suspect_probability"]
        assert result["text_decision_thresholds"] == {
            "suspect_lower": 0.30,
            "high_upper": 0.55,
            "source": TEXT_DECISION_THRESHOLD_SOURCE,
        }

    def test_english_fallback_high_risk_requires_human_review(self, engine: ModelEngine):
        """英文回退模型自带 predict=0，但概率 0.56 仍应判 high_risk。

        说明三态以「校准概率」为准，而不是模型自带的单阈值二态输出。
        """

        async def _load(model_id: str):
            if model_id in {
                "text_improved_bilingual_tfidf",
                "text_improved_bilingual_model",
            }:
                raise FileNotFoundError(model_id)
            if model_id == "text_depression_tfidf":
                return _DummyVectorizer()
            if model_id == "text_depression_model":
                return _DummyBinaryModel(0.56, pred=0)
            raise FileNotFoundError(model_id)

        with patch.object(engine, "_load_model_async", side_effect=_load):
            with patch(
                "app.core.model_engine.predict.settings.text_bilingual_decision_threshold",
                0.30,
            ):
                result = self._run(engine._predict_text_ml("I feel awful and hopeless"))

        assert result["text_decision_state"] == "high_risk"
        assert result["prediction"] == 1
        assert result["requires_human_review"] is True
        assert result["review_reasons"] == ["text_high_risk_probability"]

    def test_heuristic_fallback_also_emits_three_state(self, engine: ModelEngine):
        """所有模型都加载失败时，启发式回退同样必须带三态出口。"""

        async def _load(model_id: str):
            raise FileNotFoundError(model_id)

        with patch.object(engine, "_load_model_async", side_effect=_load):
            result = self._run(engine._predict_text_ml("最近压力有点大"))

        assert result["model_used"] == "text_heuristic_fallback"
        assert result["text_decision_state"] in {
            "normal",
            "suspect",
            "high_risk",
        }
        assert "requires_human_review" in result
        assert "text_decision_thresholds" in result
