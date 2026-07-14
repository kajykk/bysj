"""RES-P2-001 / RES-P2-004 / RES-P2-005 专项测试.

验证三项资源管理 P2 任务:
- RES-P2-001: celery_app worker 并发参数 (max_tasks_per_child + max_memory + time_limit) + 队列分离
- RES-P2-004: _pdf_executor Semaphore 限流
- RES-P2-005: monitoring_logs 表归档扩展 (AdminService.archive_old_monitoring_logs + Celery task + beat schedule)
"""

from __future__ import annotations

import inspect
from datetime import UTC, datetime, timedelta

import pytest

from app.models.monitoring import MonitoringLog
from app.services.admin_service import AdminService


# ============================================================================
# RES-P2-001: celery_app worker 并发参数 + 队列分离
# ============================================================================


class TestCeleryWorkerConcurrencyConfig:
    """RES-P2-001: Worker 并发参数配置测试."""

    def test_worker_max_tasks_per_child_configured(self) -> None:
        """worker_max_tasks_per_child 已配置 (防止内存泄漏)."""
        from app.core.celery_app import celery_app

        assert celery_app.conf.worker_max_tasks_per_child is not None
        assert celery_app.conf.worker_max_tasks_per_child > 0

    def test_worker_max_tasks_per_child_value_reasonable(self) -> None:
        """worker_max_tasks_per_child 取值合理 (50-1000)."""
        from app.core.celery_app import celery_app

        value = celery_app.conf.worker_max_tasks_per_child
        assert 50 <= value <= 1000

    def test_worker_max_memory_per_child_configured(self) -> None:
        """worker_max_memory_per_child 已配置 (容器化部署内存上限)."""
        from app.core.celery_app import celery_app

        assert celery_app.conf.worker_max_memory_per_child is not None
        assert celery_app.conf.worker_max_memory_per_child > 0

    def test_task_time_limit_configured(self) -> None:
        """task_time_limit (硬超时) 已配置."""
        from app.core.celery_app import celery_app

        assert celery_app.conf.task_time_limit is not None
        assert celery_app.conf.task_time_limit > 0

    def test_task_soft_time_limit_configured(self) -> None:
        """task_soft_time_limit (软超时) 已配置, 小于硬超时."""
        from app.core.celery_app import celery_app

        assert celery_app.conf.task_soft_time_limit is not None
        assert celery_app.conf.task_soft_time_limit > 0
        # 软超时应小于硬超时 (给任务自行清理的机会)
        assert celery_app.conf.task_soft_time_limit < celery_app.conf.task_time_limit


class TestCeleryQueueSeparation:
    """RES-P2-001: 队列分离测试."""

    def test_task_routes_configured(self) -> None:
        """task_routes 已配置."""
        from app.core.celery_app import celery_app

        assert celery_app.conf.task_routes is not None
        assert len(celery_app.conf.task_routes) > 0

    def test_task_default_queue_set(self) -> None:
        """task_default_queue 已设置为 'celery'."""
        from app.core.celery_app import celery_app

        assert celery_app.conf.task_default_queue == "celery"

    def test_cleanup_tasks_routed_to_low_prio(self) -> None:
        """清理类任务路由到 low_prio 队列."""
        from app.core.celery_app import celery_app

        routes = celery_app.conf.task_routes
        # weekly_log_archive 应路由到 low_prio
        assert "app.tasks.scheduler.weekly_log_archive" in routes
        assert routes["app.tasks.scheduler.weekly_log_archive"]["queue"] == "celery:low_prio"

    def test_weekly_risk_assessment_archive_routed_to_low_prio(self) -> None:
        """PERF-P2-003 归档任务路由到 low_prio."""
        from app.core.celery_app import celery_app

        routes = celery_app.conf.task_routes
        assert "app.tasks.scheduler.weekly_risk_assessment_archive" in routes
        assert routes["app.tasks.scheduler.weekly_risk_assessment_archive"]["queue"] == "celery:low_prio"

    def test_weekly_monitoring_logs_archive_routed_to_low_prio(self) -> None:
        """RES-P2-005 归档任务路由到 low_prio."""
        from app.core.celery_app import celery_app

        routes = celery_app.conf.task_routes
        assert "app.tasks.scheduler.weekly_monitoring_logs_archive" in routes
        assert routes["app.tasks.scheduler.weekly_monitoring_logs_archive"]["queue"] == "celery:low_prio"

    def test_normal_tasks_routed_to_default_queue(self) -> None:
        """普通任务路由到默认队列 (celery)."""
        from app.core.celery_app import celery_app

        routes = celery_app.conf.task_routes
        assert "app.tasks.scheduler.daily_risk_scan" in routes
        assert routes["app.tasks.scheduler.daily_risk_scan"]["queue"] == "celery"


# ============================================================================
# RES-P2-004: _pdf_executor Semaphore 限流
# ============================================================================


