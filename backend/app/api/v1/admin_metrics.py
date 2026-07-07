"""管理后台 metrics summary 端点 (v1.32)

提供:
- 当前活跃指标快照
- 关键性能指标 (P50/P95/P99, RPS, 错误率)
- 用于运维监控和故障排查
"""

from __future__ import annotations

import time

from fastapi import APIRouter, Depends

from app.api.v1.version import RELEASE_VERSION
from app.core.config import settings
from app.core.deps import require_role
from app.core.metrics import (
    db_pool_size,
    http_requests_total,
    model_inference_total,
    websocket_connections_active,
)
from app.core.openapi_responses import COMMON_ERROR_RESPONSES

router = APIRouter(prefix="/admin", tags=["admin", "metrics"])


@router.get("/metrics-summary", responses=COMMON_ERROR_RESPONSES)
async def metrics_summary(
    # L-17 修复：使用直接导入替代 __import__ 动态导入，提高可读性和可维护性
    _admin=Depends(require_role("admin")),
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

    # C-API-4 修复：top_paths 模糊化，避免暴露完整 API 表面（含 admin 接口路径）。
    # 将具体 path 按模块前缀聚合，仅返回模块级统计。
    def _blur_path(path: str) -> str:
        parts = path.strip("/").split("/")
        if len(parts) >= 3:
            return "/" + "/".join(parts[:3]) + "/*"
        return path

    blurred_breakdown: dict[str, int] = {}
    for path, count in path_breakdown.items():
        blurred = _blur_path(path)
        blurred_breakdown[blurred] = blurred_breakdown.get(blurred, 0) + count

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
        # L-API-1 修复：版本号统一从 version.py 的 RELEASE_VERSION 读取，避免多处硬编码不一致
        "version": RELEASE_VERSION,
        # C-API-4 修复：移除 env 字段（可能泄露内部环境名如 staging-cn-beijing-1），改为布尔值
        "is_production": settings.app_env.lower() == "production",
        "http": {
            "total_requests": http_total,
            "5xx_errors": http_errors_5xx,
            "error_rate": round(error_rate, 4),
            # C-API-4 修复：返回模糊化后的 top_paths
            "top_paths": sorted(blurred_breakdown.items(), key=lambda x: -x[1])[:5],
        },
        "websocket": {
            "active_connections": ws_active,
        },
        "database": {
            "pool_size": db_pool,
        },
        "model_inference": model_stats,
    }
