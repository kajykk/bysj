from datetime import datetime
from typing import Annotated

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_role
from app.core.openapi_responses import COMMON_ERROR_RESPONSES
from app.core.response import ok
from app.models.user import User
from app.schemas.assessment import (
    DraftUpsertRequest,
    PhysiologicalRecordRequest,
    StructuredCollectRequest,
    TextAnalyzeRequest,
)
from app.schemas.common import ApiResponse
from app.schemas.counselor import BindCodeRequest
from app.services.counselor_service import CounselorService
from app.services.risk_service import RiskService
from app.services.user_data_service import UserDataService

router = APIRouter(prefix="/user/data", tags=["user-data"])
logger = logging.getLogger(__name__)


@router.post("/collect", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def collect_structured_data(
    payload: StructuredCollectRequest,
    current_user: Annotated[User, Depends(require_role("user"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = RiskService(db)
    try:
        result = await service.assess_structured(
            user_id=current_user.id,
            payload={"assessment_type": payload.assessment_type, **payload.data_payload},
        )
        return ok(result)
    except FileNotFoundError as exc:
        logger.exception("structured assessment model file missing for user_id=%s", current_user.id)
        raise HTTPException(status_code=503, detail="模型服务暂时不可用，请稍后重试") from exc
    except ValueError as exc:
        logger.warning("structured assessment validation failed for user_id=%s: %s", current_user.id, exc)
        raise HTTPException(status_code=422, detail=f"评估失败: {exc}") from exc
    except Exception as exc:
        logger.exception("structured assessment failed for user_id=%s", current_user.id)
        raise HTTPException(status_code=500, detail="结构化评估保存失败，请稍后重试") from exc


@router.post("/draft", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def upsert_draft(
    payload: DraftUpsertRequest,
    current_user: Annotated[User, Depends(require_role("user"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = UserDataService(db)
    draft_id = await service.upsert_draft(current_user.id, payload.draft_type, payload.data_payload)
    return ok({"draft_id": draft_id})


@router.get("/draft/{draft_type}", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def get_draft(
    draft_type: str,
    current_user: Annotated[User, Depends(require_role("user"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = UserDataService(db)
    draft = await service.get_draft(current_user.id, draft_type)
    if draft is None:
        raise HTTPException(status_code=404, detail="草稿不存在")
    return ok({"draft_id": draft.id, "data_payload": draft.data_payload})


@router.post("/text/analyze", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def text_analyze(
    payload: TextAnalyzeRequest,
    current_user: Annotated[User, Depends(require_role("user"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = UserDataService(db)
    result = await service.analyze_text(
        user_id=current_user.id,
        entry_type=payload.entry_type,
        content=payload.content,
        emotion_tags=payload.emotion_tags,
        mood_score=payload.mood_score,
    )
    return ok(result)


@router.post("/physiological/record", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def physiological_record(
    payload: PhysiologicalRecordRequest,
    current_user: Annotated[User, Depends(require_role("user"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = UserDataService(db)
    data = payload.model_dump()
    record_id = await service.record_physiological(current_user.id, data)
    return ok({"record_id": record_id})


@router.get("/history", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def history(
    current_user: Annotated[User, Depends(require_role("user"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    type: str = Query(default="structured", pattern="^(structured|text|physiological)$"),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
) -> dict:
    try:
        start_dt = datetime.fromisoformat(start_date) if start_date else None
        end_dt = datetime.fromisoformat(end_date) if end_date else None
    except ValueError as exc:
        raise HTTPException(status_code=422, detail="日期格式必须为 ISO8601") from exc
    service = UserDataService(db)
    result = await service.get_history(current_user.id, type, page, page_size, start_dt, end_dt)
    return ok(result)


@router.get("/binding", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def get_binding(
    current_user: Annotated[User, Depends(require_role("user"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = CounselorService(db)
    binding = await service.get_user_binding(current_user.id)
    return ok(binding)


@router.post("/binding", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def bind_counselor(
    payload: BindCodeRequest,
    current_user: Annotated[User, Depends(require_role("user"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = CounselorService(db)
    try:
        result = await service.bind_by_code(current_user.id, payload.bind_code)
        return ok(result)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/binding", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def unbind_counselor(
    current_user: Annotated[User, Depends(require_role("user"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = CounselorService(db)
    success = await service.unbind(current_user.id)
    if not success:
        raise HTTPException(status_code=404, detail="当前无有效绑定")
    return ok({"message": "已解绑咨询师"})
