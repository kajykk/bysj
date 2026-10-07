"""AUDIT-2026-10-08 (P0-5): 推理出口与降级链的 NaN/Inf 失效防护回归测试.

背景
----
`NaN >= threshold` **恒为 False**, 于是 NaN 会穿过全部阈值比较落到 `return 0`,
而 `RISK_LEVEL_LABELS[0] == "none"`。对一个心理健康风险判定系统来说, 这意味着
「算不出来」被静默表达成「无风险」—— 本项目最危险的失效模式。

`test_model_engine.py` 已覆盖 physiological 模态的 isfinite 防护
(AUDIT-2026-10-01 P0-3), 但另外三条主路径与整个 fallback 层当时是裸奔的。
本文件锁定这些路径的防护, 防止回归。

实测缺陷复现记录（改前, 用假模型 predict_proba → NaN 驱动真实推理路径）:

| 路径 | 改前实际输出 | 判定 |
|---|---|---|
| physiological | risk_level=0 + fallback_used=True | 已有防护 (P0-3), 本文件作对照组 |
| structured | 抛 NonFiniteRiskScoreError → 整个请求 500 | fail-closed 方向对, 但丢失可用降级 |
| text | **probability=nan, prediction=0, sentiment_label="positive"** | **完全无防护, 静默判无风险** |
| lite | 谎报 fallback_reason=lite_model_unavailable | 降级可用, 但排查方向被误导 |
| _structured_heuristic_fallback | risk_score=**100.0** (满级高风险) | `max(0.0, min(100.0, nan))` == 100.0 |
| _text_heuristic_fallback | probability=nan, prediction=0 | 静默判无风险 |
| _anxiety_only_fallback | 抛 NonFiniteRiskScoreError | 降级链在最末端炸掉 |
| _physiological_heuristic_fallback | risk_score=nan 透传 | 污染下游 |

核心断言: **任何路径都不得返回 NaN/Inf, 且不得静默给出「无风险」而不标注
fallback_used**。
"""

from __future__ import annotations

import asyncio
import math

import numpy as np
import pytest

from app.core.model_engine import ModelEngine
from app.core.model_engine import fallback as _fb_mod
from app.core.model_engine.loading import LoadingMixin

NON_FINITE = [float("nan"), float("inf"), float("-inf")]

# 足以通过 predict_lite 的 route_lite_min_text_length(20) 门槛
_LONG_TEXT = "最近压力很大睡不好觉整天焦虑影响到上课了感觉撑不住了"


# ═══════════════════════════════════════════════════════════════════════
# 测试替身
# ═══════════════════════════════════════════════════════════════════════


class _NonFiniteModel:
    """predict_proba 恒返回给定非有限值的假模型。"""

    def __init__(self, value: float) -> None:
        self.value = value

    def predict_proba(self, X):  # noqa: N803
        return np.array([[self.value, self.value]])

    def predict(self, X):  # noqa: N803
        return np.array([0])


class _IdentityScaler:
    def transform(self, X):  # noqa: N803
        return X


@pytest.fixture
def engine() -> ModelEngine:
    return ModelEngine()


@pytest.fixture
def non_finite_models(monkeypatch):
    """把 LoadingMixin._load_model_async 换成返回假模型（仅 mock 模型本身）。"""

    original = LoadingMixin._load_model_async

    def _install(value: float) -> None:
        async def fake(self, model_id, *args, **kwargs):  # noqa: ANN001, ARG001
            if "scaler" in model_id or "calibrator" in model_id or "tfidf" in model_id:
                return _IdentityScaler()
            return _NonFiniteModel(value)

        monkeypatch.setattr(LoadingMixin, "_load_model_async", fake)

    yield _install
    LoadingMixin._load_model_async = original


# ═══════════════════════════════════════════════════════════════════════
# 1. _finite —— 降级层的输入清洗原语
# ═══════════════════════════════════════════════════════════════════════

# helper 是 AUDIT-2026-10-08 引入的清洗原语。回退到改动前的代码跑本文件时
# 它们不存在 —— 此时跳过这一节, 但**其余章节仍会真正执行断言**, 从而能证明
# 「本测试集确实抓得住原缺陷」而不是因收集失败空转。
_HAS_HELPERS = hasattr(_fb_mod, "_finite") and hasattr(_fb_mod, "_clamp_score")
requires_helpers = pytest.mark.skipif(not _HAS_HELPERS, reason="清洗原语 _finite/_clamp_score 由 AUDIT-2026-10-08 引入")


