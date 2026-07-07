"""STAB-P1-005 测试：Celery broker 熔断器

验证要点：
1. ``_is_celery_failure`` 失败分类器正确区分业务异常与 broker 基础设施异常
2. ``call_with_celery_breaker`` 正确包装协程: 成功放行, 失败计数, OPEN 时拒绝
3. ``celery_circuit_breaker_enabled=False`` 时禁用熔断器 (直接放行)
4. ``check_celery_worker`` 经过熔断器包装, OPEN 时返回 False
5. ``celery_worker_heartbeat`` 指标随检查结果更新 (成功=1, 失败=0)
6. ``init_celery_breaker`` 根据 settings 重新初始化
7. ``metrics.py`` 暴露 celery_circuit_* 指标
8. ``main.py`` 启动时调用 init_celery_breaker
"""

from __future__ import annotations

import asyncio
import inspect
from unittest.mock import MagicMock, patch

import pytest

from app.core.celery_breaker import (
    _is_celery_failure,
    call_with_celery_breaker,
    init_celery_breaker,
)
from app.core.db_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
)

# ── 动态收集可用的 broker 异常类型 (兼容依赖未安装场景) ──


def _get_available_broker_exceptions() -> dict[str, type[BaseException]]:
    """收集当前环境中可用的 broker 异常类型."""
    exceptions: dict[str, type[BaseException]] = {}
    try:
        from kombu.exceptions import OperationalError

        exceptions["kombu"] = OperationalError
    except ImportError:
        pass
    try:
        from celery.exceptions import TimeoutError as CeleryTimeoutError

        exceptions["celery"] = CeleryTimeoutError
    except ImportError:
        pass
    try:
        from redis.exceptions import ConnectionError as RedisConnectionError

        exceptions["redis_conn"] = RedisConnectionError
    except ImportError:
        pass
    try:
        from redis.exceptions import BusyLoadingError

        exceptions["redis_busy"] = BusyLoadingError
    except ImportError:
        pass
    return exceptions


_BROKER_EXCEPTIONS = _get_available_broker_exceptions()


# ── 辅助 fixture ──


@pytest.fixture
def fresh_celery_breaker():
    """每个测试前重置全局 celery_breaker 到 CLOSED 状态."""
    test_breaker = CircuitBreaker(
        failure_threshold=3,
        recovery_timeout=1,  # 1 秒, 便于测试
        half_open_max_calls=1,
        name="test_celery",
        failure_classifier=_is_celery_failure,
    )
    with patch("app.core.celery_breaker.celery_breaker", test_breaker):
        yield test_breaker


@pytest.fixture
def ok_coro():
    """返回一个立即返回 {'worker1': {}} 的协程 (模拟 inspect.stats 成功)."""

    async def _ok():
        return {"worker1": {"stats": "data"}}

    return _ok()


# ─────────────────────────────────────────────────────────────────────────────
# 1. _is_celery_failure 分类器测试
# ─────────────────────────────────────────────────────────────────────────────


