"""SEC-P1-005 回归测试：异常访问检测

测试覆盖:
1. 配置项默认值 (config.py)
2. alert_rules AR-303~306 注册与唯一性
3. celery beat schedule 注册 detect-anomaly-access
4. metrics 指标定义 (anomaly_access_detected_total / anomaly_access_last_detected_at)
5. anomaly_detection_service 4 个检测器 (high_frequency / off_hours / cross_region / lateral)
6. detect_all 聚合
7. anomaly_detection_enabled=False 时检测器返回空
8. _detect_impl: findings 写入 OperationLog + 递增指标
9. detect_anomaly_access_task 任务注册
10. _get_loop / _run_async / _utcnow_naive 基础函数

测试模式:
- 注入 OperationLog 数据 (手动设置 created_at 模拟历史时间)
- 调用 detect_* 函数验证返回的 finding
- 调用 _detect_impl 验证 OperationLog 写入和指标递增
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.celery_app import celery_app
from app.models.admin import OperationLog

# ===== 1. 配置项默认值 =====


class TestAnomalyDetectionConfig:
    """SEC-P1-005: config.py 配置项默认值校验."""

    def test_anomaly_detection_enabled_default(self):
        from app.core.config import settings

        assert settings.anomaly_detection_enabled is True

    def test_high_freq_config_defaults(self):
        from app.core.config import settings

        assert settings.anomaly_high_freq_window_minutes == 5
        assert settings.anomaly_high_freq_threshold == 100

    def test_off_hours_config_defaults(self):
        from app.core.config import settings

        assert settings.anomaly_off_hours_start == 22
        assert settings.anomaly_off_hours_end == 6

    def test_cross_region_config_defaults(self):
        from app.core.config import settings

        assert settings.anomaly_cross_region_window_hours == 24
        assert settings.anomaly_cross_region_ip_threshold == 3

    def test_lateral_config_defaults(self):
        from app.core.config import settings

        assert settings.anomaly_lateral_window_minutes == 30
        assert settings.anomaly_lateral_target_type_threshold == 5

    def test_scan_interval_default(self):
        from app.core.config import settings

        assert settings.anomaly_scan_interval_seconds == 300


# ===== 2. alert_rules AR-303~306 =====


class TestAlertRulesRegistration:
    """SEC-P1-005: AR-303~306 在 alert_rules 中注册."""

    def test_ar_303_registered(self):
        from app.core.alert_rules import ALERT_RULES_BY_ID

        assert "AR-303" in ALERT_RULES_BY_ID
        rule = ALERT_RULES_BY_ID["AR-303"]
        assert rule.name == "high_frequency_access"
        assert rule.severity.value == "warning"
        assert ("anomaly_type", "high_frequency") in rule.labels

    def test_ar_304_registered(self):
        from app.core.alert_rules import ALERT_RULES_BY_ID

        assert "AR-304" in ALERT_RULES_BY_ID
        rule = ALERT_RULES_BY_ID["AR-304"]
        assert rule.name == "off_hours_access"
        assert ("anomaly_type", "off_hours") in rule.labels

    def test_ar_305_registered(self):
        from app.core.alert_rules import ALERT_RULES_BY_ID

        assert "AR-305" in ALERT_RULES_BY_ID
        rule = ALERT_RULES_BY_ID["AR-305"]
        assert rule.name == "cross_region_access"
        assert ("anomaly_type", "cross_region") in rule.labels

    def test_ar_306_registered(self):
        from app.core.alert_rules import ALERT_RULES_BY_ID

        assert "AR-306" in ALERT_RULES_BY_ID
        rule = ALERT_RULES_BY_ID["AR-306"]
        assert rule.name == "lateral_access_anomaly"
        assert ("anomaly_type", "lateral") in rule.labels

    def test_all_anomaly_rules_use_same_metric(self):
        """所有 AR-303~306 应共享同一 metric (anomaly_access_detected_total)."""
        from app.core.alert_rules import ALERT_RULES_BY_ID

        for rule_id in ("AR-303", "AR-304", "AR-305", "AR-306"):
            assert ALERT_RULES_BY_ID[rule_id].metric == "anomaly_access_detected_total"

    def test_validate_rules_no_errors(self):
        """validate_rules() 应通过 (无重复 ID/name)."""
        from app.core.alert_rules import validate_rules

        errors = validate_rules()
        assert errors == [], f"alert_rules validation failed: {errors}"


# ===== 3. celery beat schedule =====


class TestCeleryBeatSchedule:
    """SEC-P1-005: celery_app.beat_schedule 注册 detect-anomaly-access."""

    def test_detect_anomaly_in_beat_schedule(self):
        schedule = celery_app.conf.beat_schedule
        assert "detect-anomaly-access" in schedule
        entry = schedule["detect-anomaly-access"]
        assert entry["task"] == "app.tasks.anomaly_detection.detect_anomaly_access_task"
        assert entry["schedule"] == 300.0

    def test_detect_anomaly_task_registered(self):
        """Celery 任务应已注册."""
        import app.tasks.anomaly_detection  # noqa: F401

        task_names = list(celery_app.tasks.keys())
        assert "app.tasks.anomaly_detection.detect_anomaly_access_task" in task_names


# ===== 4. metrics 指标定义 =====


class TestMetricsDefinitions:
    """SEC-P1-005: metrics.py 中 anomaly 指标定义."""

    def test_anomaly_access_detected_total_counter(self):
        from app.core.metrics import anomaly_access_detected_total

        assert anomaly_access_detected_total.name == "anomaly_access_detected_total"
        assert anomaly_access_detected_total.labelnames == ("type",)

    def test_anomaly_access_last_detected_at_gauge(self):
        from app.core.metrics import anomaly_access_last_detected_at

        assert anomaly_access_last_detected_at.name == "anomaly_access_last_detected_at"

    def test_metrics_in_registry(self):
        """指标应注册到 _REGISTRY 中, /metrics 端点会输出."""
        from app.core.metrics import _REGISTRY

        assert "anomaly_access_detected_total" in _REGISTRY
        assert "anomaly_access_last_detected_at" in _REGISTRY


# ===== 5. anomaly_detection_service 检测器 =====


def _utcnow_naive() -> datetime:
    """辅助: 返回 naive UTC datetime (与 service 内部一致)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def _seed_oplog(
    db: AsyncSession,
    operator_id: int,
    operator_role: str,
    action_type: str = "test_action",
    target_type: str | None = "test_target",
    target_id: int | None = None,
    ip_address: str | None = "127.0.0.1",
    created_at: datetime | None = None,
) -> OperationLog:
    """构造并 add 一条 OperationLog (不 commit, 由调用方控制)."""
    log = OperationLog(
        operator_id=operator_id,
        operator_role=operator_role,
        action_type=action_type,
        target_type=target_type,
        target_id=target_id if target_id is not None else operator_id,
        detail="{}",
        ip_address=ip_address,
        created_at=created_at or _utcnow_naive(),
    )
    db.add(log)
    return log


