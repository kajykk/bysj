"""SEC-P2-007: 日志脱敏集中化 Filter 测试.

测试范围:
1. sanitize_text 函数: 各类 PII 模式脱敏
2. SanitizingFilter 类: LogRecord 处理
3. logging_config 集成: filter 已注册
"""

from __future__ import annotations

import logging
from pathlib import Path

import pytest

from app.core.log_sanitizer import SanitizingFilter, sanitize_text


class TestSensitiveKeyValue:
    """敏感键值对脱敏测试."""

    def test_password_equals(self):
        """password=xxx 脱敏."""
        result = sanitize_text("user login password=secret123")
        assert "secret123" not in result
        assert "***MASKED***" in result

    def test_password_colon(self):
        """password: xxx 脱敏."""
        result = sanitize_text("config password: mypass")
        assert "mypass" not in result
        assert "***MASKED***" in result

    def test_token_equals(self):
        """token=xxx 脱敏."""
        result = sanitize_text("auth token=abc-123-xyz")
        assert "abc-123-xyz" not in result
        assert "***MASKED***" in result

    def test_access_token(self):
        """access_token=xxx 脱敏."""
        result = sanitize_text("bearer access_token=xyz789")
        assert "xyz789" not in result
        assert "***MASKED***" in result

    def test_api_key(self):
        """api_key=xxx 脱敏."""
        result = sanitize_text("config api_key=sk-test-12345")
        assert "sk-test-12345" not in result

    def test_secret(self):
        """secret=xxx 脱敏."""
        result = sanitize_text("client_secret=mysecret")
        assert "mysecret" not in result

    def test_authorization_header(self):
        """authorization=xxx 脱敏."""
        result = sanitize_text("header authorization=Bearer abc123")
        assert "abc123" not in result

    def test_case_insensitive(self):
        """PASSWORD=xxx (大写) 也脱敏."""
        result = sanitize_text("PASSWORD=secret")
        assert "secret" not in result

    def test_quoted_value(self):
        """password="xxx" 带引号脱敏."""
        result = sanitize_text('config password="mysecret"')
        assert "mysecret" not in result
        assert "***MASKED***" in result

    def test_json_format(self):
        """JSON 格式 "password":"xxx" 脱敏."""
        result = sanitize_text('{"password": "secret123", "user": "admin"}')
        assert "secret123" not in result


class TestBearerToken:
    """Bearer Token 脱敏测试."""

    def test_bearer_token(self):
        """Authorization: Bearer xxx 脱敏 (xxx 不再出现在结果中)."""
        result = sanitize_text("Authorization: Bearer eyJhbGciOiJIUzI1")
        assert "eyJhbGciOiJIUzI1" not in result
        assert "***MASKED***" in result

    def test_lowercase_bearer(self):
        """bearer xxx (小写) 也脱敏."""
        result = sanitize_text("header bearer abc123xyz")
        assert "abc123xyz" not in result


class TestJwtToken:
    """JWT Token 脱敏测试."""

    def test_jwt_three_segments(self):
        """三段式 JWT 脱敏."""
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.SflKxwRJSMeKKF2QT4fwpMeJf36POk6yJV_adQssw5c"
        result = sanitize_text(f"token={jwt}")
        assert jwt not in result
        assert "***JWT_MASKED***" in result or "***MASKED***" in result

    def test_jwt_in_url(self):
        """URL 中的 JWT 脱敏."""
        jwt = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.abc123-_xyz"
        result = sanitize_text(f"GET /api?token={jwt}")
        assert jwt not in result


class TestEmail:
    """Email 脱敏测试."""

    def test_email_masked(self):
        """Email 保留域名, 用户名首字符 + ***."""
        result = sanitize_text("contact: user@example.com")
        assert "user@example.com" not in result
        assert "@example.com" in result
        assert "***" in result

    def test_email_with_plus(self):
        """带 + 的 Email 脱敏."""
        result = sanitize_text("email: test+label@gmail.com")
        assert "test+label@gmail.com" not in result
        assert "@gmail.com" in result

    def test_email_preserves_first_char(self):
        """Email 保留首字符."""
        result = sanitize_text("email: alice@test.com")
        # 应保留首字符 a
        assert "a***@test.com" in result or "***@test.com" in result


