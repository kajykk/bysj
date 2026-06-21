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
    FusionPredictRequest,
    FusionPredictResult,
    PhysiologicalPredictRequest,
    PhysiologicalPredictResult,
    TabularPredictRequest,
    TextPredictRequest,
    TrainRequest,
)
from app.services.model_predict_service import ModelExperimentService, ModelPredictService
from app.models.risk import RiskAssessment
from app.core.database import AsyncSessionLocal
from app.services.risk_service import RiskService
from sqlalchemy.ext.asyncio import AsyncSession

import logging

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/model", tags=["model"])


async def save_assessment_result(
    result: dict,
    user_id: int,
    assessment_type: str,
    payload: dict | None = None,
    db: AsyncSession | None = None,
) -> None:
    """保存评估结果到数据库。

    MAJ-021 修复：支持传入现有 session，避免跨 session 事务边界问题。
    - 若传入 db：使用现有 session，不自动 commit（由调用方管理事务）
    - 若未传入 db：创建新 session 并自动 commit（用于 fire-and-forget 场景）
    """
    async def _do_save(session: AsyncSession, *, auto_commit: bool) -> None:
        structured_score: float | None = None
        text_score: float | None = None
        physio_score: float | None = None

        if assessment_type == "structured":
            structured_score = result.get("risk_score") if result.get("risk_score") is not None else None
        elif assessment_type == "text":
            sentiment = result.get("sentiment_score")
            text_score = round(sentiment * 100, 2) if sentiment is not None else result.get("risk_score")
        elif assessment_type == "physiological":
            physio_score = result.get("risk_score") if result.get("risk_score") is not None else None
        elif assessment_type == "fusion":
            fusion_detail = result.get("fusion_detail", {})
            ms = fusion_detail.get("modality_scores", {})
            structured_ms = ms.get("structured", {})
            text_ms = ms.get("text", {})
            physio_ms = ms.get("physiological", {})
            structured_score = structured_ms.get("score") if structured_ms else None
            text_score = text_ms.get("score") if text_ms else None
            physio_score = physio_ms.get("score") if physio_ms else None

        models_used = result.get("model_used", [])
        if isinstance(models_used, str):
            models_used = [models_used]

        risk_factors = result.get("risk_factors") or _generate_risk_factors(result, assessment_type, payload)

        risk_score_value = result.get("risk_score") or 0
        if risk_score_value <= 0:
            logger.info("Skipped saving %s assessment for user %s (risk_score=%s, empty input likely)", assessment_type, user_id, risk_score_value)
            return

        risk = RiskAssessment(
            user_id=user_id,
            risk_score=risk_score_value,
            risk_level=result.get("risk_level") or 0,
            structured_score=structured_score,
            text_score=text_score,
            physiological_score=physio_score,
            models_used=models_used,
            risk_factors=risk_factors,
            assessment_type=assessment_type,
        )
        session.add(risk)
        await session.flush()
        risk_service = RiskService(session)
        warning = await risk_service.trigger_warning_for_risk(risk)
        await risk_service.generate_intervention_for_risk(risk)
        if auto_commit:
            await session.commit()
        logger.info(
            "Saved %s assessment for user %s (s=%.1f t=%.1f p=%.1f factors=%d warning_id=%s intervention_checked=%s)",
            assessment_type, user_id,
            structured_score or 0, text_score or 0, physio_score or 0,
            len(risk_factors),
            warning.id if warning else None,
            risk.risk_level >= 2,
        )

    if db is not None:
        # MAJ-021 修复：使用调用方传入的 session，不自动 commit
        await _do_save(db, auto_commit=False)
    else:
        # 无传入 session：创建新 session 并自动 commit（fire-and-forget）
        async with AsyncSessionLocal() as new_db:
            await _do_save(new_db, auto_commit=True)


def _save_assessment_sync(result: dict, user_id: int, assessment_type: str, payload: dict | None = None) -> None:
    try:
        asyncio.ensure_future(save_assessment_result(result, user_id, assessment_type, payload))
    except Exception as exc:
        logger.error("Failed to schedule assessment save: %s", exc)


