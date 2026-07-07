from __future__ import annotations

import asyncio
import json
import logging
import uuid
from datetime import datetime, timezone
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import require_permission
from app.core.openapi_responses import COMMON_ERROR_RESPONSES
from app.core.rate_limit import get_real_client_ip, limiter
from app.core.response import ok
from app.models.admin import OperationLog
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.reports import BatchExportRequest, UserRiskReportRequest
from app.services.excel_export_service import excel_export_service
from app.services.pdf_job_store import MAX_PDF_JOBS, pdf_job_store
from app.services.pdf_report_service import pdf_report_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/reports", tags=["reports"])

# P1-SEC-030 修复：文件名安全长度限制
_MAX_SAFE_NAME_LEN = 64

# P1-4: 防 GC 的后台 PDF 生成任务集合
_pdf_background_tasks: set[asyncio.Task] = set()

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


@router.post("/user-risk/pdf", responses=COMMON_ERROR_RESPONSES)
@limiter.limit("5/minute")
async def generate_user_risk_pdf(
    request: Request,
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

    safe_name = "".join(
        c if c.isascii() and c.isalnum() else "_" for c in payload.user_name
    )
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


@router.post("/batch-export/excel", responses=COMMON_ERROR_RESPONSES)
@limiter.limit("5/minute")
async def batch_export_excel(
    request: Request,
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
    safe_name = (
        "".join(c if c.isascii() and c.isalnum() else "_" for c in raw_name) or "export"
    )
    # P1-SEC-030 修复：限制文件名长度，防止超长文件名导致文件系统错误
    safe_name = safe_name[:_MAX_SAFE_NAME_LEN]

    # SEC-P1-003 修复：记录批量 Excel 导出审计日志 (流式响应前先提交, 避免事务在流式生成期间关闭)
    db.add(
        OperationLog(
            operator_id=current_user.id,
            operator_role=current_user.role,
            action_type="admin.report.batch_export_excel",
            target_type="report",
            target_id=None,
            detail=json.dumps(
                {
                    "filename": safe_name,
                    "row_count": len(payload.data),
                    "columns": list(payload.columns) if payload.columns else [],
                    "filters": payload.filters if payload.filters else {},
                    "file_size": result.file_size,
                },
                ensure_ascii=False,
            )[:5000],
            ip_address=get_real_client_ip(request),
        )
    )
    await db.commit()

    return StreamingResponse(
        iter([result.excel_bytes]),
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={
            "Content-Disposition": f"attachment; filename={safe_name}.xlsx",
            "Content-Length": str(result.file_size),
        },
    )


@router.get("/templates", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
@limiter.limit("30/minute")
async def list_report_templates(
    request: Request,
    _: Annotated[User, Depends(require_permission("admin.predict.audit"))],
) -> dict:
    """Get available report templates."""
    return ok({"templates": REPORT_TEMPLATES, "total": len(REPORT_TEMPLATES)})


# ── P1-4: PDF 异步生成队列 ──────────────────────────────────────────


@router.post(
    "/user-risk/pdf/async", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES
)
@limiter.limit("10/minute")
async def generate_user_risk_pdf_async(
    request: Request,
    payload: UserRiskReportRequest,
    current_user: Annotated[User, Depends(require_permission("admin.predict.audit"))],
) -> dict:
    """P1-4: 异步生成 PDF 报告.

    立即返回 job_id, PDF 在后台线程池生成. 客户端通过
    GET /reports/pdf/{job_id}/status 查询进度,
    GET /reports/pdf/{job_id}/download 下载完成的 PDF.

    适用于大报告 (>= 1000 行) 或需要非阻塞响应的场景.
    """
    # 检查任务数量限制
    current_count = pdf_job_store.count()
    if current_count >= MAX_PDF_JOBS:
        raise HTTPException(
            status_code=429,
            detail=f"Too many PDF jobs in progress (max={MAX_PDF_JOBS}). "
            "Please wait for existing jobs to complete.",
        )

    job_id = str(uuid.uuid4())
    pdf_job_store.create(
        job_id=job_id,
        user_name=payload.user_name,
        created_by=current_user.id,
    )

    # 启动后台生成任务
    task = asyncio.create_task(_execute_pdf_generation(job_id, payload))
    _pdf_background_tasks.add(task)
    task.add_done_callback(_pdf_background_tasks.discard)
    # R-005 修复: 注册可观测性指标 (scheduled/succeeded/failed/cancelled + duration)
    from app.core.fire_forget_metrics import register_task

    register_task(task, "pdf_generation")

    return ok(
        {
            "job_id": job_id,
            "status": "queued",
            "message": "PDF generation started. Poll /reports/pdf/{job_id}/status for progress.",
        }
    )


async def _execute_pdf_generation(job_id: str, payload: UserRiskReportRequest) -> None:
    """P1-4: 后台执行 PDF 生成 (在专用线程池中运行 reportlab)."""
    pdf_job_store.update(
        job_id,
        status="running",
        started_at=datetime.now(timezone.utc).isoformat(),
        progress=10,
    )
    try:
        result = await asyncio.to_thread(
            pdf_report_service.generate_user_risk_report,
            user_name=payload.user_name,
            risk_level=payload.risk_level,
            risk_trend=[item.model_dump() for item in payload.risk_trend],
            recommendations=payload.recommendations,
        )

        if not result.success:
            pdf_job_store.update(
                job_id,
                status="failed",
                completed_at=datetime.now(timezone.utc).isoformat(),
                error=result.error_message or "PDF generation failed",
                progress=100,
            )
            return

        # 存储 PDF 字节到任务 (内存中, 供下载端点读取)
        pdf_job_store.update(
            job_id,
            status="completed",
            completed_at=datetime.now(timezone.utc).isoformat(),
            progress=100,
            pdf_bytes=result.pdf_bytes,
            file_size=result.file_size,
            page_count=result.page_count,
        )
        logger.info(
            "PDF job %s completed: size=%d bytes, pages=%d",
            job_id,
            result.file_size,
            result.page_count,
        )
    except Exception as exc:
        logger.error("PDF job %s failed: %s", job_id, exc, exc_info=True)
        pdf_job_store.update(
            job_id,
            status="failed",
            completed_at=datetime.now(timezone.utc).isoformat(),
            error=str(exc),
            progress=100,
        )


@router.get(
    "/pdf/{job_id}/status", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES
)
@limiter.limit("30/minute")
async def get_pdf_job_status(
    request: Request,
    job_id: Annotated[str, Path()],
    current_user: Annotated[User, Depends(require_permission("admin.predict.audit"))],
) -> dict:
    """P1-4: 查询 PDF 生成任务状态."""
    job = pdf_job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="PDF job not found")
    # L-API-7 一致性: 仅允许创建者查看自己的任务状态
    if job.created_by != current_user.id:
        raise HTTPException(status_code=404, detail="PDF job not found")
    return ok(job.to_status_dict())


@router.get("/pdf/{job_id}/download", responses=COMMON_ERROR_RESPONSES)
@limiter.limit("30/minute")
async def download_pdf(
    request: Request,
    job_id: Annotated[str, Path()],
    current_user: Annotated[User, Depends(require_permission("admin.predict.audit"))],
) -> StreamingResponse:
    """P1-4: 下载已完成的 PDF.

    仅 status=completed 的任务可下载. 下载后任务保留 (TTL 1h 后自动清理),
    客户端可重复下载直到过期.
    """
    job = pdf_job_store.get(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="PDF job not found")
    if job.created_by != current_user.id:
        raise HTTPException(status_code=404, detail="PDF job not found")
    if job.status != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"PDF job is {job.status}, cannot download yet",
        )
    if job.pdf_bytes is None:
        raise HTTPException(status_code=500, detail="PDF bytes missing")

    safe_name = "".join(
        c if c.isascii() and c.isalnum() else "_" for c in job.user_name
    )
    if not safe_name:
        safe_name = "user"
    safe_name = safe_name[:_MAX_SAFE_NAME_LEN]

    return StreamingResponse(
        iter([job.pdf_bytes]),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=user_risk_{safe_name}.pdf",
            "Content-Length": str(job.file_size),
        },
    )


