"""RES-P0-002 修复：统一的日志轮转配置

原问题：``app/core/`` 中无任何日志配置，所有日志通过 uvicorn 默认输出到
stdout/stderr。虽然 stdout 本身不会写满磁盘，但生产环境若通过 ``> app.log``
或 systemd ``StandardOutput=file`` 重定向，长跑进程的日志文件将无限增长。

本模块使用 ``logging.config.dictConfig`` 配置：

- **RotatingFileHandler**：按大小轮转
  - ``app.log`` (INFO+) — 应用主日志
  - ``error.log`` (ERROR+) — 错误日志独立文件，便于告警排查
  - 单文件超过 ``log_max_bytes`` (默认 10MB) 后轮转，保留 ``log_backup_count`` 份
- **StreamHandler**：控制台输出 (可关闭，测试环境推荐关闭以减少噪音)
- **格式**：``时间 | 级别 | logger | [request_id] | 消息``

logger 分级与 propagate 配置：

- ``app`` — 应用代码根 logger (propagate=False，避免 root 重复打印)
- ``uvicorn`` / ``uvicorn.access`` — ASGI 服务器日志
- ``sqlalchemy.engine`` — ORM (WARN 级别，避免 SQL 噪音)
- ``celery`` — 任务队列
- ``app.metrics`` — 观测指标 (INFO 级别)

幂等性：``configure_logging()`` 可安全多次调用，重复调用会清除已有 handler
后重新配置，避免测试中 handler 累积。

使用方式：

.. code-block:: python

    from app.core.logging_config import configure_logging
    configure_logging()  # 在 main.py lifespan 启动时调用
"""

from __future__ import annotations

import logging
import logging.config
import logging.handlers
from pathlib import Path
from typing import Any

from app.core import config as _config
from app.core.config import BACKEND_DIR

# 标记是否已配置过，避免测试中重复配置
_CONFIGURED: bool = False


def get_log_dir() -> Path:
    """获取日志目录绝对路径。

    ``settings.log_dir`` 可以是绝对路径或相对路径（相对于 BACKEND_DIR）。

    注意: 通过 ``_config.settings`` 动态访问, 而非模块级 ``settings`` 绑定,
    确保 ``patch("app.core.config.settings", ...)`` 和
    ``patch.object(settings, "log_dir", ...)`` 均能生效。
    """
    _settings = _config.settings
    log_dir = Path(_settings.log_dir)
    if not log_dir.is_absolute():
        log_dir = BACKEND_DIR / log_dir
    return log_dir.resolve()


def _build_log_format() -> str:
    """构建日志格式字符串。

    ISS-100 修复：添加 request_id / trace_id / span_id 占位符，由
    ``app.core.tracing.TraceLogFilter`` 通过 ContextVar 注入。
    若 Filter 未注册或 ContextVar 未设置，则显示 ``-``。
    """
    return (
        "%(asctime)s | %(levelname)-8s | %(name)s | "
        "req_id=%(request_id)s trace_id=%(trace_id)s span_id=%(span_id)s | "
        "%(message)s"
    )


