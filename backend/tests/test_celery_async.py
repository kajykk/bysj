"""RES-P1-003 测试: Celery 任务公共异步执行工具.

验证 ``app.core.celery_async`` 提供的进程级事件循环复用机制:
1. ``get_celery_loop`` 单例行为 (多次调用返回同一循环)
2. ``get_celery_loop`` 检测到已关闭循环时自动重建
3. ``run_async`` 同步执行协程并返回结果
4. 4 个 Celery 任务模块均通过别名导入使用 (保持 ``patch("app.tasks.xxx._run_async")`` 兼容)
"""

from __future__ import annotations

import asyncio
from unittest.mock import MagicMock

import pytest

from app.core import celery_async as celery_async_mod
from app.core.celery_async import get_celery_loop, run_async


@pytest.fixture
def reset_event_loop():
    """保存并还原 celery_async._event_loop 全局状态, 防止测试互相污染."""
    original = celery_async_mod._event_loop
    yield
    celery_async_mod._event_loop = original


class TestGetCeleryLoop:
    """Test get_celery_loop."""

    def test_returns_event_loop(self, reset_event_loop):
        """RES-P1-003-TC-001: get_celery_loop 应返回非 None 的事件循环."""
        celery_async_mod._event_loop = None
        loop = get_celery_loop()
        assert loop is not None
        assert isinstance(loop, asyncio.AbstractEventLoop)
        assert not loop.is_closed()
        # 清理: 关闭新建的循环, 防止资源泄漏
        loop.close()

    def test_caches_singleton(self, reset_event_loop):
        """RES-P1-003-TC-002: 多次调用 get_celery_loop 应返回同一事件循环."""
        celery_async_mod._event_loop = None
        loop1 = get_celery_loop()
        loop2 = get_celery_loop()
        assert loop1 is loop2
        # 清理
        loop1.close()

    def test_recreates_closed_loop(self, reset_event_loop):
        """RES-P1-003-TC-003: 已关闭的事件循环应被重建为新循环."""
        closed_loop = MagicMock()
        closed_loop.is_closed.return_value = True
        celery_async_mod._event_loop = closed_loop

        new_loop = get_celery_loop()
        try:
            assert new_loop is not closed_loop
            assert not new_loop.is_closed()
        finally:
            if not new_loop.is_closed():
                new_loop.close()


class TestRunAsync:
    """Test run_async."""

    def test_executes_coroutine(self, reset_event_loop):
        """RES-P1-003-TC-004: run_async 应同步执行协程并返回结果."""
        celery_async_mod._event_loop = None

        async def coro():
            return "ok"

        result = run_async(coro())
        assert result == "ok"
        # 清理
        get_celery_loop().close()

    def test_executes_coroutine_with_args(self, reset_event_loop):
        """RES-P1-003-TC-005: run_async 应支持带参数的协程."""
        celery_async_mod._event_loop = None

        async def add(a, b):
            return a + b

        result = run_async(add(3, 4))
        assert result == 7
        # 清理
        get_celery_loop().close()

    def test_propagates_exception(self, reset_event_loop):
        """RES-P1-003-TC-006: run_async 应将协程内的异常传播到调用方."""
        celery_async_mod._event_loop = None

        async def failing():
            raise ValueError("boom")

        with pytest.raises(ValueError, match="boom"):
            run_async(failing())
        # 清理
        get_celery_loop().close()


class TestTaskModuleAliasImports:
    """RES-P1-003-TC-007: 验证 4 个 Celery 任务模块均通过别名导入使用 celery_async.

    保证 ``patch("app.tasks.xxx._run_async")`` 等 mock 路径仍可工作,
    且 ``from app.tasks.xxx import _get_loop, _run_async`` 等 re-export 兼容.
    """

    def test_alerts_module_reexports(self):
        """alerts 模块应通过别名导入 _get_loop 和 _run_async."""
        from app.tasks import alerts

        assert hasattr(alerts, "_get_loop")
        assert hasattr(alerts, "_run_async")
        assert alerts._run_async is celery_async_mod.run_async
        assert alerts._get_loop is celery_async_mod.get_celery_loop

    def test_anomaly_detection_module_reexports(self):
        """anomaly_detection 模块应通过别名导入 _get_loop 和 _run_async."""
        from app.tasks import anomaly_detection

        assert hasattr(anomaly_detection, "_get_loop")
        assert hasattr(anomaly_detection, "_run_async")
        assert anomaly_detection._run_async is celery_async_mod.run_async
        assert anomaly_detection._get_loop is celery_async_mod.get_celery_loop

    def test_observability_module_reexports(self):
        """observability 模块应通过别名导入 _get_loop 和 _run_async."""
        from app.tasks import observability

        assert hasattr(observability, "_get_loop")
        assert hasattr(observability, "_run_async")
        assert observability._run_async is celery_async_mod.run_async
        assert observability._get_loop is celery_async_mod.get_celery_loop

    def test_scheduler_module_reexports(self):
        """scheduler 模块应通过别名导入 _get_loop 和 _run_async."""
        from app.tasks import scheduler

        assert hasattr(scheduler, "_get_loop")
        assert hasattr(scheduler, "_run_async")
        assert scheduler._run_async is celery_async_mod.run_async
        assert scheduler._get_loop is celery_async_mod.get_celery_loop

    def test_no_duplicate_event_loop_in_task_modules(self):
        """RES-P1-003-TC-008: 4 个任务模块均不应再各自维护 _event_loop 模块变量."""
        from app.tasks import alerts, anomaly_detection, observability, scheduler

        for mod in (alerts, anomaly_detection, observability, scheduler):
            assert not hasattr(
                mod, "_event_loop"
            ), f"{mod.__name__} 不应再维护模块级 _event_loop (应使用 celery_async._event_loop)"
            assert not hasattr(
                mod, "_event_loop_lock"
            ), f"{mod.__name__} 不应再维护模块级 _event_loop_lock"
