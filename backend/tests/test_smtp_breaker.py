"""STAB-P1-004 测试：SMTP 邮件熔断器

验证要点：
1. ``_is_smtp_failure`` 失败分类器正确区分业务异常与 SMTP 基础设施异常
2. ``call_with_smtp_breaker`` 正确包装协程: 成功放行, 失败计数, OPEN 时拒绝
3. ``smtp_circuit_breaker_enabled=False`` 时禁用熔断器 (直接放行)
4. ``EmailService.send_password_reset_email`` 经过熔断器包装
5. ``init_smtp_breaker`` 根据 settings 重新初始化
6. ``metrics.py`` 暴露 smtp_circuit_* 指标
7. ``main.py`` 启动时调用 init_smtp_breaker
"""

from __future__ import annotations

import asyncio
import inspect
import smtplib
from unittest.mock import AsyncMock, patch

import pytest

from app.core.db_breaker import (
    CircuitBreaker,
    CircuitBreakerOpenError,
    CircuitState,
)
from app.core.smtp_breaker import (
    _is_smtp_failure,
    call_with_smtp_breaker,
    init_smtp_breaker,
)

# ── 辅助 fixture ──


@pytest.fixture
def fresh_smtp_breaker():
    """每个测试前重置全局 smtp_breaker 到 CLOSED 状态."""
    test_breaker = CircuitBreaker(
        failure_threshold=3,
        recovery_timeout=1,  # 1 秒, 便于测试
        half_open_max_calls=1,
        name="test_smtp",
        failure_classifier=_is_smtp_failure,
    )
    with patch("app.core.smtp_breaker.smtp_breaker", test_breaker):
        yield test_breaker


@pytest.fixture
def ok_coro():
    """返回一个立即返回 'sent' 的协程."""

    async def _ok():
        return "sent"

    return _ok()


# ─────────────────────────────────────────────────────────────────────────────
# 1. _is_smtp_failure 分类器测试
# ─────────────────────────────────────────────────────────────────────────────


class TestIsSmtpFailure:
    """测试 _is_smtp_failure 异常分类器."""

    def test_none_returns_true(self):
        """显式传入 None 应视为失败 (强制计数)."""
        assert _is_smtp_failure(None) is True

    @pytest.mark.parametrize(
        "exc_cls,exc_args",
        [
            (smtplib.SMTPException, ("test",)),
            (smtplib.SMTPAuthenticationError, (535, "auth failed")),
            (smtplib.SMTPResponseException, (550, "mailbox unavailable")),
            (OSError, ("test",)),
            (ConnectionError, ("test",)),
            (ConnectionRefusedError, ("test",)),
            (ConnectionResetError, ("test",)),
            (TimeoutError, ("test",)),
            (FileNotFoundError, ("test",)),
        ],
    )
    def test_infra_exceptions_trigger_breaker(self, exc_cls, exc_args):
        """SMTP 基础设施异常应触发熔断器."""
        exc = exc_cls(*exc_args)
        assert _is_smtp_failure(exc) is True

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
            assert _is_smtp_failure(e) is False

    def test_http_exception_does_not_trigger(self):
        """FastAPI HTTPException 是业务异常, 不应触发熔断器."""
        from fastapi import HTTPException

        exc = HTTPException(status_code=422, detail="validation error")
        assert _is_smtp_failure(exc) is False

    def test_unknown_exception_triggers_breaker(self):
        """未知异常应触发熔断器 (保守策略, 避免漏判)."""

        class CustomError(Exception):
            pass

        assert _is_smtp_failure(CustomError("unknown")) is True

    def test_exception_chain_with_infra_cause(self):
        """异常链中包含 SMTPException/OSError 时应触发.

        场景: EmailService 将 SMTPException 包装为 ValueError,
        若不检查异常链会漏判, 导致 SMTP 宕机时熔断器不动作.
        """
        try:
            try:
                raise smtplib.SMTPException("connect refused")
            except smtplib.SMTPException as e:
                raise ValueError("wrapper") from e
        except BaseException as wrapper:
            assert _is_smtp_failure(wrapper) is True

    def test_exception_chain_with_oserror_context(self):
        """异常链 __context__ 中包含 OSError 时也应触发."""
        try:
            try:
                raise ConnectionRefusedError("connection refused")
            except ConnectionRefusedError:
                raise ValueError("wrapper")
        except BaseException as wrapper:
            assert _is_smtp_failure(wrapper) is True

    def test_exception_chain_with_only_business_cause(self):
        """异常链仅含业务异常时不触发."""
        try:
            try:
                raise ValueError("bad input")
            except ValueError as e:
                raise TypeError("wrapper") from e
        except BaseException as wrapper:
            assert _is_smtp_failure(wrapper) is False


