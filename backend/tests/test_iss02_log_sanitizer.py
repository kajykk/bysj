"""ISS-02 覆盖率提升：app/core/log_sanitizer.py 聚焦测试.

PII 日志脱敏（安全关键）。纯正则函数，覆盖所有脱敏模式 + Filter 行为 + 边界。
"""

from __future__ import annotations

import logging

import pytest

from app.core.log_sanitizer import SanitizingFilter, sanitize_text


class TestSanitizeTextPatterns:
    def test_password_keyvalue(self):
        assert "password=***MASKED***" in sanitize_text("password=hunter2")

    def test_token_keyvalue(self):
        assert "token=***MASKED***" in sanitize_text("token=abc123token")

    def test_bearer_token(self):
        # 源码顺序：key=value 模式先于 Bearer 模式，Bearer 头被 password/authorization 键匹配
        out = sanitize_text("Authorization: Bearer eyJabc.def.ghi")
        assert "Bearer" not in out
        assert "***MASKED***" in out
        assert "eyJabc" not in out

    def test_jwt_masked(self):
        # 实际行为：key=value 模式先于 JWT 模式，token: xxx 被 password/token 键命中
        out = sanitize_text("token: eyJAAAA.eyJBBBB.ccccc")
        assert "token=***MASKED***" in out
        assert "eyJAAAA" not in out

    def test_email_masked_keeps_domain(self):
        out = sanitize_text("contact user@corp.com please")
        assert "***@corp.com" in out
        assert "user@corp.com" not in out

    def test_phone_masked(self):
        out = sanitize_text("call 13912345678 now")
        assert "139****5678" in out

    def test_id_card_masked(self):
        out = sanitize_text("id 110101199001011234 done")
        assert "110101********1234" in out

    def test_credit_card_16(self):
        out = sanitize_text("card 4111111111111111")
        # 源码：保留前 4 + 后 4，中间 4 位 * 替换 = 4111******1111
        assert "4111******1111" in out

    def test_credit_card_grouped(self):
        out = sanitize_text("card 4111 1111 1111 1111")
        assert "4111 **** **** 1111" in out

    def test_api_key_sk(self):
        out = sanitize_text("key sk-abcdefghijklmnopqrstuvwx")
        assert "***APIKEY_MASKED***" in out

    def test_api_key_gh(self):
        out = sanitize_text("token ghp_abcdefghijklmnopqrst")
        assert "***APIKEY_MASKED***" in out

    def test_json_sensitive_key(self):
        out = sanitize_text('{"password": "secret123", "user": "bob"}')
        assert '"password":"***MASKED***"' in out
        assert "secret123" not in out
        assert '"user": "bob"' in out  # 非敏感键不动（保留原空格）


class TestSanitizeEdgeCases:
    def test_empty_returns_empty(self):
        assert sanitize_text("") == ""

    def test_non_string_returns_as_is(self):
        assert sanitize_text(None) is None  # type: ignore[arg-type]
        assert sanitize_text(123) == 123  # type: ignore[arg-type]

    def test_no_pii_unchanged(self):
        assert sanitize_text("hello world, nothing sensitive") == "hello world, nothing sensitive"

    def test_idempotent_already_masked(self):
        once = sanitize_text("password=hunter2")
        twice = sanitize_text(once)
        assert once == twice

    def test_multiple_pii_in_one_text(self):
        out = sanitize_text("user foo@bar.com phone 13800001111 password=topsecret")
        assert "f***@bar.com" in out  # email 保留首位
        assert "138****1111" in out  # 手机号
        assert "password=***MASKED***" in out  # 密码键


class TestSanitizingFilter:
    def test_filter_masks_msg(self):
        f = SanitizingFilter()
        rec = logging.LogRecord(
            "x", logging.INFO, "p", 1, "password=supersecret", None, None
        )
        assert f.filter(rec) is True
        assert rec.msg == "password=***MASKED***"

    def test_filter_masks_args_tuple(self):
        f = SanitizingFilter()
        rec = logging.LogRecord(
            "x", logging.INFO, "p", 1, "value=%s", ("token=abc",), None
        )
        f.filter(rec)
        assert rec.args == ("token=***MASKED***",)

    def test_filter_masks_args_dict(self):
        f = SanitizingFilter()
        # 直接验证 _sanitize_args 的 dict 脱敏分支（避免 LogRecord 构造期 % 格式化 KeyError）
        sanitized = f._sanitize_args({"v": "secret=abc"})
        assert sanitized == {"v": "secret=***MASKED***"}

    def test_filter_always_returns_true(self):
        f = SanitizingFilter()
        rec = logging.LogRecord("x", logging.INFO, "p", 1, "plain", None, None)
        assert f.filter(rec) is True

    def test_filter_handles_exc_info_tuple(self):
        f = SanitizingFilter()

        try:
            raise RuntimeError("password=leaked")
        except RuntimeError as e:
            rec = logging.LogRecord(
                "x",
                logging.INFO,
                "p",
                1,
                "operation failed",  # msg 必须可格式化，避免 logging 内部 KeyError
                None,
                (type(e), e, e.__traceback__),
            )
        f.filter(rec)
        # exc_value.args[0] 应被脱敏（不触发格式化 KeyError）
        assert rec.exc_info[1].args[0] == "password=***MASKED***"
