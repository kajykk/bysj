"""Tests for ModelPredictService."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.services.model_predict_service import ModelPredictService, ModelExperimentService


class TestModelPredictService:
    """Test model predict service."""

    def test_get_model_status(self):
        """TC-COV-MPD-001: Get model status."""
        service = ModelPredictService()
        result = service.get_model_status()
        assert "items" in result
        assert "ready" in result
        assert "performance" in result
        assert "performance_summary" in result
        assert isinstance(result["items"], list)

    def test_get_training_job_not_found(self):
        """TC-COV-MPD-002: Get non-existent training job."""
        service = ModelPredictService()
        result = service.get_training_job("nonexistent")
        assert result["status"] == "not_found"

    def test_list_training_jobs_empty(self):
        """TC-COV-MPD-003: List training jobs when empty."""
        service = ModelPredictService()
        result = service.list_training_jobs()
        assert isinstance(result, list)

    @pytest.mark.asyncio
    async def test_predict_tabular(self):
        """TC-COV-MPD-004: Predict tabular data."""
        service = ModelPredictService()
        with patch("app.services.model_predict_service.model_engine") as mock_engine:
            mock_engine.predict_structured = AsyncMock(return_value={
                "prediction": 1,
                "probability": 0.85,
                "risk_score": 85.0,
            })
            result = await service.predict_tabular({"feature1": 1.0, "feature2": 2})
            assert "prediction" in result

    @pytest.mark.asyncio
    async def test_predict_text(self):
        """TC-COV-MPD-005: Predict text data."""
        service = ModelPredictService()
        with patch("app.services.model_predict_service.model_engine") as mock_engine:
            mock_engine.predict_text = AsyncMock(return_value={
                "sentiment_score": 0.2,
                "sentiment_label": "negative",
            })
            result = await service.predict_text("I feel sad today")
            assert "sentiment_score" in result

    @pytest.mark.asyncio
    async def test_predict_physiological(self):
        """TC-COV-MPD-006: Predict physiological data."""
        service = ModelPredictService()
        with patch("app.services.model_predict_service.model_engine") as mock_engine:
            mock_engine.predict_physiological = AsyncMock(return_value={
                "prediction": 1,
                "probability": 0.75,
            })
            result = await service.predict_physiological({"heart_rate": 80, "sleep_hours": 6})
            assert "prediction" in result

    @pytest.mark.asyncio
    async def test_predict_fusion(self):
        """TC-COV-MPD-007: Predict fusion data."""
        service = ModelPredictService()
        with patch("app.services.model_predict_service.model_engine") as mock_engine:
            mock_engine.predict_fusion = AsyncMock(return_value={
                "prediction": 1,
                "probability": 0.9,
                "risk_score": 90.0,
            })
            result = await service.predict_fusion(
                features={"feature1": 1.0},
                text="I feel sad",
                physiological={"heart_rate": 80},
            )
            assert "prediction" in result

    @pytest.mark.asyncio
    async def test_predict_fusion_partial(self):
        """TC-COV-MPD-008: Predict fusion with partial data."""
        service = ModelPredictService()
        with patch("app.services.model_predict_service.model_engine") as mock_engine:
            mock_engine.predict_fusion = AsyncMock(return_value={
                "prediction": 1,
                "probability": 0.8,
            })
            result = await service.predict_fusion(text="I feel sad")
            assert "prediction" in result


class TestModelExperimentService:
    """Test model experiment service."""

    def test_compare_empty_models(self):
        """TC-COV-MPD-009: Compare with empty model names raises error."""
        service = ModelExperimentService()
        with pytest.raises(ValueError, match="model_names 不能为空"):
            service.compare("dataset", [])
