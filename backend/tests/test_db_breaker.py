"""STAB-P0-001 测试：数据库熔断器 (Circuit Breaker)

验证要点：
1. ``CircuitBreaker`` 状态机转换 (CLOSED→OPEN→HALF_OPEN→CLOSED)
2. ``before_request()`` 在 OPEN 状态抛 503
3. ``on_success()`` 重置失败计数
4. ``on_failure()`` 增加失败计数, 达阈值则 OPEN
5. 业务异常 (IntegrityError) 不触发熔断器
6. 连接级异常 (OperationalError/OSError) 触发熔断器
7. ``get_db()`` 集成：熔断器 OPEN 时返回 503
8. ``db_circuit_breaker_enabled=False`` 时禁用熔断器
"""

from __future__ import annotations

import asyncio

import pytest
from sqlalchemy.exc import IntegrityError, OperationalError

from app.core.db_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
    _is_connection_failure,
)


@pytest.fixture
def breaker() -> CircuitBreaker:
    """每个测试创建独立的熔断器实例, 避免全局状态污染。"""
    return CircuitBreaker(
        failure_threshold=3,
        recovery_timeout=1,  # 1 秒, 便于测试
        half_open_max_calls=1,
        name="test_db",
    )


class TestCircuitBreakerStates:
    """测试熔断器状态机转换。"""

    async def test_initial_state_is_closed(self, breaker: CircuitBreaker):
        """初始状态应为 CLOSED。"""
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0

    async def test_closed_allows_request(self, breaker: CircuitBreaker):
        """CLOSED 状态应放行请求 (不抛异常)。"""
        await breaker.before_request()  # 不抛异常

    async def test_failures_below_threshold_stay_closed(self, breaker: CircuitBreaker):
        """失败次数未达阈值时应保持 CLOSED。"""
        await breaker.on_failure(OSError("connection refused"))
        await breaker.on_failure(OSError("connection refused"))
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 2

    async def test_failures_reach_threshold_opens(self, breaker: CircuitBreaker):
        """连续失败达阈值应转为 OPEN。"""
        for _ in range(3):
            await breaker.on_failure(OSError("connection refused"))
        assert breaker.state == CircuitState.OPEN
        assert breaker.failure_count == 3

    async def test_open_state_rejects_request(self, breaker: CircuitBreaker):
        """OPEN 状态应拒绝请求 (抛 503)。"""
        for _ in range(3):
            await breaker.on_failure(OSError("connection refused"))

        with pytest.raises(CircuitBreakerOpenError) as exc_info:
            await breaker.before_request()

        assert exc_info.value.status_code == 503
        assert "Retry-After" in exc_info.value.headers

    async def test_open_transitions_to_half_open_after_timeout(
        self, breaker: CircuitBreaker
    ):
        """OPEN 状态经过 recovery_timeout 后应转为 HALF_OPEN。"""
        for _ in range(3):
            await breaker.on_failure(OSError("connection refused"))
        assert breaker.state == CircuitState.OPEN

        # 等待 recovery_timeout (1 秒)
        await asyncio.sleep(1.1)

        # before_request 应触发 OPEN→HALF_OPEN 转换, 不抛异常
        await breaker.before_request()
        assert breaker.state == CircuitState.HALF_OPEN

    async def test_half_open_success_transitions_to_closed(
        self, breaker: CircuitBreaker
    ):
        """HALF_OPEN 状态测试请求成功应转为 CLOSED。"""
        for _ in range(3):
            await breaker.on_failure(OSError("connection refused"))

        await asyncio.sleep(1.1)
        await breaker.before_request()  # OPEN → HALF_OPEN
        assert breaker.state == CircuitState.HALF_OPEN

        await breaker.on_success()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0

    async def test_half_open_failure_transitions_back_to_open(
        self, breaker: CircuitBreaker
    ):
        """HALF_OPEN 状态测试请求失败应重新转为 OPEN。"""
        for _ in range(3):
            await breaker.on_failure(OSError("connection refused"))

        await asyncio.sleep(1.1)
        await breaker.before_request()  # OPEN → HALF_OPEN
        assert breaker.state == CircuitState.HALF_OPEN

        await breaker.on_failure(OSError("still down"))
        assert breaker.state == CircuitState.OPEN

    async def test_half_open_rejects_excess_calls(self, breaker: CircuitBreaker):
        """HALF_OPEN 状态超出 max_calls 的请求应被拒绝。"""
        for _ in range(3):
            await breaker.on_failure(OSError("connection refused"))

        await asyncio.sleep(1.1)
        await breaker.before_request()  # HALF_OPEN, half_open_calls=1

        # 第二个请求应被拒绝 (max_calls=1)
        with pytest.raises(CircuitBreakerOpenError):
            await breaker.before_request()

    async def test_success_resets_failure_count_in_closed(
        self, breaker: CircuitBreaker
    ):
        """CLOSED 状态下成功应重置失败计数。"""
        await breaker.on_failure(OSError("connection refused"))
        await breaker.on_failure(OSError("connection refused"))
        assert breaker.failure_count == 2

        await breaker.on_success()
        assert breaker.failure_count == 0
        assert breaker.state == CircuitState.CLOSED


