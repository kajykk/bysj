"""SEC-P2-007: 日志脱敏集中化 Filter.

提供 ``SanitizingFilter`` 类, 注册到 logging 配置的 filters 中, 自动对
每条 LogRecord 的 message 进行 PII (Personally Identifiable Information)
脱敏处理, 避免敏感信息写入日志文件/控制台.

支持的脱敏模式:
- 密码/令牌/密钥: ``password=xxx`` / ``token: xxx`` / ``secret=xxx`` → ``password=***MASKED***``
- Bearer Token: ``Authorization: Bearer xxx`` → ``Authorization: Bearer ***MASKED***``
- JWT Token: ``eyJxxx.eyJxxx.xxx`` → ``***JWT_MASKED***``
- Email: ``user@example.com`` → ``***@example.com`` (保留域名便于排查)
- 手机号: ``13912345678`` → ``139****5678``
- 身份证号: ``110101199001011234`` → ``110101********1234``
- 信用卡号: ``4111111111111111`` → ``411111******1111``
- API Key (常见前缀): ``sk-xxx`` / ``pk-xxx`` → ``sk-***MASKED***``
- 控制字符 (AUDIT-2026-09-30-P1-5): ``\\n`` / ``\\r`` / ``\\x1b`` 等 → 转义字面量，
  阻断 log injection（伪造整行日志）与 ANSI 转义序列注入终端

设计原则:
- 幂等: 已脱敏的文本不再处理 (避免重复替换)
- 性能: 使用编译后的正则, 单次 sub 完成所有替换
- 安全: 即使正则匹配失败也不抛异常, 原样返回 (避免影响日志输出)
- 可扩展: 模式列表为模块级常量, 可通过追加扩展

使用方式:

.. code-block:: python

    from app.core.log_sanitizer import SanitizingFilter

    # 添加到 logger/handler
    handler.addFilter(SanitizingFilter())

    # 或在 dictConfig 中:
    "filters": {
        "sanitizer": {
            "()": "app.core.log_sanitizer.SanitizingFilter",
        },
    }
"""

from __future__ import annotations

import logging
import re
from typing import Any

# OPT-P3-002：脱敏器自身故障需要可观测（原实现完全静默）
logger = logging.getLogger(__name__)

# ── 敏感键名清单（三处模式共用，避免各写一份漂移）────────────────────────────
# AUDIT-2026-10-06 (P2-2) 的实测结论：
#   1. 原键名正则用 `\b(key)\b`，`\b` 要求键名两侧是非单词字符，导致**所有复合键**
#      （new_password / secret_key / access_key_id / session_id）整体失配 → 明文落盘。
#      修法：左侧 `(?<![A-Za-z0-9-])`（**不含下划线**，否则 new_password 仍被排除），
#      键名后接 `[\w.-]*`，使 new_password 由 password 匹配、secret_key 由 secret 匹配。
#   2. 清单补 email / phone / ip / username，并放宽出 key / session / credential
#      以覆盖 access_key_id、session_id 这类复合键。
#   3. 键名清单与 celery_app._SENSITIVE_KEYS 的"对齐"注释此前与实际不符，现统一。
# 取舍：宁可**过度脱敏**（cache_key=... 也会被打码）也不可漏 —— 本项目处理心理健康
# 数据，日志泄露 PII 的代价远高于日志可读性损失。
_SENSITIVE_KEY_ALTS = (
    r"password|passwd|pwd|"
    r"token|access_token|refresh_token|id_token|"
    r"secret|client_secret|api_secret|"
    r"api_key|apikey|api-key|"
    r"authorization|auth|"
    r"jwt|bearer|"
    r"credit_card|credit_card_number|card_number|cvv|cvc|"
    r"ssn|id_card|id_number|"
    r"private_key|privatekey|"
    r"email|e_mail|mail|"
    r"phone|mobile|telephone|tel|"
    r"ip|ip_address|client_ip|remote_addr|"
    r"username|user_name|"
    r"key|session|credential"
)

