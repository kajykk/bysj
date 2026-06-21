from __future__ import annotations

# v1.16 校准后的各模态专用阈值 → v1.20 结构化阈值已重新校准
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


def score_to_level(score: float, modality: str = "structured") -> int:
    """将风险分数转换为风险等级。"""
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
    if confidence is not None and confidence < 0.5:
        return thresholds["moderate"]
    if score >= thresholds["critical"]:
        return thresholds["critical"]
    if score >= thresholds["high"]:
        return thresholds["high"]
    if score >= thresholds["moderate"]:
        return thresholds["moderate"]
    if score >= thresholds["mild"]:
        return thresholds["mild"]
    return thresholds["mild"]


def should_fallback(confidence: float | None, availability: bool) -> bool:
    if not availability:
        return True
    if confidence is None:
        return False
    return confidence < 0.5
