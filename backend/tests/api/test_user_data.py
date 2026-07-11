from __future__ import annotations

from pathlib import Path

import pytest
from fastapi.testclient import TestClient

PHYSIO_MODEL_PATH = (
    Path(__file__).resolve().parents[2]
    / "models"
    / "artifacts"
    / "physiological_optimized"
    / "model.json"
)
skip_no_physio = pytest.mark.skipif(
    not PHYSIO_MODEL_PATH.exists(),
    reason="生理模型 artifacts 不存在 (models/artifacts/physiological_optimized/)",
)


class TestStructuredDataCollect:
    def test_collect_structured_success(self, client: TestClient, as_role):
        as_role("user", 1)
        resp = client.post(
            "/api/v1/user/data/collect",
            json={
                "assessment_type": "comprehensive",
                "data_payload": {
                    "age": 25,
                    "gender": "male",
                    "is_student": True,
                    "grade": "大三",
                    "major": "计算机",
                    "gpa": 3.5,
                    "sleep_hours": 7,
                    "stress_level": 3,
                    "anxiety_score": 45,
                    "depression_score": 40,
                },
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200
        assert "risk_score" in body["data"]
        assert "risk_level" in body["data"]

    def test_collect_structured_non_student_normalization(
        self, client: TestClient, as_role
    ):
        as_role("user", 1)
        resp = client.post(
            "/api/v1/user/data/collect",
            json={
                "assessment_type": "comprehensive",
                "data_payload": {
                    "age": 30,
                    "gender": "female",
                    "is_student": False,
                    "grade": "",
                    "major": "",
                    "gpa": 0,
                    "sleep_hours": 6,
                    "stress_level": 4,
                    "anxiety_score": 60,
                    "depression_score": 55,
                },
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200

    def test_collect_structured_empty_payload_uses_fallback(
        self, client: TestClient, as_role
    ):
        as_role("user", 1)
        resp = client.post(
            "/api/v1/user/data/collect",
            json={
                "assessment_type": "comprehensive",
                "data_payload": {},
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200
        assert "risk_score" in body["data"]

    def test_collect_structured_boundary_values(self, client: TestClient, as_role):
        as_role("user", 1)
        resp = client.post(
            "/api/v1/user/data/collect",
            json={
                "assessment_type": "comprehensive",
                "data_payload": {
                    "age": 0,
                    "gender": "male",
                    "is_student": True,
                    "grade": "大三",
                    "major": "计算机",
                    "gpa": 0,
                    "sleep_hours": 0,
                    "stress_level": 1,
                    "anxiety_score": 0,
                    "depression_score": 0,
                },
            },
        )
        assert resp.status_code == 200

        resp2 = client.post(
            "/api/v1/user/data/collect",
            json={
                "assessment_type": "comprehensive",
                "data_payload": {
                    "age": 120,
                    "gender": "female",
                    "is_student": False,
                    "grade": "",
                    "major": "",
                    "gpa": 4.0,
                    "sleep_hours": 24,
                    "stress_level": 5,
                    "anxiety_score": 100,
                    "depression_score": 100,
                },
            },
        )
        assert resp2.status_code == 200


class TestTextAnalyze:
    def test_text_analyze_success(self, client: TestClient, as_role):
        as_role("user", 1)
        resp = client.post(
            "/api/v1/user/data/text/analyze",
            json={
                "entry_type": "journal",
                "content": "最近感觉有点压力，但总体还好",
                "emotion_tags": ["压力"],
                "mood_score": 3,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200

    def test_text_analyze_empty_content_returns_error(
        self, client: TestClient, as_role
    ):
        as_role("user", 1)
        resp = client.post(
            "/api/v1/user/data/text/analyze",
            json={
                "entry_type": "journal",
                "content": "",
                "emotion_tags": [],
            },
        )
        assert resp.status_code == 422


class TestPhysiologicalRecord:
    @skip_no_physio
    def test_record_physiological_success(self, client: TestClient, as_role):
        as_role("user", 1)
        resp = client.post(
            "/api/v1/user/data/physiological/record",
            json={
                "source": "manual",
                "sleep_hours": 7.5,
                "sleep_quality": 4,
                "exercise_minutes": 30,
                "heart_rate": 72,
                "systolic_bp": 120,
                "diastolic_bp": 80,
                "steps": 8000,
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200
        assert "record_id" in body["data"]

    @skip_no_physio
    def test_record_physiological_invalid_fields_filtered(
        self, client: TestClient, as_role
    ):
        as_role("user", 1)
        resp = client.post(
            "/api/v1/user/data/physiological/record",
            json={
                "source": "manual",
                "sleep_hours": 7.5,
                "heart_rate": 72,
                "invalid_field": "should_be_ignored",
            },
        )
        assert resp.status_code == 200

    def test_record_physiological_negative_values_rejected(
        self, client: TestClient, as_role
    ):
        as_role("user", 1)
        resp = client.post(
            "/api/v1/user/data/physiological/record",
            json={
                "source": "manual",
                "sleep_hours": -1,
            },
        )
        assert resp.status_code == 422


class TestDraftManagement:
    def test_upsert_draft_success(self, client: TestClient, as_role):
        as_role("user", 1)
        resp = client.post(
            "/api/v1/user/data/draft",
            json={
                "draft_type": "structured",
                "data_payload": {"age": 25, "gender": "male"},
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200
        assert "draft_id" in body["data"]

    def test_update_existing_draft_success(self, client: TestClient, as_role):
        as_role("user", 1)
        client.post(
            "/api/v1/user/data/draft",
            json={
                "draft_type": "structured",
                "data_payload": {"age": 25},
            },
        )
        resp = client.post(
            "/api/v1/user/data/draft",
            json={
                "draft_type": "structured",
                "data_payload": {"age": 26, "gender": "male"},
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200

    def test_get_draft_success(self, client: TestClient, as_role):
        as_role("user", 1)
        client.post(
            "/api/v1/user/data/draft",
            json={
                "draft_type": "structured",
                "data_payload": {"age": 25},
            },
        )
        resp = client.get("/api/v1/user/data/draft/structured")
        assert resp.status_code == 200
        body = resp.json()
        assert body["code"] == 200
        assert "data_payload" in body["data"]

    def test_get_nonexistent_draft_returns_404(self, client: TestClient, as_role):
        as_role("user", 1)
        resp = client.get("/api/v1/user/data/draft/nonexistent")
        assert resp.status_code == 404