# 纯键名判定（用于容器脱敏：{"password": "x"} 的值本身不含任何特征串，
# 必须按键名判定才能拦住 —— 这是实测中最后两个用例失败的根因）
_SENSITIVE_KEY_NAME_PATTERN = re.compile(
    r"(?i)^(?:" + _SENSITIVE_KEY_ALTS + r")[\w.-]*$",
)

# key=value / key: value 格式 (无引号)
#
# AUDIT-2026-10-06 (P2-2 修复回归): 值部分必须排除** logging 的 %-转换占位符**。
# 否则 `logger.warning("... ip=%s", ip)` 里的 "ip=%s" 会整体被打码成
# "ip=***MASKED***"，而 record.args 仍有 3 个参数 →
# `record.getMessage()` 抛 `TypeError: not all arguments converted during
# string formatting`，**日志handler 整条崩掉**。
# （这个 bug 类在加入 ip/email/username 键名之前就存在：password=%s 同样会炸。）
_NOT_A_FORMAT_SPEC = r"(?!%[-+ #0-9.]*[a-zA-Z])"
_SENSITIVE_KEY_PATTERN = re.compile(
    r"(?i)(?<![A-Za-z0-9-])("
    + _SENSITIVE_KEY_ALTS
    + r")[\w.-]*\s*[:=]\s*['\"]?"
    + _NOT_A_FORMAT_SPEC
    + r"([^\s'\",}{\]]+)",
)

# JSON 格式 "key":"value" / "key": "value"（同样排除 %s 占位符）
_SENSITIVE_KEY_JSON_PATTERN = re.compile(
    r"(?i)\"(" + _SENSITIVE_KEY_ALTS + r")[\w.-]*\"\s*:\s*\"" + _NOT_A_FORMAT_SPEC + r"([^\"]+)\"",
)

# IPv4 值级模式（不带键名时也要能拦，如 `logger.warning("ip=%s", ip)` 的位置参数）
_IPV4_PATTERN = re.compile(
    r"(?<![\d.])(?:(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)\.){3}"
    r"(?:25[0-5]|2[0-4]\d|1\d{2}|[1-9]?\d)(?![\d.])"
)

# Bearer Token (Authorization header) - 必须先于 key=value 处理
_BEARER_PATTERN = re.compile(r"(?i)\b(Bearer)\s+([A-Za-z0-9\-_\.=]+)", re.IGNORECASE)

# JWT Token (三段式 base64.base64.signature)
_JWT_PATTERN = re.compile(r"eyJ[A-Za-z0-9\-_]+\.eyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+")

# Email (保留域名便于排查)
_EMAIL_PATTERN = re.compile(r"\b([A-Za-z0-9._%+\-])([A-Za-z0-9._%+\-]+)@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})\b")

# 中国手机号 (11 位, 1[3-9] 开头)
# AUDIT-2026-10-06 (P2-2): 原 `(?<!\d)` 会让带国际区号的号码整体失配 ——
# "+8613912345678" 中 "1" 的前一位是 "6"（数字）→ 负向后查找失败 → 明文落盘。
# 现在可选地吃掉 "+86" 前缀后再匹配。
_PHONE_PATTERN = re.compile(r"(?<![\d+])(?:\+?86)?(1[3-9]\d)(\d{4})(\d{4})(?![\d\w])")

# 身份证号 (18 位, 末位可能为 X)
_ID_CARD_PATTERN = re.compile(r"(?<!\d)(\d{6})(\d{8})(\d{3})([\dXx])(?!\d)")

# 信用卡号 (16 位连续或 4-4-4-4 分组)
_CARD_PATTERN = re.compile(
    r"(?<!\d)(\d{4})(\d{4})(\d{4})(\d{4})(?!\d)|" r"(?<!\d)(\d{4})[\s\-](\d{4})[\s\-](\d{4})[\s\-](\d{4})(?!\d)"
)

