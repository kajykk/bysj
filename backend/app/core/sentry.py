"""Sentry integration for error tracking."""

from __future__ import annotations

import logging
import os
import random
from typing import Any, Callable, Optional

logger = logging.getLogger(__name__)


def _extract_status_code(event: dict) -> Optional[int]:
    """从 Sentry transaction event 中提取 HTTP response status code.

    Sentry SDK 在 transaction event 的不同位置记录 status code:
    - event["request"]["response_status_code"] (FastApiIntegration)
    - event["tags"]["http.status_code"] (部分集成)
    - event["contexts"]["trace"]["tags"]["http.response.status_code"]
    """
    # 路径 1: event["request"]["response_status_code"]
    request = event.get("request") or {}
    code = request.get("response_status_code")
    if code is not None:
        try:
            return int(code)
        except (ValueError, TypeError):
            pass

    # 路径 2: event["tags"]["http.status_code"]
    tags = event.get("tags") or {}
    code = tags.get("http.status_code")
    if code is not None:
        try:
            return int(code)
        except (ValueError, TypeError):
            pass

    # 路径 3: event["contexts"]["trace"]["tags"]
    contexts = event.get("contexts") or {}
    trace_ctx = contexts.get("trace") or {}
    trace_tags = trace_ctx.get("tags") or {}
    code = trace_tags.get("http.response.status_code")
    if code is not None:
        try:
            return int(code)
        except (ValueError, TypeError):
            pass

    return None


def _make_before_send_transaction(
    base_sample_rate: float,
) -> Callable[[dict, dict], Optional[dict]]:
    """创建 before_send_transaction 回调.

    STAB-P2-010: 5xx 事务 100% 保留, 其他事务按 base_sample_rate 随机采样.

    实现: traces_sample_rate 设为 1.0 (所有事务都创建 event),
    before_send_transaction 在上报前过滤 — 5xx 保留, 其他按概率丢弃.
    """

    def _before_send_transaction(event: dict, hint: dict) -> Optional[dict]:
        status_code = _extract_status_code(event)
        if status_code is not None and 500 <= status_code < 600:
            return event  # 5xx 100% 保留

        # 非 5xx 事务按 base_sample_rate 随机采样
        if random.random() < base_sample_rate:
            return event
        return None

    return _before_send_transaction


def init_sentry(
    dsn: str | None = None,
    environment: str = "development",
    release: str | None = None,
    traces_sample_rate: float = 0.1,
    profiles_sample_rate: float = 0.1,
) -> None:
    """Initialize Sentry SDK.

    Args:
        dsn: Sentry DSN. If None, uses SENTRY_DSN env var.
        environment: Deployment environment.
        release: Release version.
        traces_sample_rate: Percentage of non-5xx transactions to trace (0.0~1.0).
            5xx transactions are always 100% sampled (STAB-P2-010).
        profiles_sample_rate: Percentage of transactions to profile.
    """
    dsn = dsn or os.getenv("SENTRY_DSN")
    if not dsn:
        logger.warning("SENTRY_DSN not set, skipping Sentry initialization")
        return

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
        from sentry_sdk.integrations.sqlalchemy import SqlalchemyIntegration
    except Exception:
        logger.warning("sentry_sdk not available, skipping Sentry initialization")
        return

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release,
        # STAB-P2-010: traces_sample_rate=1.0 让所有事务都创建 event,
        # 由 before_send_transaction 过滤 (5xx 100% 保留, 其他按 traces_sample_rate 采样)
        traces_sample_rate=1.0,
        profiles_sample_rate=profiles_sample_rate,
        send_default_pii=False,
        before_send_transaction=_make_before_send_transaction(traces_sample_rate),
        integrations=[
            FastApiIntegration(
                transaction_style="endpoint",
                # M-Core-13 修复：range(500, 599) 遗漏 599，改为 range(500, 600) 覆盖全部 5xx
                failed_request_status_codes={403, *range(500, 600)},
            ),
            SqlalchemyIntegration(),
        ],
    )
    logger.info(
        "Sentry SDK initialized (env=%s, non-5xx traces=%s, 5xx traces=1.0)",
        environment,
        traces_sample_rate,
    )


def capture_exception(error: Exception, **context: Any) -> None:
    """Capture an exception with optional context.

    Args:
        error: The exception to capture.
        **context: Additional context data.
    """
    try:
        import sentry_sdk

        # v1.32: 使用新 API (configure_scope 已弃用), 直接通过 sentry_sdk.scope
        with sentry_sdk.new_scope() as scope:
            for key, value in context.items():
                scope.set_extra(key, value)
            sentry_sdk.capture_exception(error)
    except Exception:
        logger.warning("sentry_sdk not available, exception not captured")


def capture_message(message: str, level: str = "info") -> None:
    """Capture a message.

    Args:
        message: The message to capture.
        level: Log level (debug, info, warning, error, fatal).
    """
    try:
        import sentry_sdk

        sentry_sdk.capture_message(message, level=level)
    except Exception:
        logger.warning("sentry_sdk not available, message not captured")
