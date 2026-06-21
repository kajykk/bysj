from __future__ import annotations

import asyncio
from datetime import datetime

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CanaryRecord
from app.models.monitoring import CanaryStatus


def run(coro):
    return asyncio.run(coro)


class TestCanaryRecordModel:
    """T-INFRA-002: CanaryRecord 数据模型单元测试"""

    def test_model_fields_exist(self) -> None:
        """验证 CanaryRecord 模型所有字段存在且类型正确"""
        record = CanaryRecord(
            version="v1.5.0",
            traffic_percent=5,
            status=CanaryStatus.RUNNING,
            auto_rollback_thresholds={"max_fallback_rate": 0.03},
            triggered_by=1,
            started_at=datetime(2026, 4, 28, 10, 0, 0),
            ended_at=None,
            rollback_reason=None,
        )
        assert record.version == "v1.5.0"
        assert record.traffic_percent == 5
        assert record.status == "running"
        assert record.auto_rollback_thresholds == {"max_fallback_rate": 0.03}
        assert record.triggered_by == 1
        assert record.started_at is not None
        assert record.ended_at is None
        assert record.rollback_reason is None
        assert record.id is None
        assert record.created_at is None

    def test_status_enum_values(self) -> None:
        """验证状态枚举值"""
        assert CanaryStatus.PENDING == "pending"
        assert CanaryStatus.RUNNING == "running"
        assert CanaryStatus.PAUSED == "paused"
        assert CanaryStatus.ROLLED_BACK == "rolled_back"
        assert CanaryStatus.COMPLETED == "completed"

    def test_default_status(self) -> None:
        """验证默认状态为 pending (数据库默认值，实例化时为None)"""
        record = CanaryRecord(version="v1.5.0")
        assert record.status is None
        col = CanaryRecord.__table__.columns["status"]
        assert col.default is not None
        assert col.default.arg == CanaryStatus.PENDING

    def test_default_traffic_percent(self) -> None:
        """验证默认流量百分比为 1 (数据库默认值，实例化时为None)"""
        record = CanaryRecord(version="v1.5.0")
        assert record.traffic_percent is None
        col = CanaryRecord.__table__.columns["traffic_percent"]
        assert col.default is not None
        assert col.default.arg == 1

    def test_default_rollback_thresholds(self) -> None:
        """验证默认回滚阈值配置 (数据库默认值)"""
        record = CanaryRecord(version="v1.5.0")
        assert record.auto_rollback_thresholds is None
        col = CanaryRecord.__table__.columns["auto_rollback_thresholds"]
        assert col.default is not None

    def test_table_name(self) -> None:
        """验证表名正确"""
        assert CanaryRecord.__tablename__ == "canary_records"

    def test_indexes_exist(self) -> None:
        """验证复合索引存在"""
        table_args = CanaryRecord.__table_args__
        assert len(table_args) == 2

        idx_names = [arg.name for arg in table_args]
        assert "ix_canary_records_status_started_at" in idx_names
        assert "ix_canary_records_version_created_at" in idx_names

    async def _async_test_db_write_and_read(self, db_session: AsyncSession) -> None:
        """异步辅助：测试数据库写入和读取"""
        record = CanaryRecord(
            version="v1.5.0",
            traffic_percent=25,
            status=CanaryStatus.RUNNING,
            auto_rollback_thresholds={"max_fallback_rate": 0.05},
            triggered_by=None,
            started_at=datetime(2026, 4, 28, 10, 0, 0),
            ended_at=None,
            rollback_reason=None,
        )
        db_session.add(record)
        await db_session.commit()
        await db_session.refresh(record)

        assert record.id is not None
        assert record.created_at is not None

        result = await db_session.execute(
            select(CanaryRecord).where(CanaryRecord.id == record.id)
        )
        fetched = result.scalar_one()
        assert fetched.version == "v1.5.0"
        assert fetched.traffic_percent == 25
        assert fetched.status == "running"

    def test_db_write_and_read(self, db_session: AsyncSession) -> None:
        """验证数据库写入和读取"""
        run(self._async_test_db_write_and_read(db_session))

    async def _async_test_query_by_status(self, db_session: AsyncSession) -> None:
        """异步辅助：按 status 查询"""
        records = [
            CanaryRecord(version="v1.5.0", status=CanaryStatus.RUNNING, traffic_percent=5),
            CanaryRecord(version="v1.5.0", status=CanaryStatus.RUNNING, traffic_percent=25),
            CanaryRecord(version="v1.4.0", status=CanaryStatus.ROLLED_BACK, traffic_percent=0),
        ]
        db_session.add_all(records)
        await db_session.commit()

        result = await db_session.execute(
            select(CanaryRecord).where(CanaryRecord.status == CanaryStatus.RUNNING)
        )
        running_records = result.scalars().all()
        assert len(running_records) == 2

    def test_query_by_status(self, db_session: AsyncSession) -> None:
        """验证按 status 查询"""
        run(self._async_test_query_by_status(db_session))

    async def _async_test_query_by_version(self, db_session: AsyncSession) -> None:
        """异步辅助：按 version 查询"""
        records = [
            CanaryRecord(version="v1.5.0", status=CanaryStatus.RUNNING),
            CanaryRecord(version="v1.4.0", status=CanaryStatus.COMPLETED),
            CanaryRecord(version="v1.5.0", status=CanaryStatus.PAUSED),
        ]
        db_session.add_all(records)
        await db_session.commit()

        result = await db_session.execute(
            select(CanaryRecord).where(CanaryRecord.version == "v1.5.0")
        )
        v150_records = result.scalars().all()
        assert len(v150_records) == 2

    def test_query_by_version(self, db_session: AsyncSession) -> None:
        """验证按 version 查询"""
        run(self._async_test_query_by_version(db_session))

    async def _async_test_status_transitions(self, db_session: AsyncSession) -> None:
        """异步辅助：测试状态流转"""
        record = CanaryRecord(
            version="v1.5.0",
            status=CanaryStatus.PENDING,
            traffic_percent=1,
        )
        db_session.add(record)
        await db_session.commit()
        await db_session.refresh(record)

        record.status = CanaryStatus.RUNNING
        record.started_at = datetime(2026, 4, 28, 10, 0, 0)
        await db_session.commit()
        await db_session.refresh(record)
        assert record.status == "running"

        record.status = CanaryStatus.ROLLED_BACK
        record.ended_at = datetime(2026, 4, 28, 11, 0, 0)
        record.rollback_reason = "Fallback rate exceeded threshold"
        await db_session.commit()
        await db_session.refresh(record)
        assert record.status == "rolled_back"
        assert record.rollback_reason == "Fallback rate exceeded threshold"

    def test_status_transitions(self, db_session: AsyncSession) -> None:
        """验证状态流转和回滚原因记录"""
        run(self._async_test_status_transitions(db_session))

    def test_table_exists_in_db(self, db_connection) -> None:
        """验证表在数据库中真实存在"""
        def check_table(sync_conn):
            inspector = inspect(sync_conn)
            tables = inspector.get_table_names()
            assert "canary_records" in tables

        run(db_connection.run_sync(check_table))

    def test_table_columns_exist(self, db_connection) -> None:
        """验证所有字段在数据库中存在"""
        def check_columns(sync_conn):
            inspector = inspect(sync_conn)
            columns = {col["name"] for col in inspector.get_columns("canary_records")}
            expected = {
                "id",
                "version",
                "traffic_percent",
                "status",
                "auto_rollback_thresholds",
                "triggered_by",
                "started_at",
                "ended_at",
                "rollback_reason",
                "created_at",
            }
            assert expected.issubset(columns), f"Missing columns: {expected - columns}"

        run(db_connection.run_sync(check_columns))

    def test_foreign_key_constraint(self, db_connection) -> None:
        """验证外键约束存在"""
        def check_fk(sync_conn):
            inspector = inspect(sync_conn)
            fks = inspector.get_foreign_keys("canary_records")
            fk_found = any(
                fk["referred_table"] == "users" and "triggered_by" in fk["constrained_columns"]
                for fk in fks
            )
            assert fk_found, "Foreign key to users.id not found"

        run(db_connection.run_sync(check_fk))