class TestIsCeleryFailure:
    """测试 _is_celery_failure 异常分类器."""

    def test_none_returns_true(self):
        """显式传入 None 应视为失败 (强制计数)."""
        assert _is_celery_failure(None) is True

    @pytest.mark.parametrize(
        "exc_cls",
        [
            OSError,
            ConnectionError,
            ConnectionRefusedError,
            ConnectionResetError,
            TimeoutError,
            FileNotFoundError,
        ],
    )
    def test_oslevel_exceptions_trigger_breaker(self, exc_cls):
        """OS 层异常 (OSError/ConnectionError/TimeoutError) 应触发熔断器."""
        try:
            raise exc_cls("test")
        except BaseException as e:
            assert _is_celery_failure(e) is True

    @pytest.mark.skipif("kombu" not in _BROKER_EXCEPTIONS, reason="kombu not installed")
    def test_kombu_operational_error_triggers(self):
        """kombu.exceptions.OperationalError 应触发熔断器."""
        exc = _BROKER_EXCEPTIONS["kombu"]("broker down")
        assert _is_celery_failure(exc) is True

    @pytest.mark.skipif(
        "celery" not in _BROKER_EXCEPTIONS, reason="celery not installed"
    )
    def test_celery_timeout_error_triggers(self):
        """celery.exceptions.TimeoutError 应触发熔断器."""
        exc = _BROKER_EXCEPTIONS["celery"]("task timeout")
        assert _is_celery_failure(exc) is True

    @pytest.mark.skipif(
        "redis_conn" not in _BROKER_EXCEPTIONS, reason="redis not installed"
    )
    def test_redis_connection_error_triggers(self):
        """redis.exceptions.ConnectionError 应触发熔断器."""
        exc = _BROKER_EXCEPTIONS["redis_conn"]("redis refused")
        assert _is_celery_failure(exc) is True

    @pytest.mark.skipif(
        "redis_busy" not in _BROKER_EXCEPTIONS, reason="redis not installed"
    )
    def test_redis_busy_loading_error_triggers(self):
        """redis.exceptions.BusyLoadingError 应触发熔断器."""
        exc = _BROKER_EXCEPTIONS["redis_busy"]("redis loading dataset")
        assert _is_celery_failure(exc) is True

    @pytest.mark.parametrize(
        "exc_cls",
        [
            ValueError,
            TypeError,
            KeyError,
            AttributeError,
            LookupError,
            ArithmeticError,
        ],
    )
    def test_business_exceptions_do_not_trigger(self, exc_cls):
        """业务异常 (输入校验类) 不应触发熔断器."""
        try:
            raise exc_cls("test")
        except BaseException as e:
            assert _is_celery_failure(e) is False

    def test_http_exception_does_not_trigger(self):
        """FastAPI HTTPException 是业务异常, 不应触发熔断器."""
        from fastapi import HTTPException

        exc = HTTPException(status_code=422, detail="validation error")
        assert _is_celery_failure(exc) is False

    def test_circuit_breaker_open_error_does_not_trigger(self):
        """CircuitBreakerOpenError (HTTPException 子类) 不应触发熔断器 (避免自反馈)."""
        exc = CircuitBreakerOpenError("celery circuit open")
        assert _is_celery_failure(exc) is False

    def test_unknown_exception_triggers_breaker(self):
        """未知异常应触发熔断器 (保守策略, 避免漏判)."""

        class CustomError(Exception):
            pass

        assert _is_celery_failure(CustomError("unknown")) is True

    def test_exception_chain_with_oserror_cause(self):
        """异常链 __cause__ 中包含 OSError 时应触发.

        场景: 调用方将 kombu.OperationalError 包装为 ValueError,
        若不检查异常链会漏判, 导致 broker 宕机时熔断器不动作.
        """
        try:
            try:
                raise OSError("connection refused")
            except OSError as e:
                raise ValueError("wrapper") from e
        except BaseException as wrapper:
            assert _is_celery_failure(wrapper) is True

    def test_exception_chain_with_connection_error_context(self):
        """异常链 __context__ 中包含 ConnectionError 时也应触发."""
        try:
            try:
                raise ConnectionRefusedError("broker refused")
            except ConnectionRefusedError:
                raise ValueError("wrapper")
        except BaseException as wrapper:
            assert _is_celery_failure(wrapper) is True

    @pytest.mark.skipif("kombu" not in _BROKER_EXCEPTIONS, reason="kombu not installed")
    def test_exception_chain_with_kombu_cause(self):
        """异常链 __cause__ 中包含 kombu.OperationalError 时应触发."""
        kombu_exc_cls = _BROKER_EXCEPTIONS["kombu"]
        try:
            try:
                raise kombu_exc_cls("broker down")
            except kombu_exc_cls as e:
                raise RuntimeError("wrapper") from e
        except BaseException as wrapper:
            assert _is_celery_failure(wrapper) is True

    def test_exception_chain_with_only_business_cause(self):
        """异常链仅含业务异常时不触发."""
        try:
            try:
                raise ValueError("bad input")
            except ValueError as e:
                raise TypeError("wrapper") from e
        except BaseException as wrapper:
            assert _is_celery_failure(wrapper) is False


# ─────────────────────────────────────────────────────────────────────────────
# 2. call_with_celery_breaker 测试
# ─────────────────────────────────────────────────────────────────────────────


