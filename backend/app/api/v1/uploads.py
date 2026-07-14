"""SEC-P0-001 修复：/uploads/* 鉴权路由

替代原先的 ``app.mount("/uploads", StaticFiles(...))`` 直接挂载。
原实现任何未登录用户均可访问 ``/uploads/{user_id}/{filename}``，
泄露用户头像、音频、PDF 报告等敏感数据。

本模块用单一路由 ``GET /uploads/{owner}/{filename:path}`` 智能分发：
- ``owner`` 为纯数字 → 用户私有文件，需 JWT 鉴权 + 归属校验
- ``owner`` 在 ``PUBLIC_DIRS`` 白名单 (audio/content) → 公共资源，无需鉴权
- 其他 → 404 (不暴露存在性)

兼容性：保留旧路径 ``/uploads/audio/mindfulness_10min.mp3`` 作为公共资源，
避免破坏已发布到数据库的 ``EducationContent.audio_url`` 记录。

注意：``<audio src="...">`` / ``<img src="...">`` 等浏览器原生标签
无法携带 Authorization header，因此私有文件路由额外支持 ``?token=`` query 参数。
这是 access token 的合法用途，但会出现在 nginx access log 中，
生产环境应配合 HTTPS 与日志脱敏 (SEC-P2-007) 使用。
"""

from __future__ import annotations

import json
import logging
import re
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from fastapi import Path as FastPath
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, oauth2_scheme
from app.core.rate_limit import get_real_client_ip
from app.models.admin import OperationLog
from app.models.user import User

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/uploads", tags=["uploads"], include_in_schema=False)

# 公共资源白名单目录（owner 段命中即视为公共资源）
PUBLIC_DIRS: frozenset[str] = frozenset({"audio", "content"})

# 安全的文件名模式：禁止路径分隔符、null 字节、点号开头的隐藏文件
# 允许 UUID.ext / uuid.ext / name-1.ext 等常见格式
_SAFE_FILENAME_RE = re.compile(r"^[A-Za-z0-9_\-]+\.[A-Za-z0-9]{1,8}$")

# 安全的 user_id 模式：纯数字
_SAFE_USERID_RE = re.compile(r"^\d+$")


def _resolve_upload_dir() -> Path:
    """获取 uploads 目录绝对路径。

    与 main.py 中的 upload_dir 定义保持一致：
    ``Path(__file__).resolve().parent.parent.parent / "uploads"``
    即 backend/uploads/。
    """
    # app/api/v1/uploads.py -> backend/uploads/
    return Path(__file__).resolve().parent.parent.parent / "uploads"


def _safe_join(base: Path, *parts: str) -> Path:
    """安全地拼接路径并校验仍在 base 内，防止路径遍历。

    - 拒绝 null 字节、``..`` 路径段、绝对路径
    - 解析后必须位于 base 之内
    """
    base_resolved = base.resolve()
    for part in parts:
        if "\x00" in part:
            raise HTTPException(status_code=400, detail="非法的文件路径")
        # 拒绝 .. 路径段
        for segment in part.replace("\\", "/").split("/"):
            if segment == "..":
                raise HTTPException(status_code=400, detail="非法的文件路径")
    candidate = base.joinpath(*parts).resolve()
    if candidate != base_resolved and base_resolved not in candidate.parents:
        raise HTTPException(status_code=400, detail="非法的文件路径")
    return candidate


async def _optional_resolve_user(
    request: Request,
    token: Annotated[str | None, Depends(oauth2_scheme)] = None,
    query_token: Annotated[
        str | None,
        Query(alias="token", description="备用：浏览器原生标签无法带 header 时使用"),
    ] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
) -> User | None:
    """可选鉴权：返回 User 或 None，不抛 401。

    用于 ``serve_upload`` 统一路由——公共资源路径不需要 user，
    私有文件路径在函数体内手动检查 ``user is None`` → 401。

    支持两种 token 传入方式：
    1. Authorization: Bearer <token> (标准方式)
    2. ?token=<token> (浏览器原生标签 fallback)

    如果 token 无效或过期，返回 None（让调用方决定如何处理）。

    实现细节：优先检查 ``app.dependency_overrides[get_current_user]`` (测试用),
    否则调用真实 ``get_current_user`` (生产用), 与 deps._resolve_current_user 一致.

    治理循环依赖: 原实现 ``from app.main import app`` 会形成
    ``api.v1.uploads -> main -> api.v1.uploads`` 启动期循环依赖 (已用 lazy import
    缓解为运行期循环). 改用 ``request.app`` 拿当前 FastAPI 实例 —— FastAPI 在
    路由分发时自动注入 ``request.app``, 语义等价且彻底消除对 app.main 的导入依赖.
    """
    effective_token = token or query_token
    if not effective_token:
        return None

    # 优先走 dependency_overrides (测试 fixture 会注入 mock)
    override = request.app.dependency_overrides.get(get_current_user)
    try:
        if override is not None:
            import inspect

            result = override(request=request, token=effective_token, db=db)
            if inspect.isawaitable(result):
                return await result
            return result
        return await get_current_user(request=request, token=effective_token, db=db)
    except HTTPException:
        # 鉴权失败不在此处抛出，由调用方根据场景决定
        return None