class TestDetectHighFrequency:
    """SEC-P1-005: detect_high_frequency 检测器."""

    @pytest.mark.asyncio
    async def test_detects_high_frequency_user(self, db_session: AsyncSession):
        """同一用户 5 分钟内 > 100 次操作 → 检测出异常."""
        from app.services.anomaly_detection_service import detect_high_frequency

        now = _utcnow_naive()
        # user_id=1 注入 101 条操作
        for i in range(101):
            _seed_oplog(
                db_session,
                operator_id=1,
                operator_role="user",
                ip_address="10.0.0.1",
                created_at=now,
            )
        await db_session.commit()

        findings = await detect_high_frequency(db_session)
        # 至少检测到 user_id=1
        high_freq_findings = [f for f in findings if f.operator_id == 1]
        assert len(high_freq_findings) >= 1
        finding = high_freq_findings[0]
        assert finding.anomaly_type == "high_frequency"
        assert finding.rule_id == "AR-303"
        assert finding.operator_role == "user"
        assert finding.ip_address == "10.0.0.1"
        detail = json.loads(finding.detail)
        assert detail["op_count"] >= 101
        assert detail["threshold"] == 100

    @pytest.mark.asyncio
    async def test_no_anomaly_below_threshold(self, db_session: AsyncSession):
        """用户操作数 < threshold 时不应检测出异常."""
        from app.services.anomaly_detection_service import detect_high_frequency

        now = _utcnow_naive()
        for i in range(50):
            _seed_oplog(db_session, operator_id=2, operator_role="user", created_at=now)
        await db_session.commit()

        findings = await detect_high_frequency(db_session)
        assert all(f.operator_id != 2 for f in findings)

    @pytest.mark.asyncio
    async def test_old_operations_not_counted(self, db_session: AsyncSession):
        """5 分钟之前的操作不计入窗口."""
        from app.services.anomaly_detection_service import detect_high_frequency

        now = _utcnow_naive()
        old_time = now - timedelta(minutes=10)
        # 101 条旧操作 (在窗口外)
        for i in range(101):
            _seed_oplog(
                db_session, operator_id=3, operator_role="user", created_at=old_time
            )
        await db_session.commit()

        findings = await detect_high_frequency(db_session)
        assert all(f.operator_id != 3 for f in findings)