# API Key 常见前缀 (OpenAI sk-/Stripe sk_/pk_/GitHub ghp_/gho_/ghu_/ghs_/ghr_)
_APIKEY_PATTERN = re.compile(r"\b(sk-[A-Za-z0-9]{20,}|pk_[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{20,})")

# AUDIT-2026-09-30-P1-5: 控制字符（C0 + DEL + C1）转义，防止 log injection。
#
# 背景：`POST /api/v1/monitoring/metrics/frontend` 是无鉴权端点（仅 30/min 限流），
# 其 `url` 字段直接来自浏览器且被写入 `logger.info(...)`。含 \n 的 URL 可以伪造出
# 整行日志（例如插入一条假的 "admin deleted user"），污染日志聚合与安全审计追溯；
# \x1b[...m 还能向运维终端注入 ANSI 序列。
#
# 在 sanitize_text 这一统一入口处理，可覆盖全仓所有走 SanitizingFilter 的日志，
# 而不必逐个修调用点。
_CONTROL_CHARS_PATTERN = re.compile(r"[\x00-\x1f\x7f-\x9f]")
_CONTROL_CHAR_ESCAPES = {
    0x09: "\\t",
    0x0A: "\\n",
    0x0D: "\\r",
}


def _escape_control_char(match: re.Match) -> str:
    """把单个控制字符替换为可见的转义字面量（保留可排查性，但不再是真控制字符）。"""
    code = ord(match.group(0))
    return _CONTROL_CHAR_ESCAPES.get(code, f"\\x{code:02x}")


def sanitize_text(text: str) -> str:
    """SEC-P2-007: 对文本进行 PII 脱敏.

    Args:
        text: 原始文本.

    Returns:
        脱敏后的文本. 若 text 非 str 或为空, 原样返回.
    """
    if not isinstance(text, str) or not text:
        return text

    result = text

    # 1. JWT Token (三段式, 最具体, 先匹配避免被 key=value 部分捕获)
    result = _JWT_PATTERN.sub("***JWT_MASKED***", result)

    # 2. API Key (前缀检测, 具体)
    result = _APIKEY_PATTERN.sub("***APIKEY_MASKED***", result)

    # 3. Bearer Token (Authorization: Bearer xxx, 先于 key=value)
    result = _BEARER_PATTERN.sub(lambda m: f"{m.group(1)} ***MASKED***", result)

    # 4. JSON 格式敏感键值对 ("key":"value")
    result = _SENSITIVE_KEY_JSON_PATTERN.sub(lambda m: f'"{m.group(1)}":"***MASKED***"', result)

    # 5. 普通敏感键值对 (key=value / key: value)
    result = _SENSITIVE_KEY_PATTERN.sub(lambda m: f"{m.group(1)}=***MASKED***", result)

    # 6. Email (保留首位字符 + 域名, 便于排查)
    result = _EMAIL_PATTERN.sub(lambda m: f"{m.group(1)}***@{m.group(3)}", result)

    # 6b. IPv4（GDPR 个人数据）
    # 必须有这一条：键名模式只能覆盖 "ip=1.2.3.4" 这种写法，
    # 而 `logger.warning("client ip: %s", ip)` 的 IP 在 record.args 里（位置参数），
    # 键名根本不在消息串中 —— 靠值级模式才能拦住。
    result = _IPV4_PATTERN.sub("***IP_MASKED***", result)

    # 7. 手机号 (保留前 3 + 后 4)
    result = _PHONE_PATTERN.sub(lambda m: f"{m.group(1)}****{m.group(3)}", result)

    # 8. 身份证号 (保留前 6 + 后 4, 中间 8 位生日用 * 替换)
    result = _ID_CARD_PATTERN.sub(lambda m: f"{m.group(1)}********{m.group(3)}{m.group(4)}", result)

    # 9. 信用卡号 (保留前 6 + 后 4, 中间 6 位 * 替换)
    def _mask_card(m: re.Match) -> str:
        if m.group(1):  # 16 位连续
            return f"{m.group(1)}******{m.group(4)}"
        # 4-4-4-4 分组
        return f"{m.group(5)} **** **** {m.group(8)}"

    result = _CARD_PATTERN.sub(_mask_card, result)

    # 10. 控制字符转义 (AUDIT-2026-09-30-P1-5) — 必须最后执行。
    #
    # 顺序是先脱敏、后转义，理由（由 test_pii_masking_still_works_after_escape 实测确定）：
    # 若先转义，"password=secret\nalice@example.com" 会变成
    # "password=secret\\nalice@example.com"，其中的 \n 不再是空白字符，
    # 敏感键值正则会把 secret\\nalice@example.com 整体当作 value 吞掉，
    # 结果是过度脱敏——邮箱被一并抹除，日志失去可排查性。
    # 放在最后既保留前面 9 步的原有语义，又能保证输出不含真实换行。
    result = _CONTROL_CHARS_PATTERN.sub(_escape_control_char, result)

    return result