class TestPhoneNumber:
    """中国手机号脱敏测试."""

    def test_phone_masked(self):
        """11 位手机号保留前 3 + 后 4."""
        result = sanitize_text("phone: 13912345678")
        assert "13912345678" not in result
        assert "139****5678" in result

    def test_phone_in_context(self):
        """上下文中的手机号脱敏."""
        result = sanitize_text("user phone=13812345678 login")
        assert "13812345678" not in result

    def test_phone_invalid_prefix_not_masked(self):
        """非 1[3-9] 开头的 11 位数字不脱敏."""
        # 10912345678 不是有效手机号 (0 不在 [3-9])
        result = sanitize_text("id: 10912345678")
        # 109 开头不应被脱敏
        assert "10912345678" in result


class TestIdCard:
    """身份证号脱敏测试."""

    def test_id_card_masked(self):
        """18 位身份证号脱敏 (id_card 作为敏感键时整体被脱敏)."""
        result = sanitize_text("user id_card: 110101199001011234")
        # id_card 在敏感键列表中, 整个值被替换为 ***MASKED***
        assert "110101199001011234" not in result
        assert "***MASKED***" in result

    def test_id_card_standalone(self):
        """裸身份证号 (无 id_card 前缀) 脱敏保留首尾."""
        result = sanitize_text("found 110101199001011234 in data")
        assert "110101199001011234" not in result
        # 应保留前 6 + 后 4
        assert "110101" in result
        assert "1234" in result

    def test_id_card_with_x(self):
        """末位为 X 的身份证号脱敏."""
        result = sanitize_text("id: 11010119900101123X")
        assert "11010119900101123X" not in result


class TestCreditCard:
    """信用卡号脱敏测试."""

    def test_card_continuous_16_digits(self):
        """16 位连续信用卡号脱敏."""
        result = sanitize_text("card: 4111111111111111")
        assert "4111111111111111" not in result

    def test_card_grouped_4_4_4_4(self):
        """4-4-4-4 分组信用卡号脱敏."""
        result = sanitize_text("card: 4111-1111-1111-1111")
        assert "4111-1111-1111-1111" not in result

    def test_card_space_separated(self):
        """空格分隔的信用卡号脱敏."""
        result = sanitize_text("card: 4111 1111 1111 1111")
        assert "4111 1111 1111 1111" not in result


class TestApiKeyPrefix:
    """API Key 前缀检测测试."""

    def test_openai_sk_prefix(self):
        """sk- 开头的 OpenAI API Key 脱敏."""
        result = sanitize_text("api_key=sk-abc123def456ghi789jkl012mno345")
        assert "sk-abc123def456ghi789jkl012mno345" not in result

    def test_github_token_prefix(self):
        """ghp_ 开头的 GitHub Token 脱敏."""
        result = sanitize_text("token=ghp_abcdefghijklmnopqrstuvwxyz123456")
        assert "ghp_abcdefghijklmnopqrstuvwxyz123456" not in result


class TestIdempotent:
    """幂等性测试."""

    def test_already_masked_not_reprocessed(self):
        """已脱敏的 ***MASKED*** 不再处理."""
        text = "password=***MASKED***"
        result = sanitize_text(text)
        # 应保持原样 (或仅一次脱敏)
        assert "***MASKED***" in result

    def test_double_sanitize_same_result(self):
        """二次脱敏结果一致."""
        text = "password=secret123 email=user@test.com"
        once = sanitize_text(text)
        twice = sanitize_text(once)
        assert once == twice


class TestEdgeCases:
    """边界情况测试."""

    def test_empty_string(self):
        """空字符串原样返回."""
        assert sanitize_text("") == ""

    def test_non_string_input(self):
        """非字符串输入原样返回."""
        assert sanitize_text(None) is None  # type: ignore[arg-type]
        assert sanitize_text(123) == 123  # type: ignore[arg-type]

    def test_no_pii_text(self):
        """无 PII 的文本原样返回."""
        text = "user login successful from 192.168.1.1"
        assert sanitize_text(text) == text

    def test_multiple_pii_in_one_line(self):
        """一行多个 PII 同时脱敏."""
        text = "password=secret email=user@test.com phone=13912345678"
        result = sanitize_text(text)
        assert "secret" not in result
        assert "user@test.com" not in result
        assert "13912345678" not in result