def _build_dict_config(
    log_dir: Path,
    enable_file: bool,
    enable_console: bool,
) -> dict[str, Any]:
    """构建 dictConfig 配置字典。

    参数：
        log_dir: 日志目录绝对路径（调用方确保已创建）
        enable_file: 是否启用 RotatingFileHandler
        enable_console: 是否启用 StreamHandler
    """
    _settings = _config.settings
    level = getattr(logging, _settings.log_level.upper(), logging.INFO)
    max_bytes = max(1024, int(_settings.log_max_bytes))  # 至少 1KB
    backup_count = max(1, int(_settings.log_backup_count))  # 至少 1 份

    handlers: dict[str, Any] = {}
    root_handlers: list[str] = []

    if enable_console:
        handlers["console"] = {
            "class": "logging.StreamHandler",
            "level": level,
            "formatter": "standard",
            # ISS-100: trace filter 注入 request_id/trace_id
            # SEC-P2-007: sanitizer filter 集中化脱敏 PII
            "filters": ["trace", "sanitizer"],
            "stream": "ext://sys.stderr",
        }
        root_handlers.append("console")

    if enable_file:
        handlers["app_file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "level": level,
            "formatter": "standard",
            "filters": ["trace", "sanitizer"],  # ISS-100 + SEC-P2-007
            "filename": str(log_dir / "app.log"),
            "maxBytes": max_bytes,
            "backupCount": backup_count,
            "encoding": "utf-8",
        }
        handlers["error_file"] = {
            "class": "logging.handlers.RotatingFileHandler",
            "level": logging.ERROR,
            "formatter": "standard",
            "filters": ["trace", "sanitizer"],  # ISS-100 + SEC-P2-007
            "filename": str(log_dir / "error.log"),
            "maxBytes": max_bytes,
            "backupCount": backup_count,
            "encoding": "utf-8",
        }
        root_handlers.extend(["app_file", "error_file"])

    # 如果没有任何 handler（极少见，例如测试环境全关），至少保留一个 NullHandler
    if not root_handlers:
        handlers["null"] = {
            "class": "logging.NullHandler",
        }
        root_handlers.append("null")

    return {
        "version": 1,
        "disable_existing_loggers": False,
        # ISS-100 修复：注册 TraceLogFilter，自动注入 request_id/trace_id/span_id
        # 到每条日志记录，使 format 串中的 %(request_id)s 等占位符可生效。
        # SEC-P2-007: 注册 SanitizingFilter, 集中化脱敏 PII (password/token/email/手机号等)
        "filters": {
            "trace": {
                "()": "app.core.tracing.TraceLogFilter",
            },
            "sanitizer": {
                "()": "app.core.log_sanitizer.SanitizingFilter",
            },
        },
        "formatters": {
            "standard": {
                "format": _build_log_format(),
                "datefmt": "%Y-%m-%d %H:%M:%S",
            },
        },
        "handlers": handlers,
        "loggers": {
            # 应用代码根 logger
            "app": {
                "level": level,
                "handlers": root_handlers,
                "propagate": False,
            },
            # ASGI 服务器
            "uvicorn": {
                "level": "INFO",
                "handlers": root_handlers,
                "propagate": False,
            },
            "uvicorn.access": {
                "level": "INFO",
                "handlers": root_handlers,
                "propagate": False,
            },
            "uvicorn.error": {
                "level": "INFO",
                "handlers": root_handlers,
                "propagate": False,
            },
            # SQLAlchemy ORM（避免 SQL 噪音）
            "sqlalchemy": {
                "level": "WARNING",
                "handlers": root_handlers,
                "propagate": False,
            },
            "sqlalchemy.engine": {
                "level": "WARNING",
                "handlers": root_handlers,
                "propagate": False,
            },
            # Celery 任务队列
            "celery": {
                "level": "INFO",
                "handlers": root_handlers,
                "propagate": False,
            },
        },
        "root": {
            "level": level,
            "handlers": root_handlers,
        },
    }


def configure_logging(force: bool = False) -> None:
    """应用日志配置（幂等）。

    参数：
        force: 强制重新配置（即使已配置过）。测试中可用来切换配置。

    注意：
        - 重复调用会清除已有 handler 后重新配置，避免 handler 累积
        - ``disable_existing_loggers=False`` 确保不影响其他模块已创建的 logger
        - 测试环境可通过 ``LOG_TO_FILE=false`` + ``LOG_CONSOLE=false`` 完全禁用
    """
    global _CONFIGURED
    if _CONFIGURED and not force:
        return

    _settings = _config.settings
    enable_file = bool(_settings.log_to_file)
    enable_console = bool(_settings.log_console)

    # 创建日志目录（仅在启用文件日志时）
    if enable_file:
        try:
            log_dir = get_log_dir()
            log_dir.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            # 日志目录创建失败不应阻止启动，降级为仅控制台输出
            # ISS-100 注意：basicConfig 不会注册 TraceLogFilter，故 format 中
            # 的 %(request_id)s 等占位符会触发 KeyError。这里使用简化格式。
            logging.basicConfig(
                level=logging.WARNING,
                format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
            )
            logging.warning(
                "logging.dir.create.failed path=%s err=%s - 降级为仅控制台输出",
                _settings.log_dir,
                exc,
            )
            enable_file = False
            log_dir = Path(".")
        else:
            log_dir = get_log_dir()
    else:
        log_dir = get_log_dir()

    config_dict = _build_dict_config(
        log_dir=log_dir,
        enable_file=enable_file,
        enable_console=enable_console,
    )
    logging.config.dictConfig(config_dict)
    _CONFIGURED = True

    # 配置完成后记录一条启动日志（仅在实际启用文件日志时）
    if enable_file:
        logger = logging.getLogger("app.core.logging_config")
        logger.info(
            "logging.configured dir=%s level=%s max_bytes=%d backup_count=%d file=True console=%s",
            log_dir,
            _settings.log_level,
            _settings.log_max_bytes,
            _settings.log_backup_count,
            enable_console,
        )


def reset_logging_state() -> None:
    """重置配置状态（仅供测试使用）。

    清除 ``_CONFIGURED`` 标记，使下一次 ``configure_logging()`` 调用重新配置。
    不会清除已有 handler（由 dictConfig 的 ``disable_existing_loggers=False`` 处理）。
    """
    global _CONFIGURED
    _CONFIGURED = False


__all__ = [
    "configure_logging",
    "get_log_dir",
    "reset_logging_state",
]