class TestResetMethod:
    """测试 reset() 方法。"""

    async def test_reset_restores_closed_state(self, breaker: CircuitBreaker):
        """reset() 应将熔断器恢复到 CLOSED。"""
        for _ in range(3):
            await breaker.on_failure(OSError("connection refused"))
        assert breaker.state == CircuitState.OPEN

        await breaker.reset()
        assert breaker.state == CircuitState.CLOSED
        assert breaker.failure_count == 0

    async def test_reset_allows_requests_again(self, breaker: CircuitBreaker):
        """reset() 后应能正常放行请求。"""
        for _ in range(3):
            await breaker.on_failure(OSError("connection refused"))

        await breaker.reset()
        await breaker.before_request()  # 不抛异常


class TestExceptionClassification:
    """测试 _is_connection_failure 异常分类。"""

    def test_operational_error_is_connection_failure(self):
        """OperationalError 应识别为连接级失败。"""
        exc = OperationalError("SELECT 1", {}, Exception("connection lost"))
        assert _is_connection_failure(exc) is True

    def test_os_error_is_connection_failure(self):
        """OSError 应识别为连接级失败。"""
        assert _is_connection_failure(OSError("refused")) is True

    def test_connection_refused_error_is_connection_failure(self):
        """ConnectionRefusedError 应识别为连接级失败。"""
        assert _is_connection_failure(ConnectionRefusedError()) is True

    def test_timeout_error_is_connection_failure(self):
        """TimeoutError 应识别为连接级失败。"""
        assert _is_connection_failure(TimeoutError()) is True

    def test_integrity_error_is_not_connection_failure(self):
        """IntegrityError 不应识别为连接级失败 (业务异常)。"""
        exc = IntegrityError("INSERT", {}, Exception("unique violation"))
        assert _is_connection_failure(exc) is False

    def test_value_error_is_not_connection_failure(self):
        """ValueError 不应识别为连接级失败。"""
        assert _is_connection_failure(ValueError("bad input")) is False

    def test_exception_chain_detected(self):
        """异常链中的连接级失败应被检测到。"""
        try:
            try:
                raise OSError("connection lost")
            except OSError:
                raise ValueError("wrapped error")
        except ValueError as e:
            assert _is_connection_failure(e) is True

    async def test_business_exception_does_not_trigger_breaker(
        self, breaker: CircuitBreaker
    ):
        """IntegrityError 不应触发熔断器。"""
        # 模拟 IntegrityError
        exc = IntegrityError("INSERT", {}, Exception("unique violation"))
        await breaker.on_failure(exc)
        assert breaker.failure_count == 0
        assert breaker.state == CircuitState.CLOSED

    async def test_connection_exception_triggers_breaker(self, breaker: CircuitBreaker):
        """OperationalError 应触发熔断器。"""
        exc = OperationalError("SELECT", {}, Exception("connection lost"))
        await breaker.on_failure(exc)
        assert breaker.failure_count == 1

    async def test_none_exception_triggers_breaker(self, breaker: CircuitBreaker):
        """exc=None 时应触发熔断器 (无条件计数)。"""
        await breaker.on_failure(None)
        assert breaker.failure_count == 1