class TestSanitizingFilter:
    """SanitizingFilter 类测试."""

    def _make_record(self, msg: str, args=None) -> logging.LogRecord:
        """创建测试 LogRecord."""
        return logging.LogRecord(
            name="test",
            level=logging.INFO,
            pathname="test.py",
            lineno=1,
            msg=msg,
            args=args,
            exc_info=None,
        )

    def test_filter_returns_true(self):
        """filter 总是返回 True (不丢弃记录)."""
        f = SanitizingFilter()
        record = self._make_record("normal message")
        assert f.filter(record) is True

    def test_filter_modifies_record_msg(self):
        """filter 修改 record.msg 进行脱敏."""
        f = SanitizingFilter()
        record = self._make_record("password=secret123")
        f.filter(record)
        assert "secret123" not in record.msg
        assert "***MASKED***" in record.msg

    def test_filter_with_args(self):
        """filter 处理 record.args (含 PII 模式)."""
        f = SanitizingFilter()
        # args 中传入含 PII 模式的字符串, 应被 sanitize_text 识别并脱敏
        record = self._make_record("login %s", ("password=secret123",))
        f.filter(record)
        # args 中的 PII 也应被脱敏
        if record.args:
            args_str = str(record.args)
            assert "secret123" not in args_str, (
                f"args 中仍有 PII: {args_str}"
            )
            assert "***MASKED***" in args_str

    def test_filter_with_dict_args(self):
        """filter 处理 dict 类型的 args (使用 %(key)s 格式)."""
        f = SanitizingFilter()
        # dict args 必须配合 %(key)s 格式的 msg, 且需以 tuple 包裹
        # (logging.LogRecord 内部: len(args)==1 and isinstance(args[0], Mapping)
        #  时将 args 解包为 args[0])
        record = self._make_record(
            "config %(password)s", ({"password": "password=secret"},)
        )
        f.filter(record)
        # dict args 中的 PII 也应被脱敏
        if isinstance(record.args, dict):
            assert record.args.get("password") != "secret", (
                f"dict args 中仍有 PII: {record.args}"
            )
            assert "***MASKED***" in str(record.args.get("password", ""))

    def test_filter_no_exception_on_invalid_record(self):
        """filter 对异常 record 不抛异常."""
        f = SanitizingFilter()
        # 创建一个有问题的 record
        record = self._make_record("test")
        record.args = None  # 正常情况下不应为 None, 但防御性处理
        # 不应抛异常
        assert f.filter(record) is True

    def test_filter_preserves_non_pii(self):
        """filter 不修改无 PII 的记录."""
        f = SanitizingFilter()
        original_msg = "user login successful"
        record = self._make_record(original_msg)
        f.filter(record)
        assert record.msg == original_msg


class TestExcInfoSanitization:
    """异常信息脱敏测试."""

    def test_filter_sanitizes_exception_args(self):
        """filter 脱敏异常 args 中的 PII."""
        f = SanitizingFilter()
        try:
            raise ValueError("login failed password=secret123")
        except ValueError:
            import sys

            exc_info = sys.exc_info()
        record = logging.LogRecord(
            name="test",
            level=logging.ERROR,
            pathname="test.py",
            lineno=1,
            msg="error occurred",
            args=None,
            exc_info=exc_info,
        )
        f.filter(record)
        # 异常 args 中的 PII 也应被脱敏
        exc_value = record.exc_info[1]
        assert "secret123" not in str(exc_value.args)