class TestCallWithCeleryBreaker:
    """测试 call_with_celery_breaker 异步包装."""

    @pytest.mark.asyncio
    async def test_success_returns_result(self, fresh_celery_breaker, ok_coro):
        """成功执行应返回结果, 熔断器保持 CLOSED."""
        result = await call_with_celery_breaker(ok_coro)
        assert result == {"worker1": {"stats": "data"}}
        assert fresh_celery_breaker.state == CircuitState.CLOSED
        assert fresh_celery_breaker.failure_count == 0

    @pytest.mark.asyncio
    async def test_oserror_increments_failure(self, fresh_celery_breaker):
        """OSError 应增加失败计数."""

        async def _raise_oserror():
            raise OSError("broker unreachable")

        with pytest.raises(OSError):
            await call_with_celery_breaker(_raise_oserror())
        assert fresh_celery_breaker.failure_count == 1
        assert fresh_celery_breaker.state == CircuitState.CLOSED  # 未达阈值

    @pytest.mark.asyncio
    async def test_connection_error_increments_failure(self, fresh_celery_breaker):
        """ConnectionError 应增加失败计数."""

        async def _raise_conn():
            raise ConnectionRefusedError("connection refused")

        with pytest.raises(ConnectionRefusedError):
            await call_with_celery_breaker(_raise_conn())
        assert fresh_celery_breaker.failure_count == 1

    @pytest.mark.asyncio
    async def test_timeout_error_increments_failure(self, fresh_celery_breaker):
        """TimeoutError 应增加失败计数."""

        async def _raise_timeout():
            raise TimeoutError("inspect timeout")

        with pytest.raises(TimeoutError):
            await call_with_celery_breaker(_raise_timeout())
        assert fresh_celery_breaker.failure_count == 1

    @pytest.mark.skipif("kombu" not in _BROKER_EXCEPTIONS, reason="kombu not installed")
    @pytest.mark.asyncio
    async def test_kombu_error_increments_failure(self, fresh_celery_breaker):
        """kombu.OperationalError 应增加失败计数."""
        kombu_exc_cls = _BROKER_EXCEPTIONS["kombu"]

        async def _raise_kombu():
            raise kombu_exc_cls("broker down")

        with pytest.raises(kombu_exc_cls):
            await call_with_celery_breaker(_raise_kombu())
        assert fresh_celery_breaker.failure_count == 1

    @pytest.mark.asyncio
    async def test_business_exception_does_not_count(self, fresh_celery_breaker):
        """业务异常 (ValueError) 应透传但不增加失败计数."""

        async def _raise_value():
            raise ValueError("bad input")

        with pytest.raises(ValueError):
            await call_with_celery_breaker(_raise_value())
        assert fresh_celery_breaker.failure_count == 0
        assert fresh_celery_breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_repeated_failures_open_breaker(self, fresh_celery_breaker):
        """连续失败达阈值应打开熔断器."""
        for _ in range(3):

            async def _raise_oserror():
                raise OSError("broker down")

            with pytest.raises(OSError):
                await call_with_celery_breaker(_raise_oserror())
        assert fresh_celery_breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_open_breaker_rejects_without_executing(self, fresh_celery_breaker):
        """熔断器 OPEN 时应抛 CircuitBreakerOpenError 且不执行协程."""
        # 打开熔断器
        for _ in range(3):
            await fresh_celery_breaker.on_failure(OSError("fail"))

        executed = False

        async def _would_execute():
            nonlocal executed
            executed = True
            return {"worker1": {}}

        with pytest.raises(CircuitBreakerOpenError) as exc_info:
            await call_with_celery_breaker(_would_execute())

        assert exc_info.value.status_code == 503
        assert executed is False  # 协程未执行

    @pytest.mark.asyncio
    async def test_disabled_breaker_skips_check(self, ok_coro):
        """celery_circuit_breaker_enabled=False 时应跳过熔断器."""
        with patch("app.core.config.settings.celery_circuit_breaker_enabled", False):
            result = await call_with_celery_breaker(ok_coro)
            assert result == {"worker1": {"stats": "data"}}

    @pytest.mark.asyncio
    async def test_disabled_breaker_still_propagates_exception(self):
        """禁用熔断器时异常仍应透传."""

        async def _raise():
            raise OSError("broker down")

        with patch("app.core.config.settings.celery_circuit_breaker_enabled", False):
            with pytest.raises(OSError):
                await call_with_celery_breaker(_raise())

    @pytest.mark.asyncio
    async def test_recovery_after_failure(self, fresh_celery_breaker):
        """OPEN → HALF_OPEN → CLOSED 恢复流程."""
        # 打开熔断器
        for _ in range(3):
            await fresh_celery_breaker.on_failure(OSError("fail"))
        assert fresh_celery_breaker.state == CircuitState.OPEN

        # 等待 recovery_timeout (1 秒)
        await asyncio.sleep(1.1)

        # 下一个成功请求应触发恢复
        async def _ok():
            return {"worker1": {"stats": "recovered"}}

        result = await call_with_celery_breaker(_ok())
        assert result == {"worker1": {"stats": "recovered"}}
        assert fresh_celery_breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_half_open_failure_reopens_breaker(self, fresh_celery_breaker):
        """HALF_OPEN 状态下失败应重新打开熔断器."""
        # 打开熔断器
        for _ in range(3):
            await fresh_celery_breaker.on_failure(OSError("fail"))
        assert fresh_celery_breaker.state == CircuitState.OPEN

        # 等待 recovery_timeout
        await asyncio.sleep(1.1)

        # HALF_OPEN 状态下失败 → 重新 OPEN
        async def _fail():
            raise OSError("still failing")

        with pytest.raises(OSError):
            await call_with_celery_breaker(_fail())
        assert fresh_celery_breaker.state == CircuitState.OPEN


