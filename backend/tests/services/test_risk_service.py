"""Tests for RiskService and risk-related utilities."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import ANY, AsyncMock, MagicMock, patch

import pytest

from app.core.risk_thresholds import (
    get_fusion_threshold,
    get_threshold_by_modality,
    should_fallback,
)
from app.models.intervention import (
    InterventionPlan,
    InterventionTask,
    InterventionTemplate,
)
from app.models.risk import RiskAssessment, WarningSetting
from app.services.intervention_service import InterventionRecommendation
from app.services.risk_service import (
    RiskService,
    _sanitize_csv_cell,
    shutdown_pdf_executor,
)


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
        # M-Core-11: 低置信度不再强制返回 moderate，返回实际分值对应的阈值
        assert get_fusion_threshold(90, confidence=0.3) == 82

    def test_get_fusion_threshold_with_high_score(self):
        assert get_fusion_threshold(85, confidence=0.9) == 82

    def test_should_fallback_when_unavailable(self):
        assert should_fallback(confidence=0.9, availability=False) is True

    def test_should_not_fallback_when_confident_and_available(self):
        assert should_fallback(confidence=0.8, availability=True) is False

    def test_intervention_recommendation_for_high_risk(self):
        level, actions = InterventionRecommendation.build_from_risk_level(
            4, dominant_modality="physiological"
        )
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
        assert 6 <= diff.days < 8

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
            service._validate_and_normalize_template_tasks(
                "not_a_list", "test_template"
            )

    def test_validate_template_tasks_empty(self, db_session):
        """TC-COV-RISK-009c: Empty task list raises error."""
        service = RiskService(db_session)
        with pytest.raises(ValueError, match="任务列表不能为空"):
            service._validate_and_normalize_template_tasks([], "test_template")

    def test_validate_template_tasks_invalid_item(self, db_session):
        """TC-COV-RISK-009d: Invalid task item raises error."""
        service = RiskService(db_session)
        with pytest.raises(ValueError, match="格式错误"):
            service._validate_and_normalize_template_tasks(
                ["not_a_dict"], "test_template"
            )

    def test_validate_template_tasks_missing_fields(self, db_session):
        """TC-COV-RISK-009e: Task missing required fields raises error."""
        service = RiskService(db_session)
        with pytest.raises(ValueError, match="缺少必要字段"):
            service._validate_and_normalize_template_tasks(
                [{"task_name": ""}], "test_template"
            )

    def test_validate_template_tasks_invalid_duration(self, db_session):
        """TC-COV-RISK-009f: Invalid duration raises error."""
        service = RiskService(db_session)
        with pytest.raises(ValueError, match="时长非法"):
            service._validate_and_normalize_template_tasks(
                [
                    {
                        "task_name": "Task",
                        "task_type": "Type",
                        "duration_minutes": "invalid",
                    }
                ],
                "test_template",
            )

    def test_validate_template_tasks_zero_duration(self, db_session):
        """TC-COV-RISK-009g: Zero duration raises error."""
        service = RiskService(db_session)
        with pytest.raises(ValueError, match="时长必须大于0"):
            service._validate_and_normalize_template_tasks(
                [{"task_name": "Task", "task_type": "Type", "duration_minutes": 0}],
                "test_template",
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
        # H-Svc-9: 重建 PDF 线程池（可能被前一个 TestClient lifespan 关闭）
        from concurrent.futures import ThreadPoolExecutor

        import app.services.risk_service as _rs

        if _rs._pdf_executor._shutdown:
            _rs._pdf_executor = ThreadPoolExecutor(
                max_workers=4, thread_name_prefix="pdf_gen"
            )
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


# ============================================================================
# T-303 扩展测试：覆盖 assess_structured / _check_warning_trigger / 干预生成 /
# _classify_report_factors / _sanitize_csv_cell / shutdown_pdf_executor
# ============================================================================


class TestSanitizeCsvCell:
    """C-Svc-4 修复：CSV 公式注入防护."""

    def test_passthrough_non_string(self):
        """int/float/None 原样返回."""
        assert _sanitize_csv_cell(42) == 42
        assert _sanitize_csv_cell(3.14) == 3.14
        assert _sanitize_csv_cell(None) is None

    def test_passthrough_empty_string(self):
        """空字符串原样返回."""
        assert _sanitize_csv_cell("") == ""

    def test_passthrough_normal_string(self):
        """普通字符串原样返回."""
        assert _sanitize_csv_cell("hello") == "hello"
        assert _sanitize_csv_cell("正常文本") == "正常文本"

    def test_escape_equals_prefix(self):
        """以 = 开头的字符串前置单引号."""
        assert _sanitize_csv_cell("=cmd|'/c calc'!A1") == "'=cmd|'/c calc'!A1"

    def test_escape_plus_prefix(self):
        assert _sanitize_csv_cell("+1+2") == "'+1+2"

    def test_escape_minus_prefix(self):
        assert _sanitize_csv_cell("-1-2") == "'-1-2"

    def test_escape_at_prefix(self):
        assert _sanitize_csv_cell("@admin") == "'@admin"

    def test_escape_tab_prefix(self):
        assert _sanitize_csv_cell("\tmalicious") == "'\tmalicious"

    def test_escape_cr_prefix(self):
        assert _sanitize_csv_cell("\rmalicious") == "'\rmalicious"

    def test_escape_lf_prefix(self):
        assert _sanitize_csv_cell("\nmalicious") == "'\nmalicious"


class TestShutdownPdfExecutor:
    """H-Svc-9 修复：PDF 线程池关闭."""

    def test_shutdown_sets_shutdown_flag(self):
        """shutdown_pdf_executor 应关闭线程池."""
        from concurrent.futures import ThreadPoolExecutor

        import app.services.risk_service as _rs

        # 保存原 executor 并替换为新的，避免污染全局状态
        try:
            _rs._pdf_executor = ThreadPoolExecutor(
                max_workers=1, thread_name_prefix="test_pdf"
            )
            shutdown_pdf_executor()
            assert _rs._pdf_executor._shutdown is True
        finally:
            # 重建全局 executor 供后续测试使用
            _rs._pdf_executor = ThreadPoolExecutor(
                max_workers=4, thread_name_prefix="pdf_gen"
            )


# ----------------------------------------------------------------------------
# assess_structured 测试（行 121-250，整个方法零测试）
# ----------------------------------------------------------------------------


class TestAssessStructured:
    """assess_structured 全分支覆盖."""

    @pytest.fixture
    def student_payload(self):
        return {
            "identity_type": "student",
            "is_student": "1",
            "study_year": 3,
            "age": 20,
            "gender": 1,
            "cgpa": 3.5,
            "stress_level": 7,
            "sleep_duration": 5,
            "social_support": 3,
            "financial_pressure": 6,
            "family_history": 0,
            "academic_pressure": 7,
            "exercise_frequency": 2,
            "anxiety": 8,
            "panic_attack": 4,
            "treatment_seeking": 0,
            "total_score": 30,
        }

    @pytest.mark.asyncio
    async def test_student_normal_path(
        self, db_session, seeded_user_id, student_payload
    ):
        """TC-AS-001: 学生身份正常路径，模型预测成功."""
        service = RiskService(db_session)
        # mock 模型预测成功
        mock_result = {
            "prediction": 1,
            "probability": 0.85,
            "risk_score": 75.0,
            "risk_level": 3,
            "model_used": "structured_logistic_regression_quick",
        }
        with patch("app.services.risk_service_assessment.model_engine") as mock_engine, patch(
            "app.services.risk_service._schedule_warning_and_intervention"
        ) as mock_sched:
            mock_engine.predict_structured = AsyncMock(return_value=mock_result)
            mock_engine.explain_prediction = AsyncMock(
                return_value=[
                    {"feature": "anxiety", "importance": 0.4, "direction": "positive"}
                ]
            )
            result = await service.assess_structured(seeded_user_id, student_payload)

        assert result["risk_score"] == 75.0
        assert result["risk_level"] == 3
        # level=3 → severity="high" (RISK_LEVEL_LABELS[3])
        assert result["severity"] == "high"
        # PERF-P1-004: warning 异步处理, 同步返回 None (pending)
        assert result["warning_generated"] is None
        assert result["warning_id"] is None
        assert result["risk_factors"][0]["feature"] == "anxiety"
        # 验证 fire-and-forget 被调度
        mock_sched.assert_called_once_with(seeded_user_id, ANY, 3)
        # 验证 StructuredAssessment 与 RiskAssessment 落库
        from sqlalchemy import select as sa_select

        from app.models.assessment import StructuredAssessment

        sa_rows = (
            (await db_session.execute(sa_select(StructuredAssessment))).scalars().all()
        )
        assert len(sa_rows) >= 1
        ra_rows = (await db_session.execute(sa_select(RiskAssessment))).scalars().all()
        assert len(ra_rows) >= 1

    @pytest.mark.asyncio
    async def test_non_student_overwrites_fields(
        self, db_session, seeded_user_id, student_payload
    ):
        """TC-AS-002: 非学生身份强制覆盖 study_year/academic_pressure."""
        student_payload["identity_type"] = "teacher"
        student_payload["is_student"] = 0
        student_payload["study_year"] = 5
        student_payload["academic_pressure"] = 9
        service = RiskService(db_session)
        mock_result = {
            "prediction": 0,
            "probability": 0.2,
            "risk_score": 15.0,
            "risk_level": 0,
            "model_used": "test",
        }
        with patch("app.services.risk_service_assessment.model_engine") as mock_engine:
            mock_engine.predict_structured = AsyncMock(return_value=mock_result)
            mock_engine.explain_prediction = AsyncMock(return_value=[])
            await service.assess_structured(seeded_user_id, student_payload)
        # 验证 study_year 和 academic_pressure 被强制为 0
        from sqlalchemy import select as sa_select

        from app.models.assessment import StructuredAssessment

        sa = (
            (await db_session.execute(sa_select(StructuredAssessment)))
            .scalars()
            .first()
        )
        assert sa.data_payload["study_year"] == 0
        assert sa.data_payload["academic_pressure"] == 0
        assert sa.data_payload["is_student"] == 0

    @pytest.mark.asyncio
    async def test_is_student_multi_form(
        self, db_session, seeded_user_id, student_payload
    ):
        """TC-AS-003: is_student 多形态输入 (True/"true"/"True")."""
        service = RiskService(db_session)
        mock_result = {
            "prediction": 0,
            "probability": 0.2,
            "risk_score": 15.0,
            "risk_level": 0,
            "model_used": "test",
        }
        with patch("app.services.risk_service_assessment.model_engine") as mock_engine:
            mock_engine.predict_structured = AsyncMock(return_value=mock_result)
            mock_engine.explain_prediction = AsyncMock(return_value=[])
            # is_student=True
            student_payload["is_student"] = True
            await service.assess_structured(seeded_user_id, student_payload)
        from sqlalchemy import select as sa_select

        from app.models.assessment import StructuredAssessment

        sa = (
            (await db_session.execute(sa_select(StructuredAssessment)))
            .scalars()
            .first()
        )
        assert sa.data_payload["is_student"] == 1

    @pytest.mark.asyncio
    async def test_study_year_none_setdefault(
        self, db_session, seeded_user_id, student_payload
    ):
        """TC-AS-004: 学生身份但 study_year 为 None 时 setdefault 0."""
        del student_payload["study_year"]
        service = RiskService(db_session)
        mock_result = {
            "prediction": 0,
            "probability": 0.2,
            "risk_score": 15.0,
            "risk_level": 0,
            "model_used": "test",
        }
        with patch("app.services.risk_service_assessment.model_engine") as mock_engine:
            mock_engine.predict_structured = AsyncMock(return_value=mock_result)
            mock_engine.explain_prediction = AsyncMock(return_value=[])
            await service.assess_structured(seeded_user_id, student_payload)
        from sqlalchemy import select as sa_select

        from app.models.assessment import StructuredAssessment

        sa = (
            (await db_session.execute(sa_select(StructuredAssessment)))
            .scalars()
            .first()
        )
        assert sa.data_payload["study_year"] == 0

    @pytest.mark.asyncio
    async def test_model_exception_fallback_heuristic(
        self, db_session, seeded_user_id, student_payload
    ):
        """TC-AS-005: 模型预测异常走 _calculate_heuristic_score 回退."""
        service = RiskService(db_session)
        with patch("app.services.risk_service_assessment.model_engine") as mock_engine:
            mock_engine.predict_structured = AsyncMock(
                side_effect=RuntimeError("model unavailable")
            )
            mock_engine.explain_prediction = AsyncMock(
                side_effect=RuntimeError("model unavailable")
            )
            result = await service.assess_structured(seeded_user_id, student_payload)
        # 验证回退路径
        assert result["risk_factors"][0]["feature"] == "anxiety"
        assert result["risk_factors"][1]["feature"] == "stress_level"
        # 模型异常时使用启发式分数
        assert result["risk_score"] > 0

    @pytest.mark.asyncio
    async def test_risk_level_below_2_no_intervention(
        self, db_session, seeded_user_id, student_payload
    ):
        """TC-AS-006: risk_level<2 时不生成干预计划."""
        service = RiskService(db_session)
        mock_result = {
            "prediction": 0,
            "probability": 0.1,
            "risk_score": 10.0,
            "risk_level": 1,
            "model_used": "test",
        }
        with patch("app.services.risk_service_assessment.model_engine") as mock_engine:
            mock_engine.predict_structured = AsyncMock(return_value=mock_result)
            mock_engine.explain_prediction = AsyncMock(return_value=[])
            result = await service.assess_structured(seeded_user_id, student_payload)
        assert result["intervention_level"] is None
        assert result["intervention_actions"] == []

    @pytest.mark.asyncio
    async def test_risk_level_2_with_template_generates_intervention(
        self, db_session, seeded_user_id, student_payload
    ):
        """TC-AS-007: risk_level>=2 且有模板时生成干预计划."""
        # 准备 InterventionTemplate
        template = InterventionTemplate(
            template_name="中度风险干预",
            applicable_levels=[2, 3],
            task_list=[
                {"task_name": "情绪日记", "task_type": "diary", "duration_minutes": 15},
                {
                    "task_name": "呼吸练习",
                    "task_type": "exercise",
                    "duration_minutes": 10,
                },
            ],
            estimated_weeks=4,
            status="active",
        )
        db_session.add(template)
        await db_session.flush()
        service = RiskService(db_session)
        mock_result = {
            "prediction": 1,
            "probability": 0.7,
            "risk_score": 55.0,
            "risk_level": 2,
            "model_used": "test",
        }
        with patch("app.services.risk_service_assessment.model_engine") as mock_engine:
            mock_engine.predict_structured = AsyncMock(return_value=mock_result)
            mock_engine.explain_prediction = AsyncMock(return_value=[])
            result = await service.assess_structured(seeded_user_id, student_payload)
        assert result["intervention_level"] is not None
        assert len(result["intervention_actions"]) > 0

    @pytest.mark.asyncio
    async def test_risk_level_2_no_template_returns_actions(
        self, db_session, seeded_user_id, student_payload
    ):
        """TC-AS-008: PERF-P1-004 改造后: risk_level>=2 时 intervention_actions 由静态推荐生成.

        原 H-Svc-8 修复 (无模板清空 actions) 已移除: plan 创建改为 fire-and-forget,
        intervention_actions 为静态推荐 (build_from_risk_level), 非依赖 DB 的实际计划.
        无模板时仅 log warning, 不影响响应中的推荐 actions.
        """
        service = RiskService(db_session)
        mock_result = {
            "prediction": 1,
            "probability": 0.7,
            "risk_score": 55.0,
            "risk_level": 2,
            "model_used": "test",
        }
        with patch("app.services.risk_service_assessment.model_engine") as mock_engine, patch(
            "app.services.risk_service._schedule_warning_and_intervention"
        ):
            mock_engine.predict_structured = AsyncMock(return_value=mock_result)
            mock_engine.explain_prediction = AsyncMock(return_value=[])
            result = await service.assess_structured(seeded_user_id, student_payload)
        # PERF-P1-004: intervention_actions 为静态推荐, 不再因无模板而清空
        assert result["intervention_level"] is not None
        assert len(result["intervention_actions"]) > 0


# ----------------------------------------------------------------------------
# PERF-P1-004: fire-and-forget warning + intervention 测试
# ----------------------------------------------------------------------------


class TestWarningInterventionFireAndForget:
    """PERF-P1-004: 验证 _schedule_warning_and_intervention + _trigger_warning_and_intervention."""

    def test_schedule_does_not_block(self):
        """_schedule_warning_and_intervention 应调度任务但不阻塞当前调用."""
        from app.services.risk_service import (
            _schedule_warning_and_intervention,
        )

        with patch("asyncio.ensure_future") as mock_ensure:
            mock_task = MagicMock()
            mock_ensure.return_value = mock_task

            _schedule_warning_and_intervention(user_id=1, risk_id=10, risk_level=3)

            mock_ensure.assert_called_once()
            # 任务引用应存入集合 (或注册了 discard 回调)
            assert mock_task.add_done_callback.called

    def test_schedule_does_not_raise_on_error(self):
        """asyncio.ensure_future 抛异常时不应传播给调用方."""
        from app.services.risk_service import _schedule_warning_and_intervention

        with patch(
            "asyncio.ensure_future", side_effect=RuntimeError("event loop closed")
        ):
            # 不应抛异常
            _schedule_warning_and_intervention(user_id=1, risk_id=10, risk_level=3)

    def test_schedule_registers_done_callbacks(self):
        """任务应注册 discard 和 _log_warning_intervention_exception 回调."""
        from app.services.risk_service import _schedule_warning_and_intervention

        with patch("asyncio.ensure_future") as mock_ensure:
            mock_task = MagicMock()
            mock_ensure.return_value = mock_task

            _schedule_warning_and_intervention(user_id=1, risk_id=10, risk_level=3)

            # add_done_callback 应被调用至少 2 次 (discard + log_exception)
            assert mock_task.add_done_callback.call_count >= 2

    async def test_trigger_uses_independent_session(self):
        """_trigger_warning_and_intervention 应使用 AsyncSessionLocal 独立 session."""
        from app.services.risk_service import _trigger_warning_and_intervention

        with patch("app.core.database.AsyncSessionLocal") as mock_session_cls, patch(
            "app.services.risk_service.RiskService"
        ) as mock_service_cls:
            mock_db = AsyncMock()
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            # mock RiskAssessment 查询返回
            mock_risk = MagicMock()
            mock_risk.user_id = 1
            mock_risk.risk_level = 3
            mock_db.execute = AsyncMock(
                return_value=MagicMock(
                    scalar_one_or_none=MagicMock(return_value=mock_risk)
                )
            )

            mock_service = MagicMock()
            mock_service.trigger_warning_for_risk = AsyncMock(return_value=None)
            mock_service.generate_intervention_for_risk = AsyncMock(return_value=None)
            mock_service_cls.return_value = mock_service

            await _trigger_warning_and_intervention(user_id=1, risk_id=10, risk_level=3)

            # 验证使用了独立 session
            mock_session_cls.assert_called_once()
            # 验证调用了 trigger_warning + generate_intervention
            mock_service.trigger_warning_for_risk.assert_called_once_with(mock_risk)
            mock_service.generate_intervention_for_risk.assert_called_once_with(
                mock_risk
            )
            # 验证 commit
            mock_db.commit.assert_awaited_once()

    async def test_trigger_handles_risk_not_found(self):
        """_trigger_warning_and_intervention: RiskAssessment 不存在时安全返回."""
        from app.services.risk_service import _trigger_warning_and_intervention

        with patch("app.core.database.AsyncSessionLocal") as mock_session_cls:
            mock_db = AsyncMock()
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            mock_db.execute = AsyncMock(
                return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
            )

            # 不应抛异常
            await _trigger_warning_and_intervention(
                user_id=1, risk_id=999, risk_level=3
            )

            # 不应调用 commit (无数据可写)
            mock_db.commit.assert_not_awaited()


# ----------------------------------------------------------------------------
# _check_warning_trigger 测试（行 585-664，整个方法零测试）
# ----------------------------------------------------------------------------


class TestCheckWarningTrigger:
    """_check_warning_trigger 全分支覆盖."""

    @pytest.fixture
    async def seeded_risk_low(self, db_session, seeded_user_id):
        """插入一条 risk_level=1 的 RiskAssessment."""
        risk = RiskAssessment(
            user_id=seeded_user_id,
            risk_score=15.0,
            risk_level=1,
            structured_score=15.0,
            models_used=["test"],
            risk_factors=[],
            assessment_type="structured",
        )
        db_session.add(risk)
        await db_session.flush()
        return risk

    @pytest.fixture
    async def seeded_risk_high(self, db_session, seeded_user_id):
        """插入一条 risk_level=3 的 RiskAssessment."""
        risk = RiskAssessment(
            user_id=seeded_user_id,
            risk_score=55.0,
            risk_level=3,
            structured_score=55.0,
            models_used=["test"],
            risk_factors=[],
            assessment_type="structured",
        )
        db_session.add(risk)
        await db_session.flush()
        return risk

    @pytest.mark.asyncio
    async def test_low_risk_returns_none(self, db_session, seeded_user_id):
        """TC-CWT-001: risk_level<2 (should_warn=False) 直接返回 None."""
        risk = RiskAssessment(
            user_id=seeded_user_id,
            risk_score=15.0,
            risk_level=1,
            structured_score=15.0,
            models_used=["test"],
            risk_factors=[],
            assessment_type="structured",
        )
        db_session.add(risk)
        await db_session.flush()
        service = RiskService(db_session)
        result = await service._check_warning_trigger(
            user_id=seeded_user_id, current_risk=risk
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_first_warning_no_setting(
        self, db_session, seeded_user_id, seeded_risk_low
    ):
        """TC-CWT-002: 首次告警 + 无 WarningSetting，threshold 默认 2，level>=2 创建 warning."""
        risk = RiskAssessment(
            user_id=seeded_user_id,
            risk_score=55.0,
            risk_level=3,
            structured_score=55.0,
            models_used=["test"],
            risk_factors=[],
            assessment_type="structured",
        )
        db_session.add(risk)
        await db_session.flush()
        service = RiskService(db_session)
        result = await service._check_warning_trigger(
            user_id=seeded_user_id, current_risk=risk
        )
        assert result is not None
        assert result.current_level == 3
        assert result.previous_level == 1  # 来自 seeded_risk_low
        assert "上升到" in result.trigger_reason

    @pytest.mark.asyncio
    async def test_threshold_above_current_returns_none(
        self, db_session, seeded_user_id
    ):
        """TC-CWT-003: WarningSetting.threshold_level 高于当前 level 返回 None."""
        # 插入 setting，threshold=4
        setting = WarningSetting(user_id=seeded_user_id, threshold_level=4)
        db_session.add(setting)
        await db_session.flush()
        risk = RiskAssessment(
            user_id=seeded_user_id,
            risk_score=55.0,
            risk_level=3,
            structured_score=55.0,
            models_used=["test"],
            risk_factors=[],
            assessment_type="structured",
        )
        db_session.add(risk)
        await db_session.flush()
        service = RiskService(db_session)
        result = await service._check_warning_trigger(
            user_id=seeded_user_id, current_risk=risk
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_level_not_elevated_reason(
        self, db_session, seeded_user_id, seeded_risk_high
    ):
        """TC-CWT-004: level 未升级但仍>=2，reason 含"需要咨询师关注"."""
        # 再插入一条 level=3 的当前 risk，时间晚于 seeded_risk_high
        risk = RiskAssessment(
            user_id=seeded_user_id,
            risk_score=58.0,
            risk_level=3,
            structured_score=58.0,
            models_used=["test"],
            risk_factors=[],
            assessment_type="structured",
        )
        db_session.add(risk)
        await db_session.flush()
        service = RiskService(db_session)
        result = await service._check_warning_trigger(
            user_id=seeded_user_id, current_risk=risk
        )
        assert result is not None
        assert "需要咨询师关注" in result.trigger_reason

    @pytest.mark.asyncio
    async def test_previous_risk_level_none(self, db_session, seeded_user_id):
        """TC-CWT-005: H-Svc-7 修复：previous.risk_level 为 None 不抛 TypeError."""
        # 使用 mock previous（risk_level=None），SQLite NOT NULL 约束无法真实写入 NULL
        previous = MagicMock()
        previous.risk_level = None
        previous.id = 999

        # current_risk（不需要落库）
        current_risk = MagicMock()
        current_risk.user_id = seeded_user_id
        current_risk.id = 1000
        current_risk.risk_level = 3

        # mock db.execute 返回序列：previous / setting / duplicate / binding
        mock_previous_result = MagicMock()
        mock_previous_result.scalar_one_or_none.return_value = previous

        mock_setting_result = MagicMock()
        mock_setting_result.scalar_one_or_none.return_value = None  # 无 setting

        mock_duplicate_result = MagicMock()
        mock_duplicate_result.scalar_one_or_none.return_value = None  # 无 duplicate

        mock_binding_result = MagicMock()
        mock_binding_result.scalars.return_value.first.return_value = None  # 无 binding

        # 使用真实 db_session 但 mock execute 序列
        service = RiskService(db_session)
        with patch.object(
            db_session,
            "execute",
            side_effect=[
                mock_previous_result,
                mock_setting_result,
                mock_duplicate_result,
                mock_binding_result,
            ],
        ):
            # savepoint 包裹 add+flush 需要真实事务，但因为 execute 被 mock，
            # warning 不会被实际查询，会作为内存对象返回
            # 使用 begin_nested 真实 savepoint（但 add 不会触发实际 SQL）
            result = await service._check_warning_trigger(
                user_id=seeded_user_id,
                current_risk=current_risk,
            )
        assert result is not None
        assert result.previous_level == 0  # None 被兜底为 0
        assert "上升到" in result.trigger_reason

    @pytest.mark.asyncio
    async def test_duplicate_warning_returns_existing(
        self, db_session, seeded_user_id, seeded_risk_high
    ):
        """TC-CWT-006: 已存在相同 risk_assessment_id 的 warning 直接返回."""
        # 直接对 seeded_risk_high 触发告警
        service = RiskService(db_session)
        first = await service._check_warning_trigger(
            user_id=seeded_user_id, current_risk=seeded_risk_high
        )
        assert first is not None
        # 再次触发应返回相同记录
        second = await service._check_warning_trigger(
            user_id=seeded_user_id, current_risk=seeded_risk_high
        )
        assert second is not None
        assert second.id == first.id

    @pytest.mark.asyncio
    async def test_binds_active_counselor(
        self, db_session, seeded_user_id, seeded_risk_low
    ):
        """TC-CWT-007: 绑定活跃咨询师到 warning."""
        # 创建一个 counselor 用户
        from app.core.pii_crypto import compute_blind_index
        from app.core.security import get_password_hash
        from app.models.user import User, UserCounselorBinding

        counselor = User(
            username="test_counselor_w",
            email="counselor_w@test.com",
            email_hash=compute_blind_index("counselor_w@test.com", "email"),
            password_hash=get_password_hash("TestPwd-2024!"),
            role="counselor",
            status="active",
        )
        db_session.add(counselor)
        await db_session.flush()
        binding = UserCounselorBinding(
            user_id=seeded_user_id,
            counselor_id=counselor.id,
            bind_code="T12345",
            status=BindingStatus.ACTIVE,
        )
        # bound_at 是 server_default，但 sqlite 可能需要显式设置
        binding.bound_at = datetime.now(timezone.utc)
        db_session.add(binding)
        await db_session.flush()
        # 触发告警
        risk = RiskAssessment(
            user_id=seeded_user_id,
            risk_score=55.0,
            risk_level=3,
            structured_score=55.0,
            models_used=["test"],
            risk_factors=[],
            assessment_type="structured",
        )
        db_session.add(risk)
        await db_session.flush()
        service = RiskService(db_session)
        result = await service._check_warning_trigger(
            user_id=seeded_user_id, current_risk=risk
        )
        assert result is not None
        assert result.counselor_id == counselor.id


# 需要的额外 import 放在文件顶部已经导入


class TestTriggerWarningForRisk:
    """trigger_warning_for_risk 包装器."""

    @pytest.mark.asyncio
    async def test_wrapper_delegates_to_check(self, db_session, seeded_user_id):
        """TC-TWR-001: 包装器转调 _check_warning_trigger."""
        risk = RiskAssessment(
            user_id=seeded_user_id,
            risk_score=15.0,
            risk_level=1,
            structured_score=15.0,
            models_used=["test"],
            risk_factors=[],
            assessment_type="structured",
        )
        db_session.add(risk)
        await db_session.flush()
        service = RiskService(db_session)
        result = await service.trigger_warning_for_risk(risk)
        assert result is None  # level=1 不触发告警


# ----------------------------------------------------------------------------
# 干预计划生成测试（行 669-757，完全零测试）
# ----------------------------------------------------------------------------


class TestGenerateInterventionForRisk:
    """generate_intervention_for_risk 全分支覆盖."""

    @pytest.mark.asyncio
    async def test_level_below_2_returns_none(self, db_session, seeded_user_id):
        """TC-GIF-001: level<2 直接 return."""
        risk = RiskAssessment(
            user_id=seeded_user_id,
            risk_score=15.0,
            risk_level=1,
            structured_score=15.0,
            models_used=["test"],
            risk_factors=[],
            assessment_type="structured",
        )
        db_session.add(risk)
        await db_session.flush()
        service = RiskService(db_session)
        # 应直接返回，不创建 plan
        await service.generate_intervention_for_risk(risk)
        # 验证无 InterventionPlan 创建
        from sqlalchemy import select as sa_select

        plans = (await db_session.execute(sa_select(InterventionPlan))).scalars().all()
        assert len(plans) == 0

    @pytest.mark.asyncio
    async def test_level_2_delegates_to_auto_generate(self, db_session, seeded_user_id):
        """TC-GIF-002: level>=2 转调 _auto_generate_intervention."""
        # 先创建模板
        template = InterventionTemplate(
            template_name="测试模板",
            applicable_levels=[2],
            task_list=[
                {"task_name": "测试任务", "task_type": "diary", "duration_minutes": 15}
            ],
            estimated_weeks=2,
            status="active",
        )
        db_session.add(template)
        await db_session.flush()
        risk = RiskAssessment(
            user_id=seeded_user_id,
            risk_score=55.0,
            risk_level=2,
            structured_score=55.0,
            models_used=["test"],
            risk_factors=[],
            assessment_type="structured",
        )
        db_session.add(risk)
        await db_session.flush()
        service = RiskService(db_session)
        await service.generate_intervention_for_risk(risk)
        from sqlalchemy import select as sa_select

        plans = (await db_session.execute(sa_select(InterventionPlan))).scalars().all()
        assert len(plans) == 1


class TestAutoGenerateIntervention:
    """_auto_generate_intervention 全分支覆盖."""

    @pytest.mark.asyncio
    async def test_no_active_plan_creates_new(self, db_session, seeded_user_id):
        """TC-AGI-001: 无 active plan 新建."""
        template = InterventionTemplate(
            template_name="新建测试",
            applicable_levels=[2],
            task_list=[
                {"task_name": "任务A", "task_type": "diary", "duration_minutes": 15}
            ],
            estimated_weeks=2,
            status="active",
        )
        db_session.add(template)
        await db_session.flush()
        service = RiskService(db_session)
        plan = await service._auto_generate_intervention(
            user_id=seeded_user_id, risk_level=2
        )
        assert plan is not None
        assert plan.status == "active"
        assert plan.risk_level == 2

    @pytest.mark.asyncio
    async def test_existing_plan_level_elevated_creates_new(
        self, db_session, seeded_user_id
    ):
        """TC-AGI-002: M17 修复：有 active plan 且 level 升高，建新 plan+cancel 旧 plan."""
        # 先创建旧 plan (risk_level=2)
        old_plan = InterventionPlan(
            user_id=seeded_user_id,
            plan_name="旧计划",
            risk_level=2,
            status="active",
            start_date=__import__("datetime").date.today(),
        )
        db_session.add(old_plan)
        await db_session.flush()
        # 创建模板
        template = InterventionTemplate(
            template_name="升级计划模板",
            applicable_levels=[3, 4],
            task_list=[
                {
                    "task_name": "升级任务",
                    "task_type": "exercise",
                    "duration_minutes": 30,
                }
            ],
            estimated_weeks=4,
            status="active",
        )
        db_session.add(template)
        await db_session.flush()
        service = RiskService(db_session)
        new_plan = await service._auto_generate_intervention(
            user_id=seeded_user_id, risk_level=3
        )
        assert new_plan is not None
        assert new_plan.id != old_plan.id
        assert new_plan.risk_level == 3
        # 旧 plan 应被 cancel
        from sqlalchemy import select as sa_select

        await db_session.flush()
        old_refreshed = (
            (
                await db_session.execute(
                    sa_select(InterventionPlan).where(
                        InterventionPlan.id == old_plan.id
                    )
                )
            )
            .scalars()
            .first()
        )
        assert old_refreshed.status == "cancelled"

    @pytest.mark.asyncio
    async def test_existing_plan_level_not_elevated_returns_old(
        self, db_session, seeded_user_id
    ):
        """TC-AGI-003: 有 active plan 且 level 未升高，返回旧 plan."""
        old_plan = InterventionPlan(
            user_id=seeded_user_id,
            plan_name="原计划",
            risk_level=3,
            status="active",
            start_date=__import__("datetime").date.today(),
        )
        db_session.add(old_plan)
        await db_session.flush()
        service = RiskService(db_session)
        result = await service._auto_generate_intervention(
            user_id=seeded_user_id, risk_level=3
        )
        assert result is not None
        assert result.id == old_plan.id

    @pytest.mark.asyncio
    async def test_existing_plan_elevated_but_no_template_returns_old(
        self, db_session, seeded_user_id
    ):
        """TC-AGI-004: H-Svc-8：有 plan 升级但无模板创建失败，返回旧 plan 不 cancel."""
        old_plan = InterventionPlan(
            user_id=seeded_user_id,
            plan_name="旧计划",
            risk_level=2,
            status="active",
            start_date=__import__("datetime").date.today(),
        )
        db_session.add(old_plan)
        await db_session.flush()
        # 不创建任何模板
        service = RiskService(db_session)
        result = await service._auto_generate_intervention(
            user_id=seeded_user_id, risk_level=3
        )
        assert result is not None
        assert result.id == old_plan.id
        # 旧 plan 仍应是 active
        assert result.status == "active"


class TestCreatePlanFromTemplate:
    """_create_plan_from_template 全分支覆盖."""

    @pytest.mark.asyncio
    async def test_match_by_applicable_levels(self, db_session, seeded_user_id):
        """TC-CPFT-001: 按 applicable_levels 匹配命中."""
        t1 = InterventionTemplate(
            template_name="模板1-低风险",
            applicable_levels=[1, 2],
            task_list=[
                {"task_name": "任务1", "task_type": "diary", "duration_minutes": 10}
            ],
            estimated_weeks=2,
            status="active",
        )
        t2 = InterventionTemplate(
            template_name="模板2-高风险",
            applicable_levels=[3, 4],
            task_list=[
                {"task_name": "任务2", "task_type": "exercise", "duration_minutes": 30}
            ],
            estimated_weeks=4,
            status="active",
        )
        db_session.add_all([t1, t2])
        await db_session.flush()
        service = RiskService(db_session)
        plan = await service._create_plan_from_template(
            user_id=seeded_user_id, risk_level=3
        )
        assert plan is not None
        assert plan.plan_name == "模板2-高风险"

    @pytest.mark.asyncio
    async def test_no_match_falls_back_to_first(self, db_session, seeded_user_id):
        """TC-CPFT-002: 无匹配但回退首个模板."""
        t1 = InterventionTemplate(
            template_name="通用模板",
            applicable_levels=[1, 2],  # 不含 3
            task_list=[
                {"task_name": "通用任务", "task_type": "diary", "duration_minutes": 15}
            ],
            estimated_weeks=2,
            status="active",
        )
        db_session.add(t1)
        await db_session.flush()
        service = RiskService(db_session)
        plan = await service._create_plan_from_template(
            user_id=seeded_user_id, risk_level=3
        )
        assert plan is not None
        assert plan.plan_name == "通用模板"

    @pytest.mark.asyncio
    async def test_no_active_template_returns_none(self, db_session, seeded_user_id):
        """TC-CPFT-003: H-Svc-8 修复：无任何 active 模板返回 None + 告警日志."""
        service = RiskService(db_session)
        plan = await service._create_plan_from_template(
            user_id=seeded_user_id, risk_level=3
        )
        assert plan is None

    @pytest.mark.asyncio
    async def test_creates_plan_and_tasks(self, db_session, seeded_user_id):
        """TC-CPFT-004: 创建 InterventionPlan + 多个 InterventionTask."""
        template = InterventionTemplate(
            template_name="多任务模板",
            applicable_levels=[2, 3],
            task_list=[
                {"task_name": "任务A", "task_type": "diary", "duration_minutes": 10},
                {"task_name": "任务B", "task_type": "exercise", "duration_minutes": 20},
                {
                    "task_name": "任务C",
                    "task_type": "meditation",
                    "duration_minutes": 15,
                },
            ],
            estimated_weeks=3,
            status="active",
        )
        db_session.add(template)
        await db_session.flush()
        service = RiskService(db_session)
        plan = await service._create_plan_from_template(
            user_id=seeded_user_id, risk_level=2
        )
        assert plan is not None
        # 验证 plan 字段
        assert plan.risk_level == 2
        assert plan.status == "active"
        # 验证 3 个 task 被创建
        from sqlalchemy import select as sa_select

        tasks = (
            (
                await db_session.execute(
                    sa_select(InterventionTask).where(
                        InterventionTask.plan_id == plan.id
                    )
                )
            )
            .scalars()
            .all()
        )
        assert len(tasks) == 3
        # 验证 sort_order
        sort_orders = sorted(t.sort_order for t in tasks)
        assert sort_orders == [0, 1, 2]

    @pytest.mark.asyncio
    async def test_no_active_binding_counselor_id_none(
        self, db_session, seeded_user_id
    ):
        """TC-CPFT-005: 无活跃咨询师绑定 counselor_id=None."""
        template = InterventionTemplate(
            template_name="无咨询师模板",
            applicable_levels=[2],
            task_list=[
                {"task_name": "任务X", "task_type": "diary", "duration_minutes": 15}
            ],
            estimated_weeks=2,
            status="active",
        )
        db_session.add(template)
        await db_session.flush()
        service = RiskService(db_session)
        plan = await service._create_plan_from_template(
            user_id=seeded_user_id, risk_level=2
        )
        assert plan is not None
        assert plan.counselor_id is None


# ----------------------------------------------------------------------------
# _classify_report_factors 测试（行 339-405，整个方法零测试）
# ----------------------------------------------------------------------------


class TestClassifyReportFactors:
    """_classify_report_factors 静态方法全分支覆盖."""

    def _make_record(self, factors):
        """构造 RiskAssessment mock，risk_factors 为指定列表."""
        record = MagicMock()
        record.risk_factors = factors
        return record

    def test_empty_records(self):
        """TC-CRF-001: 空记录列表返回三个空列表."""
        risk, protective, review = RiskService._classify_report_factors([])
        assert risk == []
        assert protective == []
        assert review == []

    def test_string_factor_normalized(self):
        """TC-CRF-002: 字符串因子被归一化为 {importance:0.5, direction:increase}."""
        records = [self._make_record(["anxiety"])]
        risk, protective, review = RiskService._classify_report_factors(records)
        assert len(risk) == 1
        assert risk[0]["feature"] == "anxiety"
        assert risk[0]["importance"] == 0.5
        assert risk[0]["direction"] == "increase"

    def test_non_dict_non_str_skipped(self):
        """TC-CRF-003: 非 dict/str 因子跳过."""
        records = [self._make_record([42, None, 3.14])]
        risk, protective, review = RiskService._classify_report_factors(records)
        assert risk == []
        assert protective == []
        assert review == []

    def test_empty_feature_skipped(self):
        """TC-CRF-004: feature 为空跳过."""
        records = [self._make_record([{"feature": "", "importance": 0.5}])]
        risk, _, _ = RiskService._classify_report_factors(records)
        assert risk == []

    def test_invalid_importance_default(self):
        """TC-CRF-005: importance 非法值默认 0.5."""
        records = [self._make_record([{"feature": "x", "importance": "invalid"}])]
        risk, _, _ = RiskService._classify_report_factors(records)
        assert risk[0]["importance"] == 0.5

    def test_importance_clamped_to_range(self):
        """TC-CRF-006: importance 超出 [0,1] 范围被 clamp."""
        records = [self._make_record([{"feature": "x", "importance": 1.5}])]
        risk, _, _ = RiskService._classify_report_factors(records)
        assert risk[0]["importance"] == 1.0
        records2 = [self._make_record([{"feature": "y", "importance": -0.5}])]
        risk2, _, _ = RiskService._classify_report_factors(records2)
        assert risk2[0]["importance"] == 0.0

    def test_negative_direction_goes_to_protective(self):
        """TC-CRF-007: direction negative/decrease/降低风险 → protective."""
        for direction in ["negative", "decrease", "降低风险"]:
            records = [self._make_record([{"feature": "f", "direction": direction}])]
            _, protective, _ = RiskService._classify_report_factors(records)
            assert len(protective) == 1
            assert protective[0]["direction"] == "decrease"

    def test_other_direction_goes_to_risk(self):
        """TC-CRF-008: direction 其他值 → risk."""
        records = [self._make_record([{"feature": "f", "direction": "positive"}])]
        risk, _, _ = RiskService._classify_report_factors(records)
        assert len(risk) == 1
        assert risk[0]["direction"] == "increase"

    def test_crisis_override_review_flag(self):
        """TC-CRF-009: crisis_override → review_flag type=crisis."""
        records = [
            self._make_record([{"feature": "crisis_override", "importance": 0.5}])
        ]
        _, _, review = RiskService._classify_report_factors(records)
        assert len(review) == 1
        assert review[0]["type"] == "crisis"
        assert review[0]["importance"] >= 0.9

    def test_model_disagreement_review_flag(self):
        """TC-CRF-010: model_disagreement_N_points → review_flag type=disagreement."""
        records = [
            self._make_record(
                [{"feature": "model_disagreement_15_points", "importance": 0.5}]
            )
        ]
        _, _, review = RiskService._classify_report_factors(records)
        assert len(review) == 1
        assert review[0]["type"] == "disagreement"
        assert "15" in review[0]["feature"]

    def test_modality_conflict_review_flag(self):
        """TC-CRF-011: modality_conflict → review_flag type=disagreement."""
        records = [
            self._make_record(
                [{"feature": "modality_conflict_structured_vs_text", "importance": 0.5}]
            )
        ]
        _, _, review = RiskService._classify_report_factors(records)
        assert len(review) == 1
        assert review[0]["type"] == "disagreement"

    def test_deduplication(self):
        """TC-CRF-012: 同 feature 多记录只保留首条."""
        records = [
            self._make_record([{"feature": "anxiety", "importance": 0.8}]),
            self._make_record([{"feature": "anxiety", "importance": 0.3}]),
        ]
        risk, _, _ = RiskService._classify_report_factors(records)
        assert len(risk) == 1
        assert risk[0]["importance"] == 0.8  # 保留首条

    def test_sort_and_truncate_8(self):
        """TC-CRF-013: 排序与截断 8 条."""
        factors = [{"feature": f"f{i}", "importance": i / 10.0} for i in range(1, 11)]
        records = [self._make_record(factors)]
        risk, _, _ = RiskService._classify_report_factors(records)
        assert len(risk) == 8  # 截断为 8
        # 排序：importance 降序
        assert risk[0]["importance"] > risk[7]["importance"]


# ----------------------------------------------------------------------------
# 辅助：BindingStatus 导入
# ----------------------------------------------------------------------------


from app.core.states import BindingStatus  # noqa: E402
