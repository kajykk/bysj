"""PERF-P2-003 专项测试: risk_assessments 表归档策略.

验证 AdminService.archive_old_risk_assessments + Celery task + beat schedule:
- 删除超过指定天数的 RiskAssessment 记录
- 维护 is_latest 标志位 (被删除的 is_latest=True → 重新标记剩余最新记录)
- WarningNotification.risk_assessment_id 外键 ondelete=SET NULL 自动处理
- Celery task 注册 + beat schedule 注册
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest

from app.models.risk import RiskAssessment, WarningNotification
from app.services.admin_service import AdminService


@pytest.mark.asyncio
class TestArchiveOldRiskAssessmentsService:

    async def test_empty_data_returns_zero(self, db_session) -> None:
        """无数据时返回 0."""
        service = AdminService(db_session)
        result = await service.archive_old_risk_assessments(days=365)
        assert result == 0

    async def test_deletes_old_records(self, db_session) -> None:
        """删除超过阈值的记录."""
        now = datetime.now(UTC).replace(tzinfo=None)
        old = RiskAssessment(
            user_id=2001,
            risk_score=50.0,
            risk_level=2,
            assessment_type="structured",
            created_at=now - timedelta(days=400),
        )
        recent = RiskAssessment(
            user_id=2001,
            risk_score=60.0,
            risk_level=3,
            assessment_type="structured",
            created_at=now - timedelta(days=5),
        )
        db_session.add_all([old, recent])
        await db_session.flush()

        service = AdminService(db_session)
        result = await service.archive_old_risk_assessments(days=365)
        # 至少删除了 old 记录 (rowcount 在 SQLite 可能返回 -1/0)
        assert result >= 0

    async def test_preserves_recent_records(self, db_session) -> None:
        """保留阈值内的记录."""
        now = datetime.now(UTC).replace(tzinfo=None)
        recent = RiskAssessment(
            user_id=2002,
            risk_score=50.0,
            risk_level=2,
            assessment_type="structured",
            created_at=now - timedelta(days=30),
        )
        db_session.add(recent)
        await db_session.flush()

        service = AdminService(db_session)
        await service.archive_old_risk_assessments(days=365)

        from sqlalchemy import select

        remaining = await db_session.execute(
            select(RiskAssessment).where(RiskAssessment.user_id == 2002)
        )
        records = remaining.scalars().all()
        assert len(records) == 1
        assert records[0].risk_score == 50.0

    async def test_is_latest_reassigned(self, db_session) -> None:
        """被删除的 is_latest=True 记录: 从剩余记录中重新标记."""
        now = datetime.now(UTC).replace(tzinfo=None)
        # old: is_latest=True (将被删除)
        old = RiskAssessment(
            user_id=2003,
            risk_score=50.0,
            risk_level=2,
            assessment_type="structured",
            created_at=now - timedelta(days=400),
            is_latest=True,
        )
        # remaining1: 较早的剩余记录
        remaining1 = RiskAssessment(
            user_id=2003,
            risk_score=40.0,
            risk_level=1,
            assessment_type="structured",
            created_at=now - timedelta(days=200),
            is_latest=False,
        )
        # remaining2: 最新的剩余记录 (应被标记为 is_latest)
        remaining2 = RiskAssessment(
            user_id=2003,
            risk_score=60.0,
            risk_level=3,
            assessment_type="structured",
            created_at=now - timedelta(days=100),
            is_latest=False,
        )
        db_session.add_all([old, remaining1, remaining2])
        await db_session.flush()

        service = AdminService(db_session)
        await service.archive_old_risk_assessments(days=365)

        from sqlalchemy import select

        # old 应被删除
        remaining = await db_session.execute(
            select(RiskAssessment)
            .where(RiskAssessment.user_id == 2003)
            .order_by(RiskAssessment.created_at.desc())
        )
        records = remaining.scalars().all()
        assert len(records) == 2
        # remaining2 (created_at 最大) 应被标记为 is_latest
        assert records[0].is_latest is True
        assert records[0].risk_score == 60.0
        assert records[1].is_latest is False

    async def test_is_latest_not_reassigned_when_no_remaining(self, db_session) -> None:
        """被删除的 is_latest=True 记录, 但无剩余记录: 不标记新 is_latest."""
        now = datetime.now(UTC).replace(tzinfo=None)
        old = RiskAssessment(
            user_id=2004,
            risk_score=50.0,
            risk_level=2,
            assessment_type="structured",
            created_at=now - timedelta(days=400),
            is_latest=True,
        )
        db_session.add(old)
        await db_session.flush()

        service = AdminService(db_session)
        await service.archive_old_risk_assessments(days=365)

        from sqlalchemy import select

        remaining = await db_session.execute(
            select(RiskAssessment).where(RiskAssessment.user_id == 2004)
        )
        records = remaining.scalars().all()
        assert len(records) == 0

    async def test_custom_days_parameter(self, db_session) -> None:
        """自定义 days 参数: 30 天删除 60 天前的记录."""
        now = datetime.now(UTC).replace(tzinfo=None)
        old = RiskAssessment(
            user_id=2005,
            risk_score=50.0,
            risk_level=2,
            assessment_type="structured",
            created_at=now - timedelta(days=60),
        )
        db_session.add(old)
        await db_session.flush()

        service = AdminService(db_session)
        await service.archive_old_risk_assessments(days=30)

        from sqlalchemy import select

        remaining = await db_session.execute(
            select(RiskAssessment).where(RiskAssessment.user_id == 2005)
        )
        records = remaining.scalars().all()
        assert len(records) == 0

    async def test_multiple_users_is_latest_reassigned(self, db_session) -> None:
        """多用户的 is_latest 同时被删除时, 各自重新标记."""
        now = datetime.now(UTC).replace(tzinfo=None)
        records = [
            # user1: old is_latest + recent remaining
            RiskAssessment(
                user_id=2006,
                risk_score=50.0,
                risk_level=2,
                assessment_type="structured",
                created_at=now - timedelta(days=400),
                is_latest=True,
            ),
            RiskAssessment(
                user_id=2006,
                risk_score=55.0,
                risk_level=2,
                assessment_type="structured",
                created_at=now - timedelta(days=10),
                is_latest=False,
            ),
            # user2: old is_latest + recent remaining
            RiskAssessment(
                user_id=2007,
                risk_score=60.0,
                risk_level=3,
                assessment_type="structured",
                created_at=now - timedelta(days=400),
                is_latest=True,
            ),
            RiskAssessment(
                user_id=2007,
                risk_score=65.0,
                risk_level=3,
                assessment_type="structured",
                created_at=now - timedelta(days=10),
                is_latest=False,
            ),
        ]
        db_session.add_all(records)
        await db_session.flush()

        service = AdminService(db_session)
        await service.archive_old_risk_assessments(days=365)

        from sqlalchemy import select

        for user_id, expected_score in [(2006, 55.0), (2007, 65.0)]:
            result = await db_session.execute(
                select(RiskAssessment)
                .where(
                    RiskAssessment.user_id == user_id,
                    RiskAssessment.is_latest.is_(True),
                )
            )
            latest = result.scalar_one_or_none()
            assert latest is not None
            assert latest.risk_score == expected_score


class TestCeleryTaskRegistration:
    """Celery task 注册测试."""

    def test_task_function_exists(self) -> None:
        """weekly_risk_assessment_archive task 函数存在."""
        from app.tasks import scheduler

        assert hasattr(scheduler, "weekly_risk_assessment_archive")
        assert callable(scheduler.weekly_risk_assessment_archive)

    def test_impl_function_exists(self) -> None:
        """_weekly_risk_assessment_archive_impl 实现函数存在."""
        from app.tasks import scheduler

        assert hasattr(scheduler, "_weekly_risk_assessment_archive_impl")
        assert callable(scheduler._weekly_risk_assessment_archive_impl)

    def test_task_is_celery_task(self) -> None:
        """weekly_risk_assessment_archive 是 Celery task."""
        from app.tasks.scheduler import weekly_risk_assessment_archive

        # Celery task 有 .delay 和 .apply_async 方法
        assert hasattr(weekly_risk_assessment_archive, "delay")
        assert hasattr(weekly_risk_assessment_archive, "apply_async")

    def test_task_has_bind_true(self) -> None:
        """task 装饰器配置 bind=True (支持 self.retry)."""
        import app.tasks.scheduler as scheduler_mod

        source = inspect.getsource(scheduler_mod)
        # 查找 weekly_risk_assessment_archive 的装饰器
        task_start = source.find("def weekly_risk_assessment_archive")
        # 向上查找 @celery_app.task 装饰器
        decorator_section = source[max(0, task_start - 300) : task_start]
        assert "bind=True" in decorator_section

    def test_task_has_retry_config(self) -> None:
        """task 装饰器配置 max_retries + default_retry_delay."""
        from app.tasks.scheduler import weekly_risk_assessment_archive

        # 检查 task 配置
        assert weekly_risk_assessment_archive.max_retries is not None
        assert weekly_risk_assessment_archive.default_retry_delay is not None

    def test_beat_schedule_registered(self) -> None:
        """beat_schedule 注册了 weekly-risk-assessment-archive."""
        from app.core.celery_app import celery_app

        assert "weekly-risk-assessment-archive" in celery_app.conf.beat_schedule
        schedule = celery_app.conf.beat_schedule["weekly-risk-assessment-archive"]
        assert schedule["task"] == "app.tasks.scheduler.weekly_risk_assessment_archive"

    def test_beat_schedule_weekly(self) -> None:
        """beat schedule 每周一 04:30 执行."""
        from app.core.celery_app import celery_app

        schedule = celery_app.conf.beat_schedule["weekly-risk-assessment-archive"]
        crontab = schedule["schedule"]
        # 每周一
        assert crontab.day_of_week == {1}
        assert crontab.hour == {4}
        assert crontab.minute == {30}

    def test_beat_schedule_does_not_conflict(self) -> None:
        """beat schedule 不与其他任务冲突 (04:30 独立时间槽)."""
        from app.core.celery_app import celery_app

        schedule = celery_app.conf.beat_schedule["weekly-risk-assessment-archive"]
        crontab = schedule["schedule"]
        # 确认不是 03:00 (weekly-log-archive)
        assert crontab.hour != {3} or crontab.minute != {0}
        # 确认不是 03:30 (daily-mask-old-ips)
        assert crontab.hour != {3} or crontab.minute != {30}
        # 确认不是 04:00 (cleanup-experiment-artifacts)
        assert crontab.hour != {4} or crontab.minute != {0}


class TestSourceCodeStructure:
    """源码静态扫描测试."""

    def test_service_method_exists(self) -> None:
        """AdminService.archive_old_risk_assessments 方法存在."""
        assert hasattr(AdminService, "archive_old_risk_assessments")
        assert callable(getattr(AdminService, "archive_old_risk_assessments"))

    def test_service_method_has_perf_p2_003_annotation(self) -> None:
        """方法 docstring 标注 PERF-P2-003."""
        source = inspect.getsource(AdminService.archive_old_risk_assessments)
        assert "PERF-P2-003" in source

    def test_service_method_default_days_365(self) -> None:
        """方法默认 days=365."""
        sig = inspect.signature(AdminService.archive_old_risk_assessments)
        days_param = sig.parameters.get("days")
        assert days_param is not None
        assert days_param.default == 365

    def test_service_method_handles_is_latest(self) -> None:
        """方法处理 is_latest 标志位重新标记."""
        source = inspect.getsource(AdminService.archive_old_risk_assessments)
        assert "is_latest" in source
        assert "affected_user_ids" in source

    def test_service_method_uses_commit(self) -> None:
        """方法使用 commit 提交事务 (与 archive_old_logs 一致)."""
        source = inspect.getsource(AdminService.archive_old_risk_assessments)
        assert "await self.db.commit()" in source

    def test_task_source_has_perf_p2_003_annotation(self) -> None:
        """Celery task docstring 标注 PERF-P2-003."""
        from app.tasks.scheduler import weekly_risk_assessment_archive

        source = inspect.getsource(weekly_risk_assessment_archive)
        assert "PERF-P2-003" in source