@router.get("/pdf/jobs", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
@limiter.limit("30/minute")
async def list_pdf_jobs(
    request: Request,
    current_user: Annotated[User, Depends(require_permission("admin.predict.audit"))],
) -> dict:
    """P1-4: 列出当前用户的 PDF 生成任务."""
    jobs = pdf_job_store.list_jobs(created_by=current_user.id)
    return ok({"jobs": jobs, "total": len(jobs)})


# ── P-D: PDF 生成 Celery 队列化 ────────────────────────────────────
# 与 P1-4 的 asyncio.create_task (进程内异步) 并存, 提供跨节点调度能力.
# 当 Celery broker 不可用时, 自动回退到 daemon Thread (复用 PERF-P1-006 模式).


@router.post(
    "/user-risk/pdf/celery-async",
    response_model=ApiResponse,
    responses=COMMON_ERROR_RESPONSES,
)
@limiter.limit("10/minute")
async def generate_user_risk_pdf_celery_async(
    request: Request,
    payload: UserRiskReportRequest,
    current_user: Annotated[User, Depends(require_permission("admin.predict.audit"))],
) -> dict:
    """P-D: 通过 Celery 队列异步生成 PDF 报告.

    与 /user-risk/pdf/async (asyncio.create_task, 进程内) 并存, 适用于:
    - 多实例部署 (Celery worker 可独立扩缩容)
    - 长时间 PDF 生成 (不占用 Web 进程资源)
    - 任务持久化 (Celery worker 重启后任务可恢复)

    当 Celery broker 不可用时, 自动回退到 daemon Thread.

    客户端通过:
    - GET /reports/pdf/celery/{job_id}/status 查询状态
    - GET /reports/pdf/celery/{job_id}/download 下载 PDF
    """
    import uuid as _uuid

    job_id = _uuid.uuid4().hex

    try:
        from app.tasks.pdf_report import (
            create_initial_job,
            generate_pdf_report,
            save_job_to_redis,
        )

        job_data = create_initial_job(
            job_id=job_id,
            user_name=payload.user_name,
            created_by=current_user.id,
        )
        save_job_to_redis(job_id, job_data)

        # 派发到 Celery 队列
        generate_pdf_report.delay(
            job_id=job_id,
            user_name=payload.user_name,
            risk_level=payload.risk_level,
            risk_trend=[item.model_dump() for item in payload.risk_trend],
            recommendations=payload.recommendations,
        )
        logger.info(
            "[celery-pdf] submitted job_id=%s user=%s", job_id, payload.user_name
        )

    except Exception as exc:
        # Celery/Redis 不可用时回退到 daemon Thread
        logger.warning(
            "[celery-pdf] Celery submission failed, falling back to daemon Thread: %s",
            exc,
        )
        # 复用 P1-4 的进程内 PdfJobStore 作为 fallback
        if pdf_job_store.count() >= MAX_PDF_JOBS:
            raise HTTPException(
                status_code=429,
                detail=f"Too many PDF jobs in progress (max={MAX_PDF_JOBS}).",
            )
        pdf_job_store.create(
            job_id=job_id,
            user_name=payload.user_name,
            created_by=current_user.id,
        )
        task = asyncio.create_task(_execute_pdf_generation(job_id, payload))
        _pdf_background_tasks.add(task)
        task.add_done_callback(_pdf_background_tasks.discard)
        # R-005 修复: 注册可观测性指标 (scheduled/succeeded/failed/cancelled + duration)
        from app.core.fire_forget_metrics import register_task

        register_task(task, "pdf_generation")
        return ok(
            {
                "job_id": job_id,
                "status": "queued",
                "backend": "thread-fallback",
                "message": "Celery unavailable, using in-process thread fallback. "
                "Poll /reports/pdf/{job_id}/status for progress.",
            }
        )

    return ok(
        {
            "job_id": job_id,
            "status": "queued",
            "backend": "celery",
            "message": "PDF generation queued. Poll /reports/pdf/celery/{job_id}/status for progress.",
        }
    )


@router.get(
    "/pdf/celery/{job_id}/status",
    response_model=ApiResponse,
    responses=COMMON_ERROR_RESPONSES,
)
@limiter.limit("30/minute")
async def get_celery_pdf_job_status(
    request: Request,
    job_id: Annotated[str, Path()],
    current_user: Annotated[User, Depends(require_permission("admin.predict.audit"))],
) -> dict:
    """P-D: 查询 Celery PDF 任务状态."""
    from app.tasks.pdf_report import get_job_from_redis

    job = get_job_from_redis(job_id)
    if not job:
        raise HTTPException(
            status_code=404, detail="PDF job not found in Celery backend"
        )
    # 鉴权: 仅创建者可查询
    if job.get("created_by") != current_user.id:
        raise HTTPException(status_code=404, detail="PDF job not found")
    return ok(job)


@router.get("/pdf/celery/{job_id}/download", responses=COMMON_ERROR_RESPONSES)
@limiter.limit("30/minute")
async def download_celery_pdf(
    request: Request,
    job_id: Annotated[str, Path()],
    current_user: Annotated[User, Depends(require_permission("admin.predict.audit"))],
) -> StreamingResponse:
    """P-D: 下载 Celery 生成的 PDF.

    PDF 字节从 Redis 二进制 key 读取 (TTL 1 小时).
    """
    from app.tasks.pdf_report import get_job_from_redis, get_pdf_bytes_from_redis

    job = get_job_from_redis(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="PDF job not found")
    if job.get("created_by") != current_user.id:
        raise HTTPException(status_code=404, detail="PDF job not found")
    if job.get("status") != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"PDF job is {job.get('status')}, cannot download yet",
        )

    pdf_bytes = get_pdf_bytes_from_redis(job_id)
    if not pdf_bytes:
        raise HTTPException(status_code=410, detail="PDF bytes expired or missing")

    safe_name = "".join(
        c if c.isascii() and c.isalnum() else "_" for c in job.get("user_name", "user")
    )
    if not safe_name:
        safe_name = "user"
    safe_name = safe_name[:_MAX_SAFE_NAME_LEN]

    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=user_risk_{safe_name}.pdf",
            "Content-Length": str(len(pdf_bytes)),
        },
    )
