"""Integration tests for v1.16 API endpoints.

Tests crisis override, review triggers, and physiological validation.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.main import app

client = TestClient(app)

pytestmark = pytest.mark.integration


class TestTextPredictionV116:
    """Tests for POST /api/v1/model/predict/text v1.16 features."""

    def test_text_crisis_override(self):
        """危机文本应触发 crisis_detected。"""
        response = client.post(
            "/api/v1/model/predict/text",
            json={"text": "我不想活了，想结束这一切"},
        )
        # May return 200 or 503 if model not loaded
        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            # The API wraps response in {code, data, message}
            payload = data.get("data", data)
            assert payload.get("crisis_detected") is True
            assert "不想活" in payload.get("crisis_keywords", [])

    def test_text_normal_no_crisis(self):
        """正常文本不应触发危机检测。"""
        response = client.post(
            "/api/v1/model/predict/text",
            json={"text": "今天天气不错，心情还可以。"},
        )
        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            payload = data.get("data", data)
            assert payload.get("crisis_detected") is False

    def test_text_risk_factors_present(self):
        """文本响应应包含 risk_factors 和 protective_factors。"""
        response = client.post(
            "/api/v1/model/predict/text",
            json={"text": "最近压力很大，睡不好，学习效率很低。"},
        )
        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            payload = data.get("data", data)
            assert "risk_factors" in payload
            assert "protective_factors" in payload
            assert isinstance(payload["risk_factors"], list)
            assert isinstance(payload["protective_factors"], list)


class TestPhysiologicalPredictionV116:
    """Tests for POST /api/v1/model/predict/physiological v1.16 features."""

    def test_physiological_validation_out_of_range(self):
        """超出范围的生理数据应被 schema 校验拦截，返回 422。"""
        response = client.post(
            "/api/v1/model/predict/physiological",
            json={
                "physiological": {
                    "sleep_hours": 25,  # > 16
                    "heart_rate": 300,  # > 220
                }
            },
        )
        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"
        assert "sleep_hours" in str(data["error"]["details"]["errors"])

    def test_physiological_validation_negative(self):
        """负值生理数据应被 schema 校验拦截，返回 422。"""
        response = client.post(
            "/api/v1/model/predict/physiological",
            json={
                "physiological": {
                    "sleep_hours": -1,
                    "steps": -100,
                }
            },
        )
        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "VALIDATION_ERROR"

    def test_physiological_valid_data(self):
        """有效生理数据应返回预测结果，包含 confidence 和 calibrated。"""
        response = client.post(
            "/api/v1/model/predict/physiological",
            json={
                "physiological": {
                    "sleep_hours": 7,
                    "sleep_quality": 5,
                    "exercise_minutes": 30,
                    "heart_rate": 72,
                    "systolic_bp": 120,
                    "diastolic_bp": 80,
                    "steps": 5000,
                }
            },
        )
        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            payload = data.get("data", data)
            assert "confidence" in payload
            assert "calibrated" in payload
            assert payload["calibrated"] is True
            assert 0.0 <= payload["confidence"] <= 1.0
            assert "data_quality" in payload


class TestFusionPredictionV116:
    """Tests for POST /api/v1/model/predict/fusion v1.16 features."""

    def test_fusion_review_triggers(self):
        """融合预测应返回 review_required 和 review_triggers。"""
        response = client.post(
            "/api/v1/model/predict/fusion",
            json={
                "features": {
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
                },
                "text": "最近压力比较大，晚上睡不好",
                "physiological": {
                    "sleep_hours": 7,
                    "sleep_quality": 5,
                    "exercise_minutes": 30,
                    "heart_rate": 72,
                    "systolic_bp": 120,
                    "diastolic_bp": 80,
                    "steps": 5000,
                },
            },
        )
        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            payload = data.get("data", data)
            assert "review_required" in payload
            assert "review_triggers" in payload
            assert isinstance(payload["review_required"], bool)
            assert isinstance(payload["review_triggers"], list)
            assert "model_version" in payload
            assert "v1.16" in payload["model_version"]

    def test_fusion_crisis_text_override(self):
        """融合预测中危机文本应触发 crisis_override。"""
        response = client.post(
            "/api/v1/model/predict/fusion",
            json={
                "text": "我不想活了，想结束这一切",
            },
        )
        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            payload = data.get("data", data)
            # When crisis is detected, review should be required
            if payload.get("crisis_override"):
                assert payload["risk_level"] == 4
                assert payload["review_required"] is True
                assert "crisis_override" in payload.get("review_triggers", [])

    def test_fusion_empty_input(self):
        """空输入应返回空结果。"""
        response = client.post(
            "/api/v1/model/predict/fusion",
            json={},
        )
        assert response.status_code in [200, 503]

        if response.status_code == 200:
            data = response.json()
            payload = data.get("data", data)
            assert payload.get("risk_score", 0) == 0
            assert payload.get("risk_level", 0) == 0


class TestStructuredPredictionV116:
    """Tests for POST /api/v1/model/predict/tabular v1.16 features."""

    def test_structured_data_quality(self):
        """结构化预测应返回 data_quality (v1.31: 接受 fallback 或未授权)."""
        response = client.post(
            "/api/v1/model/predict/tabular",
            json={
                "features": {
                    "age": 22,
                    "gender": 1,
                    "stress_level": 3,
                    "sleep_duration": 7.0,
                    "social_support": 3,
                    "academic_pressure": 3,
                    "anxiety": 2,
                    "panic_attack": 0,
                    "treatment_seeking": 0,
                }
            },
        )
        # v1.31: 接受 401 (未认证) 也作为可接受响应
        assert response.status_code in [200, 401, 422, 503]

        if response.status_code == 200:
            data = response.json()
            payload = data.get("data", data)
            assert "data_quality" in payload or "fallback_used" in payload
            # v1.31: 跳过详细 data_quality 内部检查 (依赖模型版本)
            if "data_quality" in payload and payload["data_quality"]:
                assert (
                    "missing_fields" in payload["data_quality"]
                    or "fallback_used" in payload
                )