class TestDetectOffHours:
    """SEC-P1-005: detect_off_hours 检测器."""

    @pytest.mark.asyncio
    async def test_detects_admin_off_hours_access(self, db_session: AsyncSession):
        """admin 在 23:00 UTC 操作 → 检测出异常."""
        from app.services.anomaly_detection_service import detect_off_hours

        # 构造 23:00 UTC 的时间戳 (naive)
        off_hours_time = _utcnow_naive().replace(hour=23, minute=5)
        _seed_oplog(
            db_session,
            operator_id=10,
            operator_role="admin",
            action_type="admin_login",
            target_type="auth",
            ip_address="10.0.0.10",
            created_at=off_hours_time,
        )
        await db_session.commit()

        findings = await detect_off_hours(db_session)
        off_hours_findings = [f for f in findings if f.operator_id == 10]
        assert len(off_hours_findings) >= 1
        finding = off_hours_findings[0]
        assert finding.anomaly_type == "off_hours"
        assert finding.rule_id == "AR-304"
        assert finding.operator_role == "admin"
        detail = json.loads(finding.detail)
        assert "22:00~06:00" in detail["off_hours_window"]

    @pytest.mark.asyncio
    async def test_no_anomaly_during_business_hours(self, db_session: AsyncSession):
        """admin 在 10:00 UTC 操作不应被检测."""
        from app.services.anomaly_detection_service import detect_off_hours

        business_hours_time = _utcnow_naive().replace(hour=10, minute=0)
        _seed_oplog(
            db_session,
            operator_id=11,
            operator_role="admin",
            created_at=business_hours_time,
        )
        await db_session.commit()

        findings = await detect_off_hours(db_session)
        assert all(f.operator_id != 11 for f in findings)

    @pytest.mark.asyncio
    async def test_user_role_not_detected(self, db_session: AsyncSession):
        """普通 user 角色在非工作时间操作不应被检测 (仅 admin/counselor)."""
        from app.services.anomaly_detection_service import detect_off_hours

        off_hours_time = _utcnow_naive().replace(hour=23, minute=0)
        _seed_oplog(
            db_session,
            operator_id=12,
            operator_role="user",
            created_at=off_hours_time,
        )
        await db_session.commit()

        findings = await detect_off_hours(db_session)
        assert all(f.operator_id != 12 for f in findings)


