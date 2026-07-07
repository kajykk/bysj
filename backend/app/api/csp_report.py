"""CSP Report API endpoint for receiving Content Security Policy violation reports."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field

from app.core.rate_limit import limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/csp-report", tags=["security"])

# Maximum payload size: 64KB
_MAX_CSP_REPORT_SIZE = 64 * 1024


class CSPReportBody(BaseModel):
    """CSP report body schema (CSP Level 3).

    M-API-11 修复：对所有字符串字段添加 max_length 限制，防止超大字段导致日志膨胀或 DoS。
    """

    blocked_url: str | None = Field(None, alias="blocked-url", max_length=2048)
    blocked_uri: str | None = Field(None, alias="blockedURI", max_length=2048)
    document_url: str | None = Field(None, alias="document-url", max_length=2048)
    document_uri: str | None = Field(None, alias="documentURI", max_length=2048)
    effective_directive: str | None = Field(
        None, alias="effective-directive", max_length=128
    )
    original_policy: str | None = Field(None, alias="original-policy", max_length=8192)
    referrer: str | None = Field(None, max_length=2048)
    script_sample: str | None = Field(None, alias="script-sample", max_length=4096)
    status_code: int | None = Field(None, alias="status-code")
    violated_directive: str | None = Field(
        None, alias="violated-directive", max_length=128
    )
    source_file: str | None = Field(None, alias="source-file", max_length=2048)
    line_number: int | None = Field(None, alias="line-number")
    column_number: int | None = Field(None, alias="column-number")
    disposition: str | None = Field(None, max_length=64)

    model_config = ConfigDict(populate_by_name=True)


class CSPReportPayload(BaseModel):
    """CSP report payload wrapper."""

    csp_report: CSPReportBody = Field(..., alias="csp-report")

    model_config = ConfigDict(populate_by_name=True)


@router.post(
    "",
    summary="Receive CSP violation reports",
    status_code=204,
    response_class=Response,
)
# M-API-11 修复：CSP report 端点无需鉴权（浏览器无法携带 token），通过限流防止滥用
@limiter.limit("30/minute")
async def receive_csp_report(request: Request) -> Response:
    """Receive and log Content Security Policy violation reports.

    Supports multiple Content-Type formats:
    - application/csp-report
    - application/json
    - application/reports+json

    Args:
        request: FastAPI request object

    Returns:
        204 No Content on success

    Raises:
        HTTPException: 413 if payload too large, 400 if invalid
    """
    # L-API-9 修复：校验 Content-Type，仅允许 CSP 报告标准类型，防止滥用
    content_type = request.headers.get("content-type", "")
    # 去掉 charset 等参数后比较，如 "application/json; charset=utf-8" -> "application/json"
    normalized_ct = content_type.split(";")[0].strip().lower()
    if normalized_ct not in (
        "application/json",
        "application/csp-report",
        "application/reports+json",
    ):
        logger.warning("CSP report rejected: invalid Content-Type (%r)", content_type)
        raise HTTPException(status_code=415, detail="Unsupported Content-Type")

    # Check payload size
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            content_length_value = int(content_length)
        except (ValueError, TypeError):
            logger.warning(
                "CSP report rejected: invalid Content-Length header (%r)",
                content_length,
            )
            raise HTTPException(status_code=400, detail="Invalid Content-Length header")
        if content_length_value > _MAX_CSP_REPORT_SIZE:
            logger.warning(
                "CSP report rejected: payload too large (%s bytes)", content_length
            )
            raise HTTPException(status_code=413, detail="Payload too large")

    # Read body
    body_bytes = await request.body()
    if len(body_bytes) > _MAX_CSP_REPORT_SIZE:
        logger.warning(
            "CSP report rejected: payload too large (%d bytes)", len(body_bytes)
        )
        raise HTTPException(status_code=413, detail="Payload too large")

    if not body_bytes:
        logger.debug("CSP report received: empty body")
        return Response(status_code=204)

    # Parse JSON
    try:
        data: dict[str, Any] = await request.json()
    except Exception:
        logger.warning("CSP report rejected: invalid JSON")
        raise HTTPException(status_code=400, detail="Invalid JSON")

    if not data:
        logger.debug("CSP report received: empty JSON")
        return Response(status_code=204)

    # Normalize payload (handle both csp-report and cspReport keys)
    report_data: dict[str, Any] | None = None
    if "csp-report" in data:
        report_data = data["csp-report"]
    elif "cspReport" in data:
        report_data = data["cspReport"]
    elif "type" in data and data.get("type") == "csp-violation":
        # Reporting API format
        report_data = data.get("body", {})
    else:
        # Try to use top-level as report body
        report_data = data

    if not report_data:
        logger.debug("CSP report received: no report body")
        return Response(status_code=204)

    # Sanitize and extract key fields
    directive = (
        report_data.get("effective-directive")
        or report_data.get("violated-directive")
        or "unknown"
    )
    blocked = (
        report_data.get("blocked-url")
        or report_data.get("blockedURI")
        or report_data.get("blocked-uri")
        or "unknown"
    )
    document = (
        report_data.get("document-url")
        or report_data.get("documentURI")
        or report_data.get("document-uri")
        or "unknown"
    )
    source = report_data.get("source-file") or "unknown"
    line = report_data.get("line-number") or report_data.get("lineNumber") or 0

    # Log the violation
    logger.info(
        "CSP violation: directive=%s blocked=%s document=%s source=%s line=%s",
        directive,
        blocked,
        document,
        source,
        line,
    )

    return Response(status_code=204)
