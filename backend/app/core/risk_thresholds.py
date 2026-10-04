from __future__ import annotations

import logging
import math

# v1.16 校准后的各模态专用阈值 → v1.20 结构化阈值已重新校准
logger = logging.getLogger(__name__)
RISK_LEVEL_THRESHOLDS: dict[str, int] = {
    "mild": 20,
    "moderate": 40,
    "high": 60,
    "critical": 80,
}

MODALITY_RISK_THRESHOLDS: dict[str, dict[str, int]] = {
    "structured": {
        "mild": 25,
        "moderate": 45,
        "high": 65,
        "critical": 85,
    },
    "text": {
        "mild": 20,
        "moderate": 40,
        "high": 60,
        "critical": 80,
    },
    "physiological": {
        "mild": 35,
        "moderate": 55,
        "high": 75,
        "critical": 90,
    },
    "fusion": {
        "mild": 22,
        "moderate": 42,
        "high": 62,
        "critical": 82,
    },
}

RISK_LEVEL_LABELS: dict[int, str] = {
    0: "none",
    1: "mild",
    2: "moderate",
    3: "high",
    4: "critical",
}


def get_threshold_by_modality(modality: str) -> dict[str, int]:
    """获取指定模态的阈值配置。"""
    return MODALITY_RISK_THRESHOLDS.get(modality, RISK_LEVEL_THRESHOLDS)


class NonFiniteRiskScoreError(ValueError):
    """风险分数为非有限值（NaN / ±Inf），拒绝映射为风险等级。

    AUDIT-2026-10-01 (P0-3)：``NaN >= 阈值`` **恒为 False**，于是 NaN 会一路
    穿过全部 ``if`` 落到末尾的 ``return 0`` —— 而 ``RISK_LEVEL_LABELS[0] == "none"``。
    对一个心理健康风险判定系统来说，这意味着「算不出来」被静默表达成「无风险」，
    是本项目最危险的失效模式（真实异常输入 → 判为正常）。

    因此这里显式抛错，把选择权交给上层：要么回退到启发式（并把 fallback 标记如实
    写进响应），要么返回 5xx。**绝不允许静默降级为最低风险等级。**
    """


def ensure_finite_score(score: float, *, context: str = "risk_score") -> float:
    """校验风险分数为有限值，否则抛 :class:`NonFiniteRiskScoreError`。

    注意：**负数与超过 100 的值是允许的**（现有测试断言 ``_score_to_level(-100) == 0``），
    本函数只拦 NaN / +Inf / -Inf 以及非数值类型。
    """
    if isinstance(score, bool) or not isinstance(score, (int, float)) or not math.isfinite(score):
        raise NonFiniteRiskScoreError(
            f"{context} 不是有限数值（{score!r}），拒绝映射为风险等级——"
            "否则 NaN 会因比较恒为 False 而被误判为『无风险』。"
        )
    return score


def score_to_level(score: float, modality: str = "structured") -> int:
    """将风险分数转换为风险等级。"""
    ensure_finite_score(score, context=f"score_to_level(modality={modality!r})")
    thresholds = get_threshold_by_modality(modality)
    if score >= thresholds["critical"]:
        return 4
    if score >= thresholds["high"]:
        return 3
    if score >= thresholds["moderate"]:
        return 2
    if score >= thresholds["mild"]:
        return 1
    return 0


def get_fusion_threshold(score: float, confidence: float | None = None) -> int:
    thresholds = MODALITY_RISK_THRESHOLDS["fusion"]
    # M-Core-11 修复：低置信度时仅记录日志而非强制返回 moderate，避免语义混乱；
    # score=0 时返回 0（最低级别）而非 mild 阈值。
    if confidence is not None and confidence < 0.5:
        logger.debug("get_fusion_threshold called with low confidence: %s", confidence)
    if score >= thresholds["critical"]:
        return thresholds["critical"]
    if score >= thresholds["high"]:
        return thresholds["high"]
    if score >= thresholds["moderate"]:
        return thresholds["moderate"]
    if score >= thresholds["mild"]:
        return thresholds["mild"]
    return 0


def should_fallback(confidence: float | None, availability: bool) -> bool:
    if not availability:
        return True
    if confidence is None:
        return False
    return confidence < 0.5
