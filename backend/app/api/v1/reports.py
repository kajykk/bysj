from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timezone
from typing import Annotated, Any

from fastapi import APIRouter, Depends, HTTPException, Path, Request
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.deps import get_current_user, require_permission
from app.core.openapi_responses import (
    COMMON_ERROR_RESPONSES,
    EXCEL_EXPORT_RESPONSE,
    PDF_SUCCESS_RESPONSE,
)
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


@router.post("/user-risk/pdf", responses={**COMMON_ERROR_RESPONSES, **PDF_SUCCESS_RESPONSE})
@limiter.limit("5/minute")
async def generate_user_risk_pdf(
    request: Request,
    payload: UserRiskReportRequest,
    current_user: Annotated[User, Depends(require_permission("admin.predict.audit"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StreamingResponse:
    """Generate a user risk assessment PDF report.

    RES-P2-002: 使用 BytesIO 流式响应, 避免 PDF bytes 在内存中拷贝.
    reportlab 生成 PDF 到 BytesIO, API 层用 StreamingResponse 分块读取.
    """
    # M8 修复：使用 asyncio.to_thread 包装同步调用，避免阻塞事件循环
    # RES-P2-002: 使用 generate_user_risk_report_stream 返回 BytesIO (不 getvalue 拷贝)
    result = await asyncio.to_thread(
        pdf_report_service.generate_user_risk_report_stream,
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
    # RES-P2-002: 分块流式读取 BytesIO (默认 64KB chunks)
    return StreamingResponse(
        _stream_bytes(result.stream),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=user_risk_{safe_name}.pdf",
            "Content-Length": str(result.file_size),
        },
    )


def _stream_bytes(buffer, chunk_size: int = 65536):
    """RES-P2-002: 分块生成器, 从 BytesIO 流式读取数据.

    Args:
        buffer: BytesIO 缓冲区 (位置指针应已 rewind 到 0).
        chunk_size: 每块大小 (字节), 默认 64KB.

    Yields:
        bytes chunks.
    """
    try:
        while True:
            chunk = buffer.read(chunk_size)
            if not chunk:
                break
            yield chunk
    finally:
        buffer.close()


# OPT-R5：Excel 导出公共常量与辅助（消除 batch_export_excel 流式/非流式双分支
# 约 110 行的逐字重复：文件名清洗、审计日志、响应头三段完全一致）
_XLSX_MEDIA_TYPE = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"


def _safe_export_filename(raw_name: str | None) -> str:
    """导出文件名清洗（ASCII 化 + 长度限制）。

    P1-SEC-030 修复：限制文件名长度，防止超长文件名导致文件系统错误。
    """
    safe_name = "".join(c if c.isascii() and c.isalnum() else "_" for c in (raw_name or "export"))
    return safe_name[:_MAX_SAFE_NAME_LEN] or "export"


async def _resolve_pdf_job(job_id: str) -> tuple[dict | Any | None, str]:
    """统一 PDF 任务读取 (R-B): Redis 优先, 内存 PdfJobStore 兜底.

    Returns:
        (job, backend) — backend ∈ {"redis", "local", None}
        - redis: app.tasks.pdf_report 的原始 dict (跨实例可见)
        - local: PdfJobStore 内存对象 (进程内降级路径)
    """
    try:
        from app.tasks.pdf_report import get_job_from_redis

        redis_job = await asyncio.to_thread(get_job_from_redis, job_id)
        if redis_job:
            return redis_job, "redis"
    except Exception as exc:  # pragma: no cover - Redis 异常降级为内存兜底
        logger.warning("[pdf-job] redis lookup failed, falling back to local: %s", exc)
    return pdf_job_store.get(job_id), "local"


def _job_created_by(job: dict | Any) -> Any:
    """兼容 Redis dict 与 PdfJob 对象两种形态的 created_by 读取."""
    return job.get("created_by") if isinstance(job, dict) else job.created_by


def _job_status(job: dict | Any) -> str | None:
    """兼容两种形态的 status 读取."""
    return job.get("status") if isinstance(job, dict) else job.status


async def _record_excel_export_audit(
    db: AsyncSession,
    request: Request,
    current_user: User,
    *,
    safe_name: str,
    row_count: int,
    columns: list[str] | None,
    filters: dict | None,
    file_size: int,
    stream_mode: bool,
) -> None:
    """SEC-P1-003 修复：记录批量 Excel 导出审计日志并提交。

    （流式响应前先提交, 避免事务在流式生成期间关闭）
    """
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
                    "row_count": row_count,
                    "columns": list(columns) if columns else [],
                    "filters": filters if filters else {},
                    "file_size": file_size,
                    "stream_mode": stream_mode,
                },
                ensure_ascii=False,
            ),
            ip_address=get_real_client_ip(request),
        )
    )
    await db.commit()