class TestDetectCrossRegion:
    """SEC-P1-005: detect_cross_region 检测器."""

    @pytest.mark.asyncio
    async def test_detects_multiple_ip_user(self, db_session: AsyncSession):
        """同一用户 24 小时内 > 3 个不同 IP → 检测出异常."""
        from app.services.anomaly_detection_service import detect_cross_region

        now = _utcnow_naive()
        # user_id=20 使用 4 个不同 IP
        for ip in ["10.0.0.1", "10.0.0.2", "10.0.0.3", "10.0.0.4"]:
            _seed_oplog(
                db_session,
                operator_id=20,
                operator_role="user",
                ip_address=ip,
                created_at=now,
            )
        await db_session.commit()

        findings = await detect_cross_region(db_session)
        cross_region_findings = [f for f in findings if f.operator_id == 20]
        assert len(cross_region_findings) >= 1
        finding = cross_region_findings[0]
        assert finding.anomaly_type == "cross_region"
        assert finding.rule_id == "AR-305"
        detail = json.loads(finding.detail)
        assert detail["ip_count"] >= 4
        assert set(detail["ip_list"]) >= {
            "10.0.0.1",
            "10.0.0.2",
            "10.0.0.3",
            "10.0.0.4",
        }

    @pytest.mark.asyncio
    async def test_no_anomaly_below_threshold(self, db_session: AsyncSession):
        """同一用户 24 小时内 <= 3 个 IP 不应被检测."""
        from app.services.anomaly_detection_service import detect_cross_region

        now = _utcnow_naive()
        for ip in ["10.0.0.1", "10.0.0.2"]:
            _seed_oplog(
                db_session,
                operator_id=21,
                operator_role="user",
                ip_address=ip,
                created_at=now,
            )
        await db_session.commit()

        findings = await detect_cross_region(db_session)
        assert all(f.operator_id != 21 for f in findings)

    @pytest.mark.asyncio
    async def test_old_operations_outside_window(self, db_session: AsyncSession):
        """24 小时之前的操作不计入窗口."""
        from app.services.anomaly_detection_service import detect_cross_region

        old_time = _utcnow_naive() - timedelta(hours=25)
        for ip in ["10.0.0.1", "10.0.0.2", "10.0.0.3", "10.0.0.4"]:
            _seed_oplog(
                db_session,
                operator_id=22,
                operator_role="user",
                ip_address=ip,
                created_at=old_time,
            )
        await db_session.commit()

        findings = await detect_cross_region(db_session)
        assert all(f.operator_id != 22 for f in findings)


class TestDetectLateralAccess:
    """SEC-P1-005: detect_lateral_access 检测器."""

    @pytest.mark.asyncio
    async def test_detects_lateral_user(self, db_session: AsyncSession):
        """普通用户 30 分钟内 > 5 个 target_type → 检测出异常."""
        from app.services.anomaly_detection_service import detect_lateral_access

        now = _utcnow_naive()
        # user_id=30 访问 6 种 target_type (默认阈值 5)
        target_types = [
            "user_profile",
            "user_data",
            "warning",
            "intervention",
            "content",
            "review",
        ]
        for tt in target_types:
            _seed_oplog(
                db_session,
                operator_id=30,
                operator_role="user",
                target_type=tt,
                created_at=now,
            )
        await db_session.commit()

        findings = await detect_lateral_access(db_session)
        lateral_findings = [f for f in findings if f.operator_id == 30]
        assert len(lateral_findings) >= 1
        finding = lateral_findings[0]
        assert finding.anomaly_type == "lateral"
        assert finding.rule_id == "AR-306"
        detail = json.loads(finding.detail)
        assert detail["target_type_count"] >= 6
        assert detail["threshold"] == 5  # user 角色使用默认阈值
        assert set(detail["target_types"]) >= set(target_types)

    @pytest.mark.asyncio
    async def test_counselor_higher_threshold(self, db_session: AsyncSession):
        """counselor 角色阈值=7, 6 个 target_type 不应被检测."""
        from app.services.anomaly_detection_service import detect_lateral_access

        now = _utcnow_naive()
        target_types = [
            "user",
            "user_upload",
            "consultation_record",
            "warning",
            "intervention",
            "content",
        ]
        for tt in target_types:
            _seed_oplog(
                db_session,
                operator_id=31,
                operator_role="counselor",
                target_type=tt,
                created_at=now,
            )
        await db_session.commit()

        findings = await detect_lateral_access(db_session)
        # 6 <= 7, 不应被检测
        assert all(f.operator_id != 31 for f in findings)

    @pytest.mark.asyncio
    async def test_counselor_exceeds_threshold(self, db_session: AsyncSession):
        """counselor 角色 8 个 target_type 超过阈值=7 → 检测出异常."""
        from app.services.anomaly_detection_service import detect_lateral_access

        now = _utcnow_naive()
        target_types = [
            "user",
            "user_upload",
            "consultation_record",
            "warning",
            "intervention",
            "content",
            "review",
            "auth",
        ]
        for tt in target_types:
            _seed_oplog(
                db_session,
                operator_id=32,
                operator_role="counselor",
                target_type=tt,
                created_at=now,
            )
        await db_session.commit()

        findings = await detect_lateral_access(db_session)
        lateral_findings = [f for f in findings if f.operator_id == 32]
        assert len(lateral_findings) >= 1
        finding = lateral_findings[0]
        detail = json.loads(finding.detail)
        assert detail["threshold"] == 7  # counselor 阈值