# ─────────────────────────────────────────────────────────────────────────────
# 2. call_with_smtp_breaker 测试
# ─────────────────────────────────────────────────────────────────────────────


class TestCallWithSmtpBreaker:
    """测试 call_with_smtp_breaker 异步包装."""

    @pytest.mark.asyncio
    async def test_success_returns_result(self, fresh_smtp_breaker, ok_coro):
        """成功执行应返回结果, 熔断器保持 CLOSED."""
        result = await call_with_smtp_breaker(ok_coro)
        assert result == "sent"
        assert fresh_smtp_breaker.state == CircuitState.CLOSED
        assert fresh_smtp_breaker.failure_count == 0

    @pytest.mark.asyncio
    async def test_smtp_exception_increments_failure(self, fresh_smtp_breaker):
        """SMTPException 应增加失败计数."""

        async def _raise_smtp():
            raise smtplib.SMTPException("auth failed")

        with pytest.raises(smtplib.SMTPException):
            await call_with_smtp_breaker(_raise_smtp())
        assert fresh_smtp_breaker.failure_count == 1
        assert fresh_smtp_breaker.state == CircuitState.CLOSED  # 未达阈值

    @pytest.mark.asyncio
    async def test_oserror_increments_failure(self, fresh_smtp_breaker):
        """OSError (含 ConnectionRefusedError) 应增加失败计数."""

        async def _raise_conn():
            raise ConnectionRefusedError("connection refused")

        with pytest.raises(ConnectionRefusedError):
            await call_with_smtp_breaker(_raise_conn())
        assert fresh_smtp_breaker.failure_count == 1

    @pytest.mark.asyncio
    async def test_business_exception_does_not_count(self, fresh_smtp_breaker):
        """业务异常 (ValueError) 应透传但不增加失败计数."""

        async def _raise_value():
            raise ValueError("bad input")

        with pytest.raises(ValueError):
            await call_with_smtp_breaker(_raise_value())
        assert fresh_smtp_breaker.failure_count == 0
        assert fresh_smtp_breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_repeated_failures_open_breaker(self, fresh_smtp_breaker):
        """连续失败达阈值应打开熔断器."""
        for _ in range(3):

            async def _raise_smtp():
                raise smtplib.SMTPException("fail")

            with pytest.raises(smtplib.SMTPException):
                await call_with_smtp_breaker(_raise_smtp())
        assert fresh_smtp_breaker.state == CircuitState.OPEN

    @pytest.mark.asyncio
    async def test_open_breaker_rejects_without_executing(self, fresh_smtp_breaker):
        """熔断器 OPEN 时应抛 CircuitBreakerOpenError 且不执行协程."""
        # 打开熔断器
        for _ in range(3):
            await fresh_smtp_breaker.on_failure(smtplib.SMTPException("fail"))

        executed = False

        async def _would_execute():
            nonlocal executed
            executed = True
            return "sent"

        with pytest.raises(CircuitBreakerOpenError) as exc_info:
            await call_with_smtp_breaker(_would_execute())

        assert exc_info.value.status_code == 503
        assert executed is False  # 协程未执行

    @pytest.mark.asyncio
    async def test_disabled_breaker_skips_check(self, ok_coro):
        """smtp_circuit_breaker_enabled=False 时应跳过熔断器."""
        with patch("app.core.config.settings.smtp_circuit_breaker_enabled", False):
            result = await call_with_smtp_breaker(ok_coro)
            assert result == "sent"

    @pytest.mark.asyncio
    async def test_disabled_breaker_still_propagates_exception(self):
        """禁用熔断器时异常仍应透传."""

        async def _raise():
            raise smtplib.SMTPException("fail")

        with patch("app.core.config.settings.smtp_circuit_breaker_enabled", False):
            with pytest.raises(smtplib.SMTPException):
                await call_with_smtp_breaker(_raise())

    @pytest.mark.asyncio
    async def test_recovery_after_failure(self, fresh_smtp_breaker):
        """OPEN → HALF_OPEN → CLOSED 恢复流程."""
        # 打开熔断器
        for _ in range(3):
            await fresh_smtp_breaker.on_failure(smtplib.SMTPException("fail"))
        assert fresh_smtp_breaker.state == CircuitState.OPEN

        # 等待 recovery_timeout (1 秒)
        await asyncio.sleep(1.1)

        # 下一个成功请求应触发恢复
        async def _ok():
            return "recovered"

        result = await call_with_smtp_breaker(_ok())
        assert result == "recovered"
        assert fresh_smtp_breaker.state == CircuitState.CLOSED

    @pytest.mark.asyncio
    async def test_half_open_failure_reopens_breaker(self, fresh_smtp_breaker):
        """HALF_OPEN 状态下失败应重新打开熔断器."""
        # 打开熔断器
        for _ in range(3):
            await fresh_smtp_breaker.on_failure(smtplib.SMTPException("fail"))
        assert fresh_smtp_breaker.state == CircuitState.OPEN

        # 等待 recovery_timeout
        await asyncio.sleep(1.1)

        # HALF_OPEN 状态下失败 → 重新 OPEN
        async def _fail():
            raise smtplib.SMTPException("still failing")

        with pytest.raises(smtplib.SMTPException):
            await call_with_smtp_breaker(_fail())
        assert fresh_smtp_breaker.state == CircuitState.OPEN


