"""Phase 0: population/validation scope disclosure tests."""

from __future__ import annotations

import pytest

from app.core.population_scope import (
    POPULATION_SCOPES,
    attach_population_scope,
    get_population_scope,
    get_population_scope_for_model_id,
)
from app.schemas.model_predict import (
    FusionDetailItem,
    FusionPredictResult,
    ModelPredictResponse,
    PhysiologicalPredictResult,
    TabularPredictResult,
    TextPredictResult,
)

REQUIRED_KEYS = {
    "scope_version",
    "population_id",
    "population_label",
    "label_definition",
    "validation_cohort",
    "evidence_level",
    "transport_risk",
    "intended_use",
    "out_of_scope",
    "automated_decision_allowed",
    "abstention_recommended",
    "abstention_reasons",
    "disclosure",
}


class TestPopulationRegistry:
    @pytest.mark.parametrize(
        "modality", ["structured", "text", "physiological", "fusion"]
    )
    def test_all_modalities_registered(self, modality: str):
        scope = get_population_scope(modality)
        assert REQUIRED_KEYS <= scope.keys()
        assert scope["automated_decision_allowed"] is False
        assert scope["abstention_recommended"] is True
        assert scope["out_of_scope"]
        assert scope["abstention_reasons"]
        assert scope["disclosure"]

    @pytest.mark.parametrize(
        ("alias", "canonical"),
        [("tabular", "structured"), ("physio", "physiological")],
    )
    def test_aliases(self, alias: str, canonical: str):
        assert get_population_scope(alias) == get_population_scope(canonical)

    def test_unknown_modality_rejected(self):
        with pytest.raises(ValueError):
            get_population_scope("not_a_modality")

    def test_fusion_is_not_evaluable(self):
        scope = get_population_scope("fusion")
        assert scope["evidence_level"] == "not_evaluable"
        assert scope["transport_risk"] == "unknown"

    def test_physiological_is_downgraded_to_synthetic_label_derived(self):
        scope = get_population_scope("physiological")
        assert scope["evidence_level"] == "synthetic_label_derived"
        assert any("合成" in reason for reason in scope["abstention_reasons"])
        assert "合成" in scope["disclosure"]

    @pytest.mark.parametrize(
        "modality", ["structured", "text", "physiological", "fusion"]
    )
    def test_evidence_level_is_registered(self, modality: str):
        assert get_population_scope(modality)["evidence_level"] in {
            "internal_source_split",
            "groupwise_oof",
            "cross_source",
            "small_internal_split",
            "small_external",
            "synthetic_label_derived",
            "not_evaluable",
            "heuristic_fallback",
        }

    @pytest.mark.parametrize(
        ("model_id", "population_id"),
        [
            ("structured_v1.23_external_lr", "students_self_report_v1_23"),
            ("text_improved_bilingual_model", "chinese_student_text_v1_27"),
            ("physiological_model_v2_dl", "depresjon_clinical_v2"),
            ("fusion_dnn_best", "no_aligned_three_modality_cohort"),
        ],
    )
    def test_model_id_mapping(self, model_id: str, population_id: str):
        scope = get_population_scope_for_model_id(model_id)
        assert scope is not None
        assert scope["population_id"] == population_id

    def test_unknown_model_id_has_no_scope(self):
        assert get_population_scope_for_model_id("some_other_model") is None


class TestAttachPopulationScope:
    def test_attach_returns_copy(self):
        result = attach_population_scope({"prediction": 0}, "text")
        result["population_scope"]["out_of_scope"].append("mutated")
        assert "mutated" not in POPULATION_SCOPES["text"]["out_of_scope"]
        assert "mutated" not in get_population_scope("text")["out_of_scope"]

    @pytest.mark.parametrize(
        "marker",
        [
            {"fallback_used": True},
            {"model_used": "rule_based_fallback"},
            {"model_used": "text_heuristic"},
        ],
    )
    def test_degraded_path_downgrades_evidence(self, marker: dict):
        result = attach_population_scope(
            {"prediction": 0, "model_used": "model", **marker}, "structured"
        )
        scope = result["population_scope"]
        assert scope["evidence_level"] == "heuristic_fallback"
        assert scope["automated_decision_allowed"] is False
        assert scope["abstention_recommended"] is True
        assert any("回退" in reason for reason in scope["abstention_reasons"])

    def test_refreshes_existing_scope(self):
        stale = {"population_scope": {"evidence_level": "stale"}}
        result = attach_population_scope(stale, "fusion")
        assert result["population_scope"]["evidence_level"] == "not_evaluable"

    def test_non_dict_input_is_returned_unchanged(self):
        assert attach_population_scope("not-a-dict", "text") == "not-a-dict"  # type: ignore[arg-type]


