"""Multimodal fusion inference and canary telemetry."""

from __future__ import annotations

import logging
from time import perf_counter

from app.core.cache import cache_get, cache_set, make_cache_key
from app.core.config import settings
from app.core.ml_breaker import call_with_ml_breaker
from app.core.model_engine import model_engine

logger = logging.getLogger(__name__)
_ML_INFERENCE_CACHE_TTL: int = getattr(settings, "ml_inference_cache_ttl", 60)


class FusionMixin:
    """Provide multimodal prediction with canary routing and caching."""

    async def predict_fusion(
        self,
        features: dict[str, float | int] | None = None,
        text: str | None = None,
        physiological: dict[str, float | int] | None = None,
        user_id: int | None = None,
    ) -> dict:
        canary_routed = False
        canary_version = None
        if user_id is not None:
            try:
                from app.core.database import AsyncSessionLocal
                from app.services.canary_manager import canary_manager

                async with AsyncSessionLocal() as db:
                    decision = await canary_manager.decide_version(
                        db_session=db,
                        user_id=user_id,
                        stable_version="v1.16-risk-calibration",
                    )
                    if decision.use_canary:
                        canary_routed = True
                        canary_version = decision.canary_version
                        logger.info(
                            "[predict_fusion] canary routed: user=%s version=%s",
                            user_id,
                            canary_version,
                        )
            except Exception as exc:
                logger.warning("[predict_fusion] canary routing failed: %s", exc)

        if _ML_INFERENCE_CACHE_TTL > 0 and not canary_routed:
            cache_key = make_cache_key(
                "ml:fusion",
                {
                    "features": features,
                    "text": text,
                    "physiological": physiological,
                },
            )
            cached = await cache_get(cache_key)
            if cached is not None:
                logger.debug("[predict_fusion] cache hit key=%s", cache_key)
                return cached

        inference_start = perf_counter()
        try:
            result = await call_with_ml_breaker(
                model_engine.predict_fusion(
                    features=features,
                    text=text,
                    physiological=physiological,
                )
            )
            inference_latency_ms = (perf_counter() - inference_start) * 1000
        except Exception:
            inference_latency_ms = (perf_counter() - inference_start) * 1000
            if canary_routed and canary_version:
                await self._log_canary_event(
                    event_type="fallback",
                    model_version=canary_version,
                    user_id=user_id,
                    latency_ms=inference_latency_ms,
                    fallback_reason="ml_breaker_or_inference_error",
                )
            raise

        if canary_routed:
            result["canary_routed"] = True
            result["canary_version"] = canary_version
            result["model_version"] = f"{canary_version} (canary)"
            try:
                from app.core.metrics import model_inference_total

                model_inference_total.inc(1, model_name="fusion_canary", status="success")
            except Exception:
                pass
            await self._log_canary_event(
                event_type="inference",
                model_version=canary_version,
                user_id=user_id,
                latency_ms=inference_latency_ms,
                response_summary={
                    "risk_level": result.get("risk_level"),
                    "risk_score": result.get("risk_score"),
                    "canary_routed": True,
                },
            )
        else:
            result["canary_routed"] = False

        if _ML_INFERENCE_CACHE_TTL > 0 and not canary_routed:
            await cache_set(cache_key, result, ttl=_ML_INFERENCE_CACHE_TTL)
        return result

    async def _log_canary_event(
        self,
        event_type: str,
        model_version: str,
        user_id: int | None,
        latency_ms: float,
        response_summary: dict | None = None,
        fallback_reason: str | None = None,
    ) -> None:
        """Write a canary event without affecting the inference response."""
        try:
            from app.core.database import AsyncSessionLocal
            from app.models.monitoring import MonitoringEventType, MonitoringLog

            if event_type == "inference":
                event_type_value = MonitoringEventType.INFERENCE
            elif event_type == "fallback":
                event_type_value = MonitoringEventType.FALLBACK
            else:
                event_type_value = event_type

            async with AsyncSessionLocal() as db:
                log = MonitoringLog(
                    event_type=event_type_value,
                    model_version=model_version,
                    user_id=user_id,
                    latency_ms=round(latency_ms, 2),
                    response_summary=response_summary,
                    fallback_reason=fallback_reason,
                )
                db.add(log)
                await db.commit()
        except Exception as exc:
            logger.warning(
                "[predict_fusion] log canary event failed (type=%s version=%s): %s",
                event_type,
                model_version,
                exc,
            )