# ─────────────────────────────────────────────────────────────────────────────
# 3. EmailService 集成测试
# ─────────────────────────────────────────────────────────────────────────────


class TestEmailServiceBreakerIntegration:
    """验证 EmailService 经过熔断器包装."""

    def test_send_password_reset_email_uses_breaker(self):
        """send_password_reset_email 源码应包含 call_with_smtp_breaker."""
        from app.services.email_service import EmailService

        src = inspect.getsource(EmailService.send_password_reset_email)
        assert "call_with_smtp_breaker" in src

    def test_email_service_imports_circuit_breaker_open_error(self):
        """email_service 模块应导入 CircuitBreakerOpenError."""
        from app.services import email_service

        assert hasattr(email_service, "CircuitBreakerOpenError")

    def test_email_service_handles_circuit_open(self):
        """send_password_reset_email 应处理 CircuitBreakerOpenError."""
        from app.services.email_service import EmailService

        src = inspect.getsource(EmailService.send_password_reset_email)
        assert "CircuitBreakerOpenError" in src
        assert "邮件服务暂时不可用" in src

    @pytest.mark.asyncio
    async def test_circuit_open_raises_value_error(self):
        """熔断器 OPEN 时应抛 ValueError('邮件服务暂时不可用')."""
        from app.services.email_service import EmailService

        with patch(
            "app.services.email_service.call_with_smtp_breaker",
            new=AsyncMock(side_effect=CircuitBreakerOpenError("smtp circuit open")),
        ):
            # 模拟 SMTP 已配置, 否则会直接返回 (smtp_not_configured)
            with patch("app.services.email_service.settings") as mock_settings:
                mock_settings.smtp_host = "smtp.test.com"
                mock_settings.smtp_from_email = "from@test.com"
                mock_settings.password_reset_base_url = "https://example.com/reset"
                mock_settings.password_reset_token_expire_minutes = 30

                svc = EmailService()
                with pytest.raises(ValueError, match="邮件服务暂时不可用"):
                    await svc.send_password_reset_email("to@test.com", "token123")

    @pytest.mark.asyncio
    async def test_smtp_failure_still_wrapped_as_value_error(self):
        """SMTP 失败 (非熔断器打开) 仍应包装为 ValueError('重置邮件发送失败')."""
        from app.services.email_service import EmailService

        async def _raise_smtp(coro):
            # 模拟 call_with_smtp_breaker 透传 SMTP 异常
            raise smtplib.SMTPException("connect refused")

        with patch(
            "app.services.email_service.call_with_smtp_breaker", new=_raise_smtp
        ):
            with patch("app.services.email_service.settings") as mock_settings:
                mock_settings.smtp_host = "smtp.test.com"
                mock_settings.smtp_from_email = "from@test.com"
                mock_settings.password_reset_base_url = "https://example.com/reset"
                mock_settings.password_reset_token_expire_minutes = 30

                svc = EmailService()
                with pytest.raises(ValueError, match="重置邮件发送失败"):
                    await svc.send_password_reset_email("to@test.com", "token123")


