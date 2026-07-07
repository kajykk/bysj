"""PERF-P0-001 测试：predict/fusion fire-and-forget 异步化

验证要点：
1. ``_create_review_task`` 异步函数正确创建复核任务 (使用独立 session)
2. ``_create_review_task_sync`` fire-and-forget 包装正确调度任务 (不抛异常)
3. ``predict_fusion`` 端点调用 ``_save_assessment_sync`` 和 ``_create_review_task_sync``
4. ``predict_fusion`` 响应不再包含 ``review_task_id`` (前端不使用)
5. ``_create_review_task`` 优先级判定逻辑正确
6. ``_create_review_task_sync`` 调度失败不影响主流程
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.api.v1.model_predict import (
    _assessment_save_tasks,
    _create_review_task,
    _create_review_task_sync,
    _log_task_exception,
    _save_assessment_sync,
)


class TestCreateReviewTaskAsync:
    """测试 _create_review_task 异步函数."""

    @pytest.mark.asyncio
    async def test_crisis_override_sets_crisis_priority(self):
        """crisis_override=True 应设置 CRISIS_REVIEW 优先级."""
        from app.schemas.review import ReviewPriority

        result = {
            "crisis_override": True,
            "risk_level": 4,
            "risk_score": 0.95,
            "review_triggers": ["crisis_override"],
        }
        mock_review_task = MagicMock(id=42)
        mock_review_service = MagicMock()
        mock_review_service.create_review_task = AsyncMock(
            return_value=mock_review_task
        )

        with patch(
            "app.api.v1.model_predict.AsyncSessionLocal"
        ) as mock_session_cls, patch(
            "app.services.review_service.ReviewService",
            return_value=mock_review_service,
        ):
            # 模拟 async context manager
            mock_db = AsyncMock()
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            await _create_review_task(result, user_id=1)

            # 验证 ReviewService.create_review_task 被调用
            mock_review_service.create_review_task.assert_called_once()
            review_data = mock_review_service.create_review_task.call_args[0][0]
            assert review_data.priority == ReviewPriority.CRISIS_REVIEW
            assert review_data.user_id == 1
            assert review_data.risk_level == 4
            mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_high_risk_level_sets_high_risk_priority(self):
        """risk_level >= 3 (无 crisis_override) 应设置 HIGH_RISK_REVIEW."""
        from app.schemas.review import ReviewPriority

        result = {
            "crisis_override": False,
            "risk_level": 3,
            "risk_score": 0.8,
            "review_triggers": ["high_risk"],
        }
        mock_review_task = MagicMock(id=10)
        mock_review_service = MagicMock()
        mock_review_service.create_review_task = AsyncMock(
            return_value=mock_review_task
        )

        with patch(
            "app.api.v1.model_predict.AsyncSessionLocal"
        ) as mock_session_cls, patch(
            "app.services.review_service.ReviewService",
            return_value=mock_review_service,
        ):
            mock_db = AsyncMock()
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            await _create_review_task(result, user_id=2)

            review_data = mock_review_service.create_review_task.call_args[0][0]
            assert review_data.priority == ReviewPriority.HIGH_RISK_REVIEW

    @pytest.mark.asyncio
    async def test_low_risk_sets_normal_priority(self):
        """risk_level < 3 (无 crisis_override) 应设置 NORMAL_REVIEW."""
        from app.schemas.review import ReviewPriority

        result = {
            "crisis_override": False,
            "risk_level": 1,
            "risk_score": 0.3,
            "review_triggers": ["text_risk"],
        }
        mock_review_task = MagicMock(id=5)
        mock_review_service = MagicMock()
        mock_review_service.create_review_task = AsyncMock(
            return_value=mock_review_task
        )

        with patch(
            "app.api.v1.model_predict.AsyncSessionLocal"
        ) as mock_session_cls, patch(
            "app.services.review_service.ReviewService",
            return_value=mock_review_service,
        ):
            mock_db = AsyncMock()
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            await _create_review_task(result, user_id=3)

            review_data = mock_review_service.create_review_task.call_args[0][0]
            assert review_data.priority == ReviewPriority.NORMAL_REVIEW

    @pytest.mark.asyncio
    async def test_missing_risk_level_defaults_to_zero(self):
        """result 中缺失 risk_level 应默认为 0."""
        from app.schemas.review import ReviewPriority

        result = {"crisis_override": False}
        mock_review_task = MagicMock(id=1)
        mock_review_service = MagicMock()
        mock_review_service.create_review_task = AsyncMock(
            return_value=mock_review_task
        )

        with patch(
            "app.api.v1.model_predict.AsyncSessionLocal"
        ) as mock_session_cls, patch(
            "app.services.review_service.ReviewService",
            return_value=mock_review_service,
        ):
            mock_db = AsyncMock()
            mock_session_cls.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session_cls.return_value.__aexit__ = AsyncMock(return_value=None)

            await _create_review_task(result, user_id=4)

            review_data = mock_review_service.create_review_task.call_args[0][0]
            assert review_data.risk_level == 0
            assert review_data.risk_score == 0
            assert review_data.review_triggers == []
            assert review_data.crisis_override is False
            assert review_data.priority == ReviewPriority.NORMAL_REVIEW


class TestCreateReviewTaskSync:
    """测试 _create_review_task_sync fire-and-forget 包装."""

    def test_schedules_task_without_blocking(self):
        """_create_review_task_sync 应调度任务但不阻塞当前调用."""
        with patch("asyncio.ensure_future") as mock_ensure:
            mock_task = MagicMock()
            mock_ensure.return_value = mock_task

            _create_review_task_sync({"risk_level": 1}, user_id=1)

            mock_ensure.assert_called_once()
            # 任务引用应存入 _assessment_save_tasks 防止 GC
            assert (
                mock_task in _assessment_save_tasks
                or mock_task.add_done_callback.called
            )

    def test_does_not_raise_on_scheduling_error(self):
        """asyncio.ensure_future 抛异常时不应传播给调用方."""
        with patch(
            "asyncio.ensure_future", side_effect=RuntimeError("event loop closed")
        ):
            # 不应抛异常
            _create_review_task_sync({"risk_level": 1}, user_id=1)

    def test_registers_done_callbacks(self):
        """任务应注册 discard 和 _log_task_exception 回调."""
        with patch("asyncio.ensure_future") as mock_ensure:
            mock_task = MagicMock()
            mock_ensure.return_value = mock_task

            _create_review_task_sync({"risk_level": 1}, user_id=1)

            # add_done_callback 应被调用至少 2 次 (discard + _log_task_exception)
            assert mock_task.add_done_callback.call_count >= 2


class TestSaveAssessmentSyncConsistency:
    """验证 _save_assessment_sync 与 _create_review_task_sync 策略一致."""

    def test_both_use_same_task_set(self):
        """两个 fire-and-forget 函数应共用 _assessment_save_tasks 集合."""
        # 这是设计约束: 单一任务集合便于统一管理

        with patch("asyncio.ensure_future") as mock_ensure:
            mock_task1 = MagicMock()
            mock_task2 = MagicMock()
            mock_ensure.side_effect = [mock_task1, mock_task2]

            _save_assessment_sync(
                {"risk_score": 0.5}, user_id=1, assessment_type="fusion"
            )
            _create_review_task_sync({"risk_level": 1}, user_id=1)

            # 两个任务都应被加入集合 (或注册了 discard 回调)
            assert mock_task1.add_done_callback.called
            assert mock_task2.add_done_callback.called


class TestPredictFusionFireForgetIntegration:
    """验证 predict_fusion 端点不再同步等待 DB 写入."""

    def test_predict_fusion_does_not_await_save_assessment_result(self):
        """predict_fusion 应调用 _save_assessment_sync 而非 await save_assessment_result."""
        import inspect

        from app.api.v1.model_predict import predict_fusion

        source = inspect.getsource(predict_fusion)
        # 不应包含 await save_assessment_result
        assert "await save_assessment_result" not in source
        # 应包含 _save_assessment_sync
        assert "_save_assessment_sync" in source

    def test_predict_fusion_does_not_await_create_review_task_inline(self):
        """predict_fusion 不应内联 await 创建复核任务 (改为 _create_review_task_sync)."""
        import inspect

        from app.api.v1.model_predict import predict_fusion

        source = inspect.getsource(predict_fusion)
        # 不应包含内联的 await review_service.create_review_task
        assert "await review_service.create_review_task" not in source
        # 应包含 _create_review_task_sync
        assert "_create_review_task_sync" in source

    def test_predict_fusion_does_not_set_review_task_id(self):
        """predict_fusion 不应在响应中设置 review_task_id (前端不使用)."""
        import inspect

        from app.api.v1.model_predict import predict_fusion

        source = inspect.getsource(predict_fusion)
        # 不应设置 review_task_id (fire-and-forget 模式下后台任务才创建)
        assert 'result["review_task_id"]' not in source


class TestLogTaskException:
    """测试 _log_task_exception 回调."""

    def test_logs_exception_when_task_fails(self):
        """任务失败时应记录错误日志."""
        mock_task = MagicMock()
        mock_task.cancelled.return_value = False
        mock_task.exception.return_value = ValueError("test error")

        with patch("app.api.v1.model_predict.logger") as mock_logger:
            _log_task_exception(mock_task)
            mock_logger.error.assert_called_once()

    def test_no_log_when_task_cancelled(self):
        """任务被取消时不应记录错误."""
        mock_task = MagicMock()
        mock_task.cancelled.return_value = True

        with patch("app.api.v1.model_predict.logger") as mock_logger:
            _log_task_exception(mock_task)
            mock_logger.error.assert_not_called()

    def test_no_log_when_task_succeeds(self):
        """任务成功完成时不应记录错误."""
        mock_task = MagicMock()
        mock_task.cancelled.return_value = False
        mock_task.exception.return_value = None

        with patch("app.api.v1.model_predict.logger") as mock_logger:
            _log_task_exception(mock_task)
            mock_logger.error.assert_not_called()


class TestFireForgetDoesNotBlockResponse:
    """验证 fire-and-forget 不阻塞响应 (通过源码静态检查)."""

    def test_predict_fusion_has_no_await_db_write(self):
        """predict_fusion 函数体不应包含 await DB 写入操作."""
        import inspect

        from app.api.v1.model_predict import predict_fusion

        source = inspect.getsource(predict_fusion)
        # 不应包含 await save_assessment_result
        assert "await save_assessment_result" not in source
        # 不应包含 async for db in get_db (内联 DB session)
        assert "async for db in get_db" not in source
        # 不应包含 await review_service.create_review_task
        assert "await review_service.create_review_task" not in source

    def test_predict_fusion_consistent_with_other_endpoints(self):
        """predict_fusion 应与其他三个预测端点使用相同的 fire-and-forget 策略."""
        import inspect

        from app.api.v1.model_predict import (
            predict_fusion,
            predict_physiological,
            predict_tabular,
            predict_text,
        )

        fusion_src = inspect.getsource(predict_fusion)
        tabular_src = inspect.getsource(predict_tabular)
        text_src = inspect.getsource(predict_text)
        physio_src = inspect.getsource(predict_physiological)

        # 所有四个端点都应使用 _save_assessment_sync
        assert "_save_assessment_sync" in fusion_src
        assert "_save_assessment_sync" in tabular_src
        assert "_save_assessment_sync" in text_src
        assert "_save_assessment_sync" in physio_src