STRUCTURED_FEATURE_LABELS: dict[str, str] = {
    "stress_level": "压力水平",
    "anxiety": "焦虑程度",
    "sleep_duration": "睡眠时长",
    "social_support": "社会支持",
    "financial_pressure": "经济压力",
    "family_history": "家族病史",
    "academic_pressure": "学业压力",
    "panic_attack": "惊恐发作",
    "exercise_frequency": "运动频率",
}
STRUCTURED_HIGH_RISK_THRESHOLDS: dict[str, float] = {
    "stress_level": 3,
    "anxiety": 3,
    "financial_pressure": 3,
    "academic_pressure": 3,
    "panic_attack": 1,
}
STRUCTURED_LOW_RISK_THRESHOLDS: dict[str, float] = {
    "sleep_duration": 5,
    "social_support": 2,
    "exercise_frequency": 1,
}

PHYSIO_FEATURE_LABELS: dict[str, str] = {
    "sleep_hours": "睡眠时长",
    "sleep_quality": "睡眠质量",
    "heart_rate": "心率",
    "steps": "步数",
    "exercise_minutes": "运动时长",
    "systolic_bp": "收缩压",
    "diastolic_bp": "舒张压",
}


def _generate_risk_factors(result: dict, assessment_type: str, payload: dict | None = None) -> list[dict]:
    if assessment_type == "structured":
        return _generate_structured_factors(result, payload)
    elif assessment_type == "physiological":
        return _generate_physio_factors(result, payload)
    elif assessment_type == "text":
        return _generate_text_factors(result)
    elif assessment_type == "fusion":
        return _generate_fusion_factors(result)
    return []


def _generate_structured_factors(result: dict, payload: dict | None = None) -> list[dict]:
    factors: list[dict] = []
    features = (payload or {}).get("features", {}) or result.get("routing_info", {}).get("features", {}) or result.get("features", {})
    if not features:
        return factors

    for key, label in STRUCTURED_FEATURE_LABELS.items():
        value = features.get(key)
        if value is None:
            continue
        try:
            v = float(value)
        except (TypeError, ValueError):
            continue

        if key in STRUCTURED_HIGH_RISK_THRESHOLDS:
            threshold = STRUCTURED_HIGH_RISK_THRESHOLDS[key]
            if v >= threshold:
                importance = min(round((v - threshold + 1) / 5, 2), 1.0)
                factors.append({"feature": label, "importance": importance, "direction": "positive"})
        elif key in STRUCTURED_LOW_RISK_THRESHOLDS:
            threshold = STRUCTURED_LOW_RISK_THRESHOLDS[key]
            if v <= threshold:
                importance = min(round((threshold - v + 1) / 5, 2), 1.0)
                direction = "positive" if key == "sleep_duration" else "negative"
                factors.append({"feature": label, "importance": importance, "direction": direction})

    factors.sort(key=lambda f: f["importance"], reverse=True)
    return factors[:5]


def _generate_physio_factors(result: dict, payload: dict | None = None) -> list[dict]:
    factors: list[dict] = []
    physio_data = (payload or {}).get("physiological", {}) or result.get("physiological_data", {})
    data_quality = result.get("data_quality", "partial")

    for key, label in PHYSIO_FEATURE_LABELS.items():
        if key == "sleep_hours":
            sleep = physio_data.get("sleep_hours")
            if sleep is not None:
                try:
                    s = float(sleep)
                    if s < 6:
                        factors.append({"feature": label, "importance": round((6 - s) / 6, 2), "direction": "睡眠不足"})
                    elif s > 10:
                        factors.append({"feature": label, "importance": 0.5, "direction": "睡眠过长"})
                except (TypeError, ValueError) as exc:
                    # P1-E 修复：生理数据解析失败必须记录日志，便于发现上游数据质量问题
                    logger.debug("Invalid sleep_hours value %r: %s", sleep, exc)
        elif key == "heart_rate":
            hr = physio_data.get("heart_rate")
            if hr is not None:
                try:
                    h = float(hr)
                    if h >= 90:
                        factors.append({"feature": label, "importance": min(round((h - 80) / 30, 2), 1.0), "direction": "偏高"})
                except (TypeError, ValueError) as exc:
                    # P1-E 修复：生理数据解析失败必须记录日志，便于发现上游数据质量问题
                    logger.debug("Invalid heart_rate value %r: %s", hr, exc)
        elif key == "steps":
            steps = physio_data.get("steps")
            if steps is not None:
                try:
                    st = float(steps)
                    if st < 3000:
                        factors.append({"feature": label, "importance": min(round((3000 - st) / 3000, 2), 1.0), "direction": "活动过少"})
                except (TypeError, ValueError) as exc:
                    # P1-E 修复：生理数据解析失败必须记录日志，便于发现上游数据质量问题
                    logger.debug("Invalid steps value %r: %s", steps, exc)
        elif key == "exercise_minutes":
            ex = physio_data.get("exercise_minutes")
            if ex is not None:
                try:
                    e = float(ex)
                    if e < 15:
                        factors.append({"feature": label, "importance": min(round((15 - e) / 15, 2), 1.0), "direction": "运动不足"})
                except (TypeError, ValueError) as exc:
                    # P1-E 修复：生理数据解析失败必须记录日志，便于发现上游数据质量问题
                    logger.debug("Invalid exercise_minutes value %r: %s", ex, exc)

    if not factors and data_quality == "poor":
        factors.append({"feature": "数据质量", "importance": 0.5, "direction": "生理数据不足，建议补充更多指标"})

    factors.sort(key=lambda f: f["importance"], reverse=True)
    return factors[:5]


