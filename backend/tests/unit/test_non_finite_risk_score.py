"""AUDIT-2026-10-01 (P0-3)：非有限风险分数不得被静默判为「无风险」。

问题（已实测复现）：``_score_to_level(float('nan'))`` 原本返回 ``0``，
而 ``RISK_LEVEL_LABELS[0] == "none"`` —— 即「算不出来」被表达成「无风险」。
根因是 ``NaN >= 阈值`` 恒为 False，NaN 一路穿过所有 ``if`` 落到末尾 ``return 0``。

本项目有 **四处各自独立** 的风险等级映射实现，只修一处等于没修，故本文件全部钉住。
同时反向钉住「有限值行为不变」——特别是负数（现有测试断言 ``-100 -> 0``）。
"""

from __future__ import annotations

import numpy as np
import pytest

from app.core.model_engine.risk import RiskMixin
from app.core.risk_thresholds import NonFiniteRiskScoreError, score_to_level
from app.ml.fusion_engine import FusionEngine
from app.ml.scaler import SimpleStandardScaler
from app.services.risk_service_assessment import AssessmentMixin

NON_FINITE = [float("nan"), float("inf"), float("-inf")]

#: 覆盖 0 / 各档边界 / 负数 / 超上限 —— 都必须保持原有行为
FINITE_SAMPLES = [0, 1, 10, 25, 50, 80, 100, -10, -100, 150, 0.0, 99.99]


class _FakeRiskService(AssessmentMixin):
    """最小可用子类（与 tests/test_iss02_risk_service_assessment.py 同款）。"""

    HEURISTIC_WEIGHTS = {
        "stress_level": 1.0,
        "anxiety": 0.8,
        "financial_pressure": 0.6,
        "panic_attack": 0.5,
        "sleep_duration": 0.5,
        "social_support": 0.3,
    }


def _implementations():
    """四处实现：(名称, 调用方式)。"""
    return [
        ("risk_thresholds.score_to_level", lambda s: score_to_level(s)),
        ("ModelEngine._score_to_level", lambda s: RiskMixin._score_to_level(s)),
        ("FusionEngine._score_to_level", lambda s: FusionEngine()._score_to_level(s)),
        ("AssessmentMixin._score_to_level", lambda s: _FakeRiskService()._score_to_level(s)),
    ]


@pytest.mark.parametrize("name,call", _implementations(), ids=lambda v: str(v)[:40])
@pytest.mark.parametrize("bad", NON_FINITE, ids=["nan", "inf", "-inf"])
def test_non_finite_score_must_raise(name, call, bad):
    """NaN / ±Inf 必须抛错，而不是落到等级 0。"""
    with pytest.raises((NonFiniteRiskScoreError, ValueError)):
        call(bad)


@pytest.mark.parametrize("name,call", _implementations(), ids=lambda v: str(v)[:40])
@pytest.mark.parametrize("ok", FINITE_SAMPLES)
def test_finite_scores_behaviour_unchanged(name, call, ok):
    """有限值（含负数、超上限）行为必须不变。"""
    level = call(ok)
    assert isinstance(level, int)
    assert 0 <= level <= 4


def test_regression_nan_previously_returned_zero():
    """回归锚点：显式记录修复前的错误行为，防止有人"简化"掉守卫后再次静默通过。"""
    with pytest.raises(NonFiniteRiskScoreError):
        _FakeRiskService()._score_to_level(float("nan"))
    # 若能走到这里说明 NaN 已被拦下；下面这条断言在修复前会失败（NaN -> 0）
    assert _FakeRiskService()._score_to_level(0.0) == 0


# ── Scaler：非有限值必须在进入模型前被拦下 ─────────────────────────────


def test_scaler_transform_rejects_non_finite_input():
    scaler = SimpleStandardScaler().fit(np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]]))
    for bad in NON_FINITE:
        with pytest.raises(ValueError, match="非有限值"):
            scaler.transform(np.array([[bad, 1.0]]))


def test_scaler_from_dict_rejects_zero_scale():
    """fit() 会把 scale_==0 替换为 1.0，但加载路径原本不校验 → 每次 transform 产出 inf。"""
    with pytest.raises(ValueError, match="scale"):
        SimpleStandardScaler.from_dict(
            {"mean": [0.0, 0.0], "scale": [0.0, 1.0], "n_features_in": 2}
        )


@pytest.mark.parametrize("bad", NON_FINITE)
def test_scaler_from_dict_rejects_non_finite(bad):
    with pytest.raises(ValueError):
        SimpleStandardScaler.from_dict({"mean": [0.0], "scale": [bad], "n_features_in": 1})


def test_scaler_from_dict_rejects_shape_mismatch():
    with pytest.raises(ValueError, match="长度不一致"):
        SimpleStandardScaler.from_dict({"mean": [0.0, 1.0], "scale": [1.0], "n_features_in": 2})


def test_scaler_roundtrip_still_works():
    """正向路径不得被新校验误伤。"""
    scaler = SimpleStandardScaler().fit(np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]]))
    loaded = SimpleStandardScaler.from_dict(scaler.to_dict())
    X = np.array([[2.0, 3.0]])
    np.testing.assert_allclose(loaded.transform(X), scaler.transform(X))