# 「敏感键 + %s 占位符」模式：值在 record.args 里，键名在 msg 里，
# 键名模式对不上（msg 里只有 `password=%s`），必须按占位符位置脱敏。
_SENSITIVE_PLACEHOLDER_PATTERN = re.compile(
    r"(?i)(?<![A-Za-z0-9-])(?:"
    + _SENSITIVE_KEY_ALTS
    + r")[\w.-]*\s*[:=]\s*['\"]?%(?:\d+\$)?[sdifgeExXorc%]"
)

# 惰性格式化占位符（%s / %.2f / %d …；%% 是转义不计）
_FORMAT_SPEC_PATTERN = re.compile(r"%(?:(\d+)\$)?([a-zA-Z%])")


def _sensitive_arg_indexes(msg: str) -> set[int]:
    """找出「键名敏感」的那些位置参数下标。

    ``logger.warning("auth.login.failed username=%s ip=%s", name, ip)``
    → msg 里两个占位符都跟在敏感键后 → 返回 {0, 1}。

    实现说明：按出现顺序编号（Python 的隐式编号规则），
    遇到 ``%1$s`` 这类显式编号则不做隐式推进 —— 覆盖不到的情况宁可漏，
    也不能错位脱敏（那会把无关字段打码，反而掩盖真实信息）。
    """
    if not msg or "%" not in msg:
        return set()
    # 占位符结束位置 -> 参数下标（Python 隐式编号；遇 %1$s 显式编号则不推进隐式计数）
    index_by_end: dict[int, int] = {}
    implicit = 0
    for spec in _FORMAT_SPEC_PATTERN.finditer(msg):
        kind = spec.group(2)
        if kind == "%":  # %% 是转义，不占参数
            continue
        if spec.group(1):
            idx = int(spec.group(1)) - 1
        else:
            idx = implicit
            implicit += 1
        index_by_end[spec.end()] = idx
    # 敏感键模式的匹配以占位符结尾，因此按结束位置配对
    hits: set[int] = set()
    for match in _SENSITIVE_PLACEHOLDER_PATTERN.finditer(msg):
        idx = index_by_end.get(match.end())
        if idx is not None:
            hits.add(idx)
    return hits


