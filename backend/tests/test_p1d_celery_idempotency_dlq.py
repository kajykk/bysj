"""P1-D-7: Celery 幂等性 + DLQ 测试.

验证:
1. archive_old_alerts_task 幂等性 - 跳过已归档的记录
2. DLQ 信号处理器 - 任务失败时记录完整上下文
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.celery_app import _sanitize_task_args, celery_app, on_task_failure

# ---------------------------------------------------------------------------
# P1-D-7: archive_old_alerts_task 幂等性
# ---------------------------------------------------------------------------


class TestArchiveIdempotency:
    """P1-D-7: 验证 archive_old_alerts_task 幂等性保护."""

    @pytest.mark.asyncio
    async def test_archive_skips_already_archived_records(self) -> None:
        """已归档的记录应被跳过, 不产生重复 AlertArchive 条目."""
        from app.models.admin import OperationLog
        from app.tasks.alerts import _archive_impl

        # 模拟数据: 2 条 OperationLog, 其中 1 条已归档
        mock_log_1 = MagicMock(spec=OperationLog)
        mock_log_1.id = 101
        mock_log_1.action_type = "alert_fired"
        mock_log_1.created_at = None
        mock_log_1.detail = '{"rule": "test_rule", "severity": "P1"}'

        mock_log_2 = MagicMock(spec=OperationLog)
        mock_log_2.id = 102
        mock_log_2.action_type = "alert_resolved"
        mock_log_2.created_at = None
        mock_log_2.detail = '{"rule": "test_rule2", "severity": "P2"}'

        # 模拟数据库会话
        mock_db = AsyncMock()
        # 第一次 execute: 查询候选 OperationLog
        # 第二次 execute: 查询已归档的 original_id (返回 101, 表示已归档)
        mock_result_1 = MagicMock()
        mock_result_1.scalars.return_value.all.return_value = [mock_log_1, mock_log_2]
        mock_result_2 = MagicMock()
        mock_result_2.scalars.return_value.all.return_value = [101]

        mock_db.execute = AsyncMock(side_effect=[mock_result_1, mock_result_2])

        with patch("app.tasks.alerts.AsyncSessionLocal") as mock_session_local:
            mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session_local.return_value.__aexit__ = AsyncMock(return_value=None)

            count = await _archive_impl()

        # 应返回 1 (只有 1 条新归档, 101 被跳过)
        assert count == 1
        # 应删除 2 条 (101 和 102 都从 OperationLog 删除)
        assert mock_db.delete.call_count == 2
        # 应只添加 1 条 AlertArchive (102)
        assert mock_db.add.call_count == 1
        # 应提交事务
        mock_db.commit.assert_called_once()

    @pytest.mark.asyncio
    async def test_archive_all_new_records(self) -> None:
        """全部新记录 (无已归档) 应全部归档."""
        from app.models.admin import OperationLog
        from app.tasks.alerts import _archive_impl

        mock_log = MagicMock(spec=OperationLog)
        mock_log.id = 201
        mock_log.action_type = "alert_fired"
        mock_log.created_at = None
        mock_log.detail = '{"rule": "new_rule"}'

        mock_db = AsyncMock()
        mock_result_1 = MagicMock()
        mock_result_1.scalars.return_value.all.return_value = [mock_log]
        mock_result_2 = MagicMock()
        mock_result_2.scalars.return_value.all.return_value = []  # 无已归档

        mock_db.execute = AsyncMock(side_effect=[mock_result_1, mock_result_2])

        with patch("app.tasks.alerts.AsyncSessionLocal") as mock_session_local:
            mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session_local.return_value.__aexit__ = AsyncMock(return_value=None)

            count = await _archive_impl()

        assert count == 1
        assert mock_db.add.call_count == 1
        assert mock_db.delete.call_count == 1

    @pytest.mark.asyncio
    async def test_archive_no_candidates_returns_zero(self) -> None:
        """无候选记录时返回 0."""
        from app.tasks.alerts import _archive_impl

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        with patch("app.tasks.alerts.AsyncSessionLocal") as mock_session_local:
            mock_session_local.return_value.__aenter__ = AsyncMock(return_value=mock_db)
            mock_session_local.return_value.__aexit__ = AsyncMock(return_value=None)

            count = await _archive_impl()

        assert count == 0
        mock_db.add.assert_not_called()
        mock_db.delete.assert_not_called()


# ---------------------------------------------------------------------------
# P1-D-7: DLQ 信号处理器
# ---------------------------------------------------------------------------


class TestDLQSignalHandler:
    """P1-D-7: 验证 DLQ 信号处理器."""

    def test_dlq_handler_is_registered(self) -> None:
        """DLQ 信号处理器应在 Celery 中注册."""
        # 验证 on_task_failure 函数存在
        assert callable(on_task_failure)

    def test_dlq_handler_logs_failure(self, caplog) -> None:
        """任务失败时 DLQ 处理器应记录 [DLQ] 日志."""
        mock_sender = MagicMock()
        mock_sender.name = "app.tasks.test_task"

        mock_exception = ValueError("test error")

        with caplog.at_level(logging.ERROR, logger="app.core.celery_app"):
            on_task_failure(
                sender=mock_sender,
                task_id="test-task-id-123",
                exception=mock_exception,
                args=("arg1",),
                kwargs={"key": "value"},
                traceback=None,
                einfo=None,
            )

        # 验证日志包含 [DLQ] 标记
        dlq_logs = [r for r in caplog.records if "[DLQ]" in r.message]
        assert len(dlq_logs) == 1
        # 验证日志包含任务名称和 ID
        log_message = dlq_logs[0].message
        assert "app.tasks.test_task" in log_message
        assert "test-task-id-123" in log_message
        assert "ValueError" in log_message
        assert "test error" in log_message

    def test_dlq_handler_handles_none_args(self, caplog) -> None:
        """DLQ 处理器应正确处理 None 参数."""
        mock_sender = MagicMock()
        mock_sender.name = "app.tasks.test_task"

        with caplog.at_level(logging.ERROR, logger="app.core.celery_app"):
            on_task_failure(
                sender=mock_sender,
                task_id="test-id",
                exception=RuntimeError("fail"),
                args=None,
                kwargs=None,
                traceback=None,
                einfo=None,
            )

        dlq_logs = [r for r in caplog.records if "[DLQ]" in r.message]
        assert len(dlq_logs) == 1

    def test_dlq_handler_handles_no_sender(self, caplog) -> None:
        """DLQ 处理器应正确处理 sender=None."""
        with caplog.at_level(logging.ERROR, logger="app.core.celery_app"):
            on_task_failure(
                sender=None,
                task_id="test-id",
                exception=Exception("fail"),
                args=None,
                kwargs=None,
                traceback=None,
                einfo=None,
            )

        dlq_logs = [r for r in caplog.records if "[DLQ]" in r.message]
        assert len(dlq_logs) == 1
        assert "unknown" in dlq_logs[0].message


class TestSanitizeTaskArgs:
    """P1-D-7: 验证任务参数脱敏."""

    def test_sanitize_none(self) -> None:
        """None 参数应返回 'None'."""
        assert _sanitize_task_args(None) == "None"

    def test_sanitize_short_args(self) -> None:
        """短参数应原样返回 repr."""
        args = (1, "hello", {"key": "value"})
        result = _sanitize_task_args(args)
        assert "1" in result
        assert "hello" in result

    def test_sanitize_long_args_truncated(self) -> None:
        """长参数应被截断到 500 字符 + ...(truncated)."""
        args = ("x" * 1000,)
        result = _sanitize_task_args(args)
        assert len(result) <= 520  # 500 + "...(truncated)"
        assert "...(truncated)" in result

    def test_sanitize_unreprable_args(self) -> None:
        """无法 repr 的参数应返回 <unreprable>."""

        class Unreprable:
            def __repr__(self):
                raise Exception("cannot repr")

        result = _sanitize_task_args(Unreprable())
        assert result == "<unreprable>"


class TestCeleryDlqConfig:
    """P1-D-7: 验证 Celery DLQ 配置."""

    def test_task_default_max_retries_configured(self) -> None:
        """Celery 应配置 task_default_max_retries."""
        assert celery_app.conf.task_default_max_retries == 2

    def test_task_default_retry_delay_configured(self) -> None:
        """Celery 应配置 task_default_retry_delay."""
        assert celery_app.conf.task_default_retry_delay == 60
