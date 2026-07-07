import json
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_role
from app.core.openapi_responses import COMMON_ERROR_RESPONSES
from app.core.rate_limit import get_real_client_ip, limiter
from app.core.request_id import get_or_create_request_id
from app.core.response import ok
from app.core.states import BindingStatus
from app.models.admin import OperationLog
from app.models.counselor import ClientGroup
from app.models.user import User, UserCounselorBinding
from app.schemas.common import ApiResponse
from app.schemas.counselor import (
    ConsultationCreateRequest,
    GroupCreateRequest,
    GroupMemberAddRequest,
    WarningEscalateRequest,
    WarningHandleRequest,
)
from app.services.counselor_service import CounselorService

router = APIRouter(prefix="/counselor", tags=["counselor"])


@router.get("/warnings", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
@limiter.limit("60/minute")
async def list_warnings(
    request: Request,
    current_user: Annotated[User, Depends(require_role("counselor"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    only_unhandled: bool = Query(default=False),
) -> dict:
    service = CounselorService(db)
    data = await service.list_warnings(current_user.id, page, page_size, only_unhandled)
    return ok(data)


@router.put(
    "/warnings/{warning_id}/handle",
    response_model=ApiResponse,
    responses=COMMON_ERROR_RESPONSES,
)
@limiter.limit("30/minute")
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
        ip_address=get_real_client_ip(request),
        request_id=request_id,
    )
    if not success:
        raise HTTPException(status_code=404, detail="预警不存在")
    return ok({"message": "预警已处理"})


# ISS-058: 预警升级端点 - 需 counselor.warning.handle 权限
@router.put(
    "/warnings/{warning_id}/escalate",
    response_model=ApiResponse,
    responses=COMMON_ERROR_RESPONSES,
)
@limiter.limit("30/minute")
async def escalate_warning(
    warning_id: int,
    payload: WarningEscalateRequest,
    request: Request,
    current_user: Annotated[User, Depends(require_role("counselor"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = CounselorService(db)
    request_id = get_or_create_request_id(request)
    success = await service.escalate_warning(
        current_user.id,
        warning_id,
        payload.reason,
        ip_address=get_real_client_ip(request),
        request_id=request_id,
    )
    if not success:
        raise HTTPException(status_code=404, detail="预警不存在")
    return ok({"message": "预警已升级"})


@router.get("/users", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
@limiter.limit("60/minute")
async def list_users(
    request: Request,
    current_user: Annotated[User, Depends(require_role("counselor"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    risk_level: int | None = Query(default=None, ge=0, le=4),
) -> dict:
    service = CounselorService(db)
    data = await service.list_my_users(
        current_user.id, page, page_size, risk_level=risk_level
    )
    # SEC-P1-004 修复：记录咨询师查看用户列表审计日志
    db.add(
        OperationLog(
            operator_id=current_user.id,
            operator_role=current_user.role,
            action_type="counselor_view_user_list",
            target_type="user",
            target_id=None,
            detail=json.dumps(
                {
                    "page": page,
                    "page_size": page_size,
                    "risk_level": risk_level,
                    "result_count": (
                        data.get("total") if isinstance(data, dict) else None
                    ),
                },
                ensure_ascii=False,
            )[:5000],
            ip_address=get_real_client_ip(request),
        )
    )
    await db.commit()
    return ok(data)


@router.get(
    "/users/{user_id}", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES
)
@limiter.limit("60/minute")
async def get_user_detail(
    user_id: int,
    request: Request,
    current_user: Annotated[User, Depends(require_role("counselor"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = CounselorService(db)
    data = await service.get_user_detail(current_user.id, user_id)
    if data is None:
        raise HTTPException(status_code=404, detail="用户不存在或未绑定")
    # SEC-P1-004 修复：记录咨询师查看用户详情审计日志
    db.add(
        OperationLog(
            operator_id=current_user.id,
            operator_role=current_user.role,
            action_type="counselor_view_user_detail",
            target_type="user",
            target_id=user_id,
            detail=json.dumps(
                {
                    "user_id": user_id,
                    "risk_level": (
                        data.get("risk_level") if isinstance(data, dict) else None
                    ),
                },
                ensure_ascii=False,
            )[:5000],
            ip_address=get_real_client_ip(request),
        )
    )
    await db.commit()
    return ok(data)


@router.post(
    "/users/{user_id}/consultations",
    response_model=ApiResponse,
    responses=COMMON_ERROR_RESPONSES,
)
@limiter.limit("30/minute")
async def create_consultation_record(
    user_id: int,
    payload: ConsultationCreateRequest,
    request: Request,
    current_user: Annotated[User, Depends(require_role("counselor"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    if payload.main_topics is not None and not payload.main_topics.strip():
        raise HTTPException(status_code=422, detail="main_topics 不能为空")
    service = CounselorService(db)
    try:
        record_id = await service.create_consultation_record(
            current_user.id, user_id, payload.model_dump()
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ok({"record_id": record_id})


@router.get(
    "/users/{user_id}/consultations",
    response_model=ApiResponse,
    responses=COMMON_ERROR_RESPONSES,
)
@limiter.limit("60/minute")
async def list_consultation_records(
    user_id: int,
    request: Request,
    current_user: Annotated[User, Depends(require_role("counselor"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    service = CounselorService(db)
    data = await service.list_consultation_records(
        current_user.id, user_id, page, page_size
    )
    # SEC-P1-004 修复：记录咨询师查看咨询记录审计日志
    db.add(
        OperationLog(
            operator_id=current_user.id,
            operator_role=current_user.role,
            action_type="counselor_view_consultation_records",
            target_type="consultation_record",
            target_id=user_id,
            detail=json.dumps(
                {
                    "user_id": user_id,
                    "page": page,
                    "page_size": page_size,
                    "result_count": (
                        data.get("total") if isinstance(data, dict) else None
                    ),
                },
                ensure_ascii=False,
            )[:5000],
            ip_address=get_real_client_ip(request),
        )
    )
    await db.commit()
    return ok(data)


@router.put(
    "/users/{user_id}/consultations/{record_id}",
    response_model=ApiResponse,
    responses=COMMON_ERROR_RESPONSES,
)
@limiter.limit("30/minute")
async def update_consultation_record(
    user_id: int,
    record_id: int,
    payload: ConsultationCreateRequest,
    request: Request,
    current_user: Annotated[User, Depends(require_role("counselor"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    if payload.main_topics is not None and not payload.main_topics.strip():
        raise HTTPException(status_code=422, detail="main_topics 不能为空")
    # H-API-1 修复：路由层显式校验归属 - 咨询师必须与该 user 存在 ACTIVE 绑定，防止 IDOR
    binding_stmt = select(UserCounselorBinding).where(
        UserCounselorBinding.counselor_id == current_user.id,
        UserCounselorBinding.user_id == user_id,
        UserCounselorBinding.status == BindingStatus.ACTIVE,
    )
    binding = (await db.execute(binding_stmt)).scalar_one_or_none()
    if binding is None:
        raise HTTPException(status_code=403, detail="无权操作：未与该用户建立绑定关系")
    service = CounselorService(db)
    try:
        success = await service.update_consultation_record(
            current_user.id, user_id, record_id, payload.model_dump()
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    if not success:
        raise HTTPException(status_code=404, detail="咨询记录不存在")
    return ok({"message": "咨询记录已更新"})


@router.post("/groups", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
@limiter.limit("30/minute")
async def create_group(
    payload: GroupCreateRequest,
    request: Request,
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


@router.get("/groups", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
@limiter.limit("60/minute")
async def list_groups(
    request: Request,
    current_user: Annotated[User, Depends(require_role("counselor"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    service = CounselorService(db)
    data = await service.list_groups(current_user.id, page, page_size)
    return ok(data)


@router.post(
    "/groups/{group_id}/members",
    response_model=ApiResponse,
    responses=COMMON_ERROR_RESPONSES,
)
@limiter.limit("30/minute")
async def add_group_member(
    group_id: int,
    payload: GroupMemberAddRequest,
    request: Request,
    current_user: Annotated[User, Depends(require_role("counselor"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    # H-API-10 修复：路由层 group 归属预校验 - 确认分组归属当前咨询师，防止向他人分组添加成员
    group = (
        await db.execute(select(ClientGroup).where(ClientGroup.id == group_id))
    ).scalar_one_or_none()
    if group is None or group.counselor_id != current_user.id:
        raise HTTPException(
            status_code=403, detail="无权操作：分组不存在或不属于当前咨询师"
        )
    service = CounselorService(db)
    success = await service.add_group_member(current_user.id, group_id, payload.user_id)
    if not success:
        # M9 修复：区分"分组不存在"和"用户未绑定"两种情况
        # 为安全起见，对外返回模糊错误信息避免信息泄露
        raise HTTPException(
            status_code=404, detail="分组不存在或用户未与您建立绑定关系"
        )
    return ok({"message": "成员已添加"})


@router.get("/bind-code", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
@limiter.limit("60/minute")
async def get_bind_code(
    request: Request,
    current_user: Annotated[User, Depends(require_role("counselor"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = CounselorService(db)
    code = await service.get_or_create_bind_code(current_user.id)
    return ok({"bind_code": code})


@router.post(
    "/bind-code/refresh", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES
)
@limiter.limit("30/minute")
async def refresh_bind_code(
    request: Request,
    current_user: Annotated[User, Depends(require_role("counselor"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = CounselorService(db)
    # M7 修复：调用 refresh_bind_code 而非 get_or_create_bind_code，真正刷新绑定码
    code = await service.refresh_bind_code(current_user.id)
    return ok({"bind_code": code})