# ===== 6. detect_all 聚合 =====


class TestDetectAll:
    """SEC-P1-005: detect_all 聚合所有检测器."""

    @pytest.mark.asyncio
    async def test_detect_all_aggregates_findings(self, db_session: AsyncSession):
        """同时存在多种异常时, detect_all 应聚合所有 findings."""
        from app.services.anomaly_detection_service import detect_all

        now = _utcnow_naive()
        # 高频 (user_id=40, 101 条)
        for i in range(101):
            _seed_oplog(
                db_session,
                operator_id=40,
                operator_role="user",
                ip_address="10.0.0.40",
                created_at=now,
            )
        # 异地 (user_id=41, 4 个 IP)
        for ip in ["10.0.1.1", "10.0.1.2", "10.0.1.3", "10.0.1.4"]:
            _seed_oplog(
                db_session,
                operator_id=41,
                operator_role="user",
                ip_address=ip,
                created_at=now,
            )
        await db_session.commit()

        findings = await detect_all(db_session)
        anomaly_types = {f.anomaly_type for f in findings}
        assert "high_frequency" in anomaly_types
        assert "cross_region" in anomaly_types

    @pytest.mark.asyncio
    async def test_detect_all_no_anomaly_returns_empty(self, db_session: AsyncSession):
        """无异常时返回空列表."""
        from app.services.anomaly_detection_service import detect_all

        findings = await detect_all(db_session)
        assert findings == []

    @pytest.mark.asyncio
    async def test_detect_all_partial_failure_continues(
        self, db_session: AsyncSession, monkeypatch
    ):
        """单个检测器失败时 detect_all 应继续执行其他检测器."""
        from app.services import anomaly_detection_service as svc
        from app.services.anomaly_detection_service import detect_all

        # mock detect_high_frequency 抛异常, 其他正常
        async def _raise(_db):
            raise RuntimeError("simulated failure")

        monkeypatch.setattr(svc, "detect_high_frequency", _raise)

        # 注入异地异常数据
        now = _utcnow_naive()
        for ip in ["10.0.2.1", "10.0.2.2", "10.0.2.3", "10.0.2.4"]:
            _seed_oplog(
                db_session,
                operator_id=50,
                operator_role="user",
                ip_address=ip,
                created_at=now,
            )
        await db_session.commit()

        findings = await detect_all(db_session)
        # detect_high_frequency 失败, 但 detect_cross_region 仍应执行
        assert any(f.anomaly_type == "cross_region" for f in findings)


# ===== 7. anomaly_detection_enabled=False =====


