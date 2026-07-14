"""ISS-02 覆盖率提升：app/core/startup_status.py 聚焦测试.

启动期结构化状态收集（/health 端点依赖）。纯逻辑，指标导入失败有容错，可全量覆盖。
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.core import startup_status as ss
from app.core.startup_status import ComponentStatus, StartupStatus, record_step_async, record_step_sync


@pytest.fixture(autouse=True)
def fake_metrics():
    # prometheus_client 在本环境未安装；record() 内部会 import app.core.metrics。
    # 用一个假模块替换，使其 inc() 可调，覆盖 metrics 标签分支。
    fake = MagicMock()
    fake.startup_component_failures_total = MagicMock()
    with patch("app.core.metrics", fake):
        yield fake


@pytest.fixture
def fresh():
    # record_step_sync/async 写入的是全局单例 startup_status，需把全局也替换为 fresh 实例
    s = StartupStatus()
    with patch.object(ss, "startup_status", s):
        yield s
    s.reset()


class TestComponentStatus:
    def test_to_dict(self):
        c = ComponentStatus(name="x", status="failed", error_type="ValueError", error_message="bad", duration_ms=12.5)
        d = c.to_dict()
        assert d["status"] == "failed"
        assert d["error_type"] == "ValueError"
        assert d["duration_ms"] == 12.5


class TestRecord:
    def test_record_ok(self, fresh):
        fresh.record("init_db", "ok", duration_ms=10.0)
        assert "init_db" in fresh.components
        assert fresh.components["init_db"].status == "ok"
        assert fresh.failed_components == []

    def test_record_failed_captures_error(self, fresh):
        fresh.record("model_preload", "failed", error=RuntimeError("nope"))
        assert fresh.failed_components == ["model_preload"]
        c = fresh.components["model_preload"]
        assert c.error_type == "RuntimeError"
        assert "nope" in c.error_message

    def test_record_skipped(self, fresh):
        fresh.record("sentry", "skipped")
        assert fresh.components["sentry"].status == "skipped"


class TestFatal:
    def test_set_fatal_from_exception(self, fresh):
        fresh.set_fatal(ValueError("fatal!"))
        assert fresh.has_fatal_error is True
        assert fresh.fatal_error_type == "ValueError"
        assert "fatal!" in fresh.fatal_error

    def test_set_fatal_from_string(self, fresh):
        fresh.set_fatal("plain msg")
        assert fresh.fatal_error_type == "FatalError"
        assert fresh.fatal_error == "plain msg"


class TestCompleted:
    def test_mark_completed(self, fresh):
        assert fresh.startup_completed is False
        fresh.mark_completed()
        assert fresh.startup_completed is True


class TestToDict:
    def test_to_dict_and_summary(self, fresh):
        fresh.record("init_db", "ok")
        fresh.record("model", "failed", error=KeyError("k"))
        fresh.set_fatal(RuntimeError("stop"))
        d = fresh.to_dict()
        assert d["startup_completed"] is False
        assert d["fatal_error_type"] == "RuntimeError"
        assert "model" in d["failed_components"]
        assert "init_db" in d["components"]
        # summary 仅暴露失败与致命信息
        s = fresh.to_summary_dict()
        assert s["startup_failed_components"] == ["model"]
        assert "stop" in s["startup_fatal_error"]


class TestRecordStepSync:
    def test_sync_ok(self, fresh):
        out = record_step_sync("seed", lambda: 42, fatal=True)
        assert out == 42
        assert fresh.components["seed"].status == "ok"

    def test_sync_fatal_failure_reraises(self, fresh):
        with pytest.raises(ValueError):
            record_step_sync("seed", lambda: (_ for _ in ()).throw(ValueError("x")), fatal=True)
        assert fresh.components["seed"].status == "failed"
        assert fresh.has_fatal_error is True

    def test_sync_nonfatal_failure_returns_none(self, fresh):
        out = record_step_sync("sentry", lambda: (_ for _ in ()).throw(RuntimeError("y")), fatal=False)
        assert out is None
        assert fresh.components["sentry"].status == "failed"
        assert fresh.has_fatal_error is False


class TestRecordStepAsync:
    async def test_async_ok(self, fresh):
        out = await record_step_async("model_preload", _coro(7), fatal=True)
        assert out == 7
        assert fresh.components["model_preload"].status == "ok"

    async def test_async_fatal_failure_reraises(self, fresh):
        with pytest.raises(ValueError):
            await record_step_async("db", _coro_fail(ValueError("z")), fatal=True)
        assert fresh.components["db"].status == "failed"

    async def test_async_nonfatal_failure_returns_none(self, fresh):
        out = await record_step_async("ws", _coro_fail(RuntimeError("w")), fatal=False)
        assert out is None
        assert fresh.components["ws"].status == "failed"


async def _coro(v):
    return v


async def _coro_fail(exc):
    raise exc


def test_global_singleton_exists():
    assert isinstance(ss.startup_status, StartupStatus)
