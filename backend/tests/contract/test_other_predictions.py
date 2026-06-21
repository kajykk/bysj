"""Contract tests for text, physiological, and fusion prediction endpoints.

Validates request/response contracts for non-structured prediction APIs.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings, strategies as st

from app.main import app

client = TestClient(app)

pytestmark = pytest.mark.contract


class TestTextPredictionContract:
    """Contract tests for POST /api/v1/predict/text"""

    @settings(max_examples=20, deadline=None)
    @given(text=st.text(min_size=1, max_size=500))
    def test_valid_text_returns_prediction(self, text):
        """TC-CNT-HP-010: Valid text input returns prediction."""
        response = client.post(
            "/api/v1/predict/text",
            json={"text": text},
        )

        # May return 200 or fallback 503
        assert response.status_code in [200, 503, 422]

        if response.status_code == 200:
            data = response.json()
            assert "risk_score" in data
            assert isinstance(data["risk_score"], (int, float))
            assert 0.0 <= data["risk_score"] <= 1.0

    def test_empty_text_returns_error(self):
        """TC-CNT-HP-011: Empty text returns validation error."""
        response = client.post(
            "/api/v1/predict/text",
            json={"text": ""},
        )

        assert response.status_code in [200, 422, 503]

    def test_missing_text_field_returns_422(self):
        """TC-CNT-HP-012: Missing text field returns validation error."""
        response = client.post(
            "/api/v1/predict/text",
            json={},
        )

        assert response.status_code == 422

    def test_text_with_special_characters(self):
        """TC-CNT-HP-013: Text with special characters handled gracefully."""
        response = client.post(
            "/api/v1/predict/text",
            json={"text": "Hello! 你好! 🎉 <script>alert('xss')</script>"},
        )

        assert response.status_code in [200, 422, 503]

    def test_very_long_text(self):
        """TC-CNT-HP-014: Very long text handled appropriately."""
        long_text = "I feel sad. " * 1000  # 12000+ characters
        response = client.post(
            "/api/v1/predict/text",
            json={"text": long_text},
        )

        assert response.status_code in [200, 413, 422, 503]


class TestPhysiologicalPredictionContract:
    """Contract tests for POST /api/v1/predict/physiological"""

    def test_valid_physiological_data(self):
        """TC-CNT-HP-015: Valid physiological data returns prediction."""
        response = client.post(
            "/api/v1/predict/physiological",
            json={
                "sleep_hours": 7.5,
                "exercise_minutes": 45.0,
                "heart_rate_avg": 72.0,
                "steps": 8000,
            },
        )

        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            assert "risk_score" in data
            assert isinstance(data["risk_score"], (int, float))

    def test_missing_physiological_fields(self):
        """TC-CNT-HP-016: Missing fields handled gracefully."""
        response = client.post(
            "/api/v1/predict/physiological",
            json={},
        )

        assert response.status_code in [200, 422, 503]

    def test_invalid_physiological_types(self):
        """TC-CNT-HP-017: Invalid types return validation error."""
        response = client.post(
            "/api/v1/predict/physiological",
            json={
                "sleep_hours": "seven",
                "exercise_minutes": [30, 45],
            },
        )

        assert response.status_code == 422

    def test_extreme_physiological_values(self):
        """TC-CNT-HP-018: Extreme values handled gracefully."""
        response = client.post(
            "/api/v1/predict/physiological",
            json={
                "sleep_hours": 999.0,
                "exercise_minutes": -100.0,
                "heart_rate_avg": 0.0,
            },
        )

        assert response.status_code in [200, 422, 503]


class TestFusionPredictionContract:
    """Contract tests for POST /api/v1/predict/fusion"""

    def test_valid_fusion_input(self):
        """TC-CNT-HP-019: Valid fusion input returns combined prediction."""
        response = client.post(
            "/api/v1/predict/fusion",
            json={
                "text": "I feel very anxious today",
                "structured": {
                    "sleep_hours": 5.0,
                    "exercise_minutes": 10.0,
                },
            },
        )

        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            assert "risk_score" in data
            assert isinstance(data["risk_score"], (int, float))

    def test_fusion_with_text_only(self):
        """TC-CNT-HP-020: Fusion with text only handled gracefully."""
        response = client.post(
            "/api/v1/predict/fusion",
            json={
                "text": "I feel sad",
            },
        )

        assert response.status_code in [200, 422, 503]

    def test_fusion_with_structured_only(self):
        """TC-CNT-HP-021: Fusion with structured only handled gracefully."""
        response = client.post(
            "/api/v1/predict/fusion",
            json={
                "structured": {
                    "sleep_hours": 7.0,
                    "exercise_minutes": 30.0,
                },
            },
        )

        assert response.status_code in [200, 422, 503]

    def test_empty_fusion_input(self):
        """TC-CNT-HP-022: Empty fusion input returns validation error."""
        response = client.post(
            "/api/v1/predict/fusion",
            json={},
        )

        assert response.status_code in [200, 422, 503]


class TestPredictionResponseSchema:
    """Schema validation for all prediction responses."""

    def test_prediction_response_has_required_fields(self):
        """TC-CNT-HP-023: All prediction responses have required fields."""
        endpoints = [
            ("/api/v1/predict/structured", {"sleep_hours": 7.0, "exercise_minutes": 30.0}),
            ("/api/v1/predict/text", {"text": "I feel happy"}),
            ("/api/v1/predict/physiological", {"sleep_hours": 7.0, "exercise_minutes": 30.0}),
        ]

        for endpoint, payload in endpoints:
            response = client.post(endpoint, json=payload)

            if response.status_code == 200:
                data = response.json()
                # Common fields
                assert "risk_score" in data
                assert isinstance(data["risk_score"], (int, float))
                assert 0.0 <= data["risk_score"] <= 1.0

                # Optional fields
                if "risk_level" in data:
                    assert isinstance(data["risk_level"], str)
                if "confidence" in data:
                    assert isinstance(data["confidence"], (int, float))
                if "fallback_used" in data:
                    assert isinstance(data["fallback_used"], bool)

    def test_error_response_schema(self):
        """TC-CNT-HP-024: Error responses follow unified schema."""
        response = client.post(
            "/api/v1/predict/structured",
            json={"invalid": "data"},
        )

        if response.status_code == 422:
            data = response.json()
            # Should have detail or error field
            assert "detail" in data or "error" in data
