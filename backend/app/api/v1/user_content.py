from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_role
from app.core.response import ok
from app.models.user import User
from app.schemas.content import MeditationLogRequest
from app.services.content_service import ContentService

router = APIRouter(prefix="/user/content", tags=["user-content"])


@router.get("/")
async def list_contents(
    current_user: Annotated[User, Depends(require_role("user"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    category: str | None = Query(default=None),
    content_type: str | None = Query(default=None),
    keyword: str | None = Query(default=None),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    service = ContentService(db)
    data = await service.list_contents(current_user.id, category, content_type, keyword, page, page_size)
    return ok(data)


@router.get("/favorites/list")
async def list_favorites(
    current_user: Annotated[User, Depends(require_role("user"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    service = ContentService(db)
    data = await service.list_favorites(current_user.id, page, page_size)
    return ok(data)


@router.get("/recommendations")
async def list_recommendations(
    current_user: Annotated[User, Depends(require_role("user"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    service = ContentService(db)
    data = await service.get_recommendations(current_user.id, page, page_size)
    return ok(data)


@router.get("/recent-views")
async def list_recent_views(
    current_user: Annotated[User, Depends(require_role("user"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    service = ContentService(db)
    data = await service.list_recent_views(current_user.id, page, page_size)
    return ok(data)


@router.post("/meditation/log")
async def meditation_log(
    payload: MeditationLogRequest,
    current_user: Annotated[User, Depends(require_role("user"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = ContentService(db)
    log_id = await service.log_meditation(current_user.id, payload.content_id, payload.completed)
    if log_id == 0:
        raise HTTPException(status_code=404, detail="内容不存在")
    return ok({"log_id": log_id})


@router.get("/{content_id}")
async def get_content_detail(
    content_id: int,
    current_user: Annotated[User, Depends(require_role("user"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = ContentService(db)
    data = await service.get_content_detail(current_user.id, content_id)
    if data is None:
        raise HTTPException(status_code=404, detail="内容不存在")
    return ok(data)


@router.post("/{content_id}/favorite")
async def toggle_favorite(
    content_id: int,
    current_user: Annotated[User, Depends(require_role("user"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = ContentService(db)
    success = await service.toggle_favorite(current_user.id, content_id)
    if not success:
        raise HTTPException(status_code=404, detail="内容不存在")
    return ok({"message": "收藏状态已切换"})