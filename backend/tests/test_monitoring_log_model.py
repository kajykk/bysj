from __future__ import annotations

import asyncio

import pytest
from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MonitoringLog
from app.models.monitoring import MonitoringEventType


def run(coro):
    return asyncio.run(coro)


class TestMonitoringLogModel:
    """T-INFRA-001: MonitoringLog 数据模型单元测试"""

    def test_model_fields_exist(self, db_session: AsyncSession) -> None:
        """验证 MonitoringLog 模型所有字段存在且类型正确"""
        log = MonitoringLog(
            event_type=MonitoringEventType.INFERENCE,
            model_version="v1.5.0",
            user_id=1,
            request_payload={"input": "test"},
            response_summary={"output": "result"},
            fallback_reason=None,
            latency_ms=150.5,
        )
        assert log.event_type == "inference"
        assert log.model_version == "v1.5.0"
        assert log.user_id == 1
        assert log.request_payload == {"input": "test"}
        assert log.response_summary == {"output": "result"}
        assert log.fallback_reason is None
        assert log.latency_ms == 150.5
        assert log.id is None
        assert log.created_at is None

    def test_event_type_enum_values(self) -> None:
        """验证事件类型枚举值"""
        assert MonitoringEventType.INFERENCE == "inference"
        assert MonitoringEventType.FALLBACK == "fallback"
        assert MonitoringEventType.INPUT_ANOMALY == "input_anomaly"
        assert MonitoringEventType.DRIFT_ALERT == "drift_alert"
        assert MonitoringEventType.MODEL_LOAD == "model_load"
        assert MonitoringEventType.CANARY_SWITCH == "canary_switch"

    def test_table_name(self) -> None:
        """验证表名正确"""
        assert MonitoringLog.__tablename__ == "monitoring_logs"

    def test_indexes_exist(self) -> None:
        """验证复合索引存在"""
        table_args = MonitoringLog.__table_args__
        # P1-D-5 修复：新增 ix_monitoring_logs_user_created 复合索引，table_args 从 2 个变为 3 个
        assert len(table_args) == 3

        idx_names = [arg.name for arg in table_args]
        assert "ix_monitoring_logs_event_type_created_at" in idx_names
        assert "ix_monitoring_logs_model_version_created_at" in idx_names
        assert "ix_monitoring_logs_user_created" in idx_names

    async def _async_test_db_write_and_read(self, db_session: AsyncSession) -> None:
        """异步辅助：测试数据库写入和读取"""
        log = MonitoringLog(
            event_type=MonitoringEventType.FALLBACK,
            model_version="v1.4.0",
            user_id=None,
            request_payload=None,
            response_summary={"error": "model timeout"},
            fallback_reason="PyTorch model load failed",
            latency_ms=250.0,
        )
        db_session.add(log)
        await db_session.commit()
        await db_session.refresh(log)

        assert log.id is not None
        assert log.created_at is not None

        result = await db_session.execute(
            select(MonitoringLog).where(MonitoringLog.id == log.id)
        )
        fetched = result.scalar_one()
        assert fetched.event_type == "fallback"
        assert fetched.model_version == "v1.4.0"
        assert fetched.fallback_reason == "PyTorch model load failed"
        assert fetched.latency_ms == 250.0

    def test_db_write_and_read(self, db_session: AsyncSession) -> None:
        """验证数据库写入和读取"""
        run(self._async_test_db_write_and_read(db_session))

    async def _async_test_query_by_event_type(self, db_session: AsyncSession) -> None:
        """异步辅助：按 event_type 查询"""
        logs = [
            MonitoringLog(event_type=MonitoringEventType.INFERENCE, model_version="v1.5.0", latency_ms=100.0),
            MonitoringLog(event_type=MonitoringEventType.INFERENCE, model_version="v1.5.0", latency_ms=120.0),
            MonitoringLog(event_type=MonitoringEventType.FALLBACK, model_version="v1.4.0", latency_ms=200.0),
        ]
        db_session.add_all(logs)
        await db_session.commit()

        result = await db_session.execute(
            select(MonitoringLog).where(MonitoringLog.event_type == MonitoringEventType.INFERENCE)
        )
        inference_logs = result.scalars().all()
        assert len(inference_logs) == 2

    def test_query_by_event_type(self, db_session: AsyncSession) -> None:
        """验证按 event_type 查询"""
        run(self._async_test_query_by_event_type(db_session))

    async def _async_test_query_by_model_version(self, db_session: AsyncSession) -> None:
        """异步辅助：按 model_version 查询"""
        logs = [
            MonitoringLog(event_type=MonitoringEventType.INFERENCE, model_version="v1.5.0"),
            MonitoringLog(event_type=MonitoringEventType.INFERENCE, model_version="v1.4.0"),
            MonitoringLog(event_type=MonitoringEventType.DRIFT_ALERT, model_version="v1.5.0"),
        ]
        db_session.add_all(logs)
        await db_session.commit()

        result = await db_session.execute(
            select(MonitoringLog).where(MonitoringLog.model_version == "v1.5.0")
        )
        v150_logs = result.scalars().all()
        assert len(v150_logs) == 2

    def test_query_by_model_version(self, db_session: AsyncSession) -> None:
        """验证按 model_version 查询"""
        run(self._async_test_query_by_model_version(db_session))

    async def _async_test_nullable_fields(self, db_session: AsyncSession) -> None:
        """异步辅助：测试可空字段"""
        log = MonitoringLog(
            event_type=MonitoringEventType.MODEL_LOAD,
            model_version=None,
            user_id=None,
            request_payload=None,
            response_summary=None,
            fallback_reason=None,
            latency_ms=None,
        )
        db_session.add(log)
        await db_session.commit()
        await db_session.refresh(log)

        assert log.id is not None
        assert log.model_version is None
        assert log.latency_ms is None

    def test_nullable_fields(self, db_session: AsyncSession) -> None:
        """验证可空字段允许 NULL"""
        run(self._async_test_nullable_fields(db_session))

    def test_table_exists_in_db(self, db_connection) -> None:
        """验证表在数据库中真实存在"""
        def check_table(sync_conn):
            inspector = inspect(sync_conn)
            tables = inspector.get_table_names()
            assert "monitoring_logs" in tables

        run(db_connection.run_sync(check_table))

    def test_table_columns_exist(self, db_connection) -> None:
        """验证所有字段在数据库中存在"""
        def check_columns(sync_conn):
            inspector = inspect(sync_conn)
            columns = {col["name"] for col in inspector.get_columns("monitoring_logs")}
            expected = {
                "id",
                "event_type",
                "model_version",
                "user_id",
                "request_payload",
                "response_summary",
                "fallback_reason",
                "latency_ms",
                "created_at",
            }
            assert expected.issubset(columns), f"Missing columns: {expected - columns}"

        run(db_connection.run_sync(check_columns))

    def test_foreign_key_constraint(self, db_connection) -> None:
        """验证外键约束存在"""
        def check_fk(sync_conn):
            inspector = inspect(sync_conn)
            fks = inspector.get_foreign_keys("monitoring_logs")
            fk_found = any(
                fk["referred_table"] == "users" and "user_id" in fk["constrained_columns"]
                for fk in fks
            )
            assert fk_found, "Foreign key to users.id not found"

        run(db_connection.run_sync(check_fk))
