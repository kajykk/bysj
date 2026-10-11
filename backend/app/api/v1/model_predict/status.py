"""状态/调试/训练任务端点."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends

from app.core.cache import cache_get, cache_set
from app.core.deps import require_permission
from app.core.openapi_responses import COMMON_ERROR_RESPONSES
from app.core.response import ok
from app.core.tenant_context import require_platform_permission
from app.models.user import User
from app.schemas.common import ApiResponse
from app.services.model_predict_service import ModelPredictService

logger = logging.getLogger(__name__)

router = APIRouter()

# PERF-P1-002: model_status 端点 30s Redis 缓存
# 避免每次请求遍历所有模型文件 stat()，降低磁盘 I/O 与响应延迟
_MODEL_STATUS_CACHE_KEY = "model_status:v1"
_MODEL_STATUS_CACHE_TTL = 30  # 秒


async def _get_cached_model_status() -> dict:
    """PERF-P1-002: 获取模型状态，优先读缓存，miss 时计算并回填.

    缓存失败时降级为直接计算，不影响请求可用性.
    """
    cached = await cache_get(_MODEL_STATUS_CACHE_KEY)
    if cached is not None:
        logger.debug("[model_status] cache hit")
        return cached
    # cache miss: 计算并回填缓存
    service = ModelPredictService()
    status = service.get_model_status()
    try:
        await cache_set(_MODEL_STATUS_CACHE_KEY, status, _MODEL_STATUS_CACHE_TTL)
    except Exception as exc:
        logger.warning("[model_status] cache_set failed: %s", exc)
    return status


@router.get("/status", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def model_status(
    _: Annotated[User, Depends(require_permission("user.predict.use"))],
) -> dict:
    # PERF-P1-002: 30s Redis 缓存，避免重复 stat() 所有模型文件
    status = await _get_cached_model_status()
    return ok(status)


@router.get(
    "/debug/performance", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES
)
async def model_performance_debug(
    _: Annotated[User, Depends(require_platform_permission("admin.predict.audit"))],
) -> dict:
    # PERF-P1-002: 复用 model_status 缓存，仅提取 performance 部分
    status = await _get_cached_model_status()
    return ok(status.get("performance", {}))


@router.get(
    "/training/jobs", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES
)
async def list_training_jobs(
    _: Annotated[User, Depends(require_platform_permission("admin.predict.audit"))],
) -> dict:
    """列出训练任务。

    P0-FIX-2026-10-11: 原权限是 ``user.predict.use`` —— 那是**普通学生**权限
    （与 ``/predict/*`` 同级），但 ``/training/jobs`` 属后台运维域：兄弟端点
    ``POST /experiment/train`` 本身就要求 ``admin.predict.audit``。
    结果任何登录用户都能列出全平台训练任务（含数据集名、训练参数、模型指标），
    跨租户且越权。
    """
    service = ModelPredictService()
    return ok({"jobs": service.list_training_jobs()})


@router.get(
    "/training/jobs/{job_id}",
    response_model=ApiResponse,
    responses=COMMON_ERROR_RESPONSES,
)
async def get_training_job(
    job_id: str,
    _: Annotated[User, Depends(require_platform_permission("admin.predict.audit"))],
) -> dict:
    """按 id 读训练任务详情。

    P0-FIX-2026-10-11: 同 ``list_training_jobs``，权限由学生级提到平台管理员级。
    此处原先是典型 IDOR —— 凭一个 job_id 即可读到不属于自己的任务详情。
    注意：``job_id`` 仍未做归属校验（任务记录里没有 tenant 字段），
    平台管理员可见全平台任务属既定语义；租户级隔离需另建归属字段，
    已记入 P1。
    """
    service = ModelPredictService()
    return ok(service.get_training_job(job_id))