# ─────────────────────────────────────────────────────────────────────────────
# 4. init_smtp_breaker 测试
# ─────────────────────────────────────────────────────────────────────────────


class TestInitSmtpBreaker:
    """测试 init_smtp_breaker 初始化函数."""

    def test_init_uses_settings_values(self):
        """init_smtp_breaker 应使用 settings 中的配置值."""
        with patch("app.core.config.settings.smtp_failure_threshold", 10), patch(
            "app.core.config.settings.smtp_recovery_timeout", 120
        ), patch("app.core.config.settings.smtp_half_open_max_calls", 2):
            init_smtp_breaker()
            from app.core.smtp_breaker import smtp_breaker as new_breaker

            assert new_breaker.failure_threshold == 10
            assert new_breaker.recovery_timeout == 120
            assert new_breaker.half_open_max_calls == 2
            assert new_breaker.name == "smtp"
            # 恢复默认值
            init_smtp_breaker()

    def test_init_breaker_uses_smtp_classifier(self):
        """init 后的 smtp_breaker 应使用 _is_smtp_failure 分类器."""
        init_smtp_breaker()
        from app.core.smtp_breaker import smtp_breaker as new_breaker

        assert new_breaker._failure_classifier is _is_smtp_failure

    def test_init_breaker_default_settings(self):
        """默认配置: threshold=5, recovery=60s, half_open=1."""
        # 重置为默认 (不 patch 任何 settings)
        init_smtp_breaker()
        # 读取当前 settings 值进行验证
        from app.core.config import settings
        from app.core.smtp_breaker import smtp_breaker as new_breaker

        assert new_breaker.failure_threshold == settings.smtp_failure_threshold
        assert new_breaker.recovery_timeout == settings.smtp_recovery_timeout
        assert new_breaker.half_open_max_calls == settings.smtp_half_open_max_calls


# ─────────────────────────────────────────────────────────────────────────────
# 5. metrics.py 与 main.py 集成测试 (静态检查)
# ─────────────────────────────────────────────────────────────────────────────