@router.post("/batch-export/excel", responses={**COMMON_ERROR_RESPONSES, **EXCEL_EXPORT_RESPONSE})
@limiter.limit("5/minute")
async def batch_export_excel(
    request: Request,
    payload: BatchExportRequest,
    current_user: Annotated[User, Depends(require_permission("admin.predict.audit"))],
    db: Annotated[AsyncSession, Depends(get_db)],
) -> StreamingResponse:
    """Export data to Excel with filtering.

    RES-P2-003: 自动切换流式输出 - 数据量 > 5000 行时使用 export_to_stream
    返回 BytesIO, 避免 bytes 拷贝. 小数据量仍用 export 返回 bytes.
    """
    # RES-P2-003: 根据数据量自动选择流式或非流式
    use_stream = excel_export_service.should_use_stream(len(payload.data))

    # OPT-R5：双分支仅导出函数与响应体不同，文件名/审计/响应头全部走公共辅助
    safe_name = _safe_export_filename(payload.filename)

    if use_stream:
        # 大数据量: 流式输出
        result = await asyncio.to_thread(
            excel_export_service.export_to_stream,
            data=[item.model_dump() for item in payload.data],
            columns=payload.columns,
            filters=payload.filters,
        )
        if not result.success:
            raise HTTPException(status_code=500, detail=result.error_message)

        await _record_excel_export_audit(
            db,
            request,
            current_user,
            safe_name=safe_name,
            row_count=result.row_count,
            columns=payload.columns,
            filters=payload.filters,
            file_size=result.file_size,
            stream_mode=True,
        )

        # RES-P2-003: 分块流式读取 BytesIO (复用 PDF 的 _stream_bytes 生成器)
        return StreamingResponse(
            _stream_bytes(result.stream),
            media_type=_XLSX_MEDIA_TYPE,
            headers={
                "Content-Disposition": f"attachment; filename={safe_name}.xlsx",
                "Content-Length": str(result.file_size),
            },
        )

    # 小数据量: 原有非流式路径 (保持向后兼容)
    # M8 修复：使用 asyncio.to_thread 包装同步调用，避免阻塞事件循环
    result = await asyncio.to_thread(
        excel_export_service.export,
        data=[item.model_dump() for item in payload.data],
        columns=payload.columns,
        filters=payload.filters,
    )
    if not result.success:
        raise HTTPException(status_code=500, detail=result.error_message)

    await _record_excel_export_audit(
        db,
        request,
        current_user,
        safe_name=safe_name,
        # 保持原行为：非流式分支审计行数取输入行数（服务层 mock 场景下
        # result.row_count 不可靠），流式分支取导出结果统计
        row_count=len(payload.data),
        columns=payload.columns,
        filters=payload.filters,
        file_size=result.file_size,
        stream_mode=False,
    )

    return StreamingResponse(
        iter([result.excel_bytes]),
        media_type=_XLSX_MEDIA_TYPE,
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


@router.post("/user-risk/pdf/async", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
@limiter.limit("10/minute")
async def generate_user_risk_pdf_async(
    request: Request,
    payload: UserRiskReportRequest,
    current_user: Annotated[User, Depends(require_permission("admin.predict.audit"))],
) -> dict:
    """R-B: 异步生成 PDF 报告（统一派发：Celery 优先，降级线程）.

    响应新增 backend 字段（celery | thread-fallback），原 job_id/status/message
    键保持不变，旧客户端零感知。
    """
    return await _dispatch_pdf_async(payload, current_user)


async def _execute_pdf_generation(job_id: str, payload: UserRiskReportRequest) -> None:
    """P1-4: 后台执行 PDF 生成 (在专用线程池中运行 reportlab)."""
    # M-FIX-005: 与 celery 变体 (tasks/pdf_report.py:_notify_progress) 对齐,
    # 通过 WebSocket 实时推送 task_progress, 供 useTaskProgress 前端订阅.
    job_record = pdf_job_store.get(job_id)
    user_id = job_record.created_by if job_record else None

    async def _notify(status: str, progress: int, error: str | None = None):
        if user_id is None:
            return
        try:
            from app.core.ws import notify_task_progress

            await notify_task_progress(
                user_id=user_id,
                job_id=job_id,
                status=status,
                progress=progress,
                job_type="pdf",
                error=error,
            )
        except Exception as exc:  # pragma: no cover
            logger.debug("notify_task_progress failed for job %s: %s", job_id, exc)

    pdf_job_store.update(
        job_id,
        status="running",
        started_at=datetime.now(timezone.utc).isoformat(),
        progress=10,
    )
    await _notify("running", 10)
    try:
        result = await asyncio.to_thread(
            pdf_report_service.generate_user_risk_report,
            user_name=payload.user_name,
            risk_level=payload.risk_level,
            risk_trend=[item.model_dump() for item in payload.risk_trend],
            recommendations=payload.recommendations,
        )

        if not result.success:
            error_message = result.error_message or "PDF generation failed"
            pdf_job_store.update(
                job_id,
                status="failed",
                completed_at=datetime.now(timezone.utc).isoformat(),
                error=error_message,
                progress=100,
            )
            await _notify("failed", 100, error_message)
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
        await _notify("completed", 100)
        logger.info(
            "PDF job %s completed: size=%d bytes, pages=%d",
            job_id,
            result.file_size,
            result.page_count,
        )
    except Exception as exc:
        logger.error("PDF job %s failed: %s", job_id, exc, exc_info=True)
        error_message = str(exc)
        pdf_job_store.update(
            job_id,
            status="failed",
            completed_at=datetime.now(timezone.utc).isoformat(),
            error=error_message,
            progress=100,
        )
        await _notify("failed", 100, error_message)


@router.get("/pdf/{job_id}/status", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
@limiter.limit("30/minute")
async def get_pdf_job_status(
    request: Request,
    job_id: Annotated[str, Path()],
    current_user: Annotated[User, Depends(require_permission("admin.predict.audit"))],
) -> dict:
    """R-B: 统一 PDF 任务状态查询（Redis 优先，内存兜底）.

    同时覆盖 Celery(Redis) 路径与进程内 PdfJobStore 路径的任务。
    """
    job, backend = await _resolve_pdf_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="PDF job not found")
    # L-API-7 一致性: 仅允许创建者查看自己的任务状态
    if _job_created_by(job) != current_user.id:
        raise HTTPException(status_code=404, detail="PDF job not found")
    if backend == "redis":
        return ok(job)
    return ok(job.to_status_dict())


@router.get("/pdf/{job_id}/download", responses={**COMMON_ERROR_RESPONSES, **PDF_SUCCESS_RESPONSE})
@limiter.limit("30/minute")
async def download_pdf(
    request: Request,
    job_id: Annotated[str, Path()],
    current_user: Annotated[User, Depends(require_permission("admin.predict.audit"))],
) -> StreamingResponse:
    """R-B: 统一 PDF 下载（Redis 字节优先，内存兜底）.

    仅 status=completed 的任务可下载。下载后任务保留 (TTL 1h 后自动清理),
    客户端可重复下载直到过期。
    """
    job, backend = await _resolve_pdf_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="PDF job not found")
    if _job_created_by(job) != current_user.id:
        raise HTTPException(status_code=404, detail="PDF job not found")
    if _job_status(job) != "completed":
        raise HTTPException(
            status_code=409,
            detail=f"PDF job is {_job_status(job)}, cannot download yet",
        )

    if backend == "redis":
        from app.tasks.pdf_report import get_pdf_bytes_from_redis

        pdf_bytes = await asyncio.to_thread(get_pdf_bytes_from_redis, job_id)
        if not pdf_bytes:
            raise HTTPException(status_code=410, detail="PDF bytes expired or missing")
        user_name = job.get("user_name", "user")
        content_length = str(len(pdf_bytes))
    else:
        if job.pdf_bytes is None:
            raise HTTPException(status_code=500, detail="PDF bytes missing")
        pdf_bytes = job.pdf_bytes
        user_name = job.user_name
        content_length = str(job.file_size)

    safe_name = _safe_export_filename(user_name)

    return StreamingResponse(
        iter([pdf_bytes]),
        media_type="application/pdf",
        headers={
            "Content-Disposition": f"attachment; filename=user_risk_{safe_name}.pdf",
            "Content-Length": content_length,
        },
    )


@router.get("/pdf/jobs", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
@limiter.limit("30/minute")
async def list_pdf_jobs(
    request: Request,
    current_user: Annotated[User, Depends(get_current_user)],
) -> dict:
    """P1-4: 列出当前用户的 PDF 生成任务.

    任务按 created_by 隔离，任何已登录用户仅能查看自己的任务，
    无需 admin.predict.audit（原权限过严导致用户端任务进度恢复 403）。

    OPT-T4-P1：合并进程内存储与 Celery(Redis) 存储两条后端的任务，
    此前列表只显示本进程内存任务，Celery 路径的任务对运维/前端不可见。
    Redis 不可用时静默跳过 celery 部分（与生成端点的回退语义一致）。
    """
    jobs = pdf_job_store.list_jobs(created_by=current_user.id)
    for item in jobs:
        item.setdefault("backend", "local")

    try:
        from app.tasks.pdf_report import list_jobs_from_redis

        celery_jobs = await asyncio.to_thread(list_jobs_from_redis, current_user.id)
        known_ids = {j["id"] for j in jobs}
        jobs.extend(j for j in celery_jobs if j["id"] not in known_ids)
    except Exception as exc:  # pragma: no cover - redis 异常已在内层降级为空列表
        logger.warning("[pdf-jobs] merge celery job list failed: %s", exc)

    # 统一按创建时间倒序（created_at 已规范化为 ISO 字符串，可直接排序）
    jobs.sort(key=lambda j: j.get("created_at") or "", reverse=True)
    return ok({"jobs": jobs, "total": len(jobs)})


# ── P-D: PDF 生成 Celery 队列化 ────────────────────────────────────
# 与 P1-4 的 asyncio.create_task (进程内异步) 并存, 提供跨节点调度能力.
# 当 Celery broker 不可用时, 自动回退到 daemon Thread (复用 PERF-P1-006 模式).


async def _dispatch_pdf_async(
    payload: UserRiskReportRequest,
    current_user: User,
) -> dict:
    """R-B: PDF 异步生成统一派发 — Celery 队列优先，broker 不可用降级线程.

    Returns:
        ok() 信封: {job_id, status:"queued", backend:"celery"|"thread-fallback", message}
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
        # SEC-FIX (M3): 同步 redis-py 调用阻塞事件循环, 移入线程池
        await asyncio.to_thread(save_job_to_redis, job_id, job_data)

        # 派发到 Celery 队列
        generate_pdf_report.delay(
            job_id=job_id,
            user_name=payload.user_name,
            risk_level=payload.risk_level,
            risk_trend=[item.model_dump() for item in payload.risk_trend],
            recommendations=payload.recommendations,
        )
        logger.info("[celery-pdf] submitted job_id=%s user=%s", job_id, payload.user_name)

    except Exception as exc:
        # Celery/Redis 不可用时回退到 daemon Thread
        logger.warning(
            "[celery-pdf] Celery submission failed, falling back to daemon Thread: %s",
            exc,
        )
        # 复用进程内 PdfJobStore 作为 fallback
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
    """P-D: 通过 Celery 队列异步生成 PDF 报告 (统一派发入口)."""
    return await _dispatch_pdf_async(payload, current_user)


@router.get(
    "/pdf/celery/{job_id}/status",
    response_model=ApiResponse,
    responses=COMMON_ERROR_RESPONSES,
    deprecated=True,
)
@limiter.limit("30/minute")
async def get_celery_pdf_job_status(
    request: Request,
    job_id: Annotated[str, Path()],
    current_user: Annotated[User, Depends(require_permission("admin.predict.audit"))],
) -> dict:
    """DEPRECATED (R-B): Celery PDF 任务状态别名，请改用 /pdf/{job_id}/status 统一端点."""
    return await get_pdf_job_status(request, job_id, current_user)


@router.get(
    "/pdf/celery/{job_id}/download",
    responses={**COMMON_ERROR_RESPONSES, **PDF_SUCCESS_RESPONSE},
    deprecated=True,
)
@limiter.limit("30/minute")
async def download_celery_pdf(
    request: Request,
    job_id: Annotated[str, Path()],
    current_user: Annotated[User, Depends(require_permission("admin.predict.audit"))],
) -> StreamingResponse:
    """DEPRECATED (R-B): Celery PDF 下载别名，请改用 /pdf/{job_id}/download 统一端点."""
    return await download_pdf(request, job_id, current_user)
