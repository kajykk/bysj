"""app.core.confidence 的口径锁定测试。

AUDIT-2026-10-04 (P2-2): 置信度阈值原先硬编码在 fusion_priority_engine(0.5/3)
与 model_engine/fusion(0.8/0.5) 两处，本文件把**旧内联实现作为 oracle** 写进来，
任何阈值改动都必须同步更新 oracle 并显式承认行为变化——否则口径会无声漂移。
"""

from __future__ import annotations

import pytest

from app.core.confidence import (
    HIGH_RISK_LEVEL_THRESHOLD,
    LLM_REVIEW_ZONE,
    LOW_CONFIDENCE_THRESHOLD,
    MODALITY_LOW_CONFIDENCE_THRESHOLD,
    MODALITY_PRIMARY_CONFIDENCE_THRESHOLD,
    in_llm_review_zone,
    is_low_confidence_high_risk,
    modality_quality,
)

CONFIDENCE_CASES = [0.0, 0.05, 0.299, 0.3, 0.4999, 0.5, 0.5999, 0.6, 0.7999, 0.8, 0.95, 1.0]


# ---------- oracle: 改动前的内联实现（原样复制） ----------


def _oracle_modality_quality(confidence: float) -> str:
    if confidence >= 0.8:
        return "primary"
    if confidence >= 0.5:
        return "secondary"
    return "low_confidence"


def _oracle_low_conf_high_risk(confidence: float, risk_level: int) -> bool:
    return confidence < 0.5 and risk_level >= 3


# ---------- 阈值常量 ----------


def test_thresholds_match_original_hardcoded_values():
    """常量值必须等于迁移前的硬编码值, 否则等于偷偷改了行为。"""
    assert LOW_CONFIDENCE_THRESHOLD == 0.5
    assert HIGH_RISK_LEVEL_THRESHOLD == 3
    assert MODALITY_LOW_CONFIDENCE_THRESHOLD == 0.5
    assert MODALITY_PRIMARY_CONFIDENCE_THRESHOLD == 0.8
    assert LLM_REVIEW_ZONE == (0.3, 0.6)


# ---------- 与 oracle 的等价性 ----------


@pytest.mark.parametrize("confidence", CONFIDENCE_CASES)
def test_modality_quality_matches_oracle(confidence: float):
    assert modality_quality(confidence) == _oracle_modality_quality(confidence)


@pytest.mark.parametrize("confidence", CONFIDENCE_CASES)
@pytest.mark.parametrize("risk_level", [0, 1, 2, 3, 4])
def test_low_confidence_high_risk_matches_oracle(confidence: float, risk_level: int):
    assert is_low_confidence_high_risk(confidence, risk_level) == _oracle_low_conf_high_risk(
        confidence, risk_level
    )


# ---------- 边界语义（写死意图, 防回归） ----------


def test_modality_quality_boundaries():
    assert modality_quality(0.8) == "primary"      # >= 0.8 归 primary
    assert modality_quality(0.7999) == "secondary"
    assert modality_quality(0.5) == "secondary"     # >= 0.5 归 secondary
    assert modality_quality(0.4999) == "low_confidence"


def test_low_confidence_high_risk_needs_both_conditions():
    # 低置信但风险不够 -> 不触发
    assert not is_low_confidence_high_risk(0.4, 2)
    # 风险高但置信足够 -> 不触发
    assert not is_low_confidence_high_risk(0.6, 4)
    # 两者都满足 -> 触发
    assert is_low_confidence_high_risk(0.4, 3)
    assert is_low_confidence_high_risk(0.0, 4)


# ---------- LLM 复核灰区（P2-2 实验接口, 未接生产） ----------


def test_llm_review_zone_is_lower_inclusive_upper_exclusive():
    assert in_llm_review_zone(0.3) is True
    assert in_llm_review_zone(0.2999) is False
    assert in_llm_review_zone(0.5999) is True
    assert in_llm_review_zone(0.6) is False


def test_llm_review_zone_is_disjoint_from_production_low_confidence_trigger():
    """两个概念用途不同: 灰区(给 LLM 第二意见) 与 生产人工复核触发。

    这里锁住它们**不被混用**: 生产触发看 risk_level, 灰区只看 confidence。
    """
    # 灰区内但风险低 -> 生产不触发人工复核(风险不足), 灰区成立
    conf, risk = 0.45, 1
    assert in_llm_review_zone(conf) and not is_low_confidence_high_risk(conf, risk)
    # 灰区外但生产触发(低置信+高风险) -> 两者可以不一致, 但不该互相影响
    conf2, risk2 = 0.2, 4
    assert not in_llm_review_zone(conf2) and is_low_confidence_high_risk(conf2, risk2)
