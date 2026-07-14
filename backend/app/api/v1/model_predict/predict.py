"""预测端点: tabular / text / physiological / fusion 及复核任务调度."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.db_breaker import CircuitBreakerOpenError
from app.core.deps import require_permission
from app.core.openapi_responses import COMMON_ERROR_RESPONSES
from app.core.rate_limit import limiter
from app.core.response import ok
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.model_predict import (
    FusionPredictRequest,
    PhysiologicalPredictRequest,
    TabularPredictRequest,
    TextPredictRequest,
)
from app.services.model_predict_service import ModelPredictService

from ._common import (
    _assessment_save_tasks,
    _log_task_exception,
    _save_assessment_sync,
    logger,
)

router = APIRouter()


async def _create_review_task(result: dict, user_id: int) -> None:
    """异步创建复核任务 (fire-and-forget 场景使用独立 session).

    PERF-P0-001 修复: 从 predict_fusion 同步路径抽取为独立异步函数,
    使用独立 session 避免与请求 session 共享事务边界.

    AsyncSessionLocal 通过函数内 import 引用包级绑定, 使测试
    patch("app.api.v1.model_predict.AsyncSessionLocal") 能正确生效.
    """
    from app.api.v1.model_predict import AsyncSessionLocal
    from app.schemas.review import ReviewPriority, ReviewTaskCreate
    from app.services.review_service import ReviewService

    # 确定优先级
    priority = ReviewPriority.NORMAL_REVIEW
    if result.get("crisis_override"):
        priority = ReviewPriority.CRISIS_REVIEW
    elif result.get("risk_level", 0) >= 3:
        priority = ReviewPriority.HIGH_RISK_REVIEW

    review_data = ReviewTaskCreate(
        user_id=user_id,
        risk_level=result.get("risk_level", 0),
        risk_score=result.get("risk_score", 0),
        review_triggers=result.get("review_triggers", []),
        crisis_override=result.get("crisis_override", False),
        priority=priority,
    )
    async with AsyncSessionLocal() as db:
        review_service = ReviewService(db)
        review_task = await review_service.create_review_task(review_data)
        await db.commit()
        logger.info("Auto-created review task %s for user %s", review_task.id, user_id)


def _create_review_task_sync(result: dict, user_id: int) -> None:
    """fire-and-forget 创建复核任务.

    PERF-P0-001 修复: 与 _save_assessment_sync 一致的异步调度策略,
    任务引用存入 _assessment_save_tasks 防止 GC 回收.
    """
    try:
        task = asyncio.ensure_future(_create_review_task(result, user_id))
        _assessment_save_tasks.add(task)
        task.add_done_callback(_assessment_save_tasks.discard)
        task.add_done_callback(_log_task_exception)
        # R-005 修复: 注册可观测性指标 (scheduled/succeeded/failed/cancelled + duration)
        from app.core.fire_forget_metrics import register_task

        register_task(task, "review_task_create")
    except Exception as exc:
        logger.error("Failed to schedule review task creation: %s", exc)


@router.post(
    "/predict/tabular", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES
)
@limiter.limit("20/minute")
async def predict_tabular(
    request: Request,
    payload: TabularPredictRequest,
    current_user: Annotated[User, Depends(require_permission("user.predict.use"))],
) -> dict:
    from app.core.kill_switch import is_model_paused
    from app.core.metrics import track_model_inference

    # Phase 3: 暂停开关检查
    if await is_model_paused():
        raise HTTPException(status_code=503, detail="模型预测服务已暂停，请联系管理员")

    service = ModelPredictService()
    with track_model_inference("tabular"):
        try:
            result = await service.predict_tabular(payload.features)
        except CircuitBreakerOpenError:
            # STAB-P1-002: 熔断器打开, 直接放行 HTTPException(503)
            raise
        except asyncio.TimeoutError as exc:
            logger.warning("表格预测推理超时: %s", exc)
            raise HTTPException(
                status_code=503, detail="模型推理超时，请稍后重试"
            ) from exc
        except FileNotFoundError as exc:
            logger.error("表格预测模型加载失败: %s", exc)
            raise HTTPException(status_code=503, detail="模型服务暂时不可用") from exc
        except Exception as exc:
            logger.error("表格预测失败: %s", exc)
            raise HTTPException(
                status_code=422, detail="预测失败，请检查输入特征"
            ) from exc
    # L-4 修复：经核对 predict_tabular / predict_text / predict_physiological 三个端点
    # 均使用 _save_assessment_sync（内部 asyncio.ensure_future 的 fire-and-forget 策略），
    # 策略已一致，无需改为 await
    _save_assessment_sync(
        result, current_user.id, "structured", {"features": payload.features}
    )
    return ok(result)


@router.post(
    "/predict/text", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES
)
@limiter.limit("20/minute")
async def predict_text(
    request: Request,
    payload: TextPredictRequest,
    current_user: Annotated[User, Depends(require_permission("user.predict.use"))],
) -> dict:
    from app.core.kill_switch import is_model_paused
    from app.core.metrics import track_model_inference

    # Phase 3: 暂停开关检查
    if await is_model_paused():
        raise HTTPException(status_code=503, detail="模型预测服务已暂停，请联系管理员")

    service = ModelPredictService()
    with track_model_inference("text"):
        try:
            result = await service.predict_text(payload.text)
        except CircuitBreakerOpenError:
            # STAB-P1-002: 熔断器打开, 直接放行 HTTPException(503)
            raise
        except asyncio.TimeoutError as exc:
            logger.warning("文本预测推理超时: %s", exc)
            raise HTTPException(
                status_code=503, detail="模型推理超时，请稍后重试"
            ) from exc
        except FileNotFoundError as exc:
            logger.error("文本预测模型加载失败: %s", exc)
            raise HTTPException(status_code=503, detail="模型服务暂时不可用") from exc
        except Exception as exc:
            logger.error("文本预测失败: %s", exc)
            raise HTTPException(
                status_code=422, detail="预测服务异常，请稍后重试"
            ) from exc

    # v1.17: 检测到危机时记录审计日志
    if result.get("crisis_detected"):
        try:
            from app.core.database import AsyncSessionLocal
            from app.schemas.review import CrisisEventCreate
            from app.services.review_service import CrisisEventService

            async with AsyncSessionLocal() as db:
                crisis_service = CrisisEventService(db)
                crisis_data = CrisisEventCreate(
                    user_id=current_user.id,
                    trigger_source="text",
                    crisis_keywords=result.get("crisis_keywords", []),
                    crisis_score=result.get("crisis_score", 0),
                    input_summary=payload.text[:200] if payload.text else None,
                )
                await crisis_service.record_crisis_event(crisis_data)
                logger.info("Crisis event recorded for user %s", current_user.id)
        except Exception as exc:
            logger.error("Failed to record crisis event: %s", exc)
            # 不影响预测结果返回

    _save_assessment_sync(result, current_user.id, "text", {"text": payload.text})
    return ok(result)


@router.post(
    "/predict/physiological",
    response_model=ApiResponse,
    responses=COMMON_ERROR_RESPONSES,
)
@limiter.limit("20/minute")
async def predict_physiological(
    request: Request,
    payload: PhysiologicalPredictRequest,
    current_user: Annotated[User, Depends(require_permission("user.predict.use"))],
) -> dict:
    from app.core.kill_switch import is_model_paused
    from app.core.metrics import track_model_inference

    # Phase 3: 暂停开关检查
    if await is_model_paused():
        raise HTTPException(status_code=503, detail="模型预测服务已暂停，请联系管理员")

    service = ModelPredictService()
    with track_model_inference("physiological"):
        try:
            result = await service.predict_physiological(payload.physiological)
        except CircuitBreakerOpenError:
            # STAB-P1-002: 熔断器打开, 直接放行 HTTPException(503)
            raise
        except asyncio.TimeoutError as exc:
            logger.warning("生理预测推理超时: %s", exc)
            raise HTTPException(
                status_code=503, detail="模型推理超时，请稍后重试"
            ) from exc
        except FileNotFoundError as exc:
            logger.error("生理预测模型加载失败: %s", exc)
            raise HTTPException(status_code=503, detail="模型服务暂时不可用") from exc
        except Exception as exc:
            logger.error("生理预测失败: %s", exc)
            raise HTTPException(status_code=422, detail="预测失败，请检查输入") from exc
    _save_assessment_sync(
        result,
        current_user.id,
        "physiological",
        {"physiological": payload.physiological},
    )
    return ok(result)


@router.post(
    "/predict/fusion", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES
)
@limiter.limit("20/minute")
async def predict_fusion(
    request: Request,
    payload: FusionPredictRequest,
    current_user: Annotated[User, Depends(require_permission("user.predict.use"))],
) -> dict:
    from app.core.kill_switch import is_model_paused
    from app.core.metrics import track_model_inference

    # Phase 3: 暂停开关检查
    if await is_model_paused():
        raise HTTPException(status_code=503, detail="模型预测服务已暂停，请联系管理员")

    service = ModelPredictService()
    with track_model_inference("fusion"):
        try:
            result = await service.predict_fusion(
                features=payload.features,
                text=payload.text,
                physiological=payload.physiological,
            )
        except CircuitBreakerOpenError:
            # STAB-P1-002: 熔断器打开, 直接放行 HTTPException(503)
            raise
        except asyncio.TimeoutError as exc:
            logger.warning("融合预测推理超时: %s", exc)
            raise HTTPException(
                status_code=503, detail="模型推理超时，请稍后重试"
            ) from exc
        except FileNotFoundError as exc:
            logger.error("融合预测模型加载失败: %s", exc)
            raise HTTPException(status_code=503, detail="模型服务暂时不可用") from exc
        except Exception as exc:
            logger.error("融合预测失败: %s", exc)
            raise HTTPException(
                status_code=422, detail="融合预测失败，请检查输入"
            ) from exc

    # v1.17: 自动创建复核任务
    # PERF-P0-001 修复: 改为 fire-and-forget 异步任务, 不阻塞响应
    # (与其他三个预测端点 _save_assessment_sync 策略一致)
    if result.get("review_required") or result.get("crisis_override"):
        _create_review_task_sync(result, current_user.id)

    # PERF-P0-001 修复: 改为 fire-and-forget, 与其他三个预测端点一致
    _save_assessment_sync(
        result,
        current_user.id,
        "fusion",
        {
            "features": payload.features,
            "text": payload.text,
            "physiological": payload.physiological,
        },
    )

    return ok(result)
