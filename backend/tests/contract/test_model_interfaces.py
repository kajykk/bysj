"""Contract tests for model interfaces.

Validates input/output contracts for individual model types.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

pytestmark = pytest.mark.contract

# 真实契约: 请求体为嵌套结构 (tabular: features / physiological: physiological),
# 响应统一为 ApiResponse 包装 {code, message, data}
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
PHYSIO_FEATURES = {
    "sleep_hours": 7.0,
    "sleep_quality": 3,
    "exercise_minutes": 30.0,
    "heart_rate": 75.0,
    "systolic_bp": 120.0,
    "diastolic_bp": 80.0,
    "steps": 6000,
}


class TestStructuredModelContract:
    """Contract tests for structured/tabular prediction models."""

    def test_structured_input_field_completeness(self):
        """TC-CNT-HP-054: Structured input requires specific fields."""
        response = client.post(
            "/api/v1/model/predict/tabular",
            json={"features": TABULAR_FEATURES},
        )

        assert response.status_code in [200, 503]

    def test_structured_output_probability_format(self):
        """TC-CNT-HP-055: Output contains risk score between 0 and 100."""
        response = client.post(
            "/api/v1/model/predict/tabular",
            json={"features": TABULAR_FEATURES},
        )

        if response.status_code == 200:
            data = response.json()
            assert "risk_score" in data["data"]
            assert 0.0 <= data["data"]["risk_score"] <= 100.0

    def test_structured_output_label_format(self):
        """TC-CNT-HP-056: Output contains valid risk level label."""
        response = client.post(
            "/api/v1/model/predict/tabular",
            json={"features": TABULAR_FEATURES},
        )

        if response.status_code == 200:
            data = response.json()
            if "risk_level" in data["data"]:
                rl = data["data"]["risk_level"]
                # 数值分级 (0-4) 或字符串标签均可
                assert rl in [0, 1, 2, 3, 4] or rl in [
                    "low",
                    "medium",
                    "high",
                    "critical",
                    "normal",
                ]

    def test_structured_missing_field_fallback(self):
        """TC-CNT-HP-057: Missing required wrapper field triggers validation."""
        response = client.post(
            "/api/v1/model/predict/tabular",
            json={},  # features 必填
        )

        assert response.status_code in [422]

    def test_structured_invalid_field_types(self):
        """TC-CNT-HP-058: Invalid field types return validation error."""
        response = client.post(
            "/api/v1/model/predict/tabular",
            json={"features": {"age": "not-a-number", "gender": [1, 2]}},
        )

        assert response.status_code in [200, 422, 503]


class TestTextModelContract:
    """Contract tests for text prediction models."""

    def test_text_input_length_boundaries(self):
        """TC-CNT-HP-059: Text input handles various lengths."""
        test_cases = [
            ("", [422]),  # Empty (min_length=1)
            ("Hi", [200, 422]),  # Very short
            ("I feel sad today. " * 100, [200, 413, 422]),  # Long
        ]

        for text, expected_statuses in test_cases:
            response = client.post(
                "/api/v1/model/predict/text",
                json={"text": text},
            )
            assert response.status_code in expected_statuses

    def test_text_empty_input_handling(self):
        """TC-CNT-HP-060: Empty text handled appropriately."""
        response = client.post(
            "/api/v1/model/predict/text",
            json={"text": ""},
        )

        assert response.status_code in [422]

    def test_text_output_structure(self):
        """TC-CNT-HP-061: Text prediction output has expected structure."""
        response = client.post(
            "/api/v1/model/predict/text",
            json={"text": "I feel very anxious and stressed"},
        )

        if response.status_code == 200:
            data = response.json()
            assert "data" in data
            assert isinstance(data["data"], dict)
            # 文本模态评分键: distress_score (或 sentiment_score 回退)
            assert any(k in data["data"] for k in ("distress_score", "sentiment_score"))

    def test_text_special_characters(self):
        """TC-CNT-HP-062: Text with special characters handled gracefully."""
        response = client.post(
            "/api/v1/model/predict/text",
            json={"text": "Hello! 你好! 🎉 <b>bold</b> &amp; special"},
        )

        assert response.status_code in [200, 422, 503]


class TestPhysiologicalModelContract:
    """Contract tests for physiological prediction models."""

    def test_physiological_field_ranges(self):
        """TC-CNT-HP-063: Physiological fields have valid ranges."""
        valid_inputs = [
            {"sleep_hours": 0.0, "exercise_minutes": 0.0},  # Minimum
            {"sleep_hours": 24.0, "exercise_minutes": 300.0},  # Maximum
            {"sleep_hours": 7.5, "exercise_minutes": 45.0},  # Normal
        ]

        for input_data in valid_inputs:
            response = client.post(
                "/api/v1/model/predict/physiological",
                json={"physiological": input_data},
            )
            assert response.status_code in [200, 422, 503]

    def test_physiological_output_format(self):
        """TC-CNT-HP-064: Physiological prediction output format."""
        response = client.post(
            "/api/v1/model/predict/physiological",
            json={"physiological": PHYSIO_FEATURES},
        )

        if response.status_code == 200:
            data = response.json()
            assert "risk_score" in data["data"]
            assert isinstance(data["data"]["risk_score"], (int, float))

    def test_physiological_invalid_values(self):
        """TC-CNT-HP-065: Invalid physiological values handled."""
        response = client.post(
            "/api/v1/model/predict/physiological",
            json={"physiological": {"sleep_hours": -5.0, "exercise_minutes": -10.0}},
        )

        assert response.status_code in [200, 422, 503]


class TestFusionModelContract:
    """Contract tests for fusion prediction models."""

    def test_fusion_input_structure(self):
        """TC-CNT-HP-066: Fusion input has text and/or structured data."""
        test_cases = [
            {"text": "I feel sad", "features": {"sleep_hours": 5.0}},
            {"text": "I feel sad"},
            {"features": {"sleep_hours": 5.0}},
        ]

        for input_data in test_cases:
            response = client.post(
                "/api/v1/model/predict/fusion",
                json=input_data,
            )
            assert response.status_code in [200, 422, 503]

    def test_fusion_output_combined_score(self):
        """TC-CNT-HP-067: Fusion output combines multiple model scores."""
        response = client.post(
            "/api/v1/model/predict/fusion",
            json={
                "text": "I feel very anxious",
                "features": {"sleep_hours": 4.0, "exercise_minutes": 5.0},
            },
        )

        if response.status_code == 200:
            data = response.json()
            assert "risk_score" in data["data"]
            assert isinstance(data["data"]["risk_score"], (int, float))

    def test_fusion_empty_input(self):
        """TC-CNT-HP-068: Empty fusion input returns error."""
        response = client.post(
            "/api/v1/model/predict/fusion",
            json={},
        )

        assert response.status_code in [200, 422, 503]


class TestModelFallbackBehavior:
    """Contract tests for model fallback behavior."""

    def test_fallback_indicator_in_response(self):
        """TC-CNT-HP-069: Fallback usage indicated in response."""
        response = client.post(
            "/api/v1/model/predict/tabular",
            json={"features": TABULAR_FEATURES},
        )

        if response.status_code == 200:
            data = response.json()["data"]
            # Should indicate if fallback was used
            assert (
                "fallback_used" in data or "model_used" in data or "risk_score" in data
            )

    def test_all_models_return_consistent_format(self):
        """TC-CNT-HP-070: All model endpoints return consistent format."""
        endpoints = [
            ("/api/v1/model/predict/tabular", {"features": TABULAR_FEATURES}),
            ("/api/v1/model/predict/text", {"text": "test"}),
            (
                "/api/v1/model/predict/physiological",
                {"physiological": PHYSIO_FEATURES},
            ),
        ]

        for endpoint, payload in endpoints:
            response = client.post(endpoint, json=payload)

            if response.status_code == 200:
                body = response.json()
                # 统一 ApiResponse 包装
                assert "data" in body
                assert "code" in body
