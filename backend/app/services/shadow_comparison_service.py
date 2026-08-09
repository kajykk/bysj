"""训练产物影子对拍服务: 候选产物 vs 生产模型 双跑对拍.

R1 增强: 激活训练产物前, 在真实推理流量上对候选产物与生产模型做影子对拍.
- 生产请求结果不变 (候选产物仅在后台异步推理, fire-and-forget)
- 统计预测一致率 (prediction 相同 & probability 差异), 写入注册表记录的 metrics
- 激活接口依据一致率阈值拒绝低一致候选 (除非 force)

支持的对拍产物格式:
- joblib Pipeline (.pkl): 特征来自 model.feature_names_in_ (解析 raw payload)
- transformers 目录: 暂不支持自动对拍, 返回 skipped

线程安全: 单例 + asyncio (单线程事件循环).
"""

from __future__ import annotations

import logging
import random
from typing import Any

from app.core.config import settings

logger = logging.getLogger(__name__)


class ShadowComparisonService:
    """候选产物 vs 生产模型影子对拍服务 (单例)."""

    _PHYS_FEATURE_COLS = [
        "sleep_hours",
        "sleep_quality",
        "exercise_minutes",
        "heart_rate",
        "systolic_bp",
        "diastolic_bp",
        "steps",
    ]

    def __init__(self) -> None:
        # 内存统计: model_id -> {total, agree, disagree, prob_diff_sum, prob_diff_max}
        self._stats: dict[str, dict[str, float | int]] = {}
        # R2 健康统计: model_id -> {total, fallback} (窗口滑动在检查时计算)
        self._health: dict[str, dict[str, int]] = {}
        self._random = random.Random(42)

    # ── 对外入口 ──────────────────────────────────────────────
    def fire_shadow_check(
        self,
        model_id: str,
        raw_input: dict[str, Any],
        production_result: dict[str, Any],
        sample_rate: float | None = None,
    ) -> None:
        """Fire-and-forget 对拍: 不阻塞生产推理.

        Args:
            model_id: 生产推理实际使用的 model_id (如 mmpsy_lite_model)
            raw_input: 原始请求特征/文本载荷
            production_result: 生产模型预测结果 (含 prediction/probability)
        """
        rate = (
            sample_rate
            if sample_rate is not None
            else settings.shadow_production_sample_rate
        )
        if rate < 1.0 and self._random.random() > rate:
            return

        # 查找替换该生产模型名的候选 (fallback_id == ... 或同名候选)
        import asyncio

        try:
            asyncio.create_task(self._shadow_check(model_id, raw_input, production_result))
        except RuntimeError:
            # 无运行中事件循环 (如同步测试/非 asyncio 上下文): 跳过对拍
            logger.debug("[SHADOW] no running event loop, skip shadow check")

    # ── 统计管理 ──

    def get_stats(self, model_id: str) -> dict[str, Any]:
        stats = self._stats.get(model_id) or {}
        total = int(stats.get("total", 0))
        agreement = int(stats.get("agreement", 0))
        return {
            "model_id": model_id,
            "total": total,
            "agreement": agreement,
            "disagreement": int(stats.get("disagreement", 0)),
            "agreement_rate": round(agreement / total, 4) if total > 0 else 0.0,
            "avg_prob_diff": (
                round(float(stats.get("prob_diff_sum", 0.0)) / total, 4)
                if total > 0
                else 0.0
            ),
            "max_prob_diff": round(float(stats.get("prob_diff_max", 0.0)), 4),
        }

    def commit_shadow_stats(self, model_id: str) -> dict[str, Any] | None:
        """将内存统计写入 registry 记录的 metrics, 并返回统计摘要.

        供激活前检查与定时持久化调用.
        """
        try:
            from app.core.model_registry_v2 import get_registry

            registry = get_registry()
            record = registry.get_model(model_id)
            if record is None:
                return None
            stats = self.get_stats(model_id)
            record.metrics["shadow_total"] = float(stats["total"])
            record.metrics["shadow_agreement_rate"] = stats["agreement_rate"]
            record.metrics["shadow_max_prob_diff"] = stats["max_prob_diff"]
            registry._save_registry()
            return stats
        except Exception as exc:
            logger.warning("commit_shadow_stats failed for %s: %s", model_id, exc)
            return None

    def is_shadow_acceptable(self, model_id: str, force: bool = False) -> tuple[bool, str]:
        """激活前校验: 一致率 >= min_agreement 且样本足够时允许切换.

        - 无候选对拍数据 (total=0): 不阻塞切换 (证据不足放行)
        - 样本超过 min_samples 且一致率低于阈值: 拒绝
        - force=True: 跳过校验
        """
        if force:
            return True, "force_override"
        stats = self.get_stats(model_id)
        total = stats["total"]
        min_samples = int(settings.shadow_production_min_samples)
        if total < min_samples:
            return True, f"insufficient_samples({total}<{min_samples})"
        rate = stats["agreement_rate"]
        threshold = float(settings.shadow_production_min_agreement)
        if rate < threshold:
            return False, (
                f"shadow_agreement {rate:.2%} below threshold {threshold:.2%} "
                f"({total} samples)"
            )
        return True, "shadow_ok"

    # ── R2 自动回退支持: 生产健康监控 ──

    def record_inference(self, model_id: str, fallback_used: bool = False) -> None:
        """记录一次生产推理 (由推理链调用, R2 自动回退的输入)."""
        health = self._health.setdefault(model_id, {"total": 0, "fallback": 0})
        health["total"] = int(health["total"]) + 1
        if fallback_used:
            health["fallback"] = int(health["fallback"]) + 1

    def get_health(self, model_id: str) -> dict[str, Any]:
        health = self._health.get(model_id) or {}
        total = int(health.get("total", 0))
        fallback = int(health.get("fallback", 0))
        return {
            "model_id": model_id,
            "total": total,
            "fallback": fallback,
            "fallback_rate": round(fallback / total, 4) if total > 0 else 0.0,
        }

    def should_auto_rollback(self, model_id: str) -> tuple[bool, str]:
        """判断 PRODUCTION 训练产物是否应自动回退.

        条件: 窗口内推理样本 >= min_samples 且回退率 > max_fallback_rate.
        """
        from app.core.config import settings

        health = self.get_health(model_id)
        total = health["total"]
        min_samples = int(settings.registry_auto_rollback_min_samples)
        if total < min_samples:
            return False, f"insufficient_samples({total}<{min_samples})"
        rate = health["fallback_rate"]
        threshold = float(settings.registry_auto_rollback_max_fallback_rate)
        if rate > threshold:
            return True, (
                f"fallback_rate {rate:.2%} exceeds threshold {threshold:.2%} "
                f"({health['fallback']}/{total} fallbacks)"
            )
        return False, "within_threshold"

    def reset_health(self, model_id: str) -> None:
        self._health.pop(model_id, None)

    # ── 内部实现 ──

    async def _shadow_check(
        self, model_id: str, raw_input: dict[str, Any], production_result: dict[str, Any]
    ) -> None:
        try:
            # 找到候选产物记录: 同名注册记录且为 CANDIDATE/STAGING
            from app.core.model_registry_v2 import ModelStatus, get_registry

            record = get_registry().get_model(model_id)
            if record is None or record.status not in (
                ModelStatus.CANDIDATE,
                ModelStatus.STAGING,
            ):
                return  # 无候选或已生产, 不进行对拍

            candidate = self._load_candidate(record.artifact_path)
            if candidate is None:
                return

            features = self._build_features(candidate, raw_input)
            if features is None:
                return

            import asyncio

            cand_pred, cand_prob = await asyncio.to_thread(
                self._candidate_predict, candidate, features
            )
            if cand_pred is None:
                return

            self._record(model_id, production_result, cand_pred, cand_prob)
        except Exception as exc:
            logger.debug("[SHADOW] comparison failed (non-blocking): %s", exc)

    def _load_candidate(self, artifact_path: str):
        """加载候选产物 (仅支持 joblib 可加载的 sklearn 产物)."""
        from pathlib import Path

        from app.core.safe_pickle import safe_joblib_load

        path = Path(artifact_path)
        candidates = [path]
        if not path.is_absolute():
            candidates.append(Path(__file__).resolve().parents[2] / path)
        for p in candidates:
            if p.exists():
                break
        else:
            return None
        try:
            if p.is_dir():
                phys = p / "physiological_model.pkl"
                if phys.exists():
                    return safe_joblib_load(phys, trusted_root=p.parent, model_id="shadow")
                return None  # transformers 产物暂不支持对拍
            if p.suffix == ".pkl":
                return safe_joblib_load(p, trusted_root=p.parent, model_id="shadow")
            return None
        except Exception as exc:
            logger.warning("[SHADOW] candidate load failed: %s", exc)
            return None

    def _build_features(self, candidate, raw_input: dict[str, Any]):
        """构建候选模型输入特征: 优先 feature_names_in_, 回退生理特征列."""
        import pandas as pd

        feature_names = list(getattr(candidate, "feature_names_in_", []))
        available = {k: v for k, v in raw_input.items() if v is not None}
        if feature_names:
            missing = set(feature_names) - set(available)
            if missing:
                return None
            return pd.DataFrame([{k: available[k] for k in feature_names}])
        phys_cols = [c for c in self._PHYS_FEATURE_COLS if c in available]
        if len(phys_cols) == len(self._PHYS_FEATURE_COLS):
            return pd.DataFrame([{k: available[k] for k in self._PHYS_FEATURE_COLS}])
        return None

    def _candidate_predict(self, candidate, features) -> tuple[int | None, float | None]:
        """候选模型预测: 返回 (prediction, probability_of_positive)."""
        try:
            if hasattr(candidate, "predict_proba"):
                proba = candidate.predict_proba(features)
                return int(candidate.predict(features)[0]), float(proba[0][1])
            pred = int(candidate.predict(features)[0])
            return pred, None
        except Exception as exc:
            logger.debug("[SHADOW] candidate predict failed: %s", exc)
            return None, None

    def _record(
        self, model_id: str, production_result: dict[str, Any], cand_pred: int, cand_prob: float | None
    ) -> None:
        prod_pred = int(production_result.get("prediction", 0))
        stats = self._stats.setdefault(
            model_id, {"total": 0, "agreement": 0, "disagreement": 0, "prob_diff_sum": 0.0, "prob_diff_max": 0.0}
        )
        stats["total"] = int(stats["total"]) + 1
        if prod_pred == cand_pred:
            stats["agreement"] = int(stats["agreement"]) + 1
        else:
            stats["disagreement"] = int(stats["disagreement"]) + 1
        if cand_prob is not None:
            prod_prob = float(production_result.get("probability", 0.0) or 0.0)
            diff = abs(prod_prob - cand_prob)
            stats["prob_diff_sum"] = float(stats["prob_diff_sum"]) + diff
            stats["prob_diff_max"] = max(float(stats["prob_diff_max"]), diff)

    def reset_stats(self, model_id: str | None = None) -> None:
        if model_id:
            self._stats.pop(model_id, None)
        else:
            self._stats.clear()


# 单例
_shadow_comparison_instance: ShadowComparisonService | None = None


def get_shadow_comparison_service() -> ShadowComparisonService:
    global _shadow_comparison_instance
    if _shadow_comparison_instance is None:
        _shadow_comparison_instance = ShadowComparisonService()
    return _shadow_comparison_instance