class TestPdfSemaphoreConfig:
    """RES-P2-004: PDF Semaphore 配置测试."""

    def test_pdf_semaphore_exists(self) -> None:
        """_pdf_semaphore 已定义."""
        from app.services import risk_service

        assert hasattr(risk_service, "_pdf_semaphore")

    def test_pdf_semaphore_is_semaphore(self) -> None:
        """_pdf_semaphore 是 threading.Semaphore 实例."""
        import threading

        from app.services import risk_service

        assert isinstance(risk_service._pdf_semaphore, threading.Semaphore)

    def test_max_concurrent_pdf_tasks_constant_exists(self) -> None:
        """MAX_CONCURRENT_PDF_TASKS 常量已定义."""
        from app.services import risk_service

        assert hasattr(risk_service, "MAX_CONCURRENT_PDF_TASKS")

    def test_max_concurrent_pdf_tasks_value_reasonable(self) -> None:
        """MAX_CONCURRENT_PDF_TASKS 取值合理 (>max_workers=4)."""
        from app.services import risk_service

        assert risk_service.MAX_CONCURRENT_PDF_TASKS > 4
        assert risk_service.MAX_CONCURRENT_PDF_TASKS <= 100  # 不宜过大

    def test_generate_pdf_async_uses_semaphore(self) -> None:
        """_generate_pdf_report_async 方法使用 Semaphore (acquire/release)."""
        from app.services.risk_service import RiskService

        source = inspect.getsource(RiskService._generate_pdf_report_async)
        assert "_pdf_semaphore" in source
        assert "acquire" in source
        assert "release" in source
        # RES-P2-004 注释
        assert "RES-P2-004" in source

    def test_threading_imported(self) -> None:
        """risk_service 导入 threading 模块."""
        from app.services import risk_service

        assert hasattr(risk_service, "threading")


# ============================================================================
# RES-P2-005: monitoring_logs 表归档扩展
# ============================================================================


class TestArchiveOldMonitoringLogsService:
    """RES-P2-005: AdminService.archive_old_monitoring_logs 测试."""

    async def test_empty_data_returns_zero(self, db_session) -> None:
        """无数据时返回 0."""
        service = AdminService(db_session)
        result = await service.archive_old_monitoring_logs(days=180)
        assert result == 0

    async def test_deletes_old_records(self, db_session) -> None:
        """删除超过阈值的 MonitoringLog 记录."""
        now = datetime.now(UTC).replace(tzinfo=None)
        old = MonitoringLog(
            event_type="inference",
            model_version="v1.0",
            created_at=now - timedelta(days=200),
        )
        recent = MonitoringLog(
            event_type="inference",
            model_version="v1.0",
            created_at=now - timedelta(days=30),
        )
        db_session.add_all([old, recent])
        await db_session.flush()

        service = AdminService(db_session)
        result = await service.archive_old_monitoring_logs(days=180)
        # SQLite rowcount 可能返回 -1/0, 至少不报错
        assert result >= 0

        from sqlalchemy import select

        remaining = await db_session.execute(select(MonitoringLog))
        records = remaining.scalars().all()
        # recent 应保留
        assert len(records) == 1
        assert records[0].event_type == "inference"

    async def test_preserves_recent_records(self, db_session) -> None:
        """保留阈值内的记录."""
        now = datetime.now(UTC).replace(tzinfo=None)
        recent = MonitoringLog(
            event_type="fallback",
            model_version="v1.0",
            created_at=now - timedelta(days=10),
        )
        db_session.add(recent)
        await db_session.flush()

        service = AdminService(db_session)
        await service.archive_old_monitoring_logs(days=180)

        from sqlalchemy import select

        remaining = await db_session.execute(select(MonitoringLog))
        records = remaining.scalars().all()
        assert len(records) == 1

    async def test_custom_days_parameter(self, db_session) -> None:
        """自定义 days 参数: 30 天删除 60 天前的记录."""
        now = datetime.now(UTC).replace(tzinfo=None)
        old = MonitoringLog(
            event_type="drift_alert",
            created_at=now - timedelta(days=60),
        )
        db_session.add(old)
        await db_session.flush()

        service = AdminService(db_session)
        await service.archive_old_monitoring_logs(days=30)

        from sqlalchemy import select

        remaining = await db_session.execute(select(MonitoringLog))
        records = remaining.scalars().all()
        assert len(records) == 0

    async def test_multiple_event_types(self, db_session) -> None:
        """多种 event_type 的记录都被归档."""
        now = datetime.now(UTC).replace(tzinfo=None)
        records = [
            MonitoringLog(event_type="inference", created_at=now - timedelta(days=200)),
            MonitoringLog(event_type="fallback", created_at=now - timedelta(days=200)),
            MonitoringLog(event_type="drift_alert", created_at=now - timedelta(days=200)),
            MonitoringLog(event_type="canary_switch", created_at=now - timedelta(days=200)),
            MonitoringLog(event_type="input_anomaly", created_at=now - timedelta(days=10)),
        ]
        db_session.add_all(records)
        await db_session.flush()

        service = AdminService(db_session)
        await service.archive_old_monitoring_logs(days=180)

        from sqlalchemy import select

        remaining = await db_session.execute(select(MonitoringLog))
        result = remaining.scalars().all()
        assert len(result) == 1
        assert result[0].event_type == "input_anomaly"


