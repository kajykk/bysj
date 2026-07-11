import json
import re
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_permission
from app.core.openapi_responses import COMMON_ERROR_RESPONSES, FILE_EXPORT_RESPONSE
from app.core.rate_limit import get_real_client_ip
from app.core.response import ok
from app.models.admin import OperationLog
from app.models.risk import RiskAssessment
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.risk_service import RiskService

router = APIRouter(prefix="/user/risk", tags=["user-risk"])


def _sanitize_filename(name: str) -> str:
    """L-API-5 修复：移除 filename 中的特殊字符，防止 Content-Disposition 头注入.

    仅保留字母、数字、下划线、连字符和点号，避免 CRLF 注入或路径穿越。
    """
    return re.sub(r"[^A-Za-z0-9_\-.]", "_", name)


@router.get("/report", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def get_risk_report(
    current_user: Annotated[User, Depends(require_permission("user.export.risk"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = RiskService(db)
    data = await service.get_risk_report(current_user.id)
    data.setdefault(
        "modality_contributions",
        {"structured": None, "text": None, "physiological": None},
    )
    if "physiological_score" not in data:
        data["physiological_score"] = None
    return ok(data)


@router.get("/trend", responses=COMMON_ERROR_RESPONSES)
async def get_risk_trend(
    current_user: Annotated[User, Depends(require_permission("user.export.risk"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    days: int = Query(default=30, ge=1, le=365),
) -> dict:
    service = RiskService(db)
    data = await service.get_risk_trend(current_user.id, days)
    if "physiological_scores" not in data:
        data["physiological_scores"] = []
    return ok(data)


@router.get("/export", responses={**COMMON_ERROR_RESPONSES, **FILE_EXPORT_RESPONSE})
async def export_risk(
    request: Request,
    current_user: Annotated[User, Depends(require_permission("user.export.risk"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    format: str = Query(default="json", pattern="^(json|csv|pdf)$"),
    days: int = Query(default=90, ge=1, le=365),
):
    service = RiskService(db)
    data = await service.export_risk(current_user.id, days, format)

    # SEC-P1-003 修复：记录风险数据导出审计日志
    db.add(
        OperationLog(
            operator_id=current_user.id,
            operator_role=current_user.role,
            action_type="user.risk.export",
            target_type="user",
            target_id=current_user.id,
            detail=json.dumps(
                {"format": format, "days": days, "filename": data.get("filename")},
                ensure_ascii=False,
            )[:5000],
            ip_address=get_real_client_ip(request),
        )
    )
    await db.commit()

    if format == "csv":
        csv_text = data["content"]
        return StreamingResponse(
            iter([csv_text]),
            media_type="text/csv; charset=utf-8",
            # L-API-5 修复：对 filename 脱敏，防止 Content-Disposition 头注入
            headers={
                "Content-Disposition": f'attachment; filename="{_sanitize_filename(data["filename"])}"'
            },
        )
    if format == "pdf":
        pdf_bytes = data["content"]
        return StreamingResponse(
            iter([pdf_bytes]),
            media_type="application/pdf",
            # L-API-5 修复：对 filename 脱敏，防止 Content-Disposition 头注入；format 已由 Query pattern 校验
            headers={
                "Content-Disposition": f'attachment; filename="{_sanitize_filename(data["filename"])}"'
            },
        )
    return ok(data)


@router.get(
    "/assessments/{assessment_id}",
    response_model=ApiResponse,
    responses=COMMON_ERROR_RESPONSES,
)
async def get_assessment_detail(
    assessment_id: int,
    current_user: Annotated[User, Depends(require_permission("user.assessment.read"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    stmt = select(RiskAssessment).where(
        RiskAssessment.id == assessment_id,
        RiskAssessment.user_id == current_user.id,
    )
    result = (await db.execute(stmt)).scalar_one_or_none()
    if result is None:
        raise HTTPException(status_code=404, detail="评估记录不存在")
    return ok(
        {
            "id": result.id,
            "assessment_type": result.assessment_type,
            "score": result.risk_score,
            "risk_level": result.risk_level,
            "created_at": result.created_at,
            "summary": None,
            "detail": None,
        }
    )