class TestGetDbIntegration:
    """测试 get_db() 与熔断器的集成。"""

    async def test_get_db_returns_503_when_breaker_open(self, monkeypatch):
        """熔断器 OPEN 时 get_db 应抛 503。"""
        from app.core import database
        from app.core.db_breaker import db_breaker as global_breaker

        # 启用熔断器
        monkeypatch.setattr(database.settings, "db_circuit_breaker_enabled", True)

        # 手动将全局熔断器设为 OPEN
        await global_breaker.reset()
        for _ in range(global_breaker.failure_threshold):
            await global_breaker.on_failure(OSError("connection refused"))
        assert global_breaker.state == CircuitState.OPEN

        # get_db 应抛 CircuitBreakerOpenError (503)
        with pytest.raises(CircuitBreakerOpenError) as exc_info:
            async for _ in database.get_db():
                pass
        assert exc_info.value.status_code == 503

        # 清理
        await global_breaker.reset()

    async def test_get_db_disabled_breaker_does_not_intercept(self, monkeypatch):
        """db_circuit_breaker_enabled=False 时熔断器不生效。"""
        from app.core import database
        from app.core.db_breaker import db_breaker as global_breaker

        # 禁用熔断器
        monkeypatch.setattr(database.settings, "db_circuit_breaker_enabled", False)

        # mock AsyncSessionLocal 避免真实 DB 连接
        class _MockSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def close(self):
                pass

        monkeypatch.setattr(database, "AsyncSessionLocal", lambda: _MockSession())

        # 即使熔断器 OPEN, get_db 也不应拦截
        await global_breaker.reset()
        for _ in range(global_breaker.failure_threshold):
            await global_breaker.on_failure(OSError("connection refused"))
        assert global_breaker.state == CircuitState.OPEN

        # get_db 应正常工作 (不抛 503)
        try:
            async for _ in database.get_db():
                pass
        except CircuitBreakerOpenError:
            pytest.fail("熔断器已禁用, 不应抛 503")

        # 清理
        await global_breaker.reset()
        monkeypatch.setattr(database.settings, "db_circuit_breaker_enabled", True)

    async def test_get_db_success_calls_on_success(self, monkeypatch):
        """get_db 成功完成应调用 on_success。"""
        from app.core import database
        from app.core.db_breaker import db_breaker as global_breaker

        monkeypatch.setattr(database.settings, "db_circuit_breaker_enabled", True)
        await global_breaker.reset()

        # 先制造一些失败
        await global_breaker.on_failure(OSError("temp failure"))
        assert global_breaker.failure_count == 1

        # mock AsyncSessionLocal 避免真实 DB 连接
        class _MockSession:
            async def __aenter__(self):
                return self

            async def __aexit__(self, *args):
                return False

            async def close(self):
                pass

        monkeypatch.setattr(database, "AsyncSessionLocal", lambda: _MockSession())

        # 正常耗尽 generator (不 break), 触发 on_success
        async for _ in database.get_db():
            pass

        # on_success 应重置失败计数
        assert global_breaker.failure_count == 0
        await global_breaker.reset()

    async def test_get_db_integrity_error_does_not_trigger_breaker(self, monkeypatch):
        """IntegrityError 不应增加熔断器失败计数。"""
        from sqlalchemy.exc import IntegrityError as SAIntegrityError

        from app.core import database
        from app.core.db_breaker import db_breaker as global_breaker

        monkeypatch.setattr(database.settings, "db_circuit_breaker_enabled", True)
        await global_breaker.reset()

        # IntegrityError 不应增加失败计数
        exc = SAIntegrityError("INSERT", {}, Exception("unique violation"))
        await global_breaker.on_failure(exc)
        assert global_breaker.failure_count == 0
        assert global_breaker.state == CircuitState.CLOSED
        await global_breaker.reset()


class TestStateSnapshot:
    """测试 get_state_snapshot()。"""

    def test_snapshot_contains_all_fields(self, breaker: CircuitBreaker):
        """状态快照应包含所有字段。"""
        snapshot = breaker.get_state_snapshot()
        assert "name" in snapshot
        assert "state" in snapshot
        assert "failure_count" in snapshot
        assert "failure_threshold" in snapshot
        assert "recovery_timeout" in snapshot
        assert "last_failure_time" in snapshot

    def test_snapshot_reflects_current_state(self, breaker: CircuitBreaker):
        """快照应反映当前状态。"""
        snapshot = breaker.get_state_snapshot()
        assert snapshot["state"] == "closed"
        assert snapshot["failure_count"] == 0
        assert snapshot["failure_threshold"] == 3
        assert snapshot["recovery_timeout"] == 1


class TestInitDbBreaker:
    """测试 init_db_breaker() 函数。"""

    def test_init_creates_breaker_with_settings(self, monkeypatch):
        """init_db_breaker 应使用 settings 配置创建熔断器。"""
        from app.core import db_breaker as db_breaker_mod
        from app.core.config import settings

        monkeypatch.setattr(settings, "db_failure_threshold", 10)
        monkeypatch.setattr(settings, "db_recovery_timeout", 60)
        monkeypatch.setattr(settings, "db_half_open_max_calls", 2)

        db_breaker_mod.init_db_breaker()

        assert db_breaker_mod.db_breaker.failure_threshold == 10
        assert db_breaker_mod.db_breaker.recovery_timeout == 60
        assert db_breaker_mod.db_breaker.half_open_max_calls == 2
        assert db_breaker_mod.db_breaker.name == "db"

    async def test_init_resets_state(self):
        """init_db_breaker 应创建全新的 CLOSED 状态熔断器。"""
        from app.core import db_breaker as db_breaker_mod

        # 先制造一些失败
        await db_breaker_mod.db_breaker.on_failure(OSError("test"))

        # init 后应重置
        db_breaker_mod.init_db_breaker()
        assert db_breaker_mod.db_breaker.state == CircuitState.CLOSED
        assert db_breaker_mod.db_breaker.failure_count == 0