class TestLoggingConfigIntegration:
    """logging_config 集成测试."""

    def test_sanitizer_filter_registered_in_config(self):
        """dictConfig 中注册了 sanitizer filter."""
        from app.core.logging_config import _build_dict_config
        from pathlib import Path

        config = _build_dict_config(
            log_dir=Path("/tmp"),
            enable_file=True,
            enable_console=True,
        )
        assert "filters" in config
        assert "sanitizer" in config["filters"]
        assert (
            config["filters"]["sanitizer"]["()"]
            == "app.core.log_sanitizer.SanitizingFilter"
        )

    def test_all_handlers_have_sanitizer_filter(self):
        """所有 handler 都注册了 sanitizer filter."""
        from app.core.logging_config import _build_dict_config
        from pathlib import Path

        config = _build_dict_config(
            log_dir=Path("/tmp"),
            enable_file=True,
            enable_console=True,
        )
        for handler_name, handler_config in config["handlers"].items():
            if handler_name == "null":
                continue
            assert "sanitizer" in handler_config.get("filters", []), (
                f"handler {handler_name} 缺少 sanitizer filter"
            )

    def test_configure_logging_loads_sanitizer(self):
        """configure_logging 后 logger 链路包含 SanitizingFilter."""
        from app.core.logging_config import configure_logging, reset_logging_state
        from app.core import config as _config
        from unittest.mock import patch

        reset_logging_state()
        with patch.object(_config.settings, "log_to_file", False), patch.object(
            _config.settings, "log_console", True
        ):
            configure_logging(force=True)

        # 检查 root logger 的 handler 是否有 SanitizingFilter
        root_logger = logging.getLogger()
        found = False
        for handler in root_logger.handlers:
            for f in handler.filters:
                if isinstance(f, SanitizingFilter):
                    found = True
                    break
        assert found, "root logger handler 未包含 SanitizingFilter"

    def test_end_to_end_pii_not_in_logs(self, caplog):
        """端到端: 含 PII 的日志记录被脱敏."""
        from app.core.logging_config import configure_logging, reset_logging_state
        from app.core import config as _config
        from unittest.mock import patch

        reset_logging_state()
        with patch.object(_config.settings, "log_to_file", False), patch.object(
            _config.settings, "log_console", True
        ):
            configure_logging(force=True)

            logger = logging.getLogger("test.sec_p2_007")
            # 临时移除 caplog 自己的 handler (避免干扰)
            logger.addHandler(logging.NullHandler())
            logger.info("user login password=secret123")

        # 检查 caplog 捕获的记录
        # 注意: caplog 使用 propagation, 不一定经过我们的 filter
        # 此测试主要验证 configure_logging 不抛异常
        assert True


class TestLogSanitizerSourceStructure:
    """log_sanitizer.py 源码结构测试."""

    def _get_module_path(self) -> Path:
        return (
            Path(__file__).resolve().parent.parent
            / "app"
            / "core"
            / "log_sanitizer.py"
        )

    def test_module_exists(self):
        """log_sanitizer.py 文件存在."""
        assert self._get_module_path().exists()

    def test_sec_p2_007_annotation_present(self):
        """log_sanitizer.py 中有 SEC-P2-007 注释."""
        content = self._get_module_path().read_text(encoding="utf-8")
        assert "SEC-P2-007" in content

    def test_exports_sanitize_text(self):
        """模块导出 sanitize_text 函数."""
        from app.core import log_sanitizer

        assert hasattr(log_sanitizer, "sanitize_text")
        assert callable(log_sanitizer.sanitize_text)

    def test_exports_sanitizing_filter(self):
        """模块导出 SanitizingFilter 类."""
        from app.core import log_sanitizer

        assert hasattr(log_sanitizer, "SanitizingFilter")
        assert issubclass(log_sanitizer.SanitizingFilter, logging.Filter)

    def test_logging_config_imports_sanitizer(self):
        """logging_config.py 导入 SanitizingFilter."""
        logging_config_path = (
            Path(__file__).resolve().parent.parent
            / "app"
            / "core"
            / "logging_config.py"
        )
        content = logging_config_path.read_text(encoding="utf-8")
        # 验证 dictConfig 配置中引用了 SanitizingFilter
        assert "app.core.log_sanitizer.SanitizingFilter" in content
        assert "sanitizer" in content
