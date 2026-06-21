from typing import Annotated

from fastapi import APIRouter, Depends, Query
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_permission
from app.core.response import ok
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.risk_service import RiskService

router = APIRouter(prefix="/user/risk", tags=["user-risk"])


@router.get("/report", response_model=ApiResponse)
async def get_risk_report(
    current_user: Annotated[User, Depends(require_permission("user.export.risk"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> dict:
    service = RiskService(db)
    data = await service.get_risk_report(current_user.id)
    data.setdefault("modality_contributions", {"structured": None, "text": None, "physiological": None})
    if "physiological_score" not in data:
        data["physiological_score"] = None
    return ok(data)


@router.get("/trend")
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


@router.get("/export")
async def export_risk(
    current_user: Annotated[User, Depends(require_permission("user.export.risk"))],
    db: Annotated[AsyncSession, Depends(get_db)],
    format: str = Query(default="json", pattern="^(json|csv|pdf)$"),
    days: int = Query(default=90, ge=1, le=365),
):
    service = RiskService(db)
    data = await service.export_risk(current_user.id, days, format)
    if format == "csv":
        csv_text = data["content"]
        return StreamingResponse(
            iter([csv_text]),
            media_type="text/csv; charset=utf-8",
            headers={"Content-Disposition": f'attachment; filename="{data["filename"]}"'},
        )
    if format == "pdf":
        pdf_bytes = data["content"]
        return StreamingResponse(
            iter([pdf_bytes]),
            media_type="application/pdf",
            headers={"Content-Disposition": f'attachment; filename="{data["filename"]}"'},
        )
    return ok(data)
