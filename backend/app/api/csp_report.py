"""CSP Report API endpoint for receiving Content Security Policy violation reports."""

from __future__ import annotations

import logging
from typing import Any

from fastapi import APIRouter, HTTPException, Request, Response
from pydantic import BaseModel, ConfigDict, Field, ValidationError

from app.core.rate_limit import limiter

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/api/v1/csp-report", tags=["security"])

# Maximum payload size: 64KB
_MAX_CSP_REPORT_SIZE = 64 * 1024

# 浏览器/Reporting API 的字段别名 → CSPReportBody 的 alias
_CSP_FIELD_ALIASES = {
    "blocked-uri": "blocked-url",
    "blockedURL": "blocked-url",
    "document-uri": "document-url",
    "documentURL": "document-url",
    "lineNumber": "line-number",
    "sourceFile": "source-file",
    "effectiveDirective": "effective-directive",
    "violatedDirective": "violated-directive",
}


def _safe_log_value(value: object, max_len: int = 256) -> str:
    """日志字段截断并转义 CRLF，防止构造值伪造日志行。"""
    text = "" if value is None else str(value)
    return text.replace("\r", "\\r").replace("\n", "\\n")[:max_len]


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
    responses={
        400: {"description": "Invalid JSON or invalid Content-Length header"},
        413: {"description": "Payload too large (> 64KB)"},
        415: {"description": "Unsupported Content-Type"},
    },
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

    # REVIEW-2026-11-06 (M-01)：让 CSPReportBody 的 max_length 校验真正生效。
    # 原实现定义了模型却只声明 request 一个参数，模型从未被实例化，注释里
    # 「M-API-11 修复」的字段长度约束是不可达死代码；且日志直接取原始 JSON
    # 值，可注入换行伪造日志。多格式别名先归一化，再用同一模型校验。
    if not isinstance(report_data, dict):
        raise HTTPException(status_code=400, detail="Invalid CSP report body")
    normalized: dict[str, Any] = dict(report_data)
    for src, dst in _CSP_FIELD_ALIASES.items():
        if src in normalized and dst not in normalized:
            normalized[dst] = normalized[src]
    try:
        body = CSPReportBody.model_validate(normalized)
    except ValidationError:
        logger.warning("CSP report rejected: field too long or invalid type")
        raise HTTPException(status_code=400, detail="Invalid CSP report payload")

    directive = _safe_log_value(
        body.effective_directive or body.violated_directive or "unknown", 128
    )
    blocked = _safe_log_value(body.blocked_url or body.blocked_uri or "unknown")
    document = _safe_log_value(body.document_url or body.document_uri or "unknown")
    source = _safe_log_value(body.source_file or "unknown")
    line = _safe_log_value(body.line_number or 0, 32)

    logger.info(
        "CSP violation: directive=%s blocked=%s document=%s source=%s line=%s",
        directive,
        blocked,
        document,
        source,
        line,
    )

    return Response(status_code=204)
