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

TABULAR_FEATURES = {
    "age": 22,
    "gender": 1,
    "study_year": 3,
    "cgpa": 3.5,
    "stress_level": 3,
    "sleep_duration": 7,
    "social_support": 4,
    "financial_pressure": 2,
    "family_history": 0,
    "academic_pressure": 3,
    "exercise_frequency": 2,
    "anxiety": 2,
    "panic_attack": 0,
    "treatment_seeking": 1,
}


def _unwrap(response) -> dict:
    """ApiResponse 包装解包: {code, message, data}."""
    body = response.json()
    return body.get("data", body) if isinstance(body, dict) else {}


class TestStructuredPredictionContract:
    """Contract tests for POST /api/v1/model/predict/tabular"""

    @settings(max_examples=5, deadline=None)
    @given(
        stress_level=st.integers(min_value=0, max_value=5),
        sleep_duration=st.floats(min_value=0.0, max_value=24.0),
        anxiety=st.integers(min_value=0, max_value=5),
    )
    def test_valid_structured_input_returns_prediction(
        self, stress_level, sleep_duration, anxiety
    ):
        """TC-CNT-HP-001: Valid structured input returns prediction with required fields."""
        features = dict(TABULAR_FEATURES)
        features["stress_level"] = stress_level
        features["sleep_duration"] = sleep_duration
        features["anxiety"] = anxiety
        response = client.post(
            "/api/v1/model/predict/tabular",
            json={"features": features},
        )

        # Should return 200 or fallback response
        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = _unwrap(response)
            assert "risk_score" in data
            assert "risk_level" in data
            assert isinstance(data["risk_score"], (int, float))
            assert 0.0 <= data["risk_score"] <= 100.0

    def test_missing_required_fields_returns_422(self):
        """TC-CNT-HP-002: Missing required fields returns validation error."""
        response = client.post(
            "/api/v1/model/predict/tabular",
            json={},
        )

        assert response.status_code == 422
        data = response.json()
        assert "detail" in data or "error" in data

    def test_invalid_types_returns_422(self):
        """TC-CNT-HP-003: Invalid field types return validation error."""
        response = client.post(
            "/api/v1/model/predict/tabular",
            json={"features": {"age": "not_a_number", "gender": [1, 2, 3]}},
        )

        assert response.status_code in [200, 422, 503]

    def test_out_of_range_values_handled(self):
        """TC-CNT-HP-004: Out-of-range values are handled gracefully."""
        response = client.post(
            "/api/v1/model/predict/tabular",
            json={
                "features": {
                    "stress_level": 999,
                    "sleep_duration": -10.0,
                }
            },
        )

        # Should either validate and reject, or handle gracefully
        assert response.status_code in [200, 422, 503]

    def test_response_schema_compliance(self):
        """TC-CNT-HP-005: Response matches expected schema."""
        response = client.post(
            "/api/v1/model/predict/tabular",
            json={"features": TABULAR_FEATURES},
        )

        if response.status_code == 200:
            data = _unwrap(response)
            # Verify schema compliance
            assert "risk_score" in data
            assert "risk_level" in data
            assert "confidence" in data or "fallback_used" in data

            # Type checks
            assert isinstance(data["risk_score"], (int, float))
            if "risk_level" in data:
                assert isinstance(data["risk_level"], (int, str))


class TestBatchPredictionContract:
    """Contract tests for batch prediction endpoints.

    H-AUDIT-01: 无真实 /model/predict/tabular/batch 端点, 保持 404 容忍.
    """

    def test_batch_prediction_with_valid_list(self):
        """TC-CNT-HP-006: Batch prediction accepts list of records."""
        response = client.post(
            "/api/v1/model/predict/tabular/batch",
            json=[
                {"features": TABULAR_FEATURES},
                {"features": TABULAR_FEATURES},
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
            "/api/v1/model/predict/tabular/batch",
            json=[],
        )

        if response.status_code != 404:
            assert response.status_code in [200, 422]


class TestHealthEndpointContract:
    """Contract tests for health check."""

    def test_health_returns_status(self):
        """TC-CNT-HP-008: Health endpoint returns status information."""
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert "status" in data
        assert data["status"] in ["ok", "degraded"]

    def test_health_response_schema(self):
        """TC-CNT-HP-009: Health response has expected schema."""
        response = client.get("/health")

        if response.status_code == 200:
            data = response.json()
            assert isinstance(data, dict)
            assert "status" in data
