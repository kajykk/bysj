"""共享基础设施: logger、任务集合、评估保存、风险因子生成、常量.

向后兼容: 此模块中的 logger / _log_task_exception / _save_assessment_sync /
save_assessment_result / _assessment_save_tasks 通过包 __init__ re-export,
仍可由 ``from app.api.v1.model_predict import xxx`` 导入.
"""

from __future__ import annotations

import asyncio
import logging

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.models.risk import RiskAssessment
from app.services.risk_service import RiskService

logger = logging.getLogger(__name__)

# 保存评估结果保存任务引用，防止被 GC 回收
_assessment_save_tasks: set[asyncio.Task] = set()


def _log_task_exception(task: asyncio.Task) -> None:
    """任务完成回调：记录未捕获异常。

    通过函数内 import 引用包级 logger, 使测试 patch("app.api.v1.model_predict.logger")
    能正确生效 (函数 __globals__ 指向本模块, 而非包 __init__).
    """
    from app.api.v1.model_predict import logger as _logger

    if task.cancelled():
        return
    exc = task.exception()
    if exc is not None:
        _logger.error("Background assessment save task failed: %s", exc)


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
            structured_score = (
                result.get("risk_score")
                if result.get("risk_score") is not None
                else None
            )
        elif assessment_type == "text":
            sentiment = result.get("sentiment_score")
            text_score = (
                round(sentiment * 100, 2)
                if sentiment is not None
                else result.get("risk_score")
            )
        elif assessment_type == "physiological":
            physio_score = (
                result.get("risk_score")
                if result.get("risk_score") is not None
                else None
            )
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

        risk_factors = result.get("risk_factors") or _generate_risk_factors(
            result, assessment_type, payload
        )

        # P1-F1 修复：risk_score=0 是合法值（无风险），不应被 `or 0` 吞掉。
        # 原逻辑 `result.get("risk_score") or 0` 会把 None 和 0 都变成 0，
        # 然后 `if risk_score_value <= 0: return` 会跳过保存合法的 0 分评估。
        # 改为显式 None 检查：仅当 risk_score 为 None（模型未返回）时跳过。
        raw_risk_score = result.get("risk_score")
        if raw_risk_score is None:
            logger.info(
                "Skipped saving %s assessment for user %s (risk_score=None, empty input likely)",
                assessment_type,
                user_id,
            )
            return
        risk_score_value = float(raw_risk_score)
        if risk_score_value < 0:
            logger.warning(
                "Negative risk_score=%s from model for user %s, clamping to 0",
                raw_risk_score,
                user_id,
            )
            risk_score_value = 0.0

        # PERF-P2-002: 清除该用户旧风险评估的 is_latest 标志
        await session.execute(
            update(RiskAssessment)
            .where(
                RiskAssessment.user_id == user_id,
                RiskAssessment.is_latest.is_(True),
            )
            .values(is_latest=False)
        )

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
            is_latest=True,
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
            assessment_type,
            user_id,
            structured_score or 0,
            text_score or 0,
            physio_score or 0,
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


def _save_assessment_sync(
    result: dict, user_id: int, assessment_type: str, payload: dict | None = None
) -> None:
    try:
        task = asyncio.ensure_future(
            save_assessment_result(result, user_id, assessment_type, payload)
        )
        # 保存任务引用防止 GC 回收，并在异常时记录日志
        _assessment_save_tasks.add(task)
        task.add_done_callback(_assessment_save_tasks.discard)
        task.add_done_callback(_log_task_exception)
        # R-005 修复: 注册可观测性指标 (scheduled/succeeded/failed/cancelled + duration)
        from app.core.fire_forget_metrics import register_task

        register_task(task, "assessment_save")
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


def _generate_risk_factors(
    result: dict, assessment_type: str, payload: dict | None = None
) -> list[dict]:
    if assessment_type == "structured":
        return _generate_structured_factors(result, payload)
    elif assessment_type == "physiological":
        return _generate_physio_factors(result, payload)
    elif assessment_type == "text":
        return _generate_text_factors(result)
    elif assessment_type == "fusion":
        return _generate_fusion_factors(result)
    return []