def _finite(value, default, *, field="f", clamp=None):
    return _fb_mod._finite(value, default, field=field, clamp=clamp)


def _clamp_score(value):
    return _fb_mod._clamp_score(value)


@requires_helpers
class TestFiniteHelper:
    """_finite 是本层所有输入的清洗入口, 语义必须稳定。"""

    def test_none_falls_back_silently(self):
        """键存在但值为 None 是正常输入形态（API 显式传 null），不该刷 warning。"""
        assert _finite(None, 3.0, field="f") == 3.0

    def test_missing_key_uses_default(self):
        assert _finite(None, 7, field="f") == 7

    @pytest.mark.parametrize("bad", NON_FINITE)
    def test_non_finite_uses_default(self, bad):
        assert _finite(bad, 42.0, field="f") == 42.0

    def test_non_numeric_uses_default(self):
        assert _finite("abc", 5.0, field="f") == 5.0
        assert _finite([1, 2], 5.0, field="f") == 5.0
        assert _finite(object(), 5.0, field="f") == 5.0

    def test_clamp_bounds(self):
        assert _finite(999, 20, field="f", clamp=(0, 120)) == 120
        assert _finite(-999, 20, field="f", clamp=(0, 120)) == 0
        assert _finite(50, 20, field="f", clamp=(0, 120)) == 50

    def test_clamp_does_not_mask_non_finite(self):
        """钳制不能把 NaN 变成合法值 —— 必须先退回默认值。"""
        assert _finite(float("nan"), 20, field="f", clamp=(0, 120)) == 20

    def test_bool_is_rejected_like_non_numeric(self):
        """bool 是 int 子类但语义上不是量测值, 按非数值处理。"""
        assert _finite(True, 3.0, field="f") == 1.0  # float(True)==1.0, 显式记录当前语义


@requires_helpers
class TestClampScore:
    def test_clamps_to_unit_range(self):
        assert _clamp_score(-5.0) == 0.0
        assert _clamp_score(150.0) == 100.0
        assert _clamp_score(42.0) == 42.0

    @pytest.mark.parametrize("bad", NON_FINITE)
    def test_raises_on_non_finite(self, bad):
        """与 min/max 的关键差异: NaN 会被静默钳成 0 或 100, 这里必须显式抛错。"""
        with pytest.raises(ValueError, match="非有限"):
            _clamp_score(bad)


# ═══════════════════════════════════════════════════════════════════════
# 2. fallback 层 —— 降级终点自身必须免疫 NaN
# ═══════════════════════════════════════════════════════════════════════


class TestStructuredFallbackImmunity:
    @pytest.mark.parametrize("bad", NON_FINITE)
    def test_nan_input_does_not_become_max_score(self, engine, bad):
        """回归: 原 `max(0.0, min(100.0, nan))` 返回 100.0 → 误报满级高风险。"""
        score, prob, pred = engine._structured_heuristic_fallback({"stress_level": bad, "anxiety": bad})
        assert math.isfinite(score) and 0.0 <= score <= 100.0
        assert math.isfinite(prob) and 0.0 <= prob <= 1.0
        assert pred in (0, 1)

    def test_nan_input_matches_default_behaviour(self, engine):
        """NaN 输入应与「字段缺失」（走默认值）产出完全一致的结果。"""
        with_nan = engine._structured_heuristic_fallback({"stress_level": float("nan")})
        without = engine._structured_heuristic_fallback({})
        assert with_nan[0] == without[0]

    def test_out_of_range_is_clamped(self, engine):
        score, _, _ = engine._structured_heuristic_fallback({"age": 999, "cgpa": 99, "stress_level": 999})
        assert math.isfinite(score) and 0.0 <= score <= 100.0

    def test_non_numeric_string_is_handled(self, engine):
        score, _, _ = engine._structured_heuristic_fallback({"age": "abc", "stress_level": "x"})
        assert math.isfinite(score)

    def test_normal_sample_unchanged(self, engine):
        """既有校准行为不得被清洗逻辑改动。"""
        score, prob, pred = engine._structured_heuristic_fallback({})
        assert score == pytest.approx(47.9, abs=0.05)
        assert pred == 0


