"""Model status and single-modality inference orchestration."""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

from app.core.cache import cache_get, cache_set, make_cache_key
from app.core.config import settings
from app.core.ml_breaker import call_with_ml_breaker
from app.core.model_engine import model_engine
from app.core.model_registry import MODEL_PATHS, get_model_info, resolve_model_path

from .fusion import FusionMixin

logger = logging.getLogger(__name__)
_ML_INFERENCE_CACHE_TTL: int = getattr(settings, "ml_inference_cache_ttl", 60)


def _model_fingerprint() -> str:
    """模型产物指纹, 用于 ML 缓存键前缀。

    AUDIT-2026-10-05: 此前 ML 推理缓存键只由入参构成, 不含模型身份。模型热替换
    (canary 切换 / 重新训练 / 手动替换文件) 后, 最长一个 TTL(默认 60s)内缓存
    仍返回**旧模型的 risk_score / risk_level** —— 对心理健康系统等于给出
    已被替换掉的评估结论。

    取所有注册模型文件的 (mtime, size) 组合做指纹:
    - 不需要人工维护版本号, 换文件即自动失效;
    - mtime 精度不足时 size 作为第二重保险(同秒内不同大小仍能区分);
    - 任一文件不可访问时返回 "unknown", 退化为不含指纹(行为同修复前),
      不因指纹计算失败而让推理不可用。
    """
    try:
        parts: list[str] = []
        for name, raw_path in sorted(MODEL_PATHS.items()):
            try:
                p = Path(raw_path)
                if not p.exists():
                    parts.append(f"{name}:missing")
                    continue
                st = p.stat()
                parts.append(f"{name}:{int(st.st_mtime)}:{st.st_size}")
            except OSError:
                parts.append(f"{name}:unreadable")
        if not parts:
            return "unknown"
        # 哈希而非直接拼接: key 长度可控
        return hashlib.sha256("|".join(parts).encode("utf-8")).hexdigest()[:12]
    except Exception:  # noqa: BLE001 - 指纹失败绝不能阻断推理
        logger.debug("模型指纹计算失败, 缓存键退化为无版本前缀", exc_info=True)
        return "unknown"


def _ml_cache_key(endpoint: str, params: dict[str, Any] | None) -> str:
    """构造带模型指纹前缀的 ML 缓存键。

    模型指纹变化 → 键前缀变化 → 旧模型的缓存条目自然失效, 无需显式清理
    (Redis 里旧条目会按 TTL 自行过期)。
    """
    return make_cache_key(f"ml:{_model_fingerprint()}:{endpoint}", params)


class InferenceService(FusionMixin):
    """Orchestrate model status and tabular/text/physiological inference."""

    def _fire_shadow_check(self, result: dict[str, Any], raw_input: dict[str, Any]) -> None:
        """Record a non-blocking shadow comparison for eligible predictions."""
        try:
            model_used = result.get("model_used")
            if not model_used or "fallback" in str(model_used):
                return
            from app.services.shadow_comparison_service import get_shadow_comparison_service

            service = get_shadow_comparison_service()
            service.record_inference(str(model_used), fallback_used=bool(result.get("fallback_used", False)))
            service.fire_shadow_check(str(model_used), raw_input, result)
        except Exception as exc:
            logger.debug("[shadow] fire failed (non-blocking): %s", exc)

    def get_model_status(self) -> dict[str, Any]:
        model_dir = Path(settings.model_dir)
        status: list[dict[str, Any]] = []
        for model_id in MODEL_PATHS:
            path = Path(resolve_model_path(model_id))
            abs_path = (
                path
                if path.is_absolute()
                else (model_dir.parent / path if path.parts and path.parts[0] == "models" else model_dir / path)
            )
            exists = abs_path.exists()
            model_info = get_model_info(model_id)
            stat_info = abs_path.stat() if exists else None
            status.append(
                {
                    "model_id": model_id,
                    "path": str(abs_path),
                    "exists": exists,
                    "size_kb": round(stat_info.st_size / 1024, 2) if stat_info else None,
                    "modified_at": stat_info.st_mtime if stat_info else None,
                    "lifecycle": model_info.lifecycle if model_info else None,
                }
            )

        performance = model_engine.get_metrics_snapshot()
        predict_stats = performance["predict_stats"]
        load_stats = performance["model_load_stats"]
        predict_calls = sum(int(item.get("count", 0)) for item in predict_stats.values())
        performance_summary = {
            "cached_models": performance["cache_size"],
            "tracked_models": len(load_stats),
            "tracked_paths": len(predict_stats),
            "cache_hits_total": sum(int(item.get("cache_hits", 0)) for item in load_stats.values()),
            "loads_total": sum(int(item.get("loads", 0)) for item in load_stats.values()),
            "predict_calls_total": predict_calls,
            "avg_predict_ms": round(
                sum(float(item.get("total_ms", 0.0)) for item in predict_stats.values()) / max(1, predict_calls),
                2,
            ),
        }
        required_models = {
            "structured_logistic_regression_quick",
            "text_depression_model",
            "text_depression_tfidf",
        }
        return {
            "model_dir": str(model_dir),
            "items": status,
            "ready": all(item["exists"] for item in status if item["model_id"] in required_models),
            "performance": performance,
            "performance_summary": performance_summary,
        }

    async def predict_tabular(self, features: dict[str, float | int | str | bool]) -> dict:
        if _ML_INFERENCE_CACHE_TTL > 0:
            cache_key = _ml_cache_key("tabular", features)
            cached = await cache_get(cache_key)
            if cached is not None:
                logger.debug("[predict_tabular] cache hit key=%s", cache_key)
                return cached

        result = await call_with_ml_breaker(model_engine.predict_structured(features))
        routing_info = result.get("routing_info", {})
        if routing_info:
            logger.info(
                "Model routing: family=%s reason=%s coverage=%.2f band=%s",
                routing_info.get("selected_model_family"),
                routing_info.get("routing_reason"),
                routing_info.get("feature_coverage_ratio", 0),
                routing_info.get("prediction_confidence_band"),
            )
        if _ML_INFERENCE_CACHE_TTL > 0:
            await cache_set(cache_key, result, ttl=_ML_INFERENCE_CACHE_TTL)
        self._fire_shadow_check(result, features)
        return result

    async def predict_text(self, text: str) -> dict:
        if not text or not text.strip():
            raise ValueError("text cannot be empty")
        cleaned = text.strip()
        if _ML_INFERENCE_CACHE_TTL > 0:
            cache_key = _ml_cache_key("text", {"text": cleaned})
            cached = await cache_get(cache_key)
            if cached is not None:
                logger.debug("[predict_text] cache hit key=%s", cache_key)
                return cached
        result = await call_with_ml_breaker(model_engine.predict_text(cleaned))
        if _ML_INFERENCE_CACHE_TTL > 0:
            await cache_set(cache_key, result, ttl=_ML_INFERENCE_CACHE_TTL)
        self._fire_shadow_check(result, {"text": cleaned})
        return result

    async def predict_physiological(self, physiological: dict[str, float | int]) -> dict:
        if _ML_INFERENCE_CACHE_TTL > 0:
            cache_key = _ml_cache_key("physiological", physiological)
            cached = await cache_get(cache_key)
            if cached is not None:
                logger.debug("[predict_physiological] cache hit key=%s", cache_key)
                return cached
        result = await call_with_ml_breaker(model_engine.predict_physiological(physiological))
        if _ML_INFERENCE_CACHE_TTL > 0:
            await cache_set(cache_key, result, ttl=_ML_INFERENCE_CACHE_TTL)
        self._fire_shadow_check(result, physiological)
        return result
