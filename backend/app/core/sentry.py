"""Sentry integration for error tracking."""

from __future__ import annotations

import logging
import os
from typing import Any

logger = logging.getLogger(__name__)


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
        traces_sample_rate: Percentage of transactions to trace.
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
        traces_sample_rate=traces_sample_rate,
        profiles_sample_rate=profiles_sample_rate,
        send_default_pii=False,
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
        "Sentry SDK initialized (env=%s, traces=%s)", environment, traces_sample_rate
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
