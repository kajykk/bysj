"""STAB-P1-008 测试: MTTR (Mean Time To Repair) 自动统计服务.

测试覆盖:
1. MttrService.compute_mttr() - MTTR 计算逻辑
2. _parse_operation_log_row - OperationLog detail JSON 解析
3. _group_by_fingerprint - fingerprint 分组排序
4. metrics.py 中 MTTR 指标定义
5. alert_rules.py 中 AR-206/AR-207 告警规则定义

数据源: OperationLog 中 alert_fired (故障开始) / alert_resolved (故障恢复)
配对键: detail JSON 中的 fingerprint 字段
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.alert_rules import ALERT_RULES, Severity
from app.core.metrics import (
    alert_mttr_seconds,
    alert_resolved_total,
    alert_unresolved_count,
)
from app.services.mttr_service import MttrService, MttrStats


def _make_operation_log(
    action_type: str,
    fingerprint: str,
    severity: str,
    created_at: datetime,
    detail_extras: dict | None = None,
) -> MagicMock:
    """构造模拟 OperationLog 行 (用于 _parse_operation_log_row 测试)."""
    detail_dict = {
        "rule": "test_rule",
        "severity": severity,
        "fingerprint": fingerprint,
        "labels": {},
        "annotations": {},
        "message": "test message",
    }
    if detail_extras:
        detail_dict.update(detail_extras)
    row = MagicMock()
    row.action_type = action_type
    row.detail = json.dumps(detail_dict)
    row.created_at = created_at
    return row


def _make_parsed_entry(
    fingerprint: str,
    severity: str,
    created_at: datetime,
) -> dict:
    """构造解析后的 entry dict (用于 compute_mttr 测试, mock _query_alert_logs 返回)."""
    return {
        "fingerprint": fingerprint,
        "severity": severity,
        "created_at": created_at,
    }


class TestParseOperationLogRow:
    """测试 OperationLog detail JSON 解析."""

    def test_parse_valid_row(self):
        """TC-MTTR-001: 有效行解析出 fingerprint/severity/created_at."""
        row = _make_operation_log(
            action_type="alert_fired",
            fingerprint="fp_001",
            severity="critical",
            created_at=datetime(2026, 7, 2, 10, 0, 0),
        )
        result = MttrService._parse_operation_log_row(row)
        assert result is not None
        assert result["fingerprint"] == "fp_001"
        assert result["severity"] == "critical"
        assert result["created_at"] == datetime(2026, 7, 2, 10, 0, 0)

    def test_parse_missing_detail(self):
        """TC-MTTR-002: detail 为 None 返回 None."""
        row = MagicMock()
        row.detail = None
        assert MttrService._parse_operation_log_row(row) is None

    def test_parse_invalid_json(self):
        """TC-MTTR-003: detail 不是有效 JSON 返回 None."""
        row = MagicMock()
        row.detail = "not a json string"
        assert MttrService._parse_operation_log_row(row) is None

    def test_parse_missing_fingerprint(self):
        """TC-MTTR-004: detail 缺少 fingerprint 返回 None."""
        row = MagicMock()
        row.detail = json.dumps({"rule": "x", "severity": "warning"})
        row.created_at = datetime(2026, 7, 2, 10, 0, 0)
        assert MttrService._parse_operation_log_row(row) is None

    def test_parse_missing_severity_defaults_unknown(self):
        """TC-MTTR-005: detail 缺少 severity 默认为 unknown."""
        row = MagicMock()
        row.detail = json.dumps({"fingerprint": "fp_x"})
        row.created_at = datetime(2026, 7, 2, 10, 0, 0)
        result = MttrService._parse_operation_log_row(row)
        assert result is not None
        assert result["severity"] == "unknown"


class TestGroupByFingerprint:
    """测试 fingerprint 分组排序."""

    def test_group_single_entry(self):
        """TC-MTTR-006: 单条记录分组."""
        entries = [
            {
                "fingerprint": "fp1",
                "severity": "warning",
                "created_at": datetime(2026, 7, 2, 10, 0),
            }
        ]
        grouped = MttrService._group_by_fingerprint(entries)
        assert "fp1" in grouped
        assert len(grouped["fp1"]) == 1

    def test_group_multiple_fingerprints(self):
        """TC-MTTR-007: 多个 fingerprint 分组."""
        entries = [
            {
                "fingerprint": "fp1",
                "severity": "warning",
                "created_at": datetime(2026, 7, 2, 10, 0),
            },
            {
                "fingerprint": "fp2",
                "severity": "critical",
                "created_at": datetime(2026, 7, 2, 11, 0),
            },
        ]
        grouped = MttrService._group_by_fingerprint(entries)
        assert len(grouped) == 2
        assert "fp1" in grouped
        assert "fp2" in grouped

    def test_group_sorts_by_created_at_ascending(self):
        """TC-MTTR-008: 同一 fingerprint 按 created_at 升序排序."""
        t1 = datetime(2026, 7, 2, 10, 0)
        t2 = datetime(2026, 7, 2, 9, 0)  # 更早
        t3 = datetime(2026, 7, 2, 11, 0)
        entries = [
            {"fingerprint": "fp1", "severity": "warning", "created_at": t1},
            {"fingerprint": "fp1", "severity": "warning", "created_at": t2},
            {"fingerprint": "fp1", "severity": "warning", "created_at": t3},
        ]
        grouped = MttrService._group_by_fingerprint(entries)
        # 应按时间升序: t2, t1, t3
        assert grouped["fp1"][0]["created_at"] == t2
        assert grouped["fp1"][1]["created_at"] == t1
        assert grouped["fp1"][2]["created_at"] == t3

    def test_group_empty_list(self):
        """TC-MTTR-009: 空列表返回空 dict."""
        assert MttrService._group_by_fingerprint([]) == {}


class TestComputeMttr:
    """测试 MTTR 计算逻辑 (使用 mock 避免 DB)."""

    @pytest.mark.asyncio
    async def test_compute_mttr_empty_db(self):
        """TC-MTTR-010: 空数据库返回 0 MTTR, 0 counts."""
        service = MttrService(window_hours=24)
        # mock _query_alert_logs 返回空列表
        with patch.object(service, "_query_alert_logs", new=AsyncMock(return_value=[])):
            stats = await service.compute_mttr(MagicMock(), window_hours=24)
        assert stats.mttr_seconds == 0.0
        assert stats.resolved_count == 0
        assert stats.unresolved_count == 0
        assert stats.total_count == 0
        assert stats.severity_breakdown == {}

    @pytest.mark.asyncio
    async def test_compute_mttr_single_pair(self):
        """TC-MTTR-011: 单对 fired+resolved 计算 MTTR."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        fired_time = now - timedelta(hours=2)
        resolved_time = now - timedelta(hours=1)  # 1 小时后恢复, MTTR=3600s
        fired = _make_parsed_entry("fp1", "critical", fired_time)
        resolved = _make_parsed_entry("fp1", "critical", resolved_time)

        service = MttrService()
        with patch.object(
            service,
            "_query_alert_logs",
            new=AsyncMock(
                side_effect=lambda db, action_type, since: (
                    [fired] if action_type == "alert_fired" else [resolved]
                )
            ),
        ):
            stats = await service.compute_mttr(MagicMock(), window_hours=24)
        assert stats.resolved_count == 1
        assert stats.unresolved_count == 0
        assert stats.mttr_seconds == 3600.0
        assert "critical" in stats.severity_breakdown
        assert stats.severity_breakdown["critical"]["mttr_seconds"] == 3600.0

    @pytest.mark.asyncio
    async def test_compute_mttr_multiple_pairs(self):
        """TC-MTTR-012: 多对配对计算平均 MTTR."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        # Pair 1: 1h MTTR
        fired1 = _make_parsed_entry("fp1", "critical", now - timedelta(hours=3))
        resolved1 = _make_parsed_entry("fp1", "critical", now - timedelta(hours=2))
        # Pair 2: 2h MTTR
        fired2 = _make_parsed_entry("fp2", "critical", now - timedelta(hours=5))
        resolved2 = _make_parsed_entry("fp2", "critical", now - timedelta(hours=3))
        fired_list = [fired1, fired2]
        resolved_list = [resolved1, resolved2]

        service = MttrService()
        with patch.object(
            service,
            "_query_alert_logs",
            new=AsyncMock(
                side_effect=lambda db, action_type, since: (
                    fired_list if action_type == "alert_fired" else resolved_list
                )
            ),
        ):
            stats = await service.compute_mttr(MagicMock(), window_hours=24)
        assert stats.resolved_count == 2
        assert stats.unresolved_count == 0
        # 平均 MTTR = (3600 + 7200) / 2 = 5400s
        assert stats.mttr_seconds == 5400.0

    @pytest.mark.asyncio
    async def test_compute_mttr_unresolved(self):
        """TC-MTTR-013: 有 fired 无 resolved 计入 unresolved_count."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        fired = _make_parsed_entry("fp1", "warning", now - timedelta(hours=2))

        service = MttrService()
        with patch.object(
            service,
            "_query_alert_logs",
            new=AsyncMock(
                side_effect=lambda db, action_type, since: (
                    [fired] if action_type == "alert_fired" else []
                )
            ),
        ):
            stats = await service.compute_mttr(MagicMock(), window_hours=24)
        assert stats.resolved_count == 0
        assert stats.unresolved_count == 1
        assert stats.mttr_seconds == 0.0
        assert "warning" in stats.severity_breakdown
        assert stats.severity_breakdown["warning"]["unresolved_count"] == 1

    @pytest.mark.asyncio
    async def test_compute_mttr_severity_breakdown(self):
        """TC-MTTR-014: 按 severity 分组统计."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        # critical pair: 1h MTTR
        fired_c = _make_parsed_entry("fp_c", "critical", now - timedelta(hours=2))
        resolved_c = _make_parsed_entry("fp_c", "critical", now - timedelta(hours=1))
        # warning pair: 2h MTTR
        fired_w = _make_parsed_entry("fp_w", "warning", now - timedelta(hours=5))
        resolved_w = _make_parsed_entry("fp_w", "warning", now - timedelta(hours=3))
        fired_list = [fired_c, fired_w]
        resolved_list = [resolved_c, resolved_w]

        service = MttrService()
        with patch.object(
            service,
            "_query_alert_logs",
            new=AsyncMock(
                side_effect=lambda db, action_type, since: (
                    fired_list if action_type == "alert_fired" else resolved_list
                )
            ),
        ):
            stats = await service.compute_mttr(MagicMock(), window_hours=24)
        assert len(stats.severity_breakdown) == 2
        assert stats.severity_breakdown["critical"]["mttr_seconds"] == 3600.0
        assert stats.severity_breakdown["warning"]["mttr_seconds"] == 7200.0
        assert stats.severity_breakdown["critical"]["resolved_count"] == 1
        assert stats.severity_breakdown["warning"]["resolved_count"] == 1

    @pytest.mark.asyncio
    async def test_compute_mttr_negative_duration_excluded(self):
        """TC-MTTR-015: 负 MTTR (resolved 早于 fired) 不计入 (窗口边界异常)."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        # 异常: resolved 早于 fired (可能是窗口前数据)
        fired = _make_parsed_entry("fp1", "critical", now - timedelta(hours=1))
        resolved = _make_parsed_entry(
            "fp1", "critical", now - timedelta(hours=2)
        )  # 早于 fired

        service = MttrService()
        with patch.object(
            service,
            "_query_alert_logs",
            new=AsyncMock(
                side_effect=lambda db, action_type, since: (
                    [fired] if action_type == "alert_fired" else [resolved]
                )
            ),
        ):
            stats = await service.compute_mttr(MagicMock(), window_hours=24)
        # 负 MTTR 不计入
        assert stats.resolved_count == 0
        assert stats.mttr_seconds == 0.0

    @pytest.mark.asyncio
    async def test_compute_mttr_resolved_only_excluded(self):
        """TC-MTTR-016: 仅有 resolved (无 fired) 不参与 MTTR 计算."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        resolved = _make_parsed_entry("fp1", "critical", now - timedelta(hours=1))

        service = MttrService()
        with patch.object(
            service,
            "_query_alert_logs",
            new=AsyncMock(
                side_effect=lambda db, action_type, since: (
                    [] if action_type == "alert_fired" else [resolved]
                )
            ),
        ):
            stats = await service.compute_mttr(MagicMock(), window_hours=24)
        # 仅有 resolved 不参与
        assert stats.resolved_count == 0
        assert stats.unresolved_count == 0
        assert stats.mttr_seconds == 0.0

    @pytest.mark.asyncio
    async def test_compute_mttr_window_hours_param(self):
        """TC-MTTR-017: window_hours 参数控制统计窗口."""
        service = MttrService(window_hours=24)
        # 调用 compute_mttr 时传入 window_hours=48
        with patch.object(
            service, "_query_alert_logs", new=AsyncMock(return_value=[])
        ) as mock_query:
            await service.compute_mttr(MagicMock(), window_hours=48)
        # 验证 _query_alert_logs 被调用, since = now - 48h
        assert mock_query.call_count == 2
        # 第二个调用 (resolved) 的 since 应该是 48h 前
        second_call_args = mock_query.call_args_list[0]
        since_arg = second_call_args.kwargs["since"]
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        # since 应该接近 now - 48h (允许 ±60s 误差)
        assert abs((now - since_arg).total_seconds() - 48 * 3600) < 60

    @pytest.mark.asyncio
    async def test_compute_mttr_uses_instance_window_when_param_none(self):
        """TC-MTTR-018: window_hours=None 时使用实例配置."""
        service = MttrService(window_hours=12)
        with patch.object(
            service, "_query_alert_logs", new=AsyncMock(return_value=[])
        ) as mock_query:
            await service.compute_mttr(MagicMock(), window_hours=None)
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        first_call_args = mock_query.call_args_list[0]
        since_arg = first_call_args.kwargs["since"]
        # since 应该接近 now - 12h
        assert abs((now - since_arg).total_seconds() - 12 * 3600) < 60


class TestMttrStats:
    """测试 MttrStats 数据类."""

    def test_mttr_stats_fields(self):
        """TC-MTTR-019: MttrStats 字段完整性."""
        stats = MttrStats(
            mttr_seconds=3600.0,
            resolved_count=5,
            unresolved_count=2,
            total_count=7,
            severity_breakdown={
                "critical": {
                    "mttr_seconds": 3600.0,
                    "resolved_count": 5,
                    "unresolved_count": 2,
                }
            },
            window_hours=24,
        )
        assert stats.mttr_seconds == 3600.0
        assert stats.resolved_count == 5
        assert stats.unresolved_count == 2
        assert stats.total_count == 7
        assert stats.window_hours == 24
        assert "critical" in stats.severity_breakdown


class TestMttrMetricsIntegration:
    """测试 MTTR 指标定义和告警规则."""

    def test_alert_mttr_seconds_metric_defined(self):
        """TC-MTTR-020: alert_mttr_seconds Gauge 已定义且有 severity 标签."""
        assert alert_mttr_seconds.name == "alert_mttr_seconds"
        assert "severity" in alert_mttr_seconds.labelnames

    def test_alert_resolved_total_metric_defined(self):
        """TC-MTTR-021: alert_resolved_total Gauge 已定义."""
        assert alert_resolved_total.name == "alert_resolved_total"

    def test_alert_unresolved_count_metric_defined(self):
        """TC-MTTR-022: alert_unresolved_count Gauge 已定义."""
        assert alert_unresolved_count.name == "alert_unresolved_count"

    def test_alert_mttr_seconds_set_with_severity(self):
        """TC-MTTR-023: alert_mttr_seconds.set 按 severity 设置."""
        alert_mttr_seconds.set(300.0, severity="critical")
        alert_mttr_seconds.set(120.0, severity="warning")
        dict((tuple(sorted(d.items())), v) for d, v in alert_mttr_seconds.collect())
        # 应有 critical=300 和 warning=120 两个标签
        assert any("critical" in str(d) for d, _ in alert_mttr_seconds.collect())
        assert any("warning" in str(d) for d, _ in alert_mttr_seconds.collect())

    def test_ar206_alert_rule_defined(self):
        """TC-MTTR-024: AR-206 high_mttr 告警规则已定义."""
        ar206 = [r for r in ALERT_RULES if r.id == "AR-206"]
        assert len(ar206) == 1
        rule = ar206[0]
        assert rule.name == "high_mttr"
        assert rule.metric == "alert_mttr_seconds"
        assert rule.severity == Severity.WARNING
        assert rule.threshold == 300.0
        assert rule.comparison == "gt"
        assert rule.duration_seconds == 600  # 持续 10 分钟

    def test_ar207_alert_rule_defined(self):
        """TC-MTTR-025: AR-207 unresolved_alerts 告警规则已定义."""
        ar207 = [r for r in ALERT_RULES if r.id == "AR-207"]
        assert len(ar207) == 1
        rule = ar207[0]
        assert rule.name == "unresolved_alerts"
        assert rule.metric == "alert_unresolved_count"
        assert rule.severity == Severity.WARNING
        assert rule.threshold == 0.0
        assert rule.comparison == "gt"
        assert rule.duration_seconds == 3600  # 持续 1 小时

    def test_ar206_ar207_in_stability_category(self):
        """TC-MTTR-026: AR-206/AR-207 归属稳定性分类."""
        for rule_id in ("AR-206", "AR-207"):
            rule = next(r for r in ALERT_RULES if r.id == rule_id)
            labels_dict = dict(rule.labels)
            assert labels_dict.get("category") == "stability"


class TestMttrServiceIntegration:
    """MTTR 服务集成测试 (使用真实 DB session)."""

    @pytest.mark.asyncio
    async def test_compute_mttr_with_real_db_empty(self, db_session):
        """TC-MTTR-027: 真实空数据库 compute_mttr 返回 0."""
        service = MttrService(window_hours=24)
        stats = await service.compute_mttr(db_session, window_hours=24)
        assert stats.resolved_count == 0
        assert stats.unresolved_count == 0
        assert stats.mttr_seconds == 0.0

    @pytest.mark.asyncio
    async def test_compute_mttr_with_real_db_single_pair(self, db_session):
        """TC-MTTR-028: 真实数据库插入单对 fired+resolved 计算 MTTR."""
        import json as json_module

        from app.models.admin import OperationLog

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        fired_detail = json_module.dumps(
            {"fingerprint": "fp_real_1", "severity": "critical"}
        )
        resolved_detail = json_module.dumps(
            {"fingerprint": "fp_real_1", "severity": "critical"}
        )

        fired = OperationLog(
            action_type="alert_fired",
            target_type="alert",
            detail=fired_detail,
            created_at=now - timedelta(hours=2),
        )
        resolved = OperationLog(
            action_type="alert_resolved",
            target_type="alert",
            detail=resolved_detail,
            created_at=now - timedelta(hours=1),  # 1h MTTR
        )
        db_session.add(fired)
        db_session.add(resolved)
        await db_session.flush()

        service = MttrService(window_hours=24)
        stats = await service.compute_mttr(db_session, window_hours=24)
        assert stats.resolved_count == 1
        assert stats.mttr_seconds == pytest.approx(3600.0, rel=0.01)
        assert stats.unresolved_count == 0

    @pytest.mark.asyncio
    async def test_compute_mttr_with_real_db_unresolved(self, db_session):
        """TC-MTTR-029: 真实数据库有 fired 无 resolved 计入 unresolved."""
        import json as json_module

        from app.models.admin import OperationLog

        now = datetime.now(timezone.utc).replace(tzinfo=None)
        fired = OperationLog(
            action_type="alert_fired",
            target_type="alert",
            detail=json_module.dumps(
                {"fingerprint": "fp_unresolved", "severity": "warning"}
            ),
            created_at=now - timedelta(hours=3),
        )
        db_session.add(fired)
        await db_session.flush()

        service = MttrService(window_hours=24)
        stats = await service.compute_mttr(db_session, window_hours=24)
        assert stats.unresolved_count == 1
        assert stats.resolved_count == 0
        assert "warning" in stats.severity_breakdown
