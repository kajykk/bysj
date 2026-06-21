"""Tests for RiskService and risk-related utilities."""

from __future__ import annotations

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.core.risk_thresholds import get_fusion_threshold, get_threshold_by_modality, should_fallback
from app.services.intervention_service import InterventionRecommendation
from app.services.risk_service import RiskService


class TestRiskThresholds:
    def test_get_threshold_by_modality_physiological(self):
        # physiological 校准阈值(以 test_risk_thresholds.py unit 为权威源)
        thresholds = get_threshold_by_modality("physiological")
        assert thresholds["mild"] == 35
        assert thresholds["critical"] == 90

    def test_get_threshold_by_modality_default(self):
        thresholds = get_threshold_by_modality("unknown")
        assert thresholds["mild"] == 20
        assert thresholds["critical"] == 80

    def test_get_fusion_threshold_with_low_confidence(self):
        assert get_fusion_threshold(90, confidence=0.3) == 42

    def test_get_fusion_threshold_with_high_score(self):
        assert get_fusion_threshold(85, confidence=0.9) == 82

    def test_should_fallback_when_unavailable(self):
        assert should_fallback(confidence=0.9, availability=False) is True

    def test_should_not_fallback_when_confident_and_available(self):
        assert should_fallback(confidence=0.8, availability=True) is False

    def test_intervention_recommendation_for_high_risk(self):
        level, actions = InterventionRecommendation.build_from_risk_level(4, dominant_modality="physiological")
        assert level == "critical"
        assert any("立即" in action or "尽快" in action for action in actions)


