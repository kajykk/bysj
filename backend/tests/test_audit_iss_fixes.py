"""ISS-037/103/104/105/111/112 审计修复回归测试."""

from __future__ import annotations

from datetime import datetime, timezone
from unittest.mock import ANY, AsyncMock, patch

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core import metrics

# conftest.py autouse fixture 会替换模块符号, 但类在模块加载时已被捕获 (与 test_observability_exporter.py 一致)
from app.services.observability_exporter import ObservabilityExporter


class TestMetricsPathNormalization:
    """ISS-037: 无路由模板时路径归一化."""

    def test_numeric_segments_collapsed(self):
        from app.core.middlewares import _normalize_metrics_path

        assert _normalize_metrics_path("/api/v1/users/123") == "/api/v1/users/{id}"
        assert _normalize_metrics_path("/a/123/456/b") == "/a/{id}/b"

    def test_consecutive_numeric_segments_deduped(self):
        from app.core.middlewares import _normalize_metrics_path

        assert _normalize_metrics_path("/x/1/2/3") == "/x/{id}"

    def test_overlong_path_truncated(self):
        from app.core.middlewares import _normalize_metrics_path

        long_path = "/" + "/".join(f"seg{i}" for i in range(20))
        result = _normalize_metrics_path(long_path)
        assert result.endswith("...")

    def test_empty_falls_back(self):
        from app.core.middlewares import _normalize_metrics_path

        assert _normalize_metrics_path("") == "unknown"


class TestWsAuthFailureMetric:
    """ISS-104: WebSocket 认证失败计数."""

    def test_auth_failure_increments_counter(self):
        metrics.ws_auth_failures_total._values.clear()
        from app.core.ws import _inc_ws_auth_failure

        _inc_ws_auth_failure("invalid_token")
        _inc_ws_auth_failure("invalid_token")
        _inc_ws_auth_failure("missing_token")
        assert metrics.ws_auth_failures_total._values[("invalid_token",)] == 2
        assert metrics.ws_auth_failures_total._values[("missing_token",)] == 1

    def test_auth_failure_metric_survives_inc_error(self):
        metrics.ws_auth_failures_total._values.clear()
        from app.core.ws import _inc_ws_auth_failure

        with patch(
            "app.core.metrics.ws_auth_failures_total.inc",
            side_effect=RuntimeError("metric down"),
        ):
            _inc_ws_auth_failure("invalid_token")  # 不应抛出


@pytest.mark.asyncio
async def test_export_failure_increments_error_counter() -> None:
    """ISS-103: _safe_set_* 失败时递增 observability_export_errors_total."""
    metrics.observability_export_errors_total._values.clear()
    exporter = ObservabilityExporter()
    with patch(
        "app.api.v1.observability._compute_channel_stats",
        new=AsyncMock(side_effect=Exception("DB down")),
    ):
        await exporter._safe_set_channel(
            AsyncMock(),
            datetime.now(timezone.utc),
            datetime.now(timezone.utc),
        )
    assert metrics.observability_export_errors_total._values[("channel_stats",)] == 1


@pytest.mark.asyncio
async def test_collect_all_runs_safely_with_session_local(
    monkeypatch,
) -> None:
    """ISS-111: _collect_all 并发采集时单查询失败不阻塞其他 (FM-1)."""
    metrics.observability_export_errors_total._values.clear()
    exporter = ObservabilityExporter()
    exporter._counter_initialized = True

    async def _fake_compute_ok(*args, **kwargs):
        return {"overall_success_rate": 0.5, "total": 10}

    async def _fake_compute_fail(*args, **kwargs):
        raise Exception("boom")

    async def _fake_trend(*args, **kwargs):
        return {"by_status": {"firing": 3}}

    with patch(
        "app.api.v1.observability._compute_channel_stats", new=AsyncMock(
            side_effect=_fake_compute_fail
        )
    ), patch(
        "app.api.v1.observability._compute_am_sync", new=AsyncMock(side_effect=_fake_compute_ok)
    ), patch(
        "app.api.v1.observability._compute_lock_stats",
        new=AsyncMock(
            return_value={
                "memory": {
                    "acquire_rate": 0.9,
                    "fallback_rate": 0.05,
                    "error_rate": 0.01,
                    "total": 20,
                }
            }
        ),
    ), patch(
        "app.api.v1.observability._compute_escalation",
        new=AsyncMock(return_value={"escalation_rate": 0.2, "total_fired": 10}),
    ), patch(
        "app.api.v1.observability._compute_trend", new=AsyncMock(side_effect=_fake_trend)
    ), patch(
        "app.services.observability_exporter.AsyncSessionLocal"
    ) as mock_session_local:
        mock_session = AsyncMock(spec=AsyncSession)
        mock_session_local.return_value.__aenter__.return_value = mock_session

        await exporter._collect_all()

    assert metrics.observability_lock_acquire_rate._values[()] == 0.9
    assert metrics.observability_alert_total._values[("total",)] == 3
    assert metrics.observability_export_errors_total._values[("channel_stats",)] == 1


_STUDENT_PAYLOAD = {
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
async def test_shap_disabled_by_default_skips_explain(
    db_session, seeded_user_id
) -> None:
    """ISS-112: 默认关闭 SHAP, assess_structured 使用启发式因子且不调用 explain."""
    from app.services.risk_service import RiskService

    service = RiskService(db_session)
    mock_result = {
        "prediction": 1,
        "probability": 0.85,
        "risk_score": 75.0,
        "risk_level": 3,
        "model_used": "structured_logistic_regression_quick",
    }
    with patch(
        "app.services.risk_service_assessment.model_engine"
    ) as mock_engine, patch(
        "app.services.risk_service._schedule_warning_and_intervention"
    ):
        mock_engine.predict_structured = AsyncMock(return_value=mock_result)
        mock_engine.explain_prediction = AsyncMock(
            side_effect=AssertionError("should not be called")
        )
        result = await service.assess_structured(seeded_user_id, _STUDENT_PAYLOAD)

    mock_engine.explain_prediction.assert_not_awaited()
    assert result["risk_factors"][0]["feature"] == "anxiety"


@pytest.mark.asyncio
async def test_shap_enabled_calls_explain(db_session, seeded_user_id, monkeypatch) -> None:
    """ISS-112: 开启开关时仍调用 explain_prediction."""
    from app.core.config import settings
    from app.services.risk_service import RiskService

    monkeypatch.setattr(settings, "risk_assessment_shap_explain_enabled", True)
    service = RiskService(db_session)
    mock_result = {
        "prediction": 1,
        "probability": 0.85,
        "risk_score": 75.0,
        "risk_level": 3,
        "model_used": "structured_logistic_regression_quick",
    }
    with patch(
        "app.services.risk_service_assessment.model_engine"
    ) as mock_engine, patch(
        "app.services.risk_service._schedule_warning_and_intervention"
    ):
        mock_engine.predict_structured = AsyncMock(return_value=mock_result)
        mock_engine.explain_prediction = AsyncMock(
            return_value=[
                {
                    "feature": "anxiety",
                    "importance": 0.4,
                    "direction": "positive",
                }
            ]
        )
        result = await service.assess_structured(seeded_user_id, _STUDENT_PAYLOAD)

    mock_engine.explain_prediction.assert_awaited_with(
        ANY, "structured_logistic_regression_quick"
    )
    assert result["risk_factors"][0]["importance"] == 0.4