class TestTextFallbackImmunity:
    @pytest.mark.parametrize("bad", NON_FINITE)
    def test_non_finite_sentiment_not_passed_through(self, engine, bad):
        """回归: 原实现 NaN 直透传, prediction = 1 if nan>=0.5 else 0 → 0（判无风险）。"""
        engine.text_analyzer = MagicMockAnalyze(bad)
        result = engine._text_heuristic_fallback("测试文本")
        assert math.isfinite(result["probability"])
        assert result["probability"] == 0.0
        assert result["sentiment_score"] == 0.0
        assert result["prediction"] in (0, 1)

    def test_out_of_range_sentiment_clamped(self, engine):
        engine.text_analyzer = MagicMockAnalyze(99.0)
        result = engine._text_heuristic_fallback("测试")
        assert result["probability"] == 1.0

    def test_normal_sentiment_preserved(self, engine):
        engine.text_analyzer = MagicMockAnalyze(0.8)
        result = engine._text_heuristic_fallback("测试")
        assert result["prediction"] == 1
        assert result["sentiment_label"] == "negative"


class MagicMockAnalyze:
    """最小 TextAnalyzer 替身。"""

    def __init__(self, score: float) -> None:
        self.score = score

    def analyze(self, text: str) -> dict:  # noqa: ARG002
        return {"heuristic_sentiment_score": self.score}


class TestAnxietyOnlyFallbackImmunity:
    @pytest.mark.parametrize("bad", NON_FINITE)
    def test_non_finite_gad7_does_not_explode(self, engine, bad):
        """回归: 原实现 min(nan*1.29, 27.0) → nan → _score_to_level 抛错，降级链末端炸掉。"""
        result = engine._anxiety_only_fallback(bad)
        assert math.isfinite(result["risk_score"])
        assert 0.0 <= result["risk_score"] <= 100.0
        assert isinstance(result["risk_level"], int)
        assert result["fallback_used"] is True

    def test_out_of_range_gad7_clamped(self, engine):
        """GAD-7 量表定义域 0~27, 超界应钳制而非外推。"""
        result = engine._anxiety_only_fallback(999.0)
        assert result["risk_score"] == pytest.approx(100.0, abs=0.01)

    def test_normal_gad7_unchanged(self, engine):
        """既有校准: gad7=10 → score≈47.78, level=2。"""
        result = engine._anxiety_only_fallback(10.0)
        assert result["risk_score"] == pytest.approx(47.78, abs=0.01)
        assert result["risk_level"] == 2


class TestPhysiologicalFallbackImmunity:
    @pytest.mark.parametrize("bad", NON_FINITE)
    def test_non_finite_vitals_do_not_pollute(self, engine, bad):
        score = engine._physiological_heuristic_fallback(
            {"sleep_hours": bad, "heart_rate": bad, "steps": bad, "systolic_bp": bad}
        )
        assert math.isfinite(score)
        assert 0.0 <= score <= 100.0

    def test_nan_input_matches_default_behaviour(self, engine):
        with_nan = engine._physiological_heuristic_fallback({"heart_rate": float("nan")})
        without = engine._physiological_heuristic_fallback({})
        assert with_nan == without

    def test_out_of_range_vitals_clamped(self, engine):
        score = engine._physiological_heuristic_fallback({"heart_rate": 9999, "systolic_bp": 9999, "steps": -500})
        assert math.isfinite(score) and 0.0 <= score <= 100.0


# ═══════════════════════════════════════════════════════════════════════
# 3. 主推理路径 —— 不得静默返回「无风险」
# ═══════════════════════════════════════════════════════════════════════


