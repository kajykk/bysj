"""ISS-02 覆盖率提升：app/core/celery_breaker.py 聚焦测试.

重点覆盖 `_is_celery_failure` 故障分类（可靠性核心逻辑）：
基础设施异常触发熔断、业务异常不触发、异常链穿透、未知异常保守触发。
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core import celery_breaker as cb


class TestIsCeleryFailure:
    def test_none_forces_count(self):
        assert cb._is_celery_failure(None) is True

    def test_os_error_is_infra(self):
        assert cb._is_celery_failure(OSError("conn refused")) is True

    def test_timeout_error_is_infra(self):
        assert cb._is_celery_failure(TimeoutError()) is True

    def test_value_error_is_business(self):
        assert cb._is_celery_failure(ValueError("bad input")) is False

    def test_type_error_is_business(self):
        assert cb._is_celery_failure(TypeError()) is False

    def test_key_error_is_business(self):
        assert cb._is_celery_failure(KeyError("missing")) is False

    def test_exception_chain_infra_through_business(self):
        # ValueError 包装 OSError 根因 → 应识别为 broker 故障
        root = OSError("broker down")
        wrapped = ValueError("wrapper")
        wrapped.__cause__ = root
        assert cb._is_celery_failure(wrapped) is True

    def test_exception_context_infra(self):
        outer = ValueError("outer")
        outer.__context__ = ConnectionError("ctx conn")
        assert cb._is_celery_failure(outer) is True

    def test_unknown_exception_conservative(self):
        # 未知异常保守视为 broker 故障，避免漏判持续阻塞
        class WeirdError(Exception):
            pass

        assert cb._is_celery_failure(WeirdError()) is True


class TestCallWithCeleryBreaker:
    async def test_open_state_raises(self, monkeypatch):
        from app.core.celery_breaker import CircuitBreakerOpenError
        from app.core.config import settings

        monkeypatch.setattr(settings, "celery_circuit_breaker_enabled", True)
        fake = MagicMock()
        fake.before_request = AsyncMock(side_effect=CircuitBreakerOpenError("open"))
        monkeypatch.setattr(cb, "celery_breaker", fake)
        with pytest.raises(CircuitBreakerOpenError):
            await cb.call_with_celery_breaker(_coro("ok"))

    async def test_closed_success_calls_on_success(self, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "celery_circuit_breaker_enabled", True)
        fake = MagicMock()
        fake.before_request = AsyncMock()
        fake.on_success = AsyncMock()
        fake.on_failure = AsyncMock()
        fake.failure_count = 0
        fake.failure_threshold = 5
        monkeypatch.setattr(cb, "celery_breaker", fake)
        result = await cb.call_with_celery_breaker(_coro("ok"))
        assert result == "ok"
        fake.on_success.assert_awaited_once()

    async def test_closed_failure_calls_on_failure_and_reraises(self, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "celery_circuit_breaker_enabled", True)
        fake = MagicMock()
        fake.before_request = AsyncMock()
        fake.on_success = AsyncMock()
        fake.on_failure = AsyncMock()
        fake.failure_count = 0
        fake.failure_threshold = 5
        monkeypatch.setattr(cb, "celery_breaker", fake)
        with pytest.raises(RuntimeError):
            await cb.call_with_celery_breaker(_coro_fail(RuntimeError("boom")))
        fake.on_failure.assert_awaited_once()

    async def test_disabled_bypasses_breaker(self, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "celery_circuit_breaker_enabled", False)
        called = {}

        async def wrapped():
            called["x"] = True
            return "ran"

        result = await cb.call_with_celery_breaker(wrapped())
        assert result == "ran"
        assert called.get("x") is True


async def _coro(v):
    return v


async def _coro_fail(exc):
    raise exc
