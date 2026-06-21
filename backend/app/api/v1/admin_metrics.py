"""管理后台 metrics summary 端点 (v1.32)

提供:
- 当前活跃指标快照
- 关键性能指标 (P50/P95/P99, RPS, 错误率)
- 用于运维监控和故障排查
"""
from __future__ import annotations

import time

from fastapi import APIRouter, Depends
from fastapi.responses import PlainTextResponse

from app.core.config import settings
from app.core.metrics import (
    db_pool_size,
    http_request_duration_seconds,
    http_requests_total,
    model_inference_total,
    render_exposition,
    websocket_connections_active,
)

router = APIRouter(prefix="/admin", tags=["admin", "metrics"])


@router.get("/metrics-summary")
async def metrics_summary(
    _admin=Depends(__import__("app.core.deps", fromlist=["require_role"]).require_role("admin")),
) -> dict:
    """返回当前指标的人类可读摘要.

    注: 不依赖 Prometheus, 直接读取 in-memory 指标状态。
    适合运维排障时的快速检查。
    """
    # 收集所有 HTTP 指标
    http_total = 0
    http_errors_5xx = 0
    path_breakdown: dict[str, int] = {}
    for labels, value in http_requests_total.collect():
        path = labels.get("path", "unknown")
        status = labels.get("status", "0")
        count = int(value)
        http_total += count
        path_breakdown[path] = path_breakdown.get(path, 0) + count
        if status.startswith("5"):
            http_errors_5xx += count

    # 计算错误率
    error_rate = (http_errors_5xx / http_total) if http_total > 0 else 0.0

    # WebSocket 统计
    ws_active = 0
    for _labels, value in websocket_connections_active.collect():
        ws_active = int(value)
        break

    # DB 池
    db_pool = 0
    for _labels, value in db_pool_size.collect():
        db_pool = int(value)
        break

    # 模型推理统计
    model_stats: dict[str, dict[str, int]] = {}
    for labels, value in model_inference_total.collect():
        model_name = labels.get("model_name", "unknown")
        status = labels.get("status", "unknown")
        count = int(value)
        if model_name not in model_stats:
            model_stats[model_name] = {"success": 0, "error": 0}
        model_stats[model_name][status] = model_stats[model_name].get(status, 0) + count

    return {
        "timestamp": int(time.time()),
        "version": "v1.32-observability-complete",
        "env": settings.app_env,
        "http": {
            "total_requests": http_total,
            "5xx_errors": http_errors_5xx,
            "error_rate": round(error_rate, 4),
            "top_paths": sorted(path_breakdown.items(), key=lambda x: -x[1])[:5],
        },
        "websocket": {
            "active_connections": ws_active,
        },
        "database": {
            "pool_size": db_pool,
        },
        "model_inference": model_stats,
    }