class TestRiskService:
    """Test RiskService core methods."""

    @pytest.mark.asyncio
    async def test_calculate_heuristic_score(self, db_session):
        """TC-COV-RISK-001: Calculate heuristic score from features."""
        service = RiskService(db_session)
        features = {
            "stress_level": 5,
            "anxiety": 3,
            "sleep_duration": 5,
            "financial_pressure": 4,
            "social_support": 2,
            "panic_attack": 1,
        }
        score = service._calculate_heuristic_score(features)
        assert 0 <= score <= 100
        assert score > 0  # With these inputs, score should be positive

    @pytest.mark.asyncio
    async def test_calculate_heuristic_score_defaults(self, db_session):
        """TC-COV-RISK-001b: Heuristic score with missing features uses defaults."""
        service = RiskService(db_session)
        score = service._calculate_heuristic_score({})
        assert 0 <= score <= 100

    def test_score_to_level(self, db_session):
        """TC-COV-RISK-002: Score to level conversion (default = structured, mild=25)."""
        service = RiskService(db_session)
        assert service._score_to_level(0) == 0
        assert service._score_to_level(24) == 0
        assert service._score_to_level(25) == 1  # structured mild threshold
        assert service._score_to_level(45) == 2  # moderate threshold
        assert service._score_to_level(65) == 3  # high threshold
        assert service._score_to_level(85) == 4  # critical threshold

    def test_score_to_level_physiological(self, db_session):
        """TC-COV-RISK-002b: Score to level with physiological modality (mild=35)."""
        service = RiskService(db_session)
        # Physiological has different thresholds (per test_risk_thresholds.py unit)
        assert service._score_to_level(34, "physiological") == 0
        assert service._score_to_level(35, "physiological") == 1

    def test_level_to_severity(self, db_session):
        """TC-COV-RISK-003: Level to severity mapping."""
        service = RiskService(db_session)
        assert service._level_to_severity(0) == "none"
        assert service._level_to_severity(1) == "mild"
        assert service._level_to_severity(2) == "moderate"
        assert service._level_to_severity(3) == "high"
        assert service._level_to_severity(4) == "critical"
        assert service._level_to_severity(99) == "unknown"

    def test_score_to_severity(self, db_session):
        """TC-COV-RISK-004: Score to severity mapping."""
        service = RiskService(db_session)
        assert service._score_to_severity(0) == "none"
        assert service._score_to_severity(4) == "none"
        assert service._score_to_severity(5) == "mild"
        assert service._score_to_severity(9) == "mild"
        assert service._score_to_severity(10) == "moderate"
        assert service._score_to_severity(14) == "moderate"
        assert service._score_to_severity(15) == "severe"

    def test_build_advice(self, db_session):
        """TC-COV-RISK-005: Build advice for different risk levels."""
        service = RiskService(db_session)
        assert len(service._build_advice(0)) > 0
        assert len(service._build_advice(1)) > 0
        assert len(service._build_advice(2)) > 0
        assert len(service._build_advice(3)) > 0
        assert len(service._build_advice(4)) > 0
        # Level 4 should have more urgent advice
        advice_4 = service._build_advice(4)
        assert any("立即" in a for a in advice_4)

    def test_since_datetime(self, db_session):
        """TC-COV-RISK-006: _since_datetime returns correct time range."""
        service = RiskService(db_session)
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        since = service._since_datetime(7)
        assert since < now
        # Should be approximately 7 days ago
        diff = now - since
        assert 6 < diff.days < 8

    def test_since_datetime_negative(self, db_session):
        """TC-COV-RISK-006b: _since_datetime handles negative days."""
        service = RiskService(db_session)
        since = service._since_datetime(-5)
        # Should clamp to 0 days
        from datetime import datetime, timezone
        now = datetime.now(timezone.utc)
        diff = now - since
        assert diff.days == 0

    @pytest.mark.asyncio
    async def test_get_risk_report_no_data(self, db_session):
        """TC-COV-RISK-007: Risk report with no assessments returns default."""
        service = RiskService(db_session)
        report = await service.get_risk_report(9999)
        assert report["risk_level"] == 0
        assert report["risk_score"] == 0
        assert report["severity"] == "none"
        assert report["trend"] == "stable"
        assert len(report["advice"]) > 0
        assert report["assessed_at"] is None

    @pytest.mark.asyncio
    async def test_get_risk_trend_no_data(self, db_session):
        """TC-COV-RISK-008: Risk trend with no data returns empty points."""
        service = RiskService(db_session)
        trend = await service.get_risk_trend(9999, 30)
        assert trend["days"] == 30
        assert trend["direction"] == "stable"
        assert trend["points"] == []

    def test_validate_and_normalize_template_tasks(self, db_session):
        """TC-COV-RISK-009: Validate and normalize template tasks."""
        service = RiskService(db_session)
        tasks = [
            {"task_name": "Task 1", "task_type": "type1", "duration_minutes": 15},
            {"task_name": "Task 2", "task_type": "type2", "duration_minutes": 30},
        ]
        result = service._validate_and_normalize_template_tasks(tasks, "test_template")
        assert len(result) == 2
        assert result[0]["task_name"] == "Task 1"
        assert result[0]["duration_minutes"] == 15

    def test_validate_template_tasks_not_list(self, db_session):
        """TC-COV-RISK-009b: Non-list task list raises error."""
        service = RiskService(db_session)
        with pytest.raises(ValueError, match="任务列表格式错误"):
            service._validate_and_normalize_template_tasks("not_a_list", "test_template")

    def test_validate_template_tasks_empty(self, db_session):
        """TC-COV-RISK-009c: Empty task list raises error."""
        service = RiskService(db_session)
        with pytest.raises(ValueError, match="任务列表不能为空"):
            service._validate_and_normalize_template_tasks([], "test_template")

    def test_validate_template_tasks_invalid_item(self, db_session):
        """TC-COV-RISK-009d: Invalid task item raises error."""
        service = RiskService(db_session)
        with pytest.raises(ValueError, match="格式错误"):
            service._validate_and_normalize_template_tasks(["not_a_dict"], "test_template")

    def test_validate_template_tasks_missing_fields(self, db_session):
        """TC-COV-RISK-009e: Task missing required fields raises error."""
        service = RiskService(db_session)
        with pytest.raises(ValueError, match="缺少必要字段"):
            service._validate_and_normalize_template_tasks([{"task_name": ""}], "test_template")

    def test_validate_template_tasks_invalid_duration(self, db_session):
        """TC-COV-RISK-009f: Invalid duration raises error."""
        service = RiskService(db_session)
        with pytest.raises(ValueError, match="时长非法"):
            service._validate_and_normalize_template_tasks(
                [{"task_name": "Task", "task_type": "Type", "duration_minutes": "invalid"}], "test_template"
            )

    def test_validate_template_tasks_zero_duration(self, db_session):
        """TC-COV-RISK-009g: Zero duration raises error."""
        service = RiskService(db_session)
        with pytest.raises(ValueError, match="时长必须大于0"):
            service._validate_and_normalize_template_tasks(
                [{"task_name": "Task", "task_type": "Type", "duration_minutes": 0}], "test_template"
            )

    @pytest.mark.asyncio
    async def test_export_risk_json(self, db_session):
        """TC-COV-RISK-010: Export risk data in JSON format."""
        service = RiskService(db_session)
        result = await service.export_risk(9999, 30, "json")
        assert result["format"] == "json"
        assert "items" in result

    @pytest.mark.asyncio
    async def test_export_risk_csv(self, db_session):
        """TC-COV-RISK-010b: Export risk data in CSV format."""
        service = RiskService(db_session)
        result = await service.export_risk(9999, 30, "csv")
        assert result["format"] == "csv"
        assert "filename" in result
        assert "content" in result
        assert "risk_score" in result["content"]

    @pytest.mark.asyncio
    async def test_export_risk_pdf(self, db_session):
        """TC-COV-RISK-010c: Export risk data in PDF format."""
        service = RiskService(db_session)
        result = await service.export_risk(9999, 30, "pdf")
        assert result["format"] == "pdf"
        assert "filename" in result
        assert "content" in result

    @pytest.mark.asyncio
    async def test_export_risk_default_format(self, db_session):
        """TC-COV-RISK-010d: Export with default format returns CSV."""
        service = RiskService(db_session)
        result = await service.export_risk(9999, 30, "")
        assert result["format"] == "csv"
