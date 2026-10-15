"""Multimodal fusion inference and canary telemetry."""

from __future__ import annotations

import logging
from time import perf_counter

from app.core.cache import cache_get, cache_set, make_cache_key
from app.core.config import settings
from app.core.degradation import record_silent_degradation
from app.core.ml_breaker import call_with_ml_breaker
from app.core.model_engine import model_engine

logger = logging.getLogger(__name__)
_ML_INFERENCE_CACHE_TTL: int = getattr(settings, "ml_inference_cache_ttl", 60)


def _cached_matches_route(
    cached: dict, canary_routed: bool, canary_version: str | None
) -> bool:
    """校验缓存条目是否可安全用于当前请求。

    P0 修复配套的纵深防御：缓存键已按路由分桶（``user_id``/``route``/
    ``canary_version``），正常路径不会跨组命中；但仍需防御历史遗留键、
    跨版本脏数据、外部写入 Redis 的条目被当作有效命中返回。

    判定规则（对两条路径采取不同严格度）：

    - **灰度请求**必须严格自证：条目须显式带 ``canary_routed=True``，且
      ``canary_version`` 与当前运行中的灰度版本一致，否则重算。发错版本的风险
      在这条路径上是有害的（灰度数据失真 → 回滚判据失真），宁可多算一次。
    - **稳定请求**只拒绝「自称灰度结果」的条目；无标记条目放行，以兼容既有
      缓存写入方（历史条目 TTL 60s 内自然过期，且旧键空间不会被查���）。

    非 dict 条目一律拒绝。
    """
    if not isinstance(cached, dict):
        return False

    marker = cached.get("canary_routed")

    if canary_routed:
        if not marker:
            return False
        return cached.get("canary_version") == canary_version

    # 稳定组：只要不自称灰度结果即可放行
    return not marker


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
                # 路由决策失败 → canary_routed 保持 False、本该进灰度的用户静默走
                # stable 版本，且响应里不会带 canary_routed 标记 —— 与「路由决策就是
                # 稳定版」完全同形。灰度样本分配因此失真（灰度组被稳定版污染）。
                logger.warning("[predict_fusion] canary routing failed: %s", exc)
                record_silent_degradation(
                    "services.model_predict.fusion.canary_routing_failed"
                )

        # P0 修复：缓存键必须纳入「路由结果」。
        # 旧实现只用 features/text/physiological 组键，而路由决策
        # decide_version() 恰恰依赖 user_id —— 不同用户对同一输入会命中
        # 同一个缓存条目，导致：
        #   1) 命中灰度的用户读到 stable 版本的结果，本该走 canary 的流量被静默替换；
        #   2) 同输入下灰度组与稳定组互相污染，灰度指标失真，
        #      进而使 AutoRollbackService 的回滚判据建立在错误样本上。
        # 修复后路由结果与输入共同决定键：灰度组与稳定组天然分桶。
        cache_key = None
        if _ML_INFERENCE_CACHE_TTL > 0:
            cache_key = make_cache_key(
                "ml:fusion",
                {
                    "features": features,
                    "text": text,
                    "physiological": physiological,
                    # user_id 参与分组：决定该用户走灰度还是稳定，
                    # 不同分组的缓存不可互换。
                    "route": "canary" if canary_routed else "stable",
                    "canary_version": canary_version,
                    "user_id": user_id,
                },
            )
            cached = await cache_get(cache_key)
            if cached is not None:
                # 一致性校验：命中缓存的条目必须是本分组（且本版本）产出的。
                # 防止历史遗留键或跨版本脏数据被当作有效命中返回。
                if _cached_matches_route(cached, canary_routed, canary_version):
                    logger.debug(
                        "[predict_fusion] cache hit key=%s canary=%s",
                        cache_key,
                        canary_routed,
                    )
                    return cached
                logger.info(
                    "[predict_fusion] cache hit 路由不一致, 丢弃并重算 key=%s "
                    "canary=%s expected_version=%s cached_version=%s",
                    cache_key,
                    canary_routed,
                    canary_version,
                    cached.get("canary_version"),
                )

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
                # P1 问题 5：指标自增失败不得阻断推理主流程（该取舍保留），
                # 但必须留痕——原实现 except: pass 完全静默，故障时无法定位，
                # 违反「失败路径需可观测」约定。降级为 debug 并保留异常栈。
                logger.debug(
                    "[predict_fusion] canary 指标自增失败（不影响推理结果）",
                    exc_info=True,
                )
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
            # 稳定组同样标记 canary_version=None，使 _cached_matches_route
            # 能区分「稳定组结果」与「灰度组结果」。
            result["canary_version"] = None

        # P0 修复：写入时带上路由标记，保证「读到的缓存」可自证来源，
        # 一致性校验（_cached_matches_route）才有依据。
        # 旧实现 not canary_routed 的短路已移除——现在灰度组与稳定组分桶缓存，
        # 灰度结果不再被丢弃，灰度指标与回滚判据才有真实样本。
        if _ML_INFERENCE_CACHE_TTL > 0 and cache_key is not None:
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
