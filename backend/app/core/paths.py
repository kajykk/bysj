"""存储路径策略（uploads 目录解析 + 公共目录白名单）.

ARCH-FIX-2026-10-05: 从 app/api/v1/uploads.py 下沉。

下沉原因:
    原先 PUBLIC_DIRS / _resolve_upload_dir 定义在 HTTP 层，导致
    app/tasks/scheduler.py 的定时清理任务必须反向 import api 层
    （tasks → api 的跨层反向依赖）。后果:
      - Celery worker 的导入链依赖 api/v1/uploads.py 及其 FastAPI router
        构造，worker 内任何 FastAPI 初始化异常都会让清理任务无法启动；
      - 改上传目录解析逻辑（例如加环境变量前缀、换成对象存储前缀）必须
        同时改 HTTP 层。

    这两个符号本质是**文件系统安全策略**（哪些目录可公开访问、上传根目录
    在哪），属于存储层职责，不该由 HTTP 层持有。

依赖方向: 本模块只依赖 pathlib 与 os, 不依赖任何 app 模块, 因此无循环风险。
"""

from __future__ import annotations

import os
from pathlib import Path

# 公共资源白名单目录（owner 段命中即视为公共资源，可免鉴权访问）
PUBLIC_DIRS: frozenset[str] = frozenset({"audio", "content"})


def resolve_upload_dir() -> Path:
    """获取 uploads 目录绝对路径。

    优先读环境变量 ``UPLOAD_DIR``，缺省回落到仓库布局推导出的
    ``backend/uploads/``（与 main.py 的 upload_dir 定义保持一致）。
    """
    env_dir = os.environ.get("UPLOAD_DIR")
    if env_dir:
        return Path(env_dir).resolve()
    # app/core/paths.py -> backend/uploads/
    return Path(__file__).resolve().parent.parent.parent / "uploads"


def is_public_dir(name: str) -> bool:
    """判断目录名是否命中公共资源白名单。"""
    return name in PUBLIC_DIRS


__all__ = ["PUBLIC_DIRS", "is_public_dir", "resolve_upload_dir"]