class SanitizingFilter(logging.Filter):
    """SEC-P2-007: 日志脱敏 Filter.

    注册到 logging 配置的 filters 中, 自动对每条 LogRecord 的 message
    进行 PII 脱敏. 修改 record.msg (和 args), 不创建新 record.

    使用 dictConfig 注册:

    .. code-block:: python

        "filters": {
            "sanitizer": {
                "()": "app.core.log_sanitizer.SanitizingFilter",
            },
        }
    """

    def filter(self, record: logging.LogRecord) -> bool:
        """对 record 进行脱敏处理.

        Args:
            record: 日志记录.

        Returns:
            总是返回 True (不丢弃任何记录, 仅修改内容).
        """
        try:
            # 1. 脱敏 record.msg (主消息)
            if isinstance(record.msg, str):
                record.msg = sanitize_text(record.msg)

            # 2. 脱敏 record.args (格式化参数, 可能包含 PII)
            if record.args:
                # 2a. 按「敏感键 + 占位符」位置脱敏：logger.info("password=%s", pwd)
                #     的真实值在 args 里，键名模式只作用于 msg，覆盖不到。
                record.args = self._mask_sensitive_args(record.args, record.msg)
                record.args = self._sanitize_args(record.args)

            # 3. 脱敏 exc_info 中的异常消息 (如有)
            # exc_info 是 (type, value, traceback) 元组, 修改 value.args
            if record.exc_info and len(record.exc_info) >= 2:
                exc_value = record.exc_info[1]
                if exc_value and exc_value.args:
                    exc_value.args = tuple(
                        sanitize_text(arg) if isinstance(arg, str) else arg for arg in exc_value.args
                    )
        except Exception:
            # 脱敏失败不应影响日志输出, 原样放行
            # OPT-P3-002：静默放行可能让未脱敏 PII 进入日志且无迹可查，
            # 至少记录 debug 级别便于排查脱敏器自身缺陷
            logger.debug("log sanitizer failed; record passed through unsanitized", exc_info=True)

        return True

    def _mask_sensitive_args(self, args: Any, msg: Any) -> Any:
        """把「跟在敏感键后的位置参数」整体打码（值级脱敏的补充）。"""
        hits = _sensitive_arg_indexes(msg if isinstance(msg, str) else "")
        if not hits:
            return args
        if isinstance(args, tuple):
            return tuple(
                "***MASKED***" if i in hits and not isinstance(v, (dict, list, tuple)) else v
                for i, v in enumerate(args)
            )
        if isinstance(args, list):
            return [
                "***MASKED***" if i in hits and not isinstance(v, (dict, list, tuple)) else v
                for i, v in enumerate(args)
            ]
        if isinstance(args, dict):
            # dict 作为唯一参数时，LogRecord 会解包成 dict —— 按键名判定
            return {
                k: ("***MASKED***" if isinstance(k, str) and _SENSITIVE_KEY_NAME_PATTERN.match(k) else v)
                for k, v in args.items()
            }
        return args

    def _sanitize_args(self, args: Any) -> Any:
        """脱敏 record.args (可能是 dict / tuple / list / 单值).

        AUDIT-2026-10-06 (P2-2)：原实现只处理「容器里的字符串」，
        - 嵌套容器（``{"smtp": {"password": "p@ss"}}``）内层值不被处理；
        - 且纯靠值匹配拦不住 —— ``{"password": "p@ss"}`` 的值本身不含任何特征串。

        现在：容器按键名判定（``_SENSITIVE_KEY_NAME_PATTERN``）+ 递归下降。
        """
        return self._sanitize_value(args, depth=0)

    # 递归深度上限：防御自引用结构（list 套自己）导致无限递归
    _MAX_DEPTH = 6

    def _sanitize_value(self, value: Any, depth: int) -> Any:
        if depth > self._MAX_DEPTH:
            return value
        if isinstance(value, str):
            return sanitize_text(value)
        if isinstance(value, dict):
            out: dict[Any, Any] = {}
            for k, v in value.items():
                # 键名本身敏感 -> 整个值打码（不依赖值是否含特征串）
                if isinstance(k, str) and _SENSITIVE_KEY_NAME_PATTERN.match(k):
                    out[k] = "***MASKED***"
                else:
                    out[k] = self._sanitize_value(v, depth + 1)
            return out
        if isinstance(value, tuple):
            return tuple(self._sanitize_value(v, depth + 1) for v in value)
        if isinstance(value, list):
            return [self._sanitize_value(v, depth + 1) for v in value]
        return value


__all__ = [
    "SanitizingFilter",
    "sanitize_text",
]
