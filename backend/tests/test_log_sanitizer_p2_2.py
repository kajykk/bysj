"""AUDIT-2026-10-06 (P2-2): 日志脱敏器的绕过用例（全部来自实测输入 → 输出）。

审查阶段用一份独立脚本跑出下表的"实测"列，确认 4 类绕过：

===============  ==========================================  ==========
输入              修复前实测输出（泄漏）                      修复后
===============  ==========================================  ==========
new_password=…    ``new_password=hunter2``（明文）            ``***MASKED***``
secret_key: …     ``secret_key: AKIA...``（明文）            ``***MASKED***``
access_key_id=…   ``access_key_id=LTAI...``（明文）          ``***MASKED***``
session_id=…      ``session_id=abc123secret``（明文）        ``***MASKED***``
phone=+86…        ``phone=+8613912345678``（明文）           ``***MASKED***``
ip=…              ``ip=203.0.113.9``（明文，GDPR 个人数据）   ``***MASKED***``
{"password": x}   容器内值不被处理（明文）                    整个值 ``***MASKED***``
===============  ==========================================  ==========

根因两条（注释里已写）：
1. 键名正则原用 ``\\b(key)\\b`` —— ``\\b`` 要求键名两侧是非单词字符，
   复合键（new_password / secret_key / access_key_id / session_id）整体失配；
2. 容器脱敏只对"值"跑正则，不按键名判定 —— 而 ``{"password": "p@ss"}``
   的值本身不含任何特征串，必然漏。

本文件把上表固化为回归测试，防止改回宽松实现。
"""

from __future__ import annotations

import logging

import pytest

from app.core.log_sanitizer import SanitizingFilter, sanitize_text


class TestCompositeKeysAreMasked:
    """复合键必须被识别（原实现因 ``\\b`` 全部失配）。"""

    @pytest.mark.parametrize(
        "text,leaked",
        [
            ("new_password=hunter2", "hunter2"),
            ("old_password=abc, password_confirm=def", "abc"),
            ("secret_key: AKIAIOSFODNN7EXAMPLE", "AKIAIOSFODNN7EXAMPLE"),
            ("access_key_id=LTAI5tQZDd", "LTAI5tQZDd"),
            ("session_id=abc123secret", "abc123secret"),
        ],
    )
    def test_value_not_leaked(self, text: str, leaked: str) -> None:
        out = sanitize_text(text)
        assert leaked not in out, f"敏感值泄漏: {out!r}"
        assert "MASKED" in out


class TestPhoneWithCountryCode:
    @pytest.mark.parametrize("text", ["phone=+8613912345678", "call +8613912345678 now"])
    def test_e164_style_phone_masked(self, text: str) -> None:
        out = sanitize_text(text)
        assert "13912345678" not in out
        assert "MASKED" in out or "****" in out


class TestIpAndUsername:
    """IP 与 username 在 GDPR 下属个人数据，此前完全不在脱敏清单里。"""

    def test_ip_masked(self) -> None:
        assert "203.0.113.9" not in sanitize_text("user=zhangsan ip=203.0.113.9")

    def test_username_key_masked(self) -> None:
        out = sanitize_text("username=zhangsan")
        assert "zhangsan" not in out


class TestExistingBehaviourPreserved:
    """不得破坏原有已覆盖的脱敏能力（回归护栏）。"""

    @pytest.mark.parametrize(
        "text",
        [
            "password=Secret123!",
            '{"token":"abc.def.ghi","id_card":"110101199001011234"}',
            "Authorization: Bearer abcdef123456",
            "身份证 110101199001011234",
            "card 4111111111111111",
            "card 4111 1111 1111 1111",
        ],
    )
    def test_still_masked(self, text: str) -> None:
        out = sanitize_text(text)
        assert "MASKED" in out or "****" in out

    @pytest.mark.parametrize(
        "text",
        [
            "model=lightgbm score=0.31",
            "GET /api/v1/metrics 200 in 12ms",
            "celery task alerts done",
        ],
    )
    def test_normal_debug_not_broken(self, text: str) -> None:
        """过度脱敏会毁掉排障能力 —— 普通调试信息必须原样保留。"""
        assert sanitize_text(text) == text


