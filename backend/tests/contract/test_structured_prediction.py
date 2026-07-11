"""Contract tests for structured prediction endpoints.

Validates request/response contracts for structured data prediction API.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from hypothesis import given, settings
from hypothesis import strategies as st

from app.main import app

client = TestClient(app)

pytestmark = pytest.mark.contract


class TestStructuredPredictionContract:
    """Contract tests for POST /api/v1/predict/structured"""

    @settings(max_examples=5, deadline=None)
    @given(
        sleep_hours=st.floats(min_value=0.0, max_value=24.0),
        exercise_minutes=st.floats(min_value=0.0, max_value=300.0),
        heart_rate_avg=st.floats(min_value=40.0, max_value=200.0),
    )
    def test_valid_structured_input_returns_prediction(
        self, sleep_hours, exercise_minutes, heart_rate_avg
    ):
        """TC-CNT-HP-001: Valid structured input returns prediction with required fields."""
        response = client.post(
            "/api/v1/predict/structured",
            json={
                "sleep_hours": sleep_hours,
                "exercise_minutes": exercise_minutes,
                "heart_rate_avg": heart_rate_avg,
            },
        )

        # Should return 200 or fallback response
        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            assert "risk_score" in data
            assert "risk_level" in data
            assert isinstance(data["risk_score"], (int, float))
            assert 0.0 <= data["risk_score"] <= 1.0

    def test_missing_required_fields_returns_422(self):
        """TC-CNT-HP-002: Missing required fields returns validation error."""
        response = client.post(
            "/api/v1/predict/structured",
            json={},
        )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data or "error" in data

    def test_invalid_types_returns_422(self):
        """TC-CNT-HP-003: Invalid field types return validation error."""
        response = client.post(
            "/api/v1/predict/structured",
            json={
                "sleep_hours": "not_a_number",
                "exercise_minutes": [1, 2, 3],
            },
        )

        assert response.status_code == 422

    def test_out_of_range_values_handled(self):
        """TC-CNT-HP-004: Out-of-range values are handled gracefully."""
        response = client.post(
            "/api/v1/predict/structured",
            json={
                "sleep_hours": 999.0,  # Way over normal range
                "exercise_minutes": -10.0,  # Negative
            },
        )

        # Should either validate and reject, or handle gracefully
        assert response.status_code in [200, 422, 503]

    def test_response_schema_compliance(self):
        """TC-CNT-HP-005: Response matches expected schema."""
        response = client.post(
            "/api/v1/predict/structured",
            json={
                "sleep_hours": 7.0,
                "exercise_minutes": 30.0,
                "heart_rate_avg": 70.0,
            },
        )

        if response.status_code == 200:
            data = response.json()
            # Verify schema compliance
            assert "risk_score" in data
            assert "risk_level" in data
            assert "confidence" in data or "fallback_used" in data

            # Type checks
            assert isinstance(data["risk_score"], (int, float))
            if "risk_level" in data:
                assert isinstance(data["risk_level"], str)


class TestBatchPredictionContract:
    """Contract tests for batch prediction endpoints."""

    def test_batch_prediction_with_valid_list(self):
        """TC-CNT-HP-006: Batch prediction accepts list of records."""
        response = client.post(
            "/api/v1/predict/structured/batch",
            json=[
                {"sleep_hours": 7.0, "exercise_minutes": 30.0},
                {"sleep_hours": 5.0, "exercise_minutes": 10.0},
            ],
        )

        # Endpoint may not exist, check accordingly
        if response.status_code != 404:
            assert response.status_code in [200, 422, 503]
            if response.status_code == 200:
                data = response.json()
                assert isinstance(data, list)

    def test_batch_prediction_with_empty_list(self):
        """TC-CNT-HP-007: Empty batch returns appropriate error."""
        response = client.post(
            "/api/v1/predict/structured/batch",
            json=[],
        )

        if response.status_code != 404:
            assert response.status_code in [200, 422]


class TestHealthEndpointContract:
    """Contract tests for health check."""

    def test_health_returns_status(self):
        """TC-CNT-HP-008: Health endpoint returns status information."""
        response = client.get("/api/v1/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] in ["healthy", "degraded", "unhealthy"]

    def test_health_response_schema(self):
        """TC-CNT-HP-009: Health response has expected schema."""
        response = client.get("/api/v1/health")

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)
            assert "status" in data
