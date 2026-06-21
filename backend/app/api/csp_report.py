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


class CSPReportBody(BaseModel):
    """CSP report body schema (CSP Level 3)."""

    blocked_url: str | None = Field(None, alias="blocked-url")
    blocked_uri: str | None = Field(None, alias="blockedURI")
    document_url: str | None = Field(None, alias="document-url")
    document_uri: str | None = Field(None, alias="documentURI")
    effective_directive: str | None = Field(None, alias="effective-directive")
    original_policy: str | None = Field(None, alias="original-policy")
    referrer: str | None = None
    script_sample: str | None = Field(None, alias="script-sample")
    status_code: int | None = Field(None, alias="status-code")
    violated_directive: str | None = Field(None, alias="violated-directive")
    source_file: str | None = Field(None, alias="source-file")
    line_number: int | None = Field(None, alias="line-number")
    column_number: int | None = Field(None, alias="column-number")
    disposition: str | None = None

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
@limiter.limit("60/minute")
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
    # Check payload size
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            content_length_value = int(content_length)
        except (ValueError, TypeError):
            logger.warning("CSP report rejected: invalid Content-Length header (%r)", content_length)
            raise HTTPException(status_code=400, detail="Invalid Content-Length header")
        if content_length_value > _MAX_CSP_REPORT_SIZE:
            logger.warning("CSP report rejected: payload too large (%s bytes)", content_length)
            raise HTTPException(status_code=413, detail="Payload too large")

    # Read body
    body_bytes = await request.body()
    if len(body_bytes) > _MAX_CSP_REPORT_SIZE:
        logger.warning("CSP report rejected: payload too large (%d bytes)", len(body_bytes))
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
