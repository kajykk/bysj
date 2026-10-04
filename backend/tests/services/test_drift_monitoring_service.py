"""决策四: DriftMonitoringService 数据不足 vs 异常路径语义测试.

钉死两条路径的关键语义差异 (drift_monitoring_service.py):
1. insufficient-samples (L168-182): baseline_n/current_n < 30 时返回
   psi=0.0 / kl=0.0 / **failed=False** —— 与「干净的无漂移结果」在
   DriftCheckResult 层面完全不可区分, Gauge 会照常推送 psi=0.0.
   这是已知局限 (本测试将其文档化为契约), 运营解读 Grafana 时
   必须结合样本量; PsiKlCalculator 的 0.0 二义性契约见
   test_psi_kl_calculator_contract.py::TestZeroAmbiguityContract.
2. exception path (L103-123): 查询抛异常 -> failed=True + 会话回滚,
   _push_to_gauge 跳过该模态 (SEC-FIX: 不把瞬时 DB 故障呈现为漂移消失).

此前该服务仅有 tests/scripts/p3_verify_drift_monitoring.py 手工验证脚本,
无 pytest 覆盖.
"""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.drift_monitoring_service import (
    MODALITY_COLUMNS,
    DriftCheckResult,
    DriftMonitoringService,
)


class FakeDetector:
    """固定返回值的探测器, 用于区分「走了计算路径」与「跳过计算」."""

    def __init__(self, psi: float = 0.123, kl: float = 0.045) -> None:
        self.psi = psi
        self.kl = kl
        self.calls: list[tuple[list[float], list[float]]] = []

    def calculate_psi(self, baseline, current):  # noqa: ANN001, ANN201
        self.calls.append((list(baseline), list(current)))
        return self.psi

    def calculate_kl(self, baseline, current):  # noqa: ANN001, ANN201
        return self.kl


def _dt_args() -> dict:
    """_check_modality 需要真实 datetime (语句构造发生在 mock 之前)."""
    now = datetime(2026, 10, 2, 12, 0, 0)
    return {
        "baseline_start": now - timedelta(days=7),
        "baseline_end": now - timedelta(hours=24),
        "current_start": now - timedelta(hours=24),
        "now": now,
    }


def _db_result(values: list[float]) -> MagicMock:
    """构造 db.execute() 返回值: .scalars().all() -> values."""
    res = MagicMock()
    res.scalars.return_value.all.return_value = values
    return res


def _mock_db() -> MagicMock:
    db = MagicMock()
    db.execute = AsyncMock()
    db.rollback = AsyncMock()
    return db


class TestInsufficientSamplesPath:
    """<30 样本跳过路径 —— failed=False 是本组测试的核心钉子."""

    @pytest.mark.asyncio
    async def test_insufficient_both_windows_failed_false(self):
        """DM-001: 29/29 -> psi=0.0, failed=False (与无漂移不可区分)."""
        service = DriftMonitoringService(detector=FakeDetector())
        db = _mock_db()
        db.execute.side_effect = [_db_result([0.5] * 29), _db_result([0.6] * 29)]

        result = await service._check_modality(
            db_session=db,
            modality="structured",
            column_name="structured_score",
            **_dt_args(),
        )

        assert result.psi == 0.0
        assert result.kl == 0.0
        assert result.baseline_n == 29
        assert result.current_n == 29
        assert result.alert_created is False
        # 核心契约: 数据不足 NOT 标记为 failed -> Gauge 仍会推送 psi=0.0
        assert result.failed is False

    @pytest.mark.asyncio
    async def test_insufficient_baseline_short_current_long(self):
        """DM-002: 29/100 -> 仍跳过 (任一侧 <30 即跳过)."""
        service = DriftMonitoringService(detector=FakeDetector())
        db = _mock_db()
        db.execute.side_effect = [_db_result([0.5] * 29), _db_result([0.6] * 100)]

        result = await service._check_modality(
            db_session=db,
            modality="text",
            column_name="text_score",
            **_dt_args(),
        )
        assert result.failed is False
        assert result.psi == 0.0
        assert result.baseline_n == 29 and result.current_n == 100

    @pytest.mark.asyncio
    async def test_boundary_30_30_computes(self):
        """DM-003: 30/30 恰好过门禁 -> 走计算路径, 结果携带探测器输出."""
        detector = FakeDetector(psi=0.123, kl=0.045)
        service = DriftMonitoringService(detector=detector)
        db = _mock_db()
        db.execute.side_effect = [_db_result([0.5] * 30), _db_result([0.6] * 30)]

        result = await service._check_modality(
            db_session=db,
            modality="structured",
            column_name="structured_score",
            **_dt_args(),
        )

        assert len(detector.calls) == 1
        assert result.psi == 0.123
        assert result.kl == 0.045
        assert result.failed is False
        assert result.alert_created is False  # 0.123 <= 0.25 不建告警

    @pytest.mark.asyncio
    async def test_none_values_filtered_before_count(self):
        """DM-004: 标量列表含 None 时被过滤后再计数 (L151/163)."""
        service = DriftMonitoringService(detector=FakeDetector())
        db = _mock_db()
        values = [0.5] * 29 + [None] * 5
        db.execute.side_effect = [_db_result(values), _db_result([0.6] * 30)]

        result = await service._check_modality(
            db_session=db,
            modality="structured",
            column_name="structured_score",
            **_dt_args(),
        )
        # 34 条原始记录, 29 条有效 -> 仍不足 30
        assert result.baseline_n == 29
        assert result.failed is False