# ─────────────────────────────────────────────────────────────────────────────
# 3. check_celery_worker 集成测试
# ─────────────────────────────────────────────────────────────────────────────


class TestCheckCeleryWorkerBreakerIntegration:
    """验证 check_celery_worker 经过熔断器包装."""

    def test_check_celery_worker_uses_breaker(self):
        """check_celery_worker 源码应包含 call_with_celery_breaker."""
        from app.core.health import check_celery_worker

        src = inspect.getsource(check_celery_worker)
        assert "call_with_celery_breaker" in src

    def test_check_celery_worker_handles_circuit_open(self):
        """check_celery_worker 源码应处理 CircuitBreakerOpenError."""
        from app.core.health import check_celery_worker

        src = inspect.getsource(check_celery_worker)
        assert "CircuitBreakerOpenError" in src

    def test_check_celery_worker_sets_heartbeat(self):
        """check_celery_worker 源码应设置 celery_worker_heartbeat 指标."""
        from app.core.health import check_celery_worker

        src = inspect.getsource(check_celery_worker)
        assert "celery_worker_heartbeat" in src

    @pytest.mark.asyncio
    async def test_circuit_open_returns_false(self, fresh_celery_breaker):
        """熔断器 OPEN 时 check_celery_worker 应返回 False."""
        from app.core.health import check_celery_worker

        # 打开熔断器
        for _ in range(3):
            await fresh_celery_breaker.on_failure(OSError("broker down"))
        assert fresh_celery_breaker.state == CircuitState.OPEN

        result = await check_celery_worker("redis://localhost:6379/0")
        assert result is False

    @pytest.mark.asyncio
    async def test_success_sets_heartbeat_to_one(self, fresh_celery_breaker):
        """成功检查应将 celery_worker_heartbeat 设为 1."""
        from app.core.health import check_celery_worker
        from app.core.metrics import celery_worker_heartbeat

        # 清零 heartbeat
        celery_worker_heartbeat.set(0.0)

        with patch("app.core.health.celery_app") as mock_celery:
            mock_inspect = MagicMock()
            mock_inspect.stats.return_value = {"worker1": {"stats": "data"}}
            mock_celery.control.inspect.return_value = mock_inspect

            result = await check_celery_worker("redis://localhost:6379/0")

        assert result is True
        # 验证 heartbeat 指标被设为 1
        entries = celery_worker_heartbeat.collect()
        assert any(value == 1.0 for _, value in entries)

    @pytest.mark.asyncio
    async def test_failure_sets_heartbeat_to_zero(self, fresh_celery_breaker):
        """失败检查应将 celery_worker_heartbeat 设为 0."""
        from app.core.health import check_celery_worker
        from app.core.metrics import celery_worker_heartbeat

        # 先设为 1
        celery_worker_heartbeat.set(1.0)

        with patch("app.core.health.celery_app") as mock_celery:
            mock_inspect = MagicMock()
            mock_inspect.stats.side_effect = OSError("broker unreachable")
            mock_celery.control.inspect.return_value = mock_inspect

            result = await check_celery_worker("redis://localhost:6379/0")

        assert result is False
        # 验证 heartbeat 指标被设为 0
        entries = celery_worker_heartbeat.collect()
        assert any(value == 0.0 for _, value in entries)

    @pytest.mark.asyncio
    async def test_circuit_open_sets_heartbeat_to_zero(self, fresh_celery_breaker):
        """熔断器 OPEN 时 heartbeat 应设为 0."""
        from app.core.health import check_celery_worker
        from app.core.metrics import celery_worker_heartbeat

        # 打开熔断器
        for _ in range(3):
            await fresh_celery_breaker.on_failure(OSError("broker down"))
        assert fresh_celery_breaker.state == CircuitState.OPEN

        # 先设为 1
        celery_worker_heartbeat.set(1.0)

        result = await check_celery_worker("redis://localhost:6379/0")
        assert result is False

        # 验证 heartbeat 指标被设为 0
        entries = celery_worker_heartbeat.collect()
        assert any(value == 0.0 for _, value in entries)