class TestMonitoringLogsCeleryTask:
    """RES-P2-005: Celery task 注册测试."""

    def test_task_function_exists(self) -> None:
        """weekly_monitoring_logs_archive task 函数存在."""
        from app.tasks import scheduler

        assert hasattr(scheduler, "weekly_monitoring_logs_archive")
        assert callable(scheduler.weekly_monitoring_logs_archive)

    def test_impl_function_exists(self) -> None:
        """_weekly_monitoring_logs_archive_impl 实现函数存在."""
        from app.tasks import scheduler

        assert hasattr(scheduler, "_weekly_monitoring_logs_archive_impl")
        assert callable(scheduler._weekly_monitoring_logs_archive_impl)

    def test_task_is_celery_task(self) -> None:
        """weekly_monitoring_logs_archive 是 Celery task."""
        from app.tasks.scheduler import weekly_monitoring_logs_archive

        assert hasattr(weekly_monitoring_logs_archive, "delay")
        assert hasattr(weekly_monitoring_logs_archive, "apply_async")

    def test_task_has_bind_true(self) -> None:
        """task 装饰器配置 bind=True."""
        import app.tasks.scheduler as scheduler_mod

        source = inspect.getsource(scheduler_mod)
        task_start = source.find("def weekly_monitoring_logs_archive")
        decorator_section = source[max(0, task_start - 300) : task_start]
        assert "bind=True" in decorator_section

    def test_task_has_retry_config(self) -> None:
        """task 装饰器配置 max_retries + default_retry_delay."""
        from app.tasks.scheduler import weekly_monitoring_logs_archive

        assert weekly_monitoring_logs_archive.max_retries is not None
        assert weekly_monitoring_logs_archive.default_retry_delay is not None

    def test_beat_schedule_registered(self) -> None:
        """beat_schedule 注册了 weekly-monitoring-logs-archive."""
        from app.core.celery_app import celery_app

        assert "weekly-monitoring-logs-archive" in celery_app.conf.beat_schedule
        schedule = celery_app.conf.beat_schedule["weekly-monitoring-logs-archive"]
        assert schedule["task"] == "app.tasks.scheduler.weekly_monitoring_logs_archive"

    def test_beat_schedule_weekly(self) -> None:
        """beat schedule 每周一 05:00 执行."""
        from app.core.celery_app import celery_app

        schedule = celery_app.conf.beat_schedule["weekly-monitoring-logs-archive"]
        crontab = schedule["schedule"]
        # 每周一
        assert crontab.day_of_week == {1}
        assert crontab.hour == {5}
        assert crontab.minute == {0}

    def test_beat_schedule_does_not_conflict(self) -> None:
        """beat schedule 不与其他任务冲突 (05:00 独立时间槽)."""
        from app.core.celery_app import celery_app

        schedule = celery_app.conf.beat_schedule["weekly-monitoring-logs-archive"]
        crontab = schedule["schedule"]
        # 确认不是 03:00 (weekly-log-archive)
        assert crontab.hour != {3} or crontab.minute != {0}
        # 确认不是 03:30 (daily-mask-old-ips)
        assert crontab.hour != {3} or crontab.minute != {30}
        # 确认不是 04:00 (cleanup-experiment-artifacts)
        assert crontab.hour != {4} or crontab.minute != {0}
        # 确认不是 04:30 (weekly-risk-assessment-archive)
        assert crontab.hour != {4} or crontab.minute != {30}


class TestMonitoringLogsSourceStructure:
    """RES-P2-005: 源码静态扫描测试."""

    def test_service_method_exists(self) -> None:
        """AdminService.archive_old_monitoring_logs 方法存在."""
        assert hasattr(AdminService, "archive_old_monitoring_logs")
        assert callable(getattr(AdminService, "archive_old_monitoring_logs"))

    def test_service_method_has_res_p2_005_annotation(self) -> None:
        """方法 docstring 标注 RES-P2-005."""
        source = inspect.getsource(AdminService.archive_old_monitoring_logs)
        assert "RES-P2-005" in source

    def test_service_method_default_days_180(self) -> None:
        """方法默认 days=180 (监控日志保留更久)."""
        sig = inspect.signature(AdminService.archive_old_monitoring_logs)
        days_param = sig.parameters.get("days")
        assert days_param is not None
        assert days_param.default == 180

    def test_service_method_uses_commit(self) -> None:
        """方法使用 commit 提交事务 (与 archive_old_logs 一致)."""
        source = inspect.getsource(AdminService.archive_old_monitoring_logs)
        assert "await self.db.commit()" in source

    def test_service_method_uses_monitoring_log_model(self) -> None:
        """方法导入并使用 MonitoringLog 模型."""
        source = inspect.getsource(AdminService.archive_old_monitoring_logs)
        assert "MonitoringLog" in source

    def test_task_source_has_res_p2_005_annotation(self) -> None:
        """Celery task docstring 标注 RES-P2-005."""
        from app.tasks.scheduler import weekly_monitoring_logs_archive

        source = inspect.getsource(weekly_monitoring_logs_archive)
        assert "RES-P2-005" in source
