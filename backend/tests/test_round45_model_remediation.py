"""ROUND_45：结构化 / 生理模型契约回归。

覆盖四项 P0：
1. 小写 cgpa 在推理边界从 0–10 归一到训练分布 0–4；
2. routing_info.selected_model_id 与真实 model_used 一致；
3. 生理降级不再谎报 DL + calibrated；
4. 空/非法生理输入在 schema 边界 422。

以及两项 P1：启发式睡眠质量 1–5 量纲、注册表元数据与 metrics.json 对齐。
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import pytest
from pydantic import ValidationError

from app.core.model_engine import ModelEngine
from app.core.model_registry import get_model_info
from app.schemas.model_predict import PhysiologicalPredictRequest

BACKEND_DIR = Path(__file__).resolve().parents[1]
V123_MODEL_PATH = BACKEND_DIR / "models" / "v1.23_external_lr" / "model.pkl"
PHYSIO_METRICS_PATH = (
    BACKEND_DIR / "models" / "artifacts" / "physiological_optimized" / "metrics.json"
)
skip_no_v123 = pytest.mark.skipif(
    not V123_MODEL_PATH.exists(),
    reason="v1.23 model.pkl 不存在",
)

FULL_STRUCTURED = {
    "age": 22,
    "gender": 1,
    "cgpa": 3.4,
    "stress_level": 1,
    "sleep_duration": 8,
    "social_support": 4,
    "financial_pressure": 1,
    "family_history": 0,
    "academic_pressure": 1,
    "exercise_frequency": 3,
    "anxiety": 1,
    "panic_attack": 0,
    "study_year": 3,
    "treatment_seeking": 0,
}

FULL_PHYSIO = {
    "sleep_hours": 7,
    "sleep_quality": 3,
    "exercise_minutes": 30,
    "heart_rate": 70,
    "systolic_bp": 120,
    "diastolic_bp": 80,
    "steps": 5000,
}


class TestStructuredGpaContract:
    def test_lowercase_cgpa_is_normalized_to_training_scale(self):
        from unittest.mock import MagicMock

        model = MagicMock()
        model.named_steps = {}
        result = ModelEngine._build_structured_input(
            {"cgpa": 8.5}, ["cgpa"], model
        )
        assert result["cgpa"] == pytest.approx(3.4)

    def test_four_point_cgpa_passes_through(self):
        from unittest.mock import MagicMock

        model = MagicMock()
        model.named_steps = {}
        result = ModelEngine._build_structured_input(
            {"cgpa": 3.5}, ["cgpa"], model
        )
        assert result["cgpa"] == pytest.approx(3.5)

    def test_missing_cgpa_keeps_training_median(self):
        from unittest.mock import MagicMock

        from app.core.feature_maps import DEFAULTS

        model = MagicMock()
        model.named_steps = {}
        result = ModelEngine._build_structured_input({}, ["cgpa"], model)
        assert result["cgpa"] == DEFAULTS["cgpa"]

    def test_uppercase_cgpa_keeps_ten_point_contract(self):
        from unittest.mock import MagicMock

        model = MagicMock()
        model.named_steps = {}
        result = ModelEngine._build_structured_input(
            {"cgpa": 8.5}, ["CGPA"], model
        )
        assert result["CGPA"] == pytest.approx(8.5)


class TestStructuredRoutingTruth:
    def test_selected_model_id_follows_default_model_config(self):
        engine = ModelEngine()
        with patch("app.core.config.settings.structured_default_model", "v1.23"):
            routing, routed = engine._route_structured(dict(FULL_STRUCTURED))
        assert routed is None
        assert routing["selected_model_id"] == "structured_v1.23_external_lr"
        assert routing["selected_model_family"] == "structured"

    @skip_no_v123
    def test_result_routing_id_matches_model_used(self):
        engine = ModelEngine()
        with patch("app.core.config.settings.structured_experimental_enabled", False):
            result = asyncio.run(engine.predict_structured(dict(FULL_STRUCTURED)))
        assert result["model_used"] == "structured_v1.23_external_lr"
        assert result["routing_info"]["selected_model_id"] == result["model_used"]


class TestPhysiologicalFallbackTruth:
    def test_prediction_error_is_reported_as_heuristic(self):
        engine = ModelEngine()

        def boom(_data):
            raise RuntimeError("synthetic inference failure")

        engine._predict_physiological_sync = boom  # type: ignore[method-assign]
        result = asyncio.run(engine.predict_physiological(dict(FULL_PHYSIO)))

        assert result["fallback_used"] is True
        assert result["fallback_reason"] == "prediction_error"
        assert result["model_used"] == "physiological_heuristic_fallback"
        assert result["calibrated"] is False
        assert result["risk_score"] > 0

    def test_heuristic_sleep_quality_uses_five_point_scale(self):
        engine = ModelEngine()
        good = engine._physiological_heuristic_fallback(
            {**FULL_PHYSIO, "sleep_quality": 5}
        )
        bad = engine._physiological_heuristic_fallback(
            {**FULL_PHYSIO, "sleep_quality": 1}
        )
        assert good < bad
        assert bad - good == pytest.approx(6.0, abs=0.01)


class TestPhysiologicalInputBoundary:
    @pytest.mark.parametrize(
        "payload",
        [
            {},
            {"foo": 1},
            {"sleep_hours": None},
            {"heart_rate": "not-a-number"},
            {"heart_rate": float("nan")},
            {"heart_rate": float("inf")},
        ],
    )
    def test_rejects_empty_unknown_or_non_finite(self, payload):
        with pytest.raises(ValidationError):
            PhysiologicalPredictRequest(physiological=payload)

    def test_accepts_single_recognized_field(self):
        req = PhysiologicalPredictRequest(physiological={"sleep_hours": 7})
        assert req.physiological == {"sleep_hours": 7}

    def test_unknown_keys_do_not_raise(self):
        req = PhysiologicalPredictRequest(
            physiological={"sleep_hours": 7, "source": "manual"}
        )
        assert req.physiological["source"] == "manual"


class TestRegistryMetadataMatchesArtifact:
    @pytest.mark.skipif(
        not PHYSIO_METRICS_PATH.exists(), reason="physiological metrics 不存在"
    )
    def test_registry_matches_metrics_json(self):
        metrics = json.loads(PHYSIO_METRICS_PATH.read_text(encoding="utf-8"))
        info = get_model_info("physiological_model_v2_dl")
        assert info is not None
        test_metrics = metrics["test_metrics"]

        assert info.feature_schema["hidden_dims"] == metrics["hyperparameters"]["hidden_dims"]
        assert info.feature_schema["dropout_rate"] == metrics["hyperparameters"]["dropout_rate"]
        assert info.artifact_metadata["test_f1"] == pytest.approx(test_metrics["f1"])
        assert info.artifact_metadata["test_accuracy"] == pytest.approx(
            test_metrics["accuracy"]
        )
        assert info.artifact_metadata["test_roc_auc"] == pytest.approx(
            test_metrics["roc_auc"]
        )
        assert info.artifact_metadata["test_auprc"] == pytest.approx(
            test_metrics["auprc"]
        )
        assert info.artifact_metadata["best_epoch"] == metrics["best_epoch"]
        assert info.artifact_metadata["model_parameters"] == metrics["model_parameters"]
        assert (
            info.artifact_metadata["evaluation_set_size"]
            == metrics["data_split"]["test_samples"]
        )