def _generate_text_factors(result: dict) -> list[dict]:
    return result.get("risk_factors", result.get("crisis_keywords", [])) or []


def _generate_fusion_factors(result: dict) -> list[dict]:
    factors = result.get("risk_factors") or []
    if not factors:
        for trigger in result.get("review_triggers", []):
            factors.append({"feature": trigger, "importance": 0.8, "direction": "融合提醒"})
    return factors[:5]


@router.get("/status", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def model_status(
    _: Annotated[User, Depends(require_permission("user.predict.use"))],
) -> dict:
    service = ModelPredictService()
    return ok(service.get_model_status())


@router.get("/debug/performance", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def model_performance_debug(
    _: Annotated[User, Depends(require_permission("admin.predict.audit"))],
) -> dict:
    service = ModelPredictService()
    return ok(service.get_model_status().get("performance", {}))


@router.get("/training/jobs", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def list_training_jobs(
    _: Annotated[User, Depends(require_permission("user.predict.use"))],
) -> dict:
    service = ModelPredictService()
    return ok({"jobs": service.list_training_jobs()})


@router.get("/training/jobs/{job_id}", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def get_training_job(
    job_id: str,
    _: Annotated[User, Depends(require_permission("user.predict.use"))],
) -> dict:
    service = ModelPredictService()
    return ok(service.get_training_job(job_id))


@router.post("/predict/tabular", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
@limiter.limit("20/minute")
async def predict_tabular(
    request: Request,
    payload: TabularPredictRequest,
    current_user: Annotated[User, Depends(require_permission("user.predict.use"))],
) -> dict:
    from app.core.metrics import track_model_inference

    service = ModelPredictService()
    with track_model_inference("tabular"):
        try:
            result = await service.predict_tabular(payload.features)
        except FileNotFoundError as exc:
            logger.error("表格预测模型加载失败: %s", exc)
            raise HTTPException(status_code=503, detail="模型服务暂时不可用") from exc
        except Exception as exc:
            logger.error("表格预测失败: %s", exc)
            raise HTTPException(status_code=422, detail="预测失败，请检查输入特征") from exc
    _save_assessment_sync(result, current_user.id, "structured", {"features": payload.features})
    return ok(result)


@router.post("/predict/text", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
@limiter.limit("20/minute")
async def predict_text(
    request: Request,
    payload: TextPredictRequest,
    current_user: Annotated[User, Depends(require_permission("user.predict.use"))],
) -> dict:
    from app.core.metrics import track_model_inference

    service = ModelPredictService()
    with track_model_inference("text"):
        try:
            result = await service.predict_text(payload.text)
        except FileNotFoundError as exc:
            logger.error("文本预测模型加载失败: %s", exc)
            raise HTTPException(status_code=503, detail="模型服务暂时不可用") from exc
        except Exception as exc:
            logger.error("文本预测失败: %s", exc)
            raise HTTPException(status_code=422, detail="预测服务异常，请稍后重试") from exc

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


@router.post("/predict/physiological", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
@limiter.limit("20/minute")
async def predict_physiological(
    request: Request,
    payload: PhysiologicalPredictRequest,
    current_user: Annotated[User, Depends(require_permission("user.predict.use"))],
) -> dict:
    from app.core.metrics import track_model_inference

    service = ModelPredictService()
    with track_model_inference("physiological"):
        try:
            result = await service.predict_physiological(payload.physiological)
        except FileNotFoundError as exc:
            logger.error("生理预测模型加载失败: %s", exc)
            raise HTTPException(status_code=503, detail="模型服务暂时不可用") from exc
        except Exception as exc:
            logger.error("生理预测失败: %s", exc)
            raise HTTPException(status_code=422, detail="预测失败，请检查输入") from exc
    _save_assessment_sync(result, current_user.id, "physiological", {"physiological": payload.physiological})
    return ok(result)


@router.post("/predict/fusion", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
@limiter.limit("20/minute")
async def predict_fusion(
    request: Request,
    payload: FusionPredictRequest,
    current_user: Annotated[User, Depends(require_permission("user.predict.use"))],
) -> dict:
    from app.core.metrics import track_model_inference

    service = ModelPredictService()
    with track_model_inference("fusion"):
        try:
            result = await service.predict_fusion(
                features=payload.features,
                text=payload.text,
                physiological=payload.physiological,
            )
        except FileNotFoundError as exc:
            logger.error("融合预测模型加载失败: %s", exc)
            raise HTTPException(status_code=503, detail="模型服务暂时不可用") from exc
        except Exception as exc:
            logger.error("融合预测失败: %s", exc)
            raise HTTPException(status_code=422, detail="融合预测失败，请检查输入") from exc

    # v1.17: 自动创建复核任务
    if result.get("review_required") or result.get("crisis_override"):
        try:
            from app.core.database import get_db
            from app.schemas.review import ReviewTaskCreate, ReviewPriority
            from app.services.review_service import ReviewService

            async for db in get_db():
                review_service = ReviewService(db)

                # 确定优先级
                priority = ReviewPriority.NORMAL_REVIEW
                if result.get("crisis_override"):
                    priority = ReviewPriority.CRISIS_REVIEW
                elif result.get("risk_level", 0) >= 3:
                    priority = ReviewPriority.HIGH_RISK_REVIEW

                review_data = ReviewTaskCreate(
                    user_id=current_user.id,
                    risk_level=result.get("risk_level", 0),
                    risk_score=result.get("risk_score", 0),
                    review_triggers=result.get("review_triggers", []),
                    crisis_override=result.get("crisis_override", False),
                    priority=priority,
                )
                review_task = await review_service.create_review_task(review_data)
                result["review_task_id"] = review_task.id
                logger.info("Auto-created review task %s for user %s", review_task.id, current_user.id)
                break
        except Exception as exc:
            logger.error("Failed to auto-create review task: %s", exc)
            # 不影响预测结果返回

    try:
        await save_assessment_result(result, current_user.id, "fusion", {"features": payload.features, "text": payload.text, "physiological": payload.physiological})
    except Exception as exc:
        logger.error("Failed to save fusion assessment for user %s: %s", current_user.id, exc)

    return ok(result)


@router.post("/experiment/import", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def import_dataset(
    payload: DatasetImportRequest,
    _: Annotated[User, Depends(require_permission("admin.predict.audit"))],
) -> dict:
    service = ModelExperimentService()
    try:
        result = await asyncio.to_thread(service.import_dataset, payload.dataset_name, payload.source_type, payload.train_ratio, payload.val_ratio, payload.test_ratio)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ok(result)


@router.post("/experiment/train", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def train_model(
    payload: TrainRequest,
    _: Annotated[User, Depends(require_permission("admin.predict.audit"))],
) -> dict:
    service = ModelPredictService()
    try:
        result = service.start_training_job(payload.dataset_name, payload.model_name, payload.epochs, payload.batch_size, payload.learning_rate)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ok(result)


@router.post("/experiment/evaluate", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def evaluate_model(
    payload: EvaluateRequest,
    _: Annotated[User, Depends(require_permission("admin.predict.audit"))],
) -> dict:
    service = ModelExperimentService()
    try:
        result = await asyncio.to_thread(service.evaluate, payload.dataset_name, payload.model_name, payload.split)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ok(result)


@router.post("/experiment/compare", response_model=ApiResponse, responses=COMMON_ERROR_RESPONSES)
async def compare_models(
    payload: CompareRequest,
    _: Annotated[User, Depends(require_permission("admin.predict.audit"))],
) -> dict:
    service = ModelExperimentService()
    try:
        result = await asyncio.to_thread(service.compare, payload.dataset_name, payload.model_names)
    except FileNotFoundError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    return ok(result)
