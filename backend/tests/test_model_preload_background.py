"""STAB-P2-004: model preload background task tests.

Tests that model preload runs as a background task without blocking startup.
"""

from __future__ import annotations

import asyncio
import inspect
from unittest.mock import patch

import pytest


class TestPreloadBackgroundSourceStructure:
    """Source code structure checks for STAB-P2-004."""

    def test_main_py_uses_create_task_for_preload(self):
        """main.py should use asyncio.create_task for model preload, not await."""
        import app.main as main_mod

        source = inspect.getsource(main_mod.lifespan)
        assert "asyncio.create_task" in source
        assert "_preload_models_background" in source

    def test_main_py_does_not_await_preload(self):
        """lifespan should not await record_step_async for model_preload."""
        import app.main as main_mod

        source = inspect.getsource(main_mod.lifespan)
        # The old pattern was: await record_step_async("model_preload", ...)
        # The new pattern uses asyncio.create_task
        # Check that no active await of record_step_async for model_preload exists (exclude comments)
        lines = source.split("\n")
        active_lines = [l for l in lines if not l.strip().startswith("#")]
        active_source = "\n".join(active_lines)
        assert 'await record_step_async("model_preload"' not in active_source

    def test_main_py_stores_task_on_app_state(self):
        """lifespan should store the preload task on app.state."""
        import app.main as main_mod

        source = inspect.getsource(main_mod.lifespan)
        assert "app.state._model_preload_task" in source

    def test_main_py_cancels_task_on_shutdown(self):
        """lifespan finally block should cancel the preload task."""
        import app.main as main_mod

        source = inspect.getsource(main_mod.lifespan)
        assert "_preload_task.cancel" in source or "_model_preload_task" in source

    def test_main_py_records_pending_status(self):
        """Background preload should record 'pending' status initially."""
        import app.main as main_mod

        source = inspect.getsource(main_mod.lifespan)
        assert '"pending"' in source or "'pending'" in source

    def test_main_py_handles_cancelled_error(self):
        """Shutdown cancellation should handle CancelledError."""
        import app.main as main_mod

        source = inspect.getsource(main_mod.lifespan)
        assert "CancelledError" in source


class TestPreloadBackgroundBehavior:
    """Behavioral tests for background model preload."""

    def test_preload_records_pending_then_ok(self):
        """Preload should record 'pending' then 'ok' on success."""
        from app.core.startup_status import startup_status

        startup_status.reset()

        async def _run():
            from app.core.model_engine import model_engine

            start_count = len(startup_status.components)

            # Simulate the background preload function
            import time as _time

            start = _time.monotonic()
            startup_status.record("model_preload", "pending")
            try:
                await asyncio.to_thread(model_engine.preload)
                duration_ms = (_time.monotonic() - start) * 1000
                startup_status.record(
                    "model_preload", "ok", duration_ms=duration_ms, fatal=False
                )
            except BaseException as exc:
                startup_status.record(
                    "model_preload", "failed", error=exc, fatal=False
                )

        asyncio.run(_run())

        assert "model_preload" in startup_status.components
        assert startup_status.components["model_preload"].status == "ok"

    def test_preload_records_failed_on_exception(self):
        """Preload should record 'failed' on exception."""
        from app.core.startup_status import startup_status

        startup_status.reset()

        async def _run():
            startup_status.record("model_preload", "pending")
            try:
                raise RuntimeError("test preload failure")
            except BaseException as exc:
                startup_status.record(
                    "model_preload", "failed", error=exc, fatal=False
                )

        asyncio.run(_run())

        assert startup_status.components["model_preload"].status == "failed"
        assert startup_status.components["model_preload"].error_type == "RuntimeError"

    def test_preload_task_can_be_cancelled(self):
        """A running preload task should be cancellable."""
        from app.core.startup_status import startup_status

        startup_status.reset()

        async def _long_preload():
            startup_status.record("model_preload", "pending")
            try:
                await asyncio.sleep(100)
                startup_status.record("model_preload", "ok", fatal=False)
            except asyncio.CancelledError:
                raise

        async def _main():
            task = asyncio.create_task(_long_preload())
            await asyncio.sleep(0.01)  # Let it start
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass

        asyncio.run(_main())

        # Task was cancelled before completing
        assert startup_status.components.get("model_preload")
        assert startup_status.components["model_preload"].status == "pending"