def _generate_structured_factors(
    result: dict, payload: dict | None = None
) -> list[dict]:
    factors: list[dict] = []
    features = (
        (payload or {}).get("features", {})
        or result.get("routing_info", {}).get("features", {})
        or result.get("features", {})
    )
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
                factors.append(
                    {
                        "feature": label,
                        "importance": importance,
                        "direction": "positive",
                    }
                )
        elif key in STRUCTURED_LOW_RISK_THRESHOLDS:
            threshold = STRUCTURED_LOW_RISK_THRESHOLDS[key]
            if v <= threshold:
                importance = min(round((threshold - v + 1) / 5, 2), 1.0)
                direction = "positive" if key == "sleep_duration" else "negative"
                factors.append(
                    {"feature": label, "importance": importance, "direction": direction}
                )

    factors.sort(key=lambda f: f["importance"], reverse=True)
    return factors[:5]


def _generate_physio_factors(result: dict, payload: dict | None = None) -> list[dict]:
    factors: list[dict] = []
    physio_data = (payload or {}).get("physiological", {}) or result.get(
        "physiological_data", {}
    )
    data_quality = result.get("data_quality", "partial")

    for key, label in PHYSIO_FEATURE_LABELS.items():
        if key == "sleep_hours":
            sleep = physio_data.get("sleep_hours")
            if sleep is not None:
                try:
                    s = float(sleep)
                    if s < 6:
                        factors.append(
                            {
                                "feature": label,
                                "importance": round((6 - s) / 6, 2),
                                "direction": "睡眠不足",
                            }
                        )
                    elif s > 10:
                        factors.append(
                            {
                                "feature": label,
                                "importance": 0.5,
                                "direction": "睡眠过长",
                            }
                        )
                except (TypeError, ValueError) as exc:
                    # P1-E 修复：生理数据解析失败必须记录日志，便于发现上游数据质量问题
                    logger.debug("Invalid sleep_hours value %r: %s", sleep, exc)
        elif key == "heart_rate":
            hr = physio_data.get("heart_rate")
            if hr is not None:
                try:
                    h = float(hr)
                    if h >= 90:
                        factors.append(
                            {
                                "feature": label,
                                "importance": min(round((h - 80) / 30, 2), 1.0),
                                "direction": "偏高",
                            }
                        )
                except (TypeError, ValueError) as exc:
                    # P1-E 修复：生理数据解析失败必须记录日志，便于发现上游数据质量问题
                    logger.debug("Invalid heart_rate value %r: %s", hr, exc)
        elif key == "steps":
            steps = physio_data.get("steps")
            if steps is not None:
                try:
                    st = float(steps)
                    if st < 3000:
                        factors.append(
                            {
                                "feature": label,
                                "importance": min(round((3000 - st) / 3000, 2), 1.0),
                                "direction": "活动过少",
                            }
                        )
                except (TypeError, ValueError) as exc:
                    # P1-E 修复：生理数据解析失败必须记录日志，便于发现上游数据质量问题
                    logger.debug("Invalid steps value %r: %s", steps, exc)
        elif key == "exercise_minutes":
            ex = physio_data.get("exercise_minutes")
            if ex is not None:
                try:
                    e = float(ex)
                    if e < 15:
                        factors.append(
                            {
                                "feature": label,
                                "importance": min(round((15 - e) / 15, 2), 1.0),
                                "direction": "运动不足",
                            }
                        )
                except (TypeError, ValueError) as exc:
                    # P1-E 修复：生理数据解析失败必须记录日志，便于发现上游数据质量问题
                    logger.debug("Invalid exercise_minutes value %r: %s", ex, exc)

    if not factors and data_quality == "poor":
        factors.append(
            {
                "feature": "数据质量",
                "importance": 0.5,
                "direction": "生理数据不足，建议补充更多指标",
            }
        )

    factors.sort(key=lambda f: f["importance"], reverse=True)
    return factors[:5]


def _generate_text_factors(result: dict) -> list[dict]:
    return result.get("risk_factors", result.get("crisis_keywords", [])) or []


def _generate_fusion_factors(result: dict) -> list[dict]:
    factors = result.get("risk_factors") or []
    if not factors:
        for trigger in result.get("review_triggers", []):
            factors.append(
                {"feature": trigger, "importance": 0.8, "direction": "融合提醒"}
            )
    return factors[:5]
