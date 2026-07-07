from __future__ import annotations

import asyncio

from sqlalchemy import inspect, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ValidationResult


def run(coro):
    return asyncio.run(coro)


class TestValidationResultModel:
    """T-INFRA-003: ValidationResult 数据模型单元测试"""

    def test_model_fields_exist(self) -> None:
        """验证 ValidationResult 模型所有字段存在且类型正确"""
        result = ValidationResult(
            sample_id="sample_001",
            model_version="v1.5.0",
            ground_truth=1,
            prediction=1,
            confidence=0.92,
            is_correct=1,
            failure_reason=None,
        )
        assert result.sample_id == "sample_001"
        assert result.model_version == "v1.5.0"
        assert result.ground_truth == 1
        assert result.prediction == 1
        assert result.confidence == 0.92
        assert result.is_correct == 1
        assert result.failure_reason is None
        assert result.id is None
        assert result.created_at is None

    def test_table_name(self) -> None:
        """验证表名正确"""
        assert ValidationResult.__tablename__ == "validation_results"

    def test_indexes_exist(self) -> None:
        """验证复合索引存在"""
        table_args = ValidationResult.__table_args__
        assert len(table_args) == 2

        idx_names = [arg.name for arg in table_args]
        assert "ix_validation_results_model_version_created_at" in idx_names
        assert "ix_validation_results_is_correct_created_at" in idx_names

    async def _async_test_db_write_and_read(self, db_session: AsyncSession) -> None:
        """异步辅助：测试数据库写入和读取"""
        result = ValidationResult(
            sample_id="sample_002",
            model_version="v1.5.0",
            ground_truth=0,
            prediction=1,
            confidence=0.65,
            is_correct=0,
            failure_reason="False positive: low confidence",
        )
        db_session.add(result)
        await db_session.commit()
        await db_session.refresh(result)

        assert result.id is not None
        assert result.created_at is not None

        fetched_result = await db_session.execute(
            select(ValidationResult).where(ValidationResult.id == result.id)
        )
        fetched = fetched_result.scalar_one()
        assert fetched.sample_id == "sample_002"
        assert fetched.model_version == "v1.5.0"
        assert fetched.ground_truth == 0
        assert fetched.prediction == 1
        assert fetched.is_correct == 0
        assert fetched.failure_reason == "False positive: low confidence"

    def test_db_write_and_read(self, db_session: AsyncSession) -> None:
        """验证数据库写入和读取"""
        run(self._async_test_db_write_and_read(db_session))

    async def _async_test_query_by_model_version(
        self, db_session: AsyncSession
    ) -> None:
        """异步辅助：按 model_version 查询"""
        results = [
            ValidationResult(
                sample_id="s1",
                model_version="v1.5.0",
                ground_truth=1,
                prediction=1,
                is_correct=1,
            ),
            ValidationResult(
                sample_id="s2",
                model_version="v1.5.0",
                ground_truth=0,
                prediction=0,
                is_correct=1,
            ),
            ValidationResult(
                sample_id="s3",
                model_version="v1.4.0",
                ground_truth=1,
                prediction=0,
                is_correct=0,
            ),
        ]
        db_session.add_all(results)
        await db_session.commit()

        result = await db_session.execute(
            select(ValidationResult).where(ValidationResult.model_version == "v1.5.0")
        )
        v150_results = result.scalars().all()
        assert len(v150_results) == 2

    def test_query_by_model_version(self, db_session: AsyncSession) -> None:
        """验证按 model_version 查询"""
        run(self._async_test_query_by_model_version(db_session))

    async def _async_test_query_by_is_correct(self, db_session: AsyncSession) -> None:
        """异步辅助：按 is_correct 查询"""
        results = [
            ValidationResult(sample_id="s1", model_version="v1.5.0", is_correct=1),
            ValidationResult(sample_id="s2", model_version="v1.5.0", is_correct=1),
            ValidationResult(sample_id="s3", model_version="v1.5.0", is_correct=0),
            ValidationResult(sample_id="s4", model_version="v1.5.0", is_correct=None),
        ]
        db_session.add_all(results)
        await db_session.commit()

        result = await db_session.execute(
            select(ValidationResult).where(ValidationResult.is_correct == 1)
        )
        correct_results = result.scalars().all()
        assert len(correct_results) == 2

    def test_query_by_is_correct(self, db_session: AsyncSession) -> None:
        """验证按 is_correct 查询"""
        run(self._async_test_query_by_is_correct(db_session))

    async def _async_test_nullable_fields(self, db_session: AsyncSession) -> None:
        """异步辅助：测试可空字段"""
        result = ValidationResult(
            sample_id="s_null",
            model_version="v1.5.0",
            ground_truth=None,
            prediction=None,
            confidence=None,
            is_correct=None,
            failure_reason=None,
        )
        db_session.add(result)
        await db_session.commit()
        await db_session.refresh(result)

        assert result.id is not None
        assert result.ground_truth is None
        assert result.prediction is None
        assert result.confidence is None
        assert result.is_correct is None

    def test_nullable_fields(self, db_session: AsyncSession) -> None:
        """验证可空字段允许 NULL"""
        run(self._async_test_nullable_fields(db_session))

    def test_table_exists_in_db(self, db_connection) -> None:
        """验证表在数据库中真实存在"""

        def check_table(sync_conn):
            inspector = inspect(sync_conn)
            tables = inspector.get_table_names()
            assert "validation_results" in tables

        run(db_connection.run_sync(check_table))

    def test_table_columns_exist(self, db_connection) -> None:
        """验证所有字段在数据库中存在"""

        def check_columns(sync_conn):
            inspector = inspect(sync_conn)
            columns = {
                col["name"] for col in inspector.get_columns("validation_results")
            }
            expected = {
                "id",
                "sample_id",
                "model_version",
                "ground_truth",
                "prediction",
                "confidence",
                "is_correct",
                "failure_reason",
                "created_at",
            }
            assert expected.issubset(columns), f"Missing columns: {expected - columns}"

        run(db_connection.run_sync(check_columns))