# ─────────────────────────────────────────────────────────────────────────────
# 4. init_celery_breaker 测试
# ─────────────────────────────────────────────────────────────────────────────


class TestInitCeleryBreaker:
    """测试 init_celery_breaker 初始化函数."""

    def test_init_uses_settings_values(self):
        """init_celery_breaker 应使用 settings 中的配置值."""
        with patch("app.core.config.settings.celery_failure_threshold", 10), patch(
            "app.core.config.settings.celery_recovery_timeout", 120
        ), patch("app.core.config.settings.celery_half_open_max_calls", 2):
            init_celery_breaker()
            from app.core.celery_breaker import celery_breaker as new_breaker

            assert new_breaker.failure_threshold == 10
            assert new_breaker.recovery_timeout == 120
            assert new_breaker.half_open_max_calls == 2
            assert new_breaker.name == "celery"
            # 恢复默认值
            init_celery_breaker()

    def test_init_breaker_uses_celery_classifier(self):
        """init 后的 celery_breaker 应使用 _is_celery_failure 分类器."""
        init_celery_breaker()
        from app.core.celery_breaker import celery_breaker as new_breaker

        assert new_breaker._failure_classifier is _is_celery_failure

    def test_init_breaker_default_settings(self):
        """默认配置: threshold=5, recovery=30s, half_open=1."""
        init_celery_breaker()
        from app.core.celery_breaker import celery_breaker as new_breaker
        from app.core.config import settings

        assert new_breaker.failure_threshold == settings.celery_failure_threshold
        assert new_breaker.recovery_timeout == settings.celery_recovery_timeout
        assert new_breaker.half_open_max_calls == settings.celery_half_open_max_calls


# ─────────────────────────────────────────────────────────────────────────────
# 5. metrics.py 与 main.py 集成测试 (静态检查)
# ─────────────────────────────────────────────────────────────────────────────


class TestMetricsAndMainIntegration:
    """验证 metrics 指标暴露与 main 启动初始化."""

    def test_metrics_exposes_celery_circuit_failure_count(self):
        """metrics.py 应定义 celery_circuit_failure_count."""
        from app.core import metrics

        assert hasattr(metrics, "celery_circuit_failure_count")

    def test_metrics_exposes_celery_circuit_state(self):
        """metrics.py 应定义 celery_circuit_state."""
        from app.core import metrics

        assert hasattr(metrics, "celery_circuit_state")

    def test_metrics_endpoint_collects_celery_state(self):
        """api/v1/metrics.py 应采集 celery_breaker 状态."""
        from app.api.v1 import metrics as metrics_api

        src = inspect.getsource(metrics_api.get_metrics)
        assert "celery_breaker" in src
        assert "celery_circuit_failure_count" in src
        assert "celery_circuit_state" in src

    def test_main_lifespan_calls_init_celery_breaker(self):
        """main.py lifespan 应调用 init_celery_breaker."""
        from app import main

        src = inspect.getsource(main.lifespan)
        assert "init_celery_breaker" in src

    def test_config_has_celery_circuit_breaker_enabled(self):
        """config.py 应包含 celery_circuit_breaker_enabled 字段."""
        from app.core.config import settings

        assert hasattr(settings, "celery_circuit_breaker_enabled")
        assert isinstance(settings.celery_circuit_breaker_enabled, bool)

    def test_config_has_celery_failure_threshold(self):
        """config.py 应包含 celery_failure_threshold 字段."""
        from app.core.config import settings

        assert hasattr(settings, "celery_failure_threshold")
        assert isinstance(settings.celery_failure_threshold, int)

    def test_config_has_celery_recovery_timeout(self):
        """config.py 应包含 celery_recovery_timeout 字段."""
        from app.core.config import settings

        assert hasattr(settings, "celery_recovery_timeout")
        assert isinstance(settings.celery_recovery_timeout, int)

    def test_config_has_celery_half_open_max_calls(self):
        """config.py 应包含 celery_half_open_max_calls 字段."""
        from app.core.config import settings

        assert hasattr(settings, "celery_half_open_max_calls")
        assert isinstance(settings.celery_half_open_max_calls, int)

    def test_metrics_exposes_celery_worker_heartbeat(self):
        """metrics.py 应定义 celery_worker_heartbeat 指标 (STAB-P1-018 定义, STAB-P1-005 激活)."""
        from app.core import metrics

        assert hasattr(metrics, "celery_worker_heartbeat")