@router.get(
    "/{owner}/{filename:path}",
    responses={
        200: {"description": "文件内容"},
        400: {"description": "非法路径"},
        401: {"description": "未认证"},
        403: {"description": "无权访问他人文件"},
        404: {"description": "文件不存在"},
    },
)
async def serve_upload(
    request: Request,
    owner: Annotated[
        str, FastPath(description="用户 ID（数字）或公共目录名（audio/content）")
    ],
    filename: Annotated[str, FastPath(description="文件相对路径")],
    current_user: Annotated[User | None, Depends(_optional_resolve_user)] = None,
    db: Annotated[AsyncSession, Depends(get_db)] = None,
) -> FileResponse:
    """统一处理 /uploads/* 请求，根据 owner 类型分发。

    **公共资源** (owner in ``PUBLIC_DIRS``，如 ``audio``/``content``)：
    - 无需鉴权（教育内容音频等）
    - filename 可包含子路径，如 ``mindfulness_10min.mp3``

    **用户私有文件** (owner 为纯数字)：
    - 必须鉴权 (Authorization header 或 ``?token=`` query 参数)
    - ``user`` 角色：只能访问 ``owner == current_user.id`` 的文件
    - ``counselor``/``admin`` 角色：可访问任意用户文件
    - filename 必须匹配 ``^[A-Za-z0-9_\\-]+\\.[A-Za-z0-9]{1,8}$`` (UUID.ext)
    """
    if not owner or not filename:
        raise HTTPException(status_code=404, detail="文件不存在")

    base = _resolve_upload_dir()

    # 分支 1：公共资源
    if owner in PUBLIC_DIRS:
        # filename 允许含子路径（如 audio/sub/file.mp3），但 owner 已固定
        # 拼接路径：uploads/audio/<filename>
        try:
            full_path = _safe_join(base, owner, filename)
        except HTTPException:
            raise
        except Exception as exc:
            logger.warning(
                "public_upload.path_resolve.failed owner=%s filename=%s err=%s",
                owner,
                filename,
                exc,
            )
            raise HTTPException(status_code=400, detail="非法的文件路径") from exc

        if not full_path.is_file():
            raise HTTPException(status_code=404, detail="文件不存在")
        return FileResponse(str(full_path))

    # 分支 2：用户私有文件
    if not _SAFE_USERID_RE.match(owner):
        # owner 既不在公共白名单，也不是数字 → 404 (不暴露存在性)
        raise HTTPException(status_code=404, detail="文件不存在")

    user_id = int(owner)

    # 鉴权：私有文件必须登录，current_user 为 None 表示未提供/无效 token
    if current_user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="未提供认证Token",
        )

    # 归属校验
    if current_user.role == "user" and current_user.id != user_id:
        # 不暴露存在性，统一返回 404
        raise HTTPException(status_code=404, detail="文件不存在")
    if current_user.role not in ("user", "counselor", "admin"):
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="权限不足")

    # filename 安全校验：私有文件的 filename 必须是单段 UUID.ext
    # 取最后一段（防止用户传入 a/b/c.jpg）
    filename_last = filename.rsplit("/", 1)[-1]
    if not _SAFE_FILENAME_RE.match(filename_last):
        raise HTTPException(status_code=400, detail="非法的文件名")

    try:
        full_path = _safe_join(base, str(user_id), filename_last)
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning(
            "private_upload.path_resolve.failed user_id=%s filename=%s err=%s",
            user_id,
            filename,
            exc,
        )
        raise HTTPException(status_code=400, detail="非法的文件路径") from exc

    if not full_path.is_file():
        raise HTTPException(status_code=404, detail="文件不存在")

    # 二次校验：确保解析后的路径在 uploads/{user_id}/ 下
    expected_dir = (base / str(user_id)).resolve()
    if expected_dir not in full_path.parents:
        raise HTTPException(status_code=400, detail="非法的文件路径")

    # SEC-P1-004 修复：记录私有文件下载审计日志（公共资源不记录）
    db.add(
        OperationLog(
            operator_id=current_user.id,
            operator_role=current_user.role,
            action_type="user_file_download",
            target_type="user_upload",
            target_id=user_id,
            detail=json.dumps(
                {
                    "owner": owner,
                    "filename": filename_last,
                    "accessor_role": current_user.role,
                    "self_access": current_user.id == user_id,
                },
                ensure_ascii=False,
            ),
            ip_address=get_real_client_ip(request),
        )
    )
    await db.commit()

    return FileResponse(str(full_path))


__all__ = ["router", "PUBLIC_DIRS"]