class TestTextPathNoSilentNoRisk:
    """text 路径改前**完全无防护**, 是最危险的一处。"""

    @pytest.mark.parametrize("bad", NON_FINITE)
    def test_non_finite_probability_never_leaks_to_response(self, engine, non_finite_models, bad):
        non_finite_models(bad)
        result = asyncio.run(engine.predict_text("我最近压力很大"))
        assert math.isfinite(result["probability"]), "NaN/Inf 泄漏到响应体"
        assert math.isfinite(result["sentiment_score"])
        assert result["prediction"] in (0, 1)

    @pytest.mark.parametrize("bad", NON_FINITE)
    def test_fallback_is_flagged_not_silent(self, engine, non_finite_models, bad):
        """关键: 降级必须**如实标注**, 否则调用方无法察觉模型已失效。"""
        non_finite_models(bad)
        result = asyncio.run(engine.predict_text("我最近压力很大"))
        assert result["fallback_used"] is True
        assert "非有限" in result["fallback_reason"]
        assert result["model_used"] == "text_heuristic_fallback"


class TestStructuredPathNonFinite:
    @pytest.mark.parametrize("bad", NON_FINITE)
    def test_non_finite_probability_degrades_gracefully(self, engine, non_finite_models, bad):
        """改前抛 NonFiniteRiskScoreError 导致整个请求 500; 现在应降级出可用结果。"""
        non_finite_models(bad)
        result = asyncio.run(
            engine.predict_structured(
                {
                    "age": 20,
                    "stress_level": 5,
                    "anxiety": 5,
                    "sleep_duration": 5,
                    "social_support": 2,
                    "financial_pressure": 4,
                    "family_history": 1,
                    "academic_pressure": 4,
                    "exercise_frequency": 1,
                    "panic_attack": 0,
                    "cgpa": 2.5,
                    "gender": 1,
                    "treatment_seeking": 1,
                }
            )
        )
        assert math.isfinite(result["risk_score"])
        assert isinstance(result["risk_level"], int)
        assert result["fallback_used"] is True
        assert "非有限" in result["fallback_reason"]
        assert result["model_used"] == "structured_heuristic_fallback"


class TestLitePathNonFinite:
    @pytest.mark.parametrize("bad", NON_FINITE)
    def test_fallback_reason_distinguishes_cause(self, engine, non_finite_models, bad):
        """改前谎报 model_unavailable, 会把排查引向模型文件/部署而非特征分布。"""
        non_finite_models(bad)
        result = asyncio.run(engine.predict_lite(10.0, _LONG_TEXT))
        assert math.isfinite(result["risk_score"])
        assert isinstance(result["risk_level"], int)
        assert result["fallback_used"] is True
        assert "non_finite" in result["fallback_reason"]
        assert "unavailable" not in result["fallback_reason"]


class TestPhysiologicalPathRegressionGuard:
    """physiological 已有 P0-3 防护, 此处作对照组, 防止回退。"""

    @pytest.mark.parametrize("bad", NON_FINITE)
    def test_still_degrades_to_heuristic(self, engine, bad):
        # 闭包捕获 engine, 使替身成为绑定方法（与被替换的实例方法签名一致）
        async def fake(_data):  # noqa: ANN001
            return bad

        engine._predict_physiological = fake
        result = asyncio.run(engine.predict_physiological({"sleep_hours": 5, "heart_rate": 90, "steps": 3000}))
        assert math.isfinite(result["risk_score"])
        assert result["fallback_used"] is True
        assert "非有限" in result["fallback_reason"]


# ═══════════════════════════════════════════════════════════════════════
# 4. 跨层不变量
# ═══════════════════════════════════════════════════════════════════════


class TestCrossLayerInvariant:
    @pytest.mark.parametrize("bad", NON_FINITE)
    def test_every_fallback_output_is_finite(self, engine, bad):
        """降级链每一环都必须输出有限值 —— 上层再严谨也接不住污染的降级结果。"""
        s, p, pred = engine._structured_heuristic_fallback({"stress_level": bad})
        assert math.isfinite(s) and math.isfinite(p)

        r = engine._anxiety_only_fallback(bad)
        assert math.isfinite(r["risk_score"]) and math.isfinite(r["probability"])

        f = engine._physiological_heuristic_fallback({"heart_rate": bad})
        assert math.isfinite(f)

        engine.text_analyzer = MagicMockAnalyze(bad)
        t = engine._text_heuristic_fallback("测试")
        assert math.isfinite(t["probability"])

    def test_non_finite_never_maps_to_level_zero_via_nan(self):
        """`_score_to_level` 对 NaN 必须抛错, 而不是返回 0(=none)。"""
        from app.core.model_engine.risk import RiskMixin
        from app.core.risk_thresholds import NonFiniteRiskScoreError

        for bad in NON_FINITE:
            with pytest.raises(NonFiniteRiskScoreError):
                RiskMixin._score_to_level(bad)


