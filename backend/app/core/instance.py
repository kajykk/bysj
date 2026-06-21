"""v1.36: 实例标识工具.

提供当前进程的唯一标识 (hostname-pid),
用于多实例部署时的可观测性区分.
"""
from __future__ import annotations

import os
import socket


def get_instance_id() -> str:
    """v1.36: 获取当前实例唯一标识.

    Returns:
        形如 "backend-pod-abc-12345" (hostname-pid)
        异常时降级为 "unknown-<pid>"
    """
    try:
        hostname = socket.gethostname()
    except Exception:
        hostname = "unknown"
    if not hostname:
        hostname = "unknown"
    return f"{hostname}-{os.getpid()}"