class TestExceptionPath:
    """查询异常路径 —— failed=True + 回滚 + Gauge 跳过."""

    @pytest.mark.asyncio
    async def test_check_all_modalities_exception_marks_failed(self):
        """DM-005: 每个模态查询都炸 -> 4 条结果全部 failed=True, 回滚 4 次."""
        service = DriftMonitoringService(detector=FakeDetector())
        db = _mock_db()
        db.execute.side_effect = RuntimeError("db down")

        results = await service.check_all_modalities(db)

        assert len(results) == len(MODALITY_COLUMNS)
        for r in results:
            assert r.failed is True
            assert r.psi == 0.0 and r.kl == 0.0
            assert r.baseline_n == 0 and r.current_n == 0
        assert db.rollback.await_count == len(MODALITY_COLUMNS)

    @pytest.mark.asyncio
    async def test_mixed_paths_failed_flag_distinction(self):
        """DM-006: 同一轮四模态的三种形态 —— 异常(failed=True) /
        正常计算(failed=False, psi=探测器值) / 数据不足(failed=False, psi=0.0)."""
        detector = FakeDetector(psi=0.123, kl=0.045)
        service = DriftMonitoringService(detector=detector)
        db = _mock_db()
        # 模态顺序 = MODALITY_COLUMNS 迭代序: structured, text,
        # physiological, fusion
        db.execute.side_effect = [
            RuntimeError("structured query fails"),  # structured -> failed
            _db_result([0.5] * 30),  # text baseline
            _db_result([0.6] * 30),  # text current -> 计算
            _db_result([0.5] * 5),  # physiological baseline
            _db_result([0.6] * 5),  # physiological current -> 不足
            RuntimeError("fusion query fails"),  # fusion -> failed
        ]

        results = await service.check_all_modalities(db)

        by_modality = {r.modality: r for r in results}
        assert by_modality["structured"].failed is True
        assert by_modality["text"].failed is False
        assert by_modality["text"].psi == 0.123
        assert by_modality["physiological"].failed is False
        assert by_modality["physiological"].psi == 0.0
        assert by_modality["fusion"].failed is True
        # 两次异常 -> 两次回滚
        assert db.rollback.await_count == 2


class TestGaugePushSemantics:
    """Gauge 推送语义 —— failed 模态跳过, 保持上次值."""

    def test_push_skips_failed_modalities(self):
        """DM-007: failed=True 的模态不推送 (不制造漂移消失假象)."""
        service = DriftMonitoringService(detector=FakeDetector())
        results = [
            DriftCheckResult(
                modality="structured",
                feature="structured_score",
                psi=0.4,
                kl=0.2,
                baseline_n=50,
                current_n=50,
                alert_created=False,
            ),
            DriftCheckResult(
                modality="text",
                feature="text_score",
                psi=0.0,
                kl=0.0,
                baseline_n=0,
                current_n=0,
                alert_created=False,
                failed=True,
            ),
        ]
        with patch(
            "app.core.metrics.model_drift_psi"
        ) as mock_psi, patch("app.core.metrics.model_drift_kl") as mock_kl:
            service._push_to_gauge(results)

        pushed_modalities = [
            c.kwargs.get("modality") for c in mock_psi.set.call_args_list
        ]
        assert pushed_modalities == ["structured"]
        assert mock_kl.set.call_count == 1
