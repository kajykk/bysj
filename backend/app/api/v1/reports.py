from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_permission
from app.core.response import ok
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.reports import BatchExportRequest, UserRiskReportRequest
from app.services.excel_export_service import excel_export_service
from app.services.pdf_report_service import pdf_report_service

router = APIRouter(prefix="/reports", tags=["reports"])

# P1-SEC-030 修复：文件名安全长度限制
_MAX_SAFE_NAME_LEN = 64

# Report templates configuration
REPORT_TEMPLATES = [
    {
        "id": "user-risk",
        "name": "User Risk Assessment Report",
        "description": "Individual user risk assessment with trend analysis and recommendations",
        "formats": ["pdf"],
        "permissions": ["admin.predict.audit"],
    },
    {
        "id": "counselor-summary",
        "name": "Counselor Summary Report",
        "description": "Summary report for counselors with patient statistics",
        "formats": ["pdf"],
        "permissions": ["counselor.dashboard.view"],
    },
    {
        "id": "management-analysis",
        "name": "Management Analysis Report",
        "description": "High-level management analysis with department statistics",
        "formats": ["pdf"],
        "permissions": ["admin.dashboard.view"],
    },
    {
        "id": "batch-export",
        "name": "Batch Data Export",
        "description": "Export large datasets to Excel with filtering",
        "formats": ["excel"],
        "permissions": ["admin.predict.audit"],
    },
]


@router.post("/user-risk/pdf")
async def generate_user_risk_pdf(
    payload: UserRiskReportRequest,
    current_user: Annotated[User, Depends(require_permission("admin.predict.audit"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StreamingResponse:
    """Generate a user risk assessment PDF report."""
    # M8 修复：使用 asyncio.to_thread 包装同步调用，避免阻塞事件循环
    result = await asyncio.to_thread(
        pdf_report_service.generate_user_risk_report,
        user_name=payload.user_name,
        risk_level=payload.risk_level,
        risk_trend=[item.model_dump() for item in payload.risk_trend],
        recommendations=payload.recommendations,
    )

    if not result.success:
        raise HTTPException(status_code=500, detail=result.error_message)

    safe_name = "".join(c if c.isascii() and c.isalnum() else "_" for c in payload.user_name)
    if not safe_name:
        safe_name = "user"
    # P1-SEC-030 修复：限制文件名长度，防止超长文件名导致文件系统错误
    safe_name = safe_name[:_MAX_SAFE_NAME_LEN]
    return StreamingResponse(
        iter([result.pdf_bytes]),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=user_risk_{safe_name}.pdf",
            "Content-Length": str(result.file_size),
        },
    )


@router.post("/batch-export/excel")
async def batch_export_excel(
    payload: BatchExportRequest,
    current_user: Annotated[User, Depends(require_permission("admin.predict.audit"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StreamingResponse:
    """Export data to Excel with filtering."""
    # M8 修复：使用 asyncio.to_thread 包装同步调用，避免阻塞事件循环
    result = await asyncio.to_thread(
        excel_export_service.export,
        data=[item.model_dump() for item in payload.data],
        columns=payload.columns,
        filters=payload.filters,
    )

    if not result.success:
        raise HTTPException(status_code=500, detail=result.error_message)

    raw_name = payload.filename or "export"
    safe_name = "".join(c if c.isascii() and c.isalnum() else "_" for c in raw_name) or "export"
    # P1-SEC-030 修复：限制文件名长度，防止超长文件名导致文件系统错误
    safe_name = safe_name[:_MAX_SAFE_NAME_LEN]
    return StreamingResponse(
        iter([result.excel_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename={safe_name}.xlsx",
            "Content-Length": str(result.file_size),
        },
    )


@router.get("/templates", response_model=ApiResponse)
async def list_report_templates(
    _: Annotated[User, Depends(require_permission("admin.predict.audit"))],
) -> dict:
    """Get available report templates."""
    return ok({"templates": REPORT_TEMPLATES, "total": len(REPORT_TEMPLATES)})
