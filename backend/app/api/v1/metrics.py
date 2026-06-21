"""Prometheus /metrics 端点 (v1.30)

提供 HTTP API `/api/v1/metrics`, 以 Prometheus exposition format 输出系统指标。

CRIT-007 修复：添加访问令牌鉴权，防止未授权访问系统内部指标。
"""
from __future__ import annotations

import logging
import secrets

from fastapi import APIRouter, Header, HTTPException
from fastapi.responses import PlainTextResponse

from app.core.config import settings
from app.core.metrics import (
    db_pool_size,
    render_exposition,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["metrics"])


@router.get("/metrics", response_class=PlainTextResponse)
async def get_metrics(
    authorization: str | None = Header(default=None, alias="Authorization"),
) -> PlainTextResponse:
    """Prometheus exposition 端点.

    CRIT-007 修复：添加访问令牌鉴权。
    生产环境必须配置 METRICS_ACCESS_TOKEN，Prometheus 需在
    Authorization header 中发送 "Bearer <token>"。

    包含:
    - http_requests_total{method,path,status}
    - http_request_duration_seconds{method,path}
    - model_inference_total{model_name,status}
    - model_inference_duration_seconds{model_name}
    - websocket_connections_active
    - db_pool_size
    - app_info
    """
    # CRIT-007 修复：Metrics 端点鉴权
    expected_token = settings.metrics_access_token
    if expected_token:
        # 已配置令牌：必须提供正确的 Bearer token
        if not authorization or not authorization.startswith("Bearer "):
            raise HTTPException(status_code=401, detail="Unauthorized: missing bearer token")
        provided = authorization.removeprefix("Bearer ").strip()
        if not secrets.compare_digest(provided, expected_token):
            raise HTTPException(status_code=403, detail="Forbidden: invalid metrics token")
    elif settings.app_env.lower() == "production":
        # 生产环境且未配置令牌：拒绝访问
        raise HTTPException(
            status_code=503,
            detail="Metrics disabled: METRICS_ACCESS_TOKEN not configured",
        )
    # 开发环境且未配置令牌：允许访问（便于本地调试）

    # 抓取 DB 连接池状态 (如果有)
    try:
        from app.core.database import engine

        pool = engine.pool
        db_pool_size.set(float(pool.size()))
    except Exception as exc:
        # P1-E 修复：监控指标采集失败必须记录日志，便于运维发现 DB 连接池监控失效
        logger.warning("db_pool_size metric collection failed: %s", exc)

    body = render_exposition()
    return PlainTextResponse(content=body, media_type="text/plain; version=0.0.4; charset=utf-8")
