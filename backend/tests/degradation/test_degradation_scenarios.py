"""Degradation scenario tests for model fallback resilience.

Tests the system's ability to gracefully degrade when:
- Primary models are unavailable
- Dependencies are missing
- Inputs are malformed
- Services timeout
"""

from __future__ import annotations

import json
import time
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from app.core.fallback_hierarchy import FallbackExhaustedError, FallbackHierarchy
from app.core.model_engine import ModelEngine
from app.services.input_validator import InputValidator

pytestmark = pytest.mark.degradation


class TestModelDegradation:
    """Test model fallback under various degradation scenarios."""

    @pytest.mark.asyncio
    async def test_primary_model_missing_fallback_to_heuristic(self) -> None:
        """TC-DEG-HP-001: When primary model file is missing, fallback to heuristic (v1.31: async)."""
        engine = ModelEngine()

        # Mock model path to non-existent file
        with patch("app.core.model_engine.MODEL_PATHS", {
            "structured_logistic_regression_quick": Path("/nonexistent/model.pkl")
        }):
            result = await engine.predict_structured({
                "sleep_hours": 5.0,
                "exercise_minutes": 10.0,
                "heart_rate_avg": 85.0,
            })

        # Should still return a result via heuristic fallback
        assert "risk_score" in result
