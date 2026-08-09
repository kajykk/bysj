"""模型注册表 (V2) 端点: 查看注册表 / 激活训练产物接推理链."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.core.deps import require_permission
from app.core.openapi_responses import COMMON_ERROR_RESPONSES
from app.core.response import ok
from app.models.user import User
from app.schemas.common import ApiResponse

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get(
    "/model-registry", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES
)
async def list_model_registry(
    _: Annotated[User, Depends(require_permission("admin.predict.audit"))],
) -> dict:
    """列出 Model Registry V2 中的所有模型记录 (含状态/指标/产物路径)."""
    from app.core.model_registry_v2 import get_registry

    try:
        return ok({"models": get_registry().list_models()})
    except Exception as exc:
        logger.exception("list_model_registry failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"注册表读取失败: {exc}") from exc


@router.get(
    "/model-registry/{model_id}/shadow",
    response_model=ApiResponse,
    responses=COMMON_ERROR_RESPONSES,
)
async def get_shadow_stats(
    model_id: str,
    _: Annotated[User, Depends(require_permission("admin.predict.audit"))],
) -> dict:
    """查询候选产物的影子对拍统计 (一致率/概率差异/样本数)."""
    from app.services.shadow_comparison_service import (
        get_shadow_comparison_service,
    )

    service = get_shadow_comparison_service()
    stats = service.get_stats(model_id)
    # 附带 registry 记录中的持久化指标
    from app.core.model_registry_v2 import get_registry

    record = get_registry().get_model(model_id)
    if record is not None:
        stats["registry_metrics"] = {
            k: v
            for k, v in record.metrics.items()
            if k.startswith("shadow_")
        }
    return ok(stats)


@router.post(
    "/model-registry/{model_id}/activate",
    response_model=ApiResponse,
    responses=COMMON_ERROR_RESPONSES,
)
async def activate_registry_model(
    model_id: str,
    _: Annotated[User, Depends(require_permission("admin.predict.audit"))],
    force: bool = False,
) -> dict:
    """将验证训练产物提升为 PRODUCTION, 使其接入推理链.

    CANDIDATE -> STAGING -> PRODUCTION 逐级提升; 提升成功后
    resolve_model_path 对该 model_id 优先返回产物路径, 推理链生效.

    影子对拍守卫: 若候选已有足够影子样本 (>= shadow_production_min_samples)
    且一致率低于 shadow_production_min_agreement, 拒绝激活; 传 force=true 强制.
    """
    from app.core.model_registry_v2 import activate_training_model
    from app.services.shadow_comparison_service import (
        get_shadow_comparison_service,
    )

    shadow_service = get_shadow_comparison_service()
    shadow_service.commit_shadow_stats(model_id)
    acceptable, reason = shadow_service.is_shadow_acceptable(model_id, force=force)
    if not acceptable:
        raise HTTPException(status_code=422, detail=f"影子对拍未达标: {reason}")

    record = activate_training_model(model_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"模型 {model_id} 激活失败或状态转换不合法")
    logger.info(
        "model %s activated to PRODUCTION (shadow_decision=%s)", model_id, reason
    )
    return ok({"model": record.to_dict(), "shadow_decision": reason})


@router.post(
    "/model-registry/auto-rollback",
    response_model=ApiResponse,
    responses=COMMON_ERROR_RESPONSES,
)
async def run_auto_rollback_check(
    _: Annotated[User, Depends(require_permission("admin.predict.audit"))],
) -> dict:
    """手动触发一次自动回退检查: 回退率超阈值的 PRODUCTION 产物降级回 CANDIDATE."""
    from app.services.registry_auto_rollback import check_auto_rollback

    try:
        results = check_auto_rollback()
    except Exception as exc:
        logger.exception("auto-rollback check failed: %s", exc)
        raise HTTPException(status_code=500, detail=f"回退检查失败: {exc}") from exc
    return ok({"results": results})


@router.post(
    "/model-registry/{model_id}/rollback",
    response_model=ApiResponse,
    responses=COMMON_ERROR_RESPONSES,
)
async def rollback_registry_model(
    model_id: str,
    _: Annotated[User, Depends(require_permission("admin.predict.audit"))],
) -> dict:
    """人工回退: 将 PRODUCTION 训练产物降级为 CANDIDATE, 推理链回退静态模型."""
    from app.core.model_registry_v2 import rollback_training_model

    record = rollback_training_model(model_id)
    if record is None:
        raise HTTPException(status_code=404, detail=f"模型 {model_id} 回退失败或状态转换不合法")
    logger.info("model %s rolled back to CANDIDATE (manual)", model_id)
    return ok(record.to_dict())