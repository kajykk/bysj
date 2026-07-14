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

# SEC-P2-007: 敏感键模式 (与 celery_app._SENSITIVE_KEYS 对齐, 扩展常见变体)
# 匹配 key=value / key: value 格式 (无引号)
_SENSITIVE_KEY_PATTERN = re.compile(
    r"(?i)\b("
    r"password|passwd|pwd|"
    r"token|access_token|refresh_token|id_token|"
    r"secret|client_secret|api_secret|"
    r"api_key|apikey|api-key|"
    r"authorization|auth|"
    r"jwt|bearer|"
    r"credit_card|credit_card_number|card_number|cvv|cvc|"
    r"ssn|id_card|id_number|"
    r"private_key|privatekey"
    r")\b\s*[:=]\s*['\"]?([^\s'\",}{\]]+)",
    re.IGNORECASE,
)

# JSON 格式 "key":"value" / "key": "value"
_SENSITIVE_KEY_JSON_PATTERN = re.compile(
    r"(?i)\"("
    r"password|passwd|pwd|"
    r"token|access_token|refresh_token|id_token|"
    r"secret|client_secret|api_secret|"
    r"api_key|apikey|api-key|"
    r"authorization|auth|"
    r"jwt|bearer|"
    r"credit_card|credit_card_number|card_number|cvv|cvc|"
    r"ssn|id_card|id_number|"
    r"private_key|privatekey"
    r")\"\s*:\s*\"([^\"]+)\"",
    re.IGNORECASE,
)

# Bearer Token (Authorization header) - 必须先于 key=value 处理
_BEARER_PATTERN = re.compile(
    r"(?i)\b(Bearer)\s+([A-Za-z0-9\-_\.=]+)", re.IGNORECASE
)

# JWT Token (三段式 base64.base64.signature)
_JWT_PATTERN = re.compile(
    r"eyJ[A-Za-z0-9\-_]+\.eyJ[A-Za-z0-9\-_]+\.[A-Za-z0-9\-_]+"
)

# Email (保留域名便于排查)
_EMAIL_PATTERN = re.compile(r"\b([A-Za-z0-9._%+\-])([A-Za-z0-9._%+\-]+)@([A-Za-z0-9.\-]+\.[A-Za-z]{2,})\b")

# 中国手机号 (11 位, 1[3-9] 开头)
_PHONE_PATTERN = re.compile(r"(?<!\d)(1[3-9]\d)(\d{4})(\d{4})(?!\d)")

# 身份证号 (18 位, 末位可能为 X)
_ID_CARD_PATTERN = re.compile(r"(?<!\d)(\d{6})(\d{8})(\d{3})([\dXx])(?!\d)")

# 信用卡号 (16 位连续或 4-4-4-4 分组)
_CARD_PATTERN = re.compile(
    r"(?<!\d)(\d{4})(\d{4})(\d{4})(\d{4})(?!\d)|"
    r"(?<!\d)(\d{4})[\s\-](\d{4})[\s\-](\d{4})[\s\-](\d{4})(?!\d)"
)

# API Key 常见前缀 (OpenAI sk-/Stripe sk_/pk_/GitHub ghp_/gho_/ghu_/ghs_/ghr_)
_APIKEY_PATTERN = re.compile(
    r"\b(sk-[A-Za-z0-9]{20,}|pk_[A-Za-z0-9]{20,}|gh[pousr]_[A-Za-z0-9]{20,})"
)


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
    result = _BEARER_PATTERN.sub(
        lambda m: f"{m.group(1)} ***MASKED***", result
    )

    # 4. JSON 格式敏感键值对 ("key":"value")
    result = _SENSITIVE_KEY_JSON_PATTERN.sub(
        lambda m: f'"{m.group(1)}":"***MASKED***"', result
    )

    # 5. 普通敏感键值对 (key=value / key: value)
    result = _SENSITIVE_KEY_PATTERN.sub(
        lambda m: f"{m.group(1)}=***MASKED***", result
    )

    # 6. Email (保留首位字符 + 域名, 便于排查)
    result = _EMAIL_PATTERN.sub(
        lambda m: f"{m.group(1)}***@{m.group(3)}", result
    )

    # 7. 手机号 (保留前 3 + 后 4)
    result = _PHONE_PATTERN.sub(
        lambda m: f"{m.group(1)}****{m.group(3)}", result
    )

    # 8. 身份证号 (保留前 6 + 后 4, 中间 8 位生日用 * 替换)
    result = _ID_CARD_PATTERN.sub(
        lambda m: f"{m.group(1)}********{m.group(3)}{m.group(4)}", result
    )

    # 9. 信用卡号 (保留前 6 + 后 4, 中间 6 位 * 替换)
    def _mask_card(m: re.Match) -> str:
        if m.group(1):  # 16 位连续
            return f"{m.group(1)}******{m.group(4)}"
        # 4-4-4-4 分组
        return f"{m.group(5)} **** **** {m.group(8)}"

    result = _CARD_PATTERN.sub(_mask_card, result)

    return result


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
                record.args = self._sanitize_args(record.args)

            # 3. 脱敏 exc_info 中的异常消息 (如有)
            # exc_info 是 (type, value, traceback) 元组, 修改 value.args
            if record.exc_info and len(record.exc_info) >= 2:
                exc_value = record.exc_info[1]
                if exc_value and exc_value.args:
                    exc_value.args = tuple(
                        sanitize_text(arg) if isinstance(arg, str) else arg
                        for arg in exc_value.args
                    )
        except Exception:
            # 脱敏失败不应影响日志输出, 原样放行
            pass

        return True

    def _sanitize_args(self, args: Any) -> Any:
        """脱敏 record.args (可能是 tuple/dict/单值)."""
        if isinstance(args, dict):
            return {
                k: (sanitize_text(v) if isinstance(v, str) else v)
                for k, v in args.items()
            }
        if isinstance(args, (tuple, list)):
            sanitized = [
                sanitize_text(arg) if isinstance(arg, str) else arg
                for arg in args
            ]
            return tuple(sanitized) if isinstance(args, tuple) else sanitized
        if isinstance(args, str):
            return sanitize_text(args)
        return args


__all__ = [
    "SanitizingFilter",
    "sanitize_text",
]