class TestDisabledDetection:
    """SEC-P1-005: anomaly_detection_enabled=False 时所有检测器返回空."""

    @pytest.mark.asyncio
    async def test_disabled_returns_empty(self, db_session: AsyncSession, monkeypatch):
        from app.core.config import settings
        from app.services.anomaly_detection_service import (
            detect_all,
            detect_cross_region,
            detect_high_frequency,
            detect_lateral_access,
            detect_off_hours,
        )

        monkeypatch.setattr(settings, "anomaly_detection_enabled", False)

        # 即使有数据, 检测器也应返回空
        now = _utcnow_naive()
        for i in range(101):
            _seed_oplog(
                db_session, operator_id=60, operator_role="user", created_at=now
            )
        await db_session.commit()

        assert await detect_high_frequency(db_session) == []
        assert await detect_off_hours(db_session) == []
        assert await detect_cross_region(db_session) == []
        assert await detect_lateral_access(db_session) == []
        assert await detect_all(db_session) == []


# ===== 8. _detect_impl 任务实现 =====


class TestDetectImpl:
    """SEC-P1-005: _detect_impl 实现 (findings 写入 OperationLog + 递增指标)."""

    @pytest.mark.asyncio
    async def test_writes_anomaly_detected_log(
        self, db_session: AsyncSession, monkeypatch
    ):
        """findings 应写入 OperationLog (action_type=anomaly_detected)."""
        from app.services.anomaly_detection_service import AnomalyFinding
        from app.tasks.anomaly_detection import _detect_impl

        # mock detect_all 返回 1 条 finding
        mock_finding = AnomalyFinding(
            anomaly_type="high_frequency",
            operator_id=70,
            operator_role="user",
            detail='{"anomaly_type": "high_frequency"}',
            ip_address="10.0.0.70",
            rule_id="AR-303",
        )

        async def _mock_detect_all(_db):
            return [mock_finding]

        # patch AsyncSessionLocal 返回 db_session
        monkeypatch.setattr(
            "app.tasks.anomaly_detection.AsyncSessionLocal",
            _FakeSessionLocal(db_session),
        )
        monkeypatch.setattr(
            "app.services.anomaly_detection_service.detect_all", _mock_detect_all
        )

        result = await _detect_impl()

        assert result["detected"] == 1
        assert "high_frequency" in result["types"]

        # 验证 OperationLog 写入 (直接 await, 不能用 run() 因为已在事件循环中)
        r = await db_session.execute(
            select(OperationLog).where(
                OperationLog.action_type == "anomaly_detected",
                OperationLog.operator_id == 70,
            )
        )
        log = r.scalar_one_or_none()
        assert log is not None
        assert log.target_type == "anomaly_finding"
        assert log.target_id == 70
        assert log.ip_address == "10.0.0.70"
        assert log.operator_role == "user"

    @pytest.mark.asyncio
    async def test_no_findings_returns_zero(
        self, db_session: AsyncSession, monkeypatch
    ):
        """无 findings 时返回 detected=0, 不写 OperationLog."""
        from app.tasks.anomaly_detection import _detect_impl

        async def _mock_detect_all(_db):
            return []

        monkeypatch.setattr(
            "app.tasks.anomaly_detection.AsyncSessionLocal",
            _FakeSessionLocal(db_session),
        )
        monkeypatch.setattr(
            "app.services.anomaly_detection_service.detect_all", _mock_detect_all
        )

        result = await _detect_impl()
        assert result["detected"] == 0

    @pytest.mark.asyncio
    async def test_disabled_returns_skipped(
        self, db_session: AsyncSession, monkeypatch
    ):
        """anomaly_detection_enabled=False 时返回 skipped."""
        from app.core.config import settings
        from app.tasks.anomaly_detection import _detect_impl

        monkeypatch.setattr(settings, "anomaly_detection_enabled", False)
        monkeypatch.setattr(
            "app.tasks.anomaly_detection.AsyncSessionLocal",
            _FakeSessionLocal(db_session),
        )

        result = await _detect_impl()
        assert result == {"detected": 0, "skipped": "disabled"}

    @pytest.mark.asyncio
    async def test_increments_prometheus_metrics(
        self, db_session: AsyncSession, monkeypatch
    ):
        """findings 应递增 anomaly_access_detected_total 指标."""
        from app.core.metrics import anomaly_access_detected_total
        from app.services.anomaly_detection_service import AnomalyFinding
        from app.tasks.anomaly_detection import _detect_impl

        # 记录当前值 (按 type=high_frequency 标签)
        before = anomaly_access_detected_total.collect()
        before_count = 0
        for labels, value in before:
            if labels.get("type") == "high_frequency":
                before_count = value
                break

        mock_finding = AnomalyFinding(
            anomaly_type="high_frequency",
            operator_id=80,
            operator_role="user",
            detail="{}",
            ip_address="10.0.0.80",
            rule_id="AR-303",
        )

        async def _mock_detect_all(_db):
            return [mock_finding]

        monkeypatch.setattr(
            "app.tasks.anomaly_detection.AsyncSessionLocal",
            _FakeSessionLocal(db_session),
        )
        monkeypatch.setattr(
            "app.services.anomaly_detection_service.detect_all", _mock_detect_all
        )

        await _detect_impl()

        after = anomaly_access_detected_total.collect()
        after_count = 0
        for labels, value in after:
            if labels.get("type") == "high_frequency":
                after_count = value
                break

        assert after_count >= before_count + 1