# ─────────────────────────────────────────────────────────────────────────────
# 6. 端到端熔断器场景测试
# ─────────────────────────────────────────────────────────────────────────────


class TestCeleryBreakerEndToEnd:
    """端到端验证 Celery broker 熔断器在连续失败后打开."""

    @pytest.mark.asyncio
    async def test_five_consecutive_failures_open_breaker(self):
        """5 次连续 broker 失败应打开熔断器 (默认阈值)."""
        breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60,
            half_open_max_calls=1,
            name="e2e_celery",
            failure_classifier=_is_celery_failure,
        )
        with patch("app.core.celery_breaker.celery_breaker", breaker), patch(
            "app.core.config.settings.celery_circuit_breaker_enabled", True
        ):
            for i in range(5):

                async def _fail():
                    raise OSError(f"broker unreachable {i}")

                with pytest.raises(OSError):
                    await call_with_celery_breaker(_fail())
            assert breaker.state == CircuitState.OPEN

            # 第 6 次应直接被熔断器拒绝, 不执行协程
            executed = False

            async def _would_execute():
                nonlocal executed
                executed = True

            with pytest.raises(CircuitBreakerOpenError):
                await call_with_celery_breaker(_would_execute())
            assert executed is False

    @pytest.mark.asyncio
    async def test_business_exception_does_not_open_breaker(self):
        """业务异常连续出现不应打开熔断器."""
        breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=60,
            half_open_max_calls=1,
            name="biz_test_celery",
            failure_classifier=_is_celery_failure,
        )
        with patch("app.core.celery_breaker.celery_breaker", breaker), patch(
            "app.core.config.settings.celery_circuit_breaker_enabled", True
        ):
            for _ in range(10):

                async def _raise_value():
                    raise ValueError("bad inspect params")

                with pytest.raises(ValueError):
                    await call_with_celery_breaker(_raise_value())
            assert breaker.state == CircuitState.CLOSED
            assert breaker.failure_count == 0

    @pytest.mark.asyncio
    async def test_check_celery_worker_e2e_circuit_open(self):
        """端到端: check_celery_worker 连续失败后熔断, 后续快速返回 False."""
        from app.core.health import check_celery_worker
        from app.core.metrics import celery_worker_heartbeat

        breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=60,
            half_open_max_calls=1,
            name="e2e_health",
            failure_classifier=_is_celery_failure,
        )

        with patch("app.core.celery_breaker.celery_breaker", breaker), patch(
            "app.core.config.settings.celery_circuit_breaker_enabled", True
        ), patch("app.core.health.celery_app") as mock_celery:
            # 模拟 broker 不可达
            mock_inspect = MagicMock()
            mock_inspect.stats.side_effect = OSError("broker unreachable")
            mock_celery.control.inspect.return_value = mock_inspect

            # 前 3 次失败打开熔断器
            for _ in range(3):
                result = await check_celery_worker("redis://localhost:6379/0")
                assert result is False
            assert breaker.state == CircuitState.OPEN

            # 第 4 次应被熔断器快速拒绝 (inspect.stats 不应被再次调用)
            mock_inspect.stats.reset_mock()
            result = await check_celery_worker("redis://localhost:6379/0")
            assert result is False
            # 熔断器 OPEN 时 inspect.stats 不应被调用
            assert mock_inspect.stats.call_count == 0

        # 验证 heartbeat 最终为 0
        entries = celery_worker_heartbeat.collect()
        assert any(value == 0.0 for _, value in entries)
