"""STAB-P1-002 测试：ML 推理熔断器 + asyncio.wait_for 超时

验证要点：
1. ``_is_ml_failure`` 失败分类器正确区分业务异常与基础设施异常
2. ``CircuitBreaker`` 支持自定义 ``failure_classifier`` (向后兼容 DB 熔断器)
3. ``call_with_ml_breaker`` 正确包装协程: 成功放行, 超时/失败计数, OPEN 时拒绝
4. ``ml_circuit_breaker_enabled=False`` 时禁用熔断器 (仍保留超时)
5. ``ModelPredictService.predict_*`` 4 个方法均经过熔断器包装
6. ``init_ml_breaker`` 根据 settings 重新初始化
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from app.core.db_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
)
from app.core.ml_breaker import (
    _is_ml_failure,
    call_with_ml_breaker,
    init_ml_breaker,
)

# ── 辅助 fixture ──


@pytest.fixture
def fresh_ml_breaker():
    """每个测试前重置全局 ml_breaker 到 CLOSED 状态."""
    # 使用 patch 替换 ml_breaker 模块级变量, 避免污染其他测试
    test_breaker = CircuitBreaker(
        failure_threshold=3,
        recovery_timeout=1,  # 1 秒, 便于测试
        half_open_max_calls=1,
        name="test_ml",
        failure_classifier=_is_ml_failure,
    )
    with patch("app.core.ml_breaker.ml_breaker", test_breaker):
        yield test_breaker


@pytest.fixture
def slow_coro():
    """返回一个永不完成的协程 (用于测试超时)."""

    async def _hang():
        await asyncio.sleep(100)

    return _hang()


@pytest.fixture
def fast_coro():
    """返回一个立即返回 42 的协程."""

    async def _fast():
        return 42

    return _fast()


# ─────────────────────────────────────────────────────────────────────────────
# 1. _is_ml_failure 分类器测试
# ─────────────────────────────────────────────────────────────────────────────


class TestIsMlFailure:
    """测试 _is_ml_failure 异常分类器."""

    def test_none_returns_true(self):
        """显式传入 None 应视为失败 (强制计数)."""
        assert _is_ml_failure(None) is True

    @pytest.mark.parametrize(
        "exc_cls",
        [
            TimeoutError,
            OSError,
            FileNotFoundError,
            RuntimeError,
            MemoryError,
            ImportError,
            ConnectionError,
        ],
    )
    def test_infra_exceptions_trigger_breaker(self, exc_cls):
        """基础设施异常应触发熔断器."""
        exc = exc_cls("test")
        assert _is_ml_failure(exc) is True

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
            assert _is_ml_failure(e) is False

    def test_http_exception_does_not_trigger(self):
        """FastAPI HTTPException 是业务异常, 不应触发熔断器."""
        exc = HTTPException(status_code=422, detail="validation error")
        assert _is_ml_failure(exc) is False

    def test_unknown_exception_triggers_breaker(self):
        """未知异常应触发熔断器 (保守策略, 避免漏判)."""

        class CustomError(Exception):
            pass

        assert _is_ml_failure(CustomError("unknown")) is True

    def test_exception_chain_with_infra_cause(self):
        """异常链中包含基础设施异常时应触发."""
        try:
            try:
                raise OSError("model file locked")
            except OSError as e:
                raise ValueError("wrapper") from e
        except BaseException as wrapper:
            assert _is_ml_failure(wrapper) is True

    def test_exception_chain_with_only_business_cause(self):
        """异常链仅含业务异常时不触发."""
        try:
            try:
                raise ValueError("bad input")
            except ValueError as e:
                raise TypeError("wrapper") from e
        except BaseException as wrapper:
            assert _is_ml_failure(wrapper) is False


# ─────────────────────────────────────────────────────────────────────────────
# 2. CircuitBreaker 自定义分类器测试 (向后兼容)
# ─────────────────────────────────────────────────────────────────────────────


class TestCircuitBreakerCustomClassifier:
    """测试 CircuitBreaker 支持自定义 failure_classifier."""

    async def test_custom_classifier_used(self):
        """CircuitBreaker 应使用传入的 failure_classifier."""

        # 分类器: 只把 RuntimeError 视为失败
        def only_runtime(exc):
            return isinstance(exc, RuntimeError)

        breaker = CircuitBreaker(
            failure_threshold=2,
            failure_classifier=only_runtime,
            name="custom",
        )
        # ValueError 不计数
        await breaker.on_failure(ValueError("business"))
        assert breaker.failure_count == 0
        # RuntimeError 计数
        await breaker.on_failure(RuntimeError("infra"))
        assert breaker.failure_count == 1
        # 再次 RuntimeError 达到阈值 → OPEN
        await breaker.on_failure(RuntimeError("infra"))
        assert breaker.state == CircuitState.OPEN

    async def test_db_breaker_backward_compatible(self):
        """DB 熔断器 (不传 classifier) 应仍使用 _is_connection_failure."""
        from app.core.db_breaker import _is_connection_failure, db_breaker

        # db_breaker 实例的 classifier 应为默认的 _is_connection_failure
        assert db_breaker._failure_classifier is _is_connection_failure
        # IntegrityError (业务异常) 不计数
        from sqlalchemy.exc import IntegrityError, OperationalError

        # 构造一个假的 IntegrityError (不需要真实 DB session)
        fake_integrity = IntegrityError("stmt", params={}, orig=Exception("fake"))
        await db_breaker.on_failure(fake_integrity)
        # OperationalError 应计数
        fake_operational = OperationalError("stmt", params={}, orig=Exception("fake"))
        before = db_breaker.failure_count
        await db_breaker.on_failure(fake_operational)
        assert db_breaker.failure_count == before + 1
        # 清理: reset
        await db_breaker.reset()


# ─────────────────────────────────────────────────────────────────────────────
# 3. call_with_ml_breaker 测试
# ─────────────────────────────────────────────────────────────────────────────


class TestCallWithMlBreaker:
    """测试 call_with_ml_breaker 异步包装."""

    @pytest.mark.asyncio
    async def test_success_returns_result(self, fresh_ml_breaker, fast_coro):
        """成功执行应返回结果, 熔断器保持 CLOSED."""
        result = await call_with_ml_breaker(fast_coro, timeout=1.0)
        assert result == 42
        assert fresh_ml_breaker.state == CircuitState.CLOSED
        assert fresh_ml_breaker.failure_count == 0

    @pytest.mark.asyncio
    async def test_timeout_increments_failure(self, fresh_ml_breaker, slow_coro):
        """超时应抛出 TimeoutError 并增加失败计数."""
        with pytest.raises(asyncio.TimeoutError):
            await call_with_ml_breaker(slow_coro, timeout=0.1)
        assert fresh_ml_breaker.failure_count == 1
        assert fresh_ml_breaker.state == CircuitState.CLOSED  # 未达阈值

    @pytest.mark.asyncio
    async def test_timeout_reaches_threshold_opens_breaker(self, fresh_ml_breaker):
        """连续超时达阈值应打开熔断器."""
        for _ in range(3):

            async def _hang():
                await asyncio.sleep(100)

            with pytest.raises(asyncio.TimeoutError):
                await call_with_ml_breaker(_hang(), timeout=0.05)
        assert fresh_ml_breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_business_exception_does_not_count(self, fresh_ml_breaker):
        """业务异常 (ValueError) 应透传但不增加失败计数."""

        async def _raise_value():
            raise ValueError("bad input")

        with pytest.raises(ValueError):
            await call_with_ml_breaker(_raise_value(), timeout=1.0)
        assert fresh_ml_breaker.failure_count == 0
        assert fresh_ml_breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_infra_exception_counts(self, fresh_ml_breaker):
        """基础设施异常 (RuntimeError) 应增加失败计数."""

        async def _raise_runtime():
            raise RuntimeError("model crashed")

        with pytest.raises(RuntimeError):
            await call_with_ml_breaker(_raise_runtime(), timeout=1.0)
        assert fresh_ml_breaker.failure_count == 1

    @pytest.mark.asyncio
    async def test_open_breaker_rejects_without_executing(self, fresh_ml_breaker):
        """熔断器 OPEN 时应抛 CircuitBreakerOpenError 且不执行协程."""
        # 打开熔断器
        for _ in range(3):
            await fresh_ml_breaker.on_failure(RuntimeError("fail"))

        executed = False

        async def _would_execute():
            nonlocal executed
            executed = True
            return "result"

        with pytest.raises(CircuitBreakerOpenError) as exc_info:
            await call_with_ml_breaker(_would_execute(), timeout=1.0)

        assert exc_info.value.status_code == 503
        assert executed is False  # 协程未执行

    @pytest.mark.asyncio
    async def test_disabled_breaker_still_has_timeout(self, fast_coro):
        """ml_circuit_breaker_enabled=False 时应跳过熔断器但保留超时."""
        with patch("app.core.config.settings.ml_circuit_breaker_enabled", False):
            result = await call_with_ml_breaker(fast_coro, timeout=1.0)
            assert result == 42

    @pytest.mark.asyncio
    async def test_disabled_breaker_timeout_still_raises(self, slow_coro):
        """禁用熔断器时超时仍应抛出."""
        with patch("app.core.config.settings.ml_circuit_breaker_enabled", False):
            with pytest.raises(asyncio.TimeoutError):
                await call_with_ml_breaker(slow_coro, timeout=0.1)

    @pytest.mark.asyncio
    async def test_recovery_after_timeout(self, fresh_ml_breaker):
        """OPEN → HALF_OPEN → CLOSED 恢复流程."""
        # 打开熔断器
        for _ in range(3):
            await fresh_ml_breaker.on_failure(RuntimeError("fail"))
        assert fresh_ml_breaker.state == CircuitState.OPEN

        # 等待 recovery_timeout (1 秒)
        await asyncio.sleep(1.1)

        # 下一个成功请求应触发恢复
        async def _ok():
            return "recovered"

        result = await call_with_ml_breaker(_ok(), timeout=1.0)
        assert result == "recovered"
        assert fresh_ml_breaker.state == CircuitState.CLOSED


# ─────────────────────────────────────────────────────────────────────────────
# 4. ModelPredictService 集成测试
# ─────────────────────────────────────────────────────────────────────────────


class TestModelPredictServiceBreakerIntegration:
    """验证 ModelPredictService.predict_* 4 个方法均经过熔断器包装."""

    def test_predict_tabular_uses_breaker(self):
        """predict_tabular 源码应包含 call_with_ml_breaker."""
        import inspect

        from app.services.model_predict_service import ModelPredictService

        src = inspect.getsource(ModelPredictService.predict_tabular)
        assert "call_with_ml_breaker" in src

    def test_predict_text_uses_breaker(self):
        """predict_text 源码应包含 call_with_ml_breaker."""
        import inspect

        from app.services.model_predict_service import ModelPredictService

        src = inspect.getsource(ModelPredictService.predict_text)
        assert "call_with_ml_breaker" in src

    def test_predict_physiological_uses_breaker(self):
        """predict_physiological 源码应包含 call_with_ml_breaker."""
        import inspect

        from app.services.model_predict_service import ModelPredictService

        src = inspect.getsource(ModelPredictService.predict_physiological)
        assert "call_with_ml_breaker" in src

    def test_predict_fusion_uses_breaker(self):
        """predict_fusion 源码应包含 call_with_ml_breaker."""
        import inspect

        from app.services.model_predict_service import ModelPredictService

        src = inspect.getsource(ModelPredictService.predict_fusion)
        assert "call_with_ml_breaker" in src

    @pytest.mark.asyncio
    async def test_predict_tabular_success_calls_breaker(self):
        """predict_tabular 成功时应调用 call_with_ml_breaker."""
        from app.services.model_predict_service import ModelPredictService

        with patch(
            "app.services.model_predict_service.call_with_ml_breaker",
            new=AsyncMock(return_value={"risk_level": 1}),
        ) as mock_call:
            service = ModelPredictService()
            result = await service.predict_tabular({"age": 20})
            assert result == {"risk_level": 1}
            mock_call.assert_called_once()

    @pytest.mark.asyncio
    async def test_predict_text_empty_raises_value_before_breaker(self):
        """predict_text 空文本应在调用熔断器前抛 ValueError."""
        from app.services.model_predict_service import ModelPredictService

        with patch(
            "app.services.model_predict_service.call_with_ml_breaker", new=AsyncMock()
        ) as mock_call:
            service = ModelPredictService()
            with pytest.raises(ValueError):
                await service.predict_text("")
            # 熔断器不应被调用 (空文本校验在前)
            mock_call.assert_not_called()


# ─────────────────────────────────────────────────────────────────────────────
# 5. init_ml_breaker 测试
# ─────────────────────────────────────────────────────────────────────────────


class TestInitMlBreaker:
    """测试 init_ml_breaker 初始化函数."""

    def test_init_uses_settings_values(self):
        """init_ml_breaker 应使用 settings 中的配置值."""
        with patch("app.core.config.settings.ml_failure_threshold", 10), patch(
            "app.core.config.settings.ml_recovery_timeout", 60
        ), patch("app.core.config.settings.ml_half_open_max_calls", 2), patch(
            "app.core.config.settings.ml_inference_timeout", 10
        ):
            init_ml_breaker()
            from app.core.ml_breaker import ml_breaker as new_breaker

            assert new_breaker.failure_threshold == 10
            assert new_breaker.recovery_timeout == 60
            assert new_breaker.half_open_max_calls == 2
            assert new_breaker.name == "ml"
            # 恢复默认值
            init_ml_breaker()

    def test_init_breaker_uses_ml_classifier(self):
        """init 后的 ml_breaker 应使用 _is_ml_failure 分类器."""
        init_ml_breaker()
        from app.core.ml_breaker import ml_breaker as new_breaker

        assert new_breaker._failure_classifier is _is_ml_failure


# ─────────────────────────────────────────────────────────────────────────────
# 6. API 层异常处理测试 (静态检查)
# ─────────────────────────────────────────────────────────────────────────────


class TestApiLayerExceptionHandling:
    """验证 predict.py 4 个端点正确处理熔断器异常."""

    def test_predict_tabular_handles_circuit_breaker_open(self):
        """predict_tabular 应处理 CircuitBreakerOpenError."""
        import inspect

        from app.api.v1.model_predict.predict import predict_tabular

        src = inspect.getsource(predict_tabular)
        assert "CircuitBreakerOpenError" in src
        assert "asyncio.TimeoutError" in src

    def test_predict_text_handles_circuit_breaker_open(self):
        """predict_text 应处理 CircuitBreakerOpenError."""
        import inspect

        from app.api.v1.model_predict.predict import predict_text

        src = inspect.getsource(predict_text)
        assert "CircuitBreakerOpenError" in src
        assert "asyncio.TimeoutError" in src

    def test_predict_physiological_handles_circuit_breaker_open(self):
        """predict_physiological 应处理 CircuitBreakerOpenError."""
        import inspect

        from app.api.v1.model_predict.predict import predict_physiological

        src = inspect.getsource(predict_physiological)
        assert "CircuitBreakerOpenError" in src
        assert "asyncio.TimeoutError" in src

    def test_predict_fusion_handles_circuit_breaker_open(self):
        """predict_fusion 应处理 CircuitBreakerOpenError."""
        import inspect

        from app.api.v1.model_predict.predict import predict_fusion

        src = inspect.getsource(predict_fusion)
        assert "CircuitBreakerOpenError" in src
        assert "asyncio.TimeoutError" in src
