from __future__ import annotations

import asyncio
from datetime import datetime

from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DriftAlert
from app.models.monitoring import DriftSeverity


def run(coro):
    return asyncio.run(coro)


class TestDriftAlertModel:
    """T-INFRA-004: DriftAlert 数据模型单元测试"""

    def test_model_fields_exist(self) -> None:
        """验证 DriftAlert 模型所有字段存在且类型正确"""
        alert = DriftAlert(
            model_version="v1.5.0",
            feature_name="stress_level",
            drift_type="feature_drift",
            severity=DriftSeverity.HIGH,
            metric_value=0.35,
            threshold=0.25,
            details={"ks_statistic": 0.35, "p_value": 0.01},
            resolved_at=None,
        )
        assert alert.model_version == "v1.5.0"
        assert alert.feature_name == "stress_level"
        assert alert.drift_type == "feature_drift"
        assert alert.severity == "HIGH"
        assert alert.metric_value == 0.35
        assert alert.threshold == 0.25
        assert alert.details == {"ks_statistic": 0.35, "p_value": 0.01}
        assert alert.resolved_at is None
        assert alert.id is None
        assert alert.created_at is None

    def test_severity_enum_values(self) -> None:
        """验证严重程度枚举值"""
        assert DriftSeverity.LOW == "LOW"
        assert DriftSeverity.MEDIUM == "MEDIUM"
        assert DriftSeverity.HIGH == "HIGH"
        assert DriftSeverity.CRITICAL == "CRITICAL"

    def test_default_severity(self) -> None:
        """验证默认严重程度为 MEDIUM"""
        alert = DriftAlert(drift_type="prediction_drift")
        assert alert.severity is None
        col = DriftAlert.__table__.columns["severity"]
        assert col.default is not None
        assert col.default.arg == DriftSeverity.MEDIUM

    def test_table_name(self) -> None:
        """验证表名正确"""
        assert DriftAlert.__tablename__ == "drift_alerts"

    def test_indexes_exist(self) -> None:
        """验证复合索引存在"""
        table_args = DriftAlert.__table_args__
        assert len(table_args) == 2

        idx_names = [arg.name for arg in table_args]
        assert "ix_drift_alerts_severity_created_at" in idx_names
        assert "ix_drift_alerts_model_version_created_at" in idx_names

    async def _async_test_db_write_and_read(self, db_session: AsyncSession) -> None:
        """异步辅助：测试数据库写入和读取"""
        alert = DriftAlert(
            model_version="v1.5.0",
            feature_name="sleep_hours",
            drift_type="feature_drift",
            severity=DriftSeverity.CRITICAL,
            metric_value=0.55,
            threshold=0.25,
            details={"psi": 0.55},
            resolved_at=None,
        )
        db_session.add(alert)
        await db_session.commit()
        await db_session.refresh(alert)

        assert alert.id is not None
        assert alert.created_at is not None

        result = await db_session.execute(
            select(DriftAlert).where(DriftAlert.id == alert.id)
        )
        fetched = result.scalar_one()
        assert fetched.model_version == "v1.5.0"
        assert fetched.feature_name == "sleep_hours"
        assert fetched.severity == "CRITICAL"
        assert fetched.metric_value == 0.55

    def test_db_write_and_read(self, db_session: AsyncSession) -> None:
        """验证数据库写入和读取"""
        run(self._async_test_db_write_and_read(db_session))

    async def _async_test_resolved_at(self, db_session: AsyncSession) -> None:
        """异步辅助：测试 resolved_at 可空性"""
        alert = DriftAlert(
            drift_type="performance_drift",
            severity=DriftSeverity.LOW,
            resolved_at=datetime(2026, 4, 28, 12, 0, 0),
        )
        db_session.add(alert)
        await db_session.commit()
        await db_session.refresh(alert)

        assert alert.resolved_at is not None
        assert alert.resolved_at == datetime(2026, 4, 28, 12, 0, 0)

        alert.resolved_at = None
        await db_session.commit()
        await db_session.refresh(alert)
        assert alert.resolved_at is None

    def test_resolved_at_nullable(self, db_session: AsyncSession) -> None:
        """验证 resolved_at 可空性"""
        run(self._async_test_resolved_at(db_session))

    async def _async_test_query_by_severity(self, db_session: AsyncSession) -> None:
        """异步辅助：按 severity 查询"""
        alerts = [
            DriftAlert(
                drift_type="feature_drift",
                severity=DriftSeverity.HIGH,
                model_version="v1.5.0",
            ),
            DriftAlert(
                drift_type="feature_drift",
                severity=DriftSeverity.HIGH,
                model_version="v1.5.0",
            ),
            DriftAlert(
                drift_type="prediction_drift",
                severity=DriftSeverity.LOW,
                model_version="v1.5.0",
            ),
        ]
        db_session.add_all(alerts)
        await db_session.commit()

        result = await db_session.execute(
            select(DriftAlert).where(DriftAlert.severity == DriftSeverity.HIGH)
        )
        high_alerts = result.scalars().all()
        assert len(high_alerts) == 2

    def test_query_by_severity(self, db_session: AsyncSession) -> None:
        """验证按 severity 查询"""
        run(self._async_test_query_by_severity(db_session))

    def test_table_exists_in_db(self, db_connection) -> None:
        """验证表在数据库中真实存在"""

        def check_table(sync_conn):
            inspector = inspect(sync_conn)
            tables = inspector.get_table_names()
            assert "drift_alerts" in tables

        run(db_connection.run_sync(check_table))

    def test_table_columns_exist(self, db_connection) -> None:
        """验证所有字段在数据库中存在"""

        def check_columns(sync_conn):
            inspector = inspect(sync_conn)
            columns = {col["name"] for col in inspector.get_columns("drift_alerts")}
            expected = {
                "id",
                "model_version",
                "feature_name",
                "drift_type",
                "severity",
                "metric_value",
                "threshold",
                "details",
                "resolved_at",
                "created_at",
            }
            assert expected.issubset(columns), f"Missing columns: {expected - columns}"

        run(db_connection.run_sync(check_columns))
