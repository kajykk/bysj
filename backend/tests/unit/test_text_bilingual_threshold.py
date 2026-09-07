from __future__ import annotations

import asyncio
from unittest.mock import patch

import pytest

from app.core.config import settings
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
            with patch("app.core.model_engine.predict._contains_cjk", return_value=False):
                with patch(
                    "app.core.model_engine.predict.settings.text_bilingual_decision_threshold",
                    0.30,
                ):
                    result = self._run(engine._predict_text_ml("I feel awful and hopeless"))

        assert result["model_used"] == "text_improved_bilingual_model"
        assert result["probability"] == 0.29
        assert result["prediction"] == 0
        assert result["sentiment_label"] == "positive"

        async def _load_high(model_id: str):
            if model_id == "text_improved_bilingual_tfidf":
                return _DummyVectorizer()
            if model_id == "text_improved_bilingual_model":
                return _DummyBinaryModel(0.31, pred=0)
            raise FileNotFoundError(model_id)

        with patch.object(engine, "_load_model_async", side_effect=_load_high):
            with patch("app.core.model_engine.predict._contains_cjk", return_value=False):
                with patch(
                    "app.core.model_engine.predict.settings.text_bilingual_decision_threshold",
                    0.30,
                ):
                    result = self._run(engine._predict_text_ml("I feel awful and hopeless"))

        assert result["prediction"] == 1
        assert result["sentiment_label"] == "negative"
        assert result["probability"] == 0.31

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
            with patch("app.core.model_engine.predict._contains_cjk", return_value=False):
                result = self._run(engine._predict_text_ml("I feel awful and hopeless"))

        assert result["model_used"] == "text_depression_model"
        assert result["prediction"] == 1
        assert result["probability"] == 0.92
        assert result["sentiment_label"] == "negative"