class TestNestedContainers:
    """容器脱敏必须按键名判定 + 递归下降。"""

    @staticmethod
    def _record(msg: str, args: object) -> logging.LogRecord:
        """构造真实 LogRecord。

        ``args`` 必须传 tuple —— LogRecord 内部对单个 Mapping 会自动解包成
        dict（``self.args = args[0]``），直接传 dict 会在构造期抛 KeyError。
        """
        if not isinstance(args, tuple):
            args = (args,)
        return logging.LogRecord(
            name="t", level=logging.INFO, pathname=__file__, lineno=1,
            msg=msg, args=args, exc_info=None,
        )

    def test_nested_dict_value_masked(self) -> None:
        rec = self._record("cfg=%s", {"smtp": {"password": "p@ss"}})
        SanitizingFilter().filter(rec)
        assert "p@ss" not in str(rec.args)

    def test_list_of_dict_masked(self) -> None:
        rec = self._record("payload=%s", [{"ip": "203.0.113.9", "access_token": "abc.def.ghi"}])
        SanitizingFilter().filter(rec)
        assert "203.0.113.9" not in str(rec.args)
        assert "abc.def.ghi" not in str(rec.args)

    def test_non_sensitive_container_preserved(self) -> None:
        rec = self._record("cfg=%s", {"host": "db.internal", "port": 5432})
        SanitizingFilter().filter(rec)
        assert rec.args == {"host": "db.internal", "port": 5432}

    def test_self_referential_structure_does_not_hang(self) -> None:
        """自引用结构不能无限递归。"""
        d: dict = {"name": "x"}
        d["self"] = d
        rec = self._record("cfg=%s", d)
        SanitizingFilter().filter(rec)  # 不抛异常即通过


class TestFormatSpecifiersSurvive:
    """回归：脱敏不得吃掉 %s 占位符。

    AUDIT-2026-10-06 实测事故：把 `ip` 加入敏感键名后，
    ``logger.warning("... ip=%s", ip)`` 的 msg 被打码成 "ip=***MASKED***"，
    而 record.args 仍有 3 项 → ``record.getMessage()`` 抛
    ``TypeError: not all arguments converted during string formatting``，
    **整条日志记录在 handler 里崩掉**（测试套件抓到的，不是理论推演）。
    此类问题在加入 ip/email/username 之前就存在（password=%s 同样会炸）。
    """

    @staticmethod
    def _render(msg: str, args: tuple) -> str:
        rec = logging.LogRecord(
            name="t", level=logging.INFO, pathname=__file__, lineno=1,
            msg=msg, args=args, exc_info=None,
        )
        SanitizingFilter().filter(rec)
        return rec.getMessage()  # 若占位符被破坏，这里抛 TypeError

    def test_placeholders_not_consumed(self) -> None:
        out = self._render(
            "auth.login.failed username=%s reason=%s ip=%s",
            ("zhangsan", "invalid_credentials", "203.0.113.9"),
        )
        assert "reason=invalid_credentials" in out
        assert "203.0.113.9" not in out  # IP 仍被值级模式拦下

    @pytest.mark.parametrize(
        "msg,args",
        [
            ("user_id=%s role=%s", (7, "user")),
            ("GET %s -> %s in %.2fms", ("/api/v1/metrics", 200, 12.345)),
            ("model=%s score=%.3f threshold=%s", ("v1.23", 0.667, 0.5)),
            ("progress 50%% done=%s", (0.5,)),
        ],
    )
    def test_non_sensitive_logs_unaffected(self, msg: str, args: tuple) -> None:
        """非敏感日志必须原样渲染（脱敏不能毁掉排障能力）。"""
        assert self._render(msg, args) == msg % args

    def test_positional_value_under_sensitive_key_masked(self) -> None:
        """值在 args 里也要脱敏 —— `password=%s` 的密码不能落到日志。"""
        assert "Str0ngPass" not in self._render("password=%s", ("Str0ngPass!2026",))

    def test_only_sensitive_positional_masked(self) -> None:
        out = self._render("user=%s pwd=%s id=%s", ("alice", "s3cret", 7))
        assert "alice" in out and "id=7" in out
        assert "s3cret" not in out
