"""Test v1.16 schema serialization and backward compatibility."""

from __future__ import annotations

from app.schemas.model_predict import (
    DataQualityItem,
    FusionPredictResult,
    PhysiologicalPredictResult,
    TabularPredictResult,
    TextPredictResult,
)


class TestTextPredictResult:
    def test_minimal_fields(self):
        result = TextPredictResult(prediction=0, probability=0.5, model_used="test")
        assert result.risk_level == 0
        assert result.crisis_override is False
        assert result.crisis_detected is False

    def test_full_fields(self):
        result = TextPredictResult(
            prediction=1,
            probability=0.85,
            sentiment_label="negative",
            sentiment_score=0.85,
            distress_score=85.0,
            crisis_score=90.0,
            risk_factors=["失眠", "焦虑"],
            protective_factors=["社交支持"],
            crisis_detected=True,
            crisis_keywords=["自杀"],
            risk_level=4,
            crisis_override=True,
            model_used="text_depression_model",
        )
        assert result.risk_level == 4
        assert result.crisis_override is True
        assert result.crisis_detected is True
        data = result.model_dump()
        assert data["risk_level"] == 4
        assert data["crisis_override"] is True


class TestTabularPredictResult:
    def test_without_data_quality(self):
        result = TabularPredictResult(
            prediction=0,
            probability=0.3,
            risk_score=30.0,
            risk_level=1,
            model_used="lr",
        )
        assert result.data_quality is None
        data = result.model_dump()
        assert "data_quality" in data

    def test_with_data_quality(self):
        dq = DataQualityItem(
            missing_fields=["social_support"],
            confidence_penalty=0.1,
            quality_level="partial",
        )
        result = TabularPredictResult(
            prediction=0,
            probability=0.3,
            risk_score=30.0,
            risk_level=1,
            model_used="lr",
            data_quality=dq,
        )
        assert result.data_quality is not None
        assert result.data_quality.quality_level == "partial"
        data = result.model_dump()
        assert data["data_quality"]["missing_fields"] == ["social_support"]


class TestPhysiologicalPredictResult:
    def test_default_fields(self):
        result = PhysiologicalPredictResult(
            prediction=0,
            probability=0.4,
            risk_score=40.0,
            risk_level=1,
            model_used="physio",
        )
        assert result.confidence == 0.8
        assert result.data_quality == "complete"
        assert result.calibrated is True

    def test_custom_fields(self):
        result = PhysiologicalPredictResult(
            prediction=1,
            probability=0.7,
            risk_score=70.0,
            risk_level=3,
            model_used="physio",
            confidence=0.6,
            data_quality="partial",
            calibrated=True,
        )
        data = result.model_dump()
        assert data["confidence"] == 0.6
        assert data["data_quality"] == "partial"
        assert data["calibrated"] is True


class TestFusionPredictResult:
    def test_default_fields(self):
        result = FusionPredictResult(
            risk_score=50.0,
            risk_level=2,
            severity="moderate",
            model_used=["structured", "text"],
            fusion_detail={},
            intervention_level="medium",
            intervention_actions=["action1"],
        )
        assert result.review_required is False
        assert result.review_triggers == []
        assert result.crisis_override is False
        assert result.model_version == "v1.16-risk-calibration"

    def test_full_fields(self):
        result = FusionPredictResult(
            risk_score=90.0,
            risk_level=4,
            severity="critical",
            model_used=["structured", "text", "physio"],
            model_version="v1.16-risk-calibration",
            fusion_detail={"modality_scores": {}},
            intervention_level="critical",
            intervention_actions=["立即触发紧急预警"],
            review_required=True,
            review_triggers=["crisis_detected", "high_risk_single_model"],
            crisis_override=True,
        )
        data = result.model_dump()
        assert data["review_required"] is True
        assert data["review_triggers"] == ["crisis_detected", "high_risk_single_model"]
        assert data["crisis_override"] is True
        assert data["model_version"] == "v1.16-risk-calibration"


class TestBackwardCompatibility:
    def test_old_tabular_response_still_valid(self):
        """旧版 Tabular 响应（无 data_quality）应能序列化。"""
        result = TabularPredictResult(
            prediction=0,
            probability=0.2,
            risk_score=20.0,
            risk_level=0,
            model_used="lr",
        )
        data = result.model_dump()
        assert "prediction" in data
        assert "risk_score" in data

    def test_old_fusion_response_still_valid(self):
        """旧版 Fusion 响应应能序列化，新增字段有默认值。"""
        result = FusionPredictResult(
            risk_score=30.0,
            risk_level=1,
            severity="mild",
            model_used=["structured"],
            fusion_detail={},
            intervention_level="low",
            intervention_actions=["保持日常心理健康维护"],
        )
        data = result.model_dump()
        assert data["review_required"] is False
        assert data["crisis_override"] is False