class TestSchemaPopulationScope:
    @pytest.mark.parametrize(
        ("modality", "payload"),
        [
            (
                "structured",
                {
                    "prediction": 0,
                    "probability": 0.1,
                    "risk_score": 10.0,
                    "risk_level": 0,
                    "model_used": "structured_model",
                },
            ),
            (
                "text",
                {
                    "prediction": 0,
                    "probability": 0.1,
                    "model_used": "text_model",
                },
            ),
            (
                "physiological",
                {
                    "prediction": 0,
                    "probability": 0.1,
                    "risk_score": 10.0,
                    "risk_level": 0,
                    "model_used": "physio_model",
                },
            ),
            (
                "fusion",
                {
                    "risk_score": 10.0,
                    "risk_level": 0,
                    "severity": "none",
                    "model_used": ["fusion_model"],
                    "fusion_detail": FusionDetailItem(),
                    "intervention_level": "none",
                    "intervention_actions": [],
                },
            ),
        ],
    )
    def test_result_models_accept_scope(self, modality: str, payload: dict):
        scope = get_population_scope(modality)
        model_cls = {
            "structured": TabularPredictResult,
            "text": TextPredictResult,
            "physiological": PhysiologicalPredictResult,
            "fusion": FusionPredictResult,
        }[modality]
        result = model_cls(**payload, population_scope=scope)
        dumped = result.model_dump()
        assert dumped["population_scope"]["population_id"] == scope["population_id"]
        assert dumped["population_scope"]["automated_decision_allowed"] is False

    def test_model_predict_response_accepts_scope(self):
        scope = get_population_scope("structured")
        response = ModelPredictResponse(population_scope=scope)
        assert response.population_scope is not None
        assert response.population_scope.population_id == "students_self_report_v1_23"

    def test_scope_defaults_to_none(self):
        assert ModelPredictResponse().population_scope is None
        assert (
            TextPredictResult(prediction=0, probability=0.1, model_used="m").population_scope
            is None
        )


class TestStatusWiring:
    def test_model_status_items_carry_population_scope(self):
        from app.services.model_predict_service import ModelPredictService

        status = ModelPredictService().get_model_status()
        items = {item["model_id"]: item for item in status["items"]}
        assert (
            items["structured_v1.23_external_lr"]["population_scope"]["population_id"]
            == "students_self_report_v1_23"
        )
        assert (
            items["text_depression_model"]["population_scope"]["population_id"]
            == "chinese_student_text_v1_27"
        )


class TestInferenceWiring:
    @pytest.mark.asyncio
    async def test_text_inference_attaches_scope(self, monkeypatch):
        from app.services.model_predict import inference

        async def fake_predict(_text: str) -> dict:
            return {
                "prediction": 0,
                "probability": 0.2,
                "sentiment_score": 0.2,
                "model_used": "text_model",
                "risk_level": 0,
            }

        async def fake_breaker(coro):
            return await coro

        monkeypatch.setattr(inference, "_ML_INFERENCE_CACHE_TTL", 0)
        monkeypatch.setattr(inference.model_engine, "predict_text", fake_predict)
        monkeypatch.setattr(inference, "call_with_ml_breaker", fake_breaker)
        monkeypatch.setattr(
            inference.InferenceService, "_fire_shadow_check", lambda *a, **k: None
        )

        result = await inference.InferenceService().predict_text(
            "今天心情还可以，想把最近的学习和生活记录下来。"
        )
        assert result["population_scope"]["population_id"] == "chinese_student_text_v1_27"

    @pytest.mark.asyncio
    async def test_fusion_inference_attaches_scope(self, monkeypatch):
        from app.services.model_predict import fusion

        async def fake_predict(**_kwargs) -> dict:
            return {
                "risk_score": 10.0,
                "risk_level": 0,
                "severity": "none",
                "model_used": ["fusion_model"],
                "fusion_detail": {"modality_scores": {}},
                "intervention_level": "none",
                "intervention_actions": [],
            }

        async def fake_breaker(coro):
            return await coro

        monkeypatch.setattr(fusion, "_ML_INFERENCE_CACHE_TTL", 0)
        monkeypatch.setattr(fusion.model_engine, "predict_fusion", fake_predict)
        monkeypatch.setattr(fusion, "call_with_ml_breaker", fake_breaker)

        result = await fusion.FusionMixin().predict_fusion(text="test")
        assert result["population_scope"]["evidence_level"] == "not_evaluable"
