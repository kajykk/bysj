"""兼容层: 告警可观测性 query 函数已下沉至 services 层.

ARCH-FIX-2026-10-05: 详见同目录 aggregate.py 的说明（含为何用模块级
__getattr__ 转发而非手写 re-export 清单）。

本模块同时转发 aggregate 的符号，因为原 query.py 的使用者可能按
`from app.api.v1.observability.query import _compute_channel_stats` 取值。
"""

from __future__ import annotations

from typing import Any

from app.services.observability.aggregate import (  # noqa: F401
    _compute_am_sync,
    _compute_channel_stats,
    _compute_lock_stats,
    _compute_silence_hit_rate,
)
from app.services.observability.query import (  # noqa: F401
    _compute_escalation,
    _compute_response_time,
    _compute_trend,
    _percentile,
)

_IMPL_MODULE = "app.services.observability.query"


def __getattr__(name: str) -> Any:
    """PEP 562: 把本模块未定义的属性转发到 services 层 query 实现."""
    if name.startswith("__"):
        raise AttributeError(name)
    import importlib

    return getattr(importlib.import_module(_IMPL_MODULE), name)


__all__ = [
    "_compute_am_sync",
    "_compute_channel_stats",
    "_compute_lock_stats",
    "_compute_silence_hit_rate",
    "_compute_escalation",
    "_compute_response_time",
    "_compute_trend",
    "_percentile",
]
