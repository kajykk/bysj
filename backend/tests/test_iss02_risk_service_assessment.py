"""ISS-02 / WF-1: app.services.risk_service_assessment 纯方法覆盖率补齐（原 ~14%）。

聚焦 AssessmentMixin 内不依赖 DB / 模型引擎的纯逻辑：
- ``_calculate_heuristic_score``（含 C-01 零值保留修复）
- ``_score_to_level``（依赖 risk_thresholds 配置阈值）
- ``_score_to_severity``（PHQ-9 量纲静态映射）

``assess_structured``（异步 + DB + model_engine）留待后续批次以 mock 方式补齐。
"""
from __future__ import annotations

from app.core.risk_thresholds import get_threshold_by_modality
from app.services.risk_service_assessment import AssessmentMixin


class _FakeRiskService(AssessmentMixin):
    """最小可用子类，仅提供 AssessmentMixin 依赖的类常量。"""

    HEURISTIC_WEIGHTS = {
        "stress_level": 1.0,
        "anxiety": 0.8,
        "financial_pressure": 0.6,
        "panic_attack": 0.5,
        "sleep_duration": 0.5,
        "social_support": 0.3,
    }


def _svc() -> _FakeRiskService:
    return _FakeRiskService()


def test_score_to_severity_boundaries() -> None:
    f = AssessmentMixin._score_to_severity
    assert f(0) == "none"
    assert f(4) == "none"
    assert f(5) == "mild"
    assert f(9) == "mild"
    assert f(10) == "moderate"
    assert f(14) == "moderate"
    assert f(15) == "severe"
    assert f(27) == "severe"


def test_calculate_heuristic_score_known_inputs() -> None:
    svc = _svc()
    features = {
        "stress_level": 10,
        "anxiety": 5,
        "financial_pressure": 2,
        "panic_attack": 3,
        "sleep_duration": 4,
        "social_support": 1,
    }
    # 10*1.0 + 5*0.8 + 2*0.6 + 3*0.5 + (7-4)*0.5 + (5-1)*0.3 = 19.4
    assert abs(svc._calculate_heuristic_score(features) - 19.4) < 1e-6


def test_calculate_heuristic_score_defaults_preserve_zero() -> None:
    """C-01 修复：合法 0 值不应被默认值替换。"""
    svc = _svc()
    # 全部缺省：stress=0 anxiety=0 financial=0 panic=0 sleep=7 social=3
    # => 0 + 0 + 0 + 0 + (7-7)*0.5 + (5-3)*0.3 = 0.6
    assert abs(svc._calculate_heuristic_score({}) - 0.6) < 1e-6

    # 显式 0 的 sleep/social 必须保留，不能回退默认值
    zeroed = {"sleep_duration": 0, "social_support": 0}
    # => (7-0)*0.5 + (5-0)*0.3 = 3.5 + 1.5 = 5.0
    assert abs(svc._calculate_heuristic_score(zeroed) - 5.0) < 1e-6


def test_calculate_heuristic_score_clamps() -> None:
    svc = _svc()
    huge = {k: 1000 for k in svc.HEURISTIC_WEIGHTS}
    assert svc._calculate_heuristic_score(huge) == 100.0
    negative = {k: -1000 for k in svc.HEURISTIC_WEIGHTS}
    assert svc._calculate_heuristic_score(negative) == 0.0


def test_score_to_level_boundaries() -> None:
    svc = _svc()
    t = get_threshold_by_modality("structured")
    assert svc._score_to_level(t["mild"] - 0.01) == 0
    assert svc._score_to_level(t["mild"]) == 1
    assert svc._score_to_level(t["moderate"]) == 2
    assert svc._score_to_level(t["high"]) == 3
    assert svc._score_to_level(t["critical"]) == 4
    assert svc._score_to_level(t["critical"] + 10) == 4


def test_score_to_level_other_modality() -> None:
    svc = _svc()
    # 非 structured 模态也应返回 0-4 等级，不抛异常
    assert svc._score_to_level(0, modality="physiological") == 0
    t = get_threshold_by_modality("physiological")
    assert svc._score_to_level(t["critical"], modality="physiological") == 4
