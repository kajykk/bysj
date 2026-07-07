"""实验管理端点: 数据集导入 / 训练 / 评估 / 对比."""

from __future__ import annotations

import asyncio
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.deps import require_permission
from app.core.openapi_responses import COMMON_ERROR_RESPONSES
from app.core.rate_limit import limiter
from app.core.response import ok
from app.models.user import User
from app.schemas.common import ApiResponse
from app.schemas.model_predict import (
    CompareRequest,
    DatasetImportRequest,
    EvaluateRequest,
    TrainRequest,
)
from app.services.model_predict_service import (
    ModelExperimentService,
    ModelPredictService,
)

router = APIRouter()


@router.post(
    "/experiment/import", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES
)
@limiter.limit("5/minute")
async def import_dataset(
    request: Request,
    payload: DatasetImportRequest,
    _: Annotated[User, Depends(require_permission("admin.predict.audit"))],
) -> dict:
    service = ModelExperimentService()
    try:
        result = await asyncio.to_thread(
            service.import_dataset,
            payload.dataset_name,
            payload.source_type,
            payload.train_ratio,
            payload.val_ratio,
            payload.test_ratio,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ok(result)


@router.post(
    "/experiment/train", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES
)
@limiter.limit("5/minute")
async def train_model(
    request: Request,
    payload: TrainRequest,
    _: Annotated[User, Depends(require_permission("admin.predict.audit"))],
) -> dict:
    service = ModelPredictService()
    try:
        result = service.start_training_job(
            payload.dataset_name,
            payload.model_name,
            payload.epochs,
            payload.batch_size,
            payload.learning_rate,
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ok(result)


@router.post(
    "/experiment/evaluate", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES
)
@limiter.limit("5/minute")
async def evaluate_model(
    request: Request,
    payload: EvaluateRequest,
    _: Annotated[User, Depends(require_permission("admin.predict.audit"))],
) -> dict:
    """PERF-P1-006: 异步模型评估.

    立即返回 job_id, 评估在 Celery worker 中执行 (替代原 asyncio.to_thread 阻塞调用).
    客户端通过 GET /training/jobs/{job_id} 轮询状态.
    """
    service = ModelPredictService()
    try:
        result = service.start_evaluate_job(
            payload.dataset_name, payload.model_name, payload.split
        )
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ok(result)


@router.post(
    "/experiment/compare", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES
)
@limiter.limit("5/minute")
async def compare_models(
    request: Request,
    payload: CompareRequest,
    _: Annotated[User, Depends(require_permission("admin.predict.audit"))],
) -> dict:
    """PERF-P1-006: 异步多模型对比.

    立即返回 job_id, 对比在 Celery worker 中执行 (替代原 asyncio.to_thread 阻塞调用).
    客户端通过 GET /training/jobs/{job_id} 轮询状态.
    """
    service = ModelPredictService()
    try:
        result = service.start_compare_job(payload.dataset_name, payload.model_names)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ok(result)