class TestMetricsAndMainIntegration:
    """验证 metrics 指标暴露与 main 启动初始化."""

    def test_metrics_exposes_smtp_circuit_failure_count(self):
        """metrics.py 应定义 smtp_circuit_failure_count."""
        from app.core import metrics

        assert hasattr(metrics, "smtp_circuit_failure_count")

    def test_metrics_exposes_smtp_circuit_state(self):
        """metrics.py 应定义 smtp_circuit_state."""
        from app.core import metrics

        assert hasattr(metrics, "smtp_circuit_state")

    def test_metrics_endpoint_collects_smtp_state(self):
        """api/v1/metrics.py 应采集 smtp_breaker 状态."""
        from app.api.v1 import metrics as metrics_api

        src = inspect.getsource(metrics_api.get_metrics)
        assert "smtp_breaker" in src
        assert "smtp_circuit_failure_count" in src
        assert "smtp_circuit_state" in src

    def test_main_lifespan_calls_init_smtp_breaker(self):
        """main.py lifespan 应调用 init_smtp_breaker."""
        from app import main

        src = inspect.getsource(main.lifespan)
        assert "init_smtp_breaker" in src

    def test_config_has_smtp_circuit_breaker_enabled(self):
        """config.py 应包含 smtp_circuit_breaker_enabled 字段."""
        from app.core.config import settings

        assert hasattr(settings, "smtp_circuit_breaker_enabled")
        assert isinstance(settings.smtp_circuit_breaker_enabled, bool)

    def test_config_has_smtp_failure_threshold(self):
        """config.py 应包含 smtp_failure_threshold 字段."""
        from app.core.config import settings

        assert hasattr(settings, "smtp_failure_threshold")
        assert isinstance(settings.smtp_failure_threshold, int)

    def test_config_has_smtp_recovery_timeout(self):
        """config.py 应包含 smtp_recovery_timeout 字段."""
        from app.core.config import settings

        assert hasattr(settings, "smtp_recovery_timeout")
        assert isinstance(settings.smtp_recovery_timeout, int)

    def test_config_has_smtp_half_open_max_calls(self):
        """config.py 应包含 smtp_half_open_max_calls 字段."""
        from app.core.config import settings

        assert hasattr(settings, "smtp_half_open_max_calls")
        assert isinstance(settings.smtp_half_open_max_calls, int)


# ─────────────────────────────────────────────────────────────────────────────
# 6. 端到端熔断器场景测试
# ─────────────────────────────────────────────────────────────────────────────


class TestSmtpBreakerEndToEnd:
    """端到端验证 SMTP 熔断器在连续失败后打开."""

    @pytest.mark.asyncio
    async def test_five_consecutive_failures_open_breaker(self):
        """5 次连续 SMTP 失败应打开熔断器 (默认阈值)."""
        # 使用独立 breaker, 不污染全局
        breaker = CircuitBreaker(
            failure_threshold=5,
            recovery_timeout=60,
            half_open_max_calls=1,
            name="e2e_smtp",
            failure_classifier=_is_smtp_failure,
        )
        with patch("app.core.smtp_breaker.smtp_breaker", breaker), patch(
            "app.core.config.settings.smtp_circuit_breaker_enabled", True
        ):
            for i in range(5):

                async def _fail():
                    raise smtplib.SMTPException(f"fail {i}")

                with pytest.raises(smtplib.SMTPException):
                    await call_with_smtp_breaker(_fail())
            assert breaker.state == CircuitState.OPEN

            # 第 6 次应直接被熔断器拒绝, 不执行协程
            executed = False

            async def _would_execute():
                nonlocal executed
                executed = True

            with pytest.raises(CircuitBreakerOpenError):
                await call_with_smtp_breaker(_would_execute())
            assert executed is False

    @pytest.mark.asyncio
    async def test_business_exception_does_not_open_breaker(self):
        """业务异常连续出现不应打开熔断器."""
        breaker = CircuitBreaker(
            failure_threshold=3,
            recovery_timeout=60,
            half_open_max_calls=1,
            name="biz_test",
            failure_classifier=_is_smtp_failure,
        )
        with patch("app.core.smtp_breaker.smtp_breaker", breaker), patch(
            "app.core.config.settings.smtp_circuit_breaker_enabled", True
        ):
            for _ in range(10):

                async def _raise_value():
                    raise ValueError("bad email format")

                with pytest.raises(ValueError):
                    await call_with_smtp_breaker(_raise_value())
            assert breaker.state == CircuitState.CLOSED
            assert breaker.failure_count == 0