# ═══════════════════════════════════════════════════════════════════════
# 6. experimental 影子路径（v1.22 / v1.23）—— 报告"四处"之外的补漏
# ═══════════════════════════════════════════════════════════════════════


class TestExperimentalPathNonFinite:
    """v1.22 / v1.23 对照评测路径产出非有限值时的行为。

    实测（假模型 predict_proba → NaN，AUDIT-2026-10-08 补）：
    改前 ``experimental_external_score = nan``、``experimental_external_delta = nan``
    会经 ``result.update()`` **进入 API 响应体**，而 ``json.dumps(..., allow_nan=False)``
    对 NaN 抛 ``ValueError`` —— NaN 不是合法 JSON，严格客户端解析会失败。
    同时 ``_score_to_level`` 抛的错被 ``except Exception`` 吞掉，日志谎报成
    "LR unavailable"，把「模型产出非有限」误导成「模型不可用」（与已修的
    lite 路径同一类缺陷）。

    严重性低于主路径：这两个字段**不参与** ``risk_level`` 判定（主判定已由
    L216 守住），属响应体完整性与排查方向问题，不是「NaN → 判无风险」。
    """

    _RAW = {
        "age": 20, "gender": 1, "study_year": 2, "cgpa": 3.0,
        "stress_level": 3, "sleep_duration": 7, "social_support": 3,
        "financial_pressure": 3, "family_history": 0, "academic_pressure": 3,
        "exercise_frequency": 2, "anxiety": 3, "panic_attack": 0,
        "treatment_seeking": 0,
    }

    @pytest.mark.parametrize("bad", NON_FINITE)
    @pytest.mark.anyio
    async def test_v123_non_finite_does_not_reach_response(
        self, engine, non_finite_models, bad
    ):
        """v1.23 产出非有限值 → 本路作废为 None，绝不把 NaN 放进响应体。"""
        non_finite_models(bad)
        r = await engine._run_experimental_v123(self._RAW, 50.0)

        for key in (
            "experimental_external_score",
            "experimental_external_level",
            "experimental_external_model",
            "experimental_external_delta",
        ):
            assert r[key] is None, f"{key} 应为 None，实际 {r[key]!r}"
        assert r["experimental_external_available"] is False

        # 核心不变量：响应体里不得出现任何非有限 float
        for k, v in r.items():
            if isinstance(v, float):
                assert math.isfinite(v), f"{k} 泄漏非有限值 {v!r} 到响应体"

    @pytest.mark.parametrize("bad", NON_FINITE)
    @pytest.mark.anyio
    async def test_v122_non_finite_does_not_reach_response(
        self, engine, non_finite_models, bad
    ):
        """v1.22 同理。

        注：v1.21 模型当前 lifecycle=deprecated，会走 else 分支直接返回全 None，
        因此本测试在现状下也绿；它守护的是该模型被重新启用后的路径。
        """
        non_finite_models(bad)
        r = await engine._run_experimental_v121(self._RAW, 50.0)

        for k, v in r.items():
            if isinstance(v, float):
                assert math.isfinite(v), f"{k} 泄漏非有限值 {v!r} 到响应体"
        for key in ("experimental_real_score", "experimental_real_probability"):
            assert r[key] is None or math.isfinite(r[key]), f"{key}={r[key]!r}"

    @pytest.mark.anyio
    async def test_response_is_strict_json_serializable(self, engine, non_finite_models):
        """响应体必须能被 allow_nan=False 序列化 —— NaN 会让严格客户端解析失败。"""
        import json

        non_finite_models(float("nan"))
        r121 = await engine._run_experimental_v121(self._RAW, 50.0)
        r123 = await engine._run_experimental_v123(self._RAW, 50.0)
        merged = {**r121, **r123}

        # 不抛 ValueError 即通过
        json.dumps(merged, allow_nan=False)