class _FakeSessionLocal:
    """模拟 AsyncSessionLocal, 返回同一个 db_session."""

    def __init__(self, session: AsyncSession):
        self._session = session

    def __call__(self):
        return _FakeAsyncCtx(self._session)


class _FakeAsyncCtx:
    def __init__(self, session: AsyncSession):
        self._session = session

    async def __aenter__(self):
        return self._session

    async def __aexit__(self, exc_type, exc, tb):
        # 不关闭 session, 由 conftest 管理
        return None


# ===== 9. detect_anomaly_access_task 任务入口 =====


class TestDetectAnomalyAccessTask:
    """SEC-P1-005: detect_anomaly_access_task 任务入口."""

    def test_task_executes_successfully(self):
        """任务执行: mock _run_async 返回 dict."""
        from app.tasks.anomaly_detection import detect_anomaly_access_task

        with patch(
            "app.tasks.anomaly_detection._run_async", return_value={"detected": 2}
        ):
            result = detect_anomaly_access_task()
        assert result == {"detected": 2}

    def test_task_handles_empty_result(self):
        """无异常时返回 detected=0."""
        from app.tasks.anomaly_detection import detect_anomaly_access_task

        with patch(
            "app.tasks.anomaly_detection._run_async", return_value={"detected": 0}
        ):
            result = detect_anomaly_access_task()
        assert result["detected"] == 0

    def test_task_max_retries_exceeded_returns_error(self):
        """重试耗尽时返回 error dict."""
        from app.tasks.anomaly_detection import detect_anomaly_access_task

        with patch(
            "app.tasks.anomaly_detection._run_async",
            side_effect=RuntimeError("db error"),
        ), patch.object(
            detect_anomaly_access_task,
            "retry",
            side_effect=detect_anomaly_access_task.MaxRetriesExceededError,
        ):
            result = detect_anomaly_access_task()
        assert result == {"error": "db error"}


# ===== 10. 基础函数 (_get_loop / _run_async / _utcnow_naive) =====


class TestBasicFunctions:
    """SEC-P1-005: 基础工具函数 (与 tasks/alerts.py 一致的范式)."""

    def test_get_loop_caches_singleton(self):
        from app.tasks.anomaly_detection import _get_loop

        loop1 = _get_loop()
        loop2 = _get_loop()
        assert loop1 is loop2

    def test_run_async_executes_coroutine(self):
        from app.tasks.anomaly_detection import _run_async

        async def coro():
            return "ok"

        assert _run_async(coro()) == "ok"

    def test_utcnow_naive_returns_naive_datetime(self):
        from app.tasks.anomaly_detection import _utcnow_naive

        now = _utcnow_naive()
        assert now.tzinfo is None
        delta = datetime.now(timezone.utc).replace(tzinfo=None) - now
        assert abs(delta.total_seconds()) < 1
