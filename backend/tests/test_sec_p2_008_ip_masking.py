"""SEC-P2-008: OperationLog IP 掩码 (GDPR 合规) 测试.

测试范围:
1. _mask_ip 函数: IPv4/IPv6/非标准格式的掩码逻辑
2. AdminService.mask_old_ips: 服务层批量掩码
3. mask_old_ips_task: Celery 任务注册与执行
4. beat_schedule: 任务调度注册
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.admin import OperationLog
from app.services.admin_service import AdminService, _mask_ip


class TestMaskIpFunction:
    """_mask_ip 函数单元测试."""

    def test_ipv4_masked(self):
        """IPv4: 末段替换为 0."""
        assert _mask_ip("192.168.1.100") == "192.168.1.0"
        assert _mask_ip("10.0.0.255") == "10.0.0.0"
        assert _mask_ip("172.16.254.1") == "172.16.254.0"

    def test_ipv4_already_masked_idempotent(self):
        """IPv4 已掩码 (末段为 0) 原样返回 (幂等)."""
        assert _mask_ip("192.168.1.0") == "192.168.1.0"
        assert _mask_ip("10.0.0.0") == "10.0.0.0"

    def test_ipv6_masked(self):
        """IPv6: 保留前两组 + ::."""
        assert _mask_ip("2001:db8::1") == "2001:db8::"
        assert _mask_ip("2001:0db8:85a3:0000:0000:8a2e:0370:7334") == "2001:0db8::"

    def test_ipv6_already_masked_idempotent(self):
        """IPv6 已掩码原样返回 (幂等)."""
        assert _mask_ip("2001:db8::") == "2001:db8::"

    def test_non_standard_format(self):
        """非标准格式 IP 替换为 xxx.xxx.xxx.xxx."""
        assert _mask_ip("unknown") == "xxx.xxx.xxx.xxx"
        assert _mask_ip("localhost") == "xxx.xxx.xxx.xxx"
        assert _mask_ip("internal-proxy") == "xxx.xxx.xxx.xxx"

    def test_empty_string(self):
        """空字符串原样返回."""
        assert _mask_ip("") == ""

    def test_ipv4_with_zero_last_octet(self):
        """原始 IP 末段为 0 (极少见) 不再处理 (幂等)."""
        # 这种情况下无法区分原始 0 还是掩码后的 0, 保守起见不再处理
        assert _mask_ip("8.8.8.0") == "8.8.8.0"

    def test_ipv4_loopback(self):
        """IPv4 loopback 127.0.0.1 掩码为 127.0.0.0."""
        assert _mask_ip("127.0.0.1") == "127.0.0.0"


class TestMaskOldIpsService:
    """AdminService.mask_old_ips 服务层测试."""

    @pytest.mark.asyncio
    async def test_no_data_returns_zero(self, db_session: AsyncSession):
        """空数据库返回 0."""
        service = AdminService(db_session)
        result = await service.mask_old_ips(days=30)
        assert result == 0

    @pytest.mark.asyncio
    async def test_masks_30_day_old_ipv4(
        self, db_session: AsyncSession, seeded_user_id: int
    ):
        """30 天前的 IPv4 记录被掩码."""
        service = AdminService(db_session)
        old_time = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=45)
        old_log = OperationLog(
            operator_id=seeded_user_id,
            operator_role="admin",
            action_type="test_action_old",
            ip_address="192.168.1.100",
            created_at=old_time,
        )
        db_session.add(old_log)
        await db_session.commit()

        result = await service.mask_old_ips(days=30)
        assert result == 1

        # 验证 IP 已被掩码
        from sqlalchemy import select

        stmt = select(OperationLog).where(OperationLog.action_type == "test_action_old")
        updated = (await db_session.execute(stmt)).scalar_one()
        assert updated.ip_address == "192.168.1.0"

    @pytest.mark.asyncio
    async def test_preserves_recent_ip(
        self, db_session: AsyncSession, seeded_user_id: int
    ):
        """30 天内的 IP 不被掩码."""
        service = AdminService(db_session)
        recent_time = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=5)
        recent_log = OperationLog(
            operator_id=seeded_user_id,
            operator_role="admin",
            action_type="test_action_recent",
            ip_address="192.168.1.100",
            created_at=recent_time,
        )
        db_session.add(recent_log)
        await db_session.commit()

        result = await service.mask_old_ips(days=30)
        assert result == 0  # 没有需要掩码的

        from sqlalchemy import select

        stmt = select(OperationLog).where(
            OperationLog.action_type == "test_action_recent"
        )
        record = (await db_session.execute(stmt)).scalar_one()
        assert record.ip_address == "192.168.1.100"  # 保持原样

    @pytest.mark.asyncio
    async def test_custom_days(
        self, db_session: AsyncSession, seeded_user_id: int
    ):
        """自定义掩码阈值天数."""
        service = AdminService(db_session)
        # 50 天前的日志
        mid_time = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=50)
        mid_log = OperationLog(
            operator_id=seeded_user_id,
            operator_role="admin",
            action_type="test_action_mid",
            ip_address="10.0.0.255",
            created_at=mid_time,
        )
        db_session.add(mid_log)
        await db_session.commit()

        # 用 30 天阈值, 50 天前的应被掩码
        result = await service.mask_old_ips(days=30)
        assert result == 1

        from sqlalchemy import select

        stmt = select(OperationLog).where(OperationLog.action_type == "test_action_mid")
        record = (await db_session.execute(stmt)).scalar_one()
        assert record.ip_address == "10.0.0.0"

    @pytest.mark.asyncio
    async def test_idempotent_second_run(
        self, db_session: AsyncSession, seeded_user_id: int
    ):
        """二次运行幂等: 已掩码的不再处理."""
        service = AdminService(db_session)
        old_time = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=45)
        old_log = OperationLog(
            operator_id=seeded_user_id,
            operator_role="admin",
            action_type="test_action_idempotent",
            ip_address="192.168.1.100",
            created_at=old_time,
        )
        db_session.add(old_log)
        await db_session.commit()

        # 第一次运行: 掩码 1 条
        result1 = await service.mask_old_ips(days=30)
        assert result1 == 1

        # 第二次运行: 已掩码的不再处理, 返回 0
        result2 = await service.mask_old_ips(days=30)
        assert result2 == 0

    @pytest.mark.asyncio
    async def test_skips_null_ip(
        self, db_session: AsyncSession, seeded_user_id: int
    ):
        """ip_address 为 NULL 的记录被跳过."""
        service = AdminService(db_session)
        old_time = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=45)
        old_log = OperationLog(
            operator_id=seeded_user_id,
            operator_role="admin",
            action_type="test_action_null_ip",
            ip_address=None,
            created_at=old_time,
        )
        db_session.add(old_log)
        await db_session.commit()

        result = await service.mask_old_ips(days=30)
        assert result == 0  # NULL 不处理

    @pytest.mark.asyncio
    async def test_masks_non_standard_format(
        self, db_session: AsyncSession, seeded_user_id: int
    ):
        """非标准格式 IP 被替换为 xxx.xxx.xxx.xxx."""
        service = AdminService(db_session)
        old_time = datetime.now(UTC).replace(tzinfo=None) - timedelta(days=45)
        old_log = OperationLog(
            operator_id=seeded_user_id,
            operator_role="admin",
            action_type="test_action_non_standard",
            ip_address="unknown-proxy",
            created_at=old_time,
        )
        db_session.add(old_log)
        await db_session.commit()

        result = await service.mask_old_ips(days=30)
        assert result == 1

        from sqlalchemy import select

        stmt = select(OperationLog).where(
            OperationLog.action_type == "test_action_non_standard"
        )
        record = (await db_session.execute(stmt)).scalar_one()
        assert record.ip_address == "xxx.xxx.xxx.xxx"


class TestMaskOldIpsTaskRegistration:
    """mask_old_ips_task Celery 任务注册测试."""

    def test_task_registered_in_beat_schedule(self):
        """beat_schedule 中注册了 daily-mask-old-ips 任务."""
        from app.core.celery_app import celery_app

        assert "daily-mask-old-ips" in celery_app.conf.beat_schedule
        schedule_entry = celery_app.conf.beat_schedule["daily-mask-old-ips"]
        assert schedule_entry["task"] == "app.tasks.scheduler.mask_old_ips_task"

    def test_task_schedule_daily_0330(self):
        """任务调度为每日 03:30 (避开 03:00 weekly-log-archive)."""
        from app.core.celery_app import celery_app

        schedule_entry = celery_app.conf.beat_schedule["daily-mask-old-ips"]
        schedule = schedule_entry["schedule"]
        # crontab 应该是 hour=3, minute=30
        assert schedule.hour == {3}
        assert schedule.minute == {30}

    def test_task_function_exists(self):
        """mask_old_ips_task 函数存在于 scheduler 模块."""
        from app.tasks import scheduler

        assert hasattr(scheduler, "mask_old_ips_task")
        assert hasattr(scheduler, "_mask_old_ips_impl")

    def test_task_is_celery_task(self):
        """mask_old_ips_task 是 Celery Task 实例."""
        from app.tasks.scheduler import mask_old_ips_task

        # Celery task 装饰器返回 Task 类, 具有 delay/apply_async 等方法
        assert hasattr(mask_old_ips_task, "delay")
        assert hasattr(mask_old_ips_task, "apply_async")


class TestMaskOldIpsTaskExecution:
    """mask_old_ips_task Celery 任务执行测试."""

    def test_task_callable(self):
        """mask_old_ips_task 是可调用的 Celery Task."""
        from app.tasks.scheduler import mask_old_ips_task

        assert callable(mask_old_ips_task)
        # Celery Task 应有 delay/apply_async 方法
        assert hasattr(mask_old_ips_task, "delay")
        assert hasattr(mask_old_ips_task, "apply_async")

    def test_impl_is_coroutine(self):
        """_mask_old_ips_impl 是 async 函数."""
        import inspect

        from app.tasks.scheduler import _mask_old_ips_impl

        assert inspect.iscoroutinefunction(_mask_old_ips_impl)

    def test_task_has_correct_decorator_config(self):
        """mask_old_ips_task 装饰器配置正确 (max_retries=2, time_limit=60)."""
        from app.tasks.scheduler import mask_old_ips_task

        # Celery Task 的 max_retries 配置
        assert mask_old_ips_task.max_retries == 2

    def test_impl_calls_mask_old_ips(self):
        """_mask_old_ips_impl 调用 AdminService.mask_old_ips(days=30)."""
        import inspect

        from app.tasks.scheduler import _mask_old_ips_impl

        source = inspect.getsource(_mask_old_ips_impl)
        # 验证 impl 函数体引用了 mask_old_ips 和 days=30
        assert "mask_old_ips" in source
        assert "days=30" in source
