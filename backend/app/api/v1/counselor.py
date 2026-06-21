from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_role
from app.core.request_id import get_or_create_request_id
from app.core.response import ok
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.counselor import (
    BindCodeRequest,
    ConsultationCreateRequest,
    GroupCreateRequest,
    GroupMemberAddRequest,
    WarningHandleRequest,
)
from app.services.counselor_service import CounselorService

router = APIRouter(prefix="/counselor", tags=["counselor"])


@router.get("/warnings", response_model=ApiResponse)
async def list_warnings(
    current_user: Annotated[User, Depends(require_role("counselor"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    only_unhandled: bool = Query(default=False),
) -> dict:
    service = CounselorService(db)
    data = await service.list_warnings(current_user.id, page, page_size, only_unhandled)
    return ok(data)


@router.put("/warnings/{warning_id}/handle", response_model=ApiResponse)
async def handle_warning(
    warning_id: int,
    payload: WarningHandleRequest,
    request: Request,
    current_user: Annotated[User, Depends(require_role("counselor"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = CounselorService(db)
    request_id = get_or_create_request_id(request)
    success = await service.handle_warning(
        current_user.id,
        warning_id,
        payload.action,
        payload.note,
        ip_address=request.client.host if request.client else None,
        request_id=request_id,
    )
    if not success:
        raise HTTPException(status_code=404, detail="预警不存在")
    return ok({"message": "预警已处理"})


@router.get("/users", response_model=ApiResponse)
async def list_users(
    current_user: Annotated[User, Depends(require_role("counselor"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    service = CounselorService(db)
    data = await service.list_my_users(current_user.id, page, page_size)
    return ok(data)


@router.get("/users/{user_id}", response_model=ApiResponse)
async def get_user_detail(
    user_id: int,
    current_user: Annotated[User, Depends(require_role("counselor"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = CounselorService(db)
    data = await service.get_user_detail(current_user.id, user_id)
    if data is None:
        raise HTTPException(status_code=404, detail="用户不存在或未绑定")
    return ok(data)


@router.post("/users/{user_id}/consultations", response_model=ApiResponse)
async def create_consultation_record(
    user_id: int,
    payload: ConsultationCreateRequest,
    current_user: Annotated[User, Depends(require_role("counselor"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    if payload.main_topics is not None and not payload.main_topics.strip():
        raise HTTPException(status_code=422, detail="main_topics 不能为空")
    service = CounselorService(db)
    try:
        record_id = await service.create_consultation_record(current_user.id, user_id, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ok({"record_id": record_id})


@router.get("/users/{user_id}/consultations", response_model=ApiResponse)
async def list_consultation_records(
    user_id: int,
    current_user: Annotated[User, Depends(require_role("counselor"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    service = CounselorService(db)
    data = await service.list_consultation_records(current_user.id, user_id, page, page_size)
    return ok(data)


@router.put("/users/{user_id}/consultations/{record_id}", response_model=ApiResponse)
async def update_consultation_record(
    user_id: int,
    record_id: int,
    payload: ConsultationCreateRequest,
    current_user: Annotated[User, Depends(require_role("counselor"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    if payload.main_topics is not None and not payload.main_topics.strip():
        raise HTTPException(status_code=422, detail="main_topics 不能为空")
    service = CounselorService(db)
    try:
        success = await service.update_consultation_record(current_user.id, user_id, record_id, payload.model_dump())
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not success:
        raise HTTPException(status_code=404, detail="咨询记录不存在")
    return ok({"message": "咨询记录已更新"})


@router.post("/groups", response_model=ApiResponse)
async def create_group(
    payload: GroupCreateRequest,
    current_user: Annotated[User, Depends(require_role("counselor"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = CounselorService(db)
    group_id = await service.create_group(
        current_user.id,
        payload.group_name,
        payload.description,
        payload.color_tag,
    )
    return ok({"group_id": group_id})


@router.get("/groups", response_model=ApiResponse)
async def list_groups(
    current_user: Annotated[User, Depends(require_role("counselor"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    service = CounselorService(db)
    data = await service.list_groups(current_user.id, page, page_size)
    return ok(data)


@router.post("/groups/{group_id}/members", response_model=ApiResponse)
async def add_group_member(
    group_id: int,
    payload: GroupMemberAddRequest,
    current_user: Annotated[User, Depends(require_role("counselor"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = CounselorService(db)
    success = await service.add_group_member(current_user.id, group_id, payload.user_id)
    if not success:
        raise HTTPException(status_code=404, detail="分组不存在")
    return ok({"message": "成员已添加"})


@router.get("/bind-code", response_model=ApiResponse)
async def get_bind_code(
    current_user: Annotated[User, Depends(require_role("counselor"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = CounselorService(db)
    code = await service.get_or_create_bind_code(current_user.id)
    return ok({"bind_code": code})


@router.post("/bind-code/refresh", response_model=ApiResponse)
async def refresh_bind_code(
    current_user: Annotated[User, Depends(require_role("counselor"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = CounselorService(db)
    # M7 修复：调用 refresh_bind_code 而非 get_or_create_bind_code，真正刷新绑定码
    code = await service.refresh_bind_code(current_user.id)
    return ok({"bind_code": code})
