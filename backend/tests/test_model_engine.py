"""MAINT-P0-001: ModelEngine 专属单元测试.

聚焦 model_engine.py 中完全无直接单元测试的核心方法, 覆盖:
- 4 层回退逻辑: _structured_heuristic_fallback / _anxiety_only_fallback
  / _text_heuristic_fallback / _physiological_heuristic_fallback
- 4 层路由: _route_structured (f_coverage≥0.8 / lite / anxiety_only / insufficient)
- 特征预处理: _build_structured_input / LiteFeatureExtractor.extract
- 风险映射: score_to_level / _score_to_level / _level_to_severity
- 干预计划: _build_intervention_plan
- 危机检查: _check_crisis_safety
- 门控: _attention_gate / _boost_gate_for_physiology

不重复以下已有测试覆盖的范围:
- test_model_cache_lru.py: LRU 缓存层
- test_predict_structured_parallel.py: asyncio.gather 并行执行
- test_predict_structured_quality.py: 端到端数据质量检测
- test_predict_physiological_confidence.py: 端到端置信度计算
- api/test_model_predict.py: 端到端模型预测
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.core.model_engine import LiteFeatureExtractor, ModelEngine

# ═══════════════════════════════════════════════════════════════════════
# 1. _structured_heuristic_fallback (4 层回退 - 结构化)
# ═══════════════════════════════════════════════════════════════════════


class TestStructuredHeuristicFallback:
    """测试结构化启发式回退 (_structured_heuristic_fallback).

    源码注释校准点:
    - 健康样本 ~8 分
    - 中等风险 ~54 分
    - 高风险/极高风险 ~100 分
    返回 (risk_score, probability, prediction).
    """

    @pytest.fixture
    def engine(self) -> ModelEngine:
        return ModelEngine()

    def test_healthy_sample_low_score(self, engine: ModelEngine) -> None:
        """健康样本应返回低风险分数 (≤20)."""
        raw = {
            "age": 22,
            "cgpa": 3.8,
            "stress_level": 1,
            "sleep_duration": 8,
            "social_support": 5,
            "financial_pressure": 1,
            "family_history": 0,
            "academic_pressure": 1,
            "exercise_frequency": 3,
            "anxiety": 1,
            "panic_attack": 0,
            "treatment_seeking": 0,
        }
        score, prob, pred = engine._structured_heuristic_fallback(raw)
        assert 0 <= score <= 20, f"健康样本分数 {score} 应在 0-20 区间"
        assert prob == score / 100.0
        assert pred == 0  # risk_score < 50 -> 0

    def test_medium_risk_sample(self, engine: ModelEngine) -> None:
        """中等风险样本应返回 30-70 区间分数."""
        raw = {
            "age": 20,
            "cgpa": 3.0,
            "stress_level": 3,
            "sleep_duration": 6,
            "social_support": 3,
            "financial_pressure": 3,
            "family_history": 0,
            "academic_pressure": 3,
            "exercise_frequency": 1,
            "anxiety": 3,
            "panic_attack": 0,
            "treatment_seeking": 0,
        }
        score, prob, pred = engine._structured_heuristic_fallback(raw)
        assert 30 <= score <= 70, f"中等风险分数 {score} 应在 30-70 区间"
        assert prob == score / 100.0
        # 中等风险可能 pred=0 或 1, 不强制断言

    def test_high_risk_sample(self, engine: ModelEngine) -> None:
        """高风险样本应返回 ≥70 分且 prediction=1."""
        raw = {
            "age": 19,
            "cgpa": 2.0,
            "stress_level": 5,
            "sleep_duration": 3,
            "social_support": 1,
            "financial_pressure": 5,
            "family_history": 1,
            "academic_pressure": 5,
            "exercise_frequency": 0,
            "anxiety": 5,
            "panic_attack": 1,
            "treatment_seeking": 1,
        }
        score, prob, pred = engine._structured_heuristic_fallback(raw)
        assert score >= 70, f"高风险分数 {score} 应 ≥70"
        assert pred == 1  # risk_score >= 50 -> 1
        assert prob == score / 100.0

    def test_extreme_risk_clamped_to_100(self, engine: ModelEngine) -> None:
        """极高风险样本应被裁剪到 100."""
        raw = {
            "age": 18,
            "cgpa": 0,
            "stress_level": 5,
            "sleep_duration": 0,
            "social_support": 0,
            "financial_pressure": 5,
            "family_history": 1,
            "academic_pressure": 5,
            "exercise_frequency": 0,
            "anxiety": 5,
            "panic_attack": 1,
            "treatment_seeking": 1,
        }
        score, _, pred = engine._structured_heuristic_fallback(raw)
        assert score == 100.0, f"极高风险分数 {score} 应被裁剪到 100"
        assert pred == 1

    def test_protective_factors_reduce_score(self, engine: ModelEngine) -> None:
        """保护因子 (高 GPA + 年长) 应降低风险分数."""
        base_raw = {
            "age": 19,
            "cgpa": 2.0,
            "stress_level": 4,
            "sleep_duration": 5,
            "social_support": 2,
            "financial_pressure": 3,
            "family_history": 0,
            "academic_pressure": 3,
            "exercise_frequency": 1,
            "anxiety": 3,
            "panic_attack": 0,
            "treatment_seeking": 0,
        }
        protective_raw = dict(base_raw)
        protective_raw["cgpa"] = 4.0  # 提高 GPA
        protective_raw["age"] = 35  # 提高年龄

        base_score, _, _ = engine._structured_heuristic_fallback(base_raw)
        protective_score, _, _ = engine._structured_heuristic_fallback(protective_raw)
        assert protective_score < base_score, "保护因子应降低分数"

    def test_empty_input_uses_defaults(self, engine: ModelEngine) -> None:
        """空输入应使用默认值, 不抛异常, 返回合法分数."""
        score, prob, pred = engine._structured_heuristic_fallback({})
        assert 0 <= score <= 100
        assert 0 <= prob <= 1
        assert pred in (0, 1)

    def test_panic_attack_high_weight(self, engine: ModelEngine) -> None:
        """panic_attack (权重 15) 应显著提升分数."""
        base_raw = {
            "age": 22,
            "cgpa": 3.5,
            "stress_level": 2,
            "sleep_duration": 7,
            "social_support": 4,
            "financial_pressure": 2,
            "family_history": 0,
            "academic_pressure": 2,
            "exercise_frequency": 2,
            "anxiety": 2,
            "panic_attack": 0,
            "treatment_seeking": 0,
        }
        panic_raw = dict(base_raw)
        panic_raw["panic_attack"] = 1

        base_score, _, _ = engine._structured_heuristic_fallback(base_raw)
        panic_score, _, _ = engine._structured_heuristic_fallback(panic_raw)
        # panic_attack 权重 15, 至少提升 15 分 (减去保护因子差异)
        assert panic_score - base_score >= 10, "panic_attack 应显著提升分数"

    def test_prediction_threshold_at_50(self, engine: ModelEngine) -> None:
        """prediction=1 当且仅当 risk_score >= 50."""
        raw = {
            "age": 20,
            "cgpa": 3.0,
            "stress_level": 3,
            "sleep_duration": 6,
            "social_support": 3,
            "financial_pressure": 3,
            "family_history": 0,
            "academic_pressure": 3,
            "exercise_frequency": 1,
            "anxiety": 3,
            "panic_attack": 0,
            "treatment_seeking": 0,
        }
        score, _, pred = engine._structured_heuristic_fallback(raw)
        if score >= 50:
            assert pred == 1
        else:
            assert pred == 0


# ═══════════════════════════════════════════════════════════════════════
# 2. _anxiety_only_fallback (4 层回退 - 仅焦虑)
# ═══════════════════════════════════════════════════════════════════════


class TestAnxietyOnlyFallback:
    """测试仅焦虑回退 (_anxiety_only_fallback).

    公式: estimated = min(gad7 * 1.29, 27) -> risk_score = estimated / 27 * 100
    """

    @pytest.fixture
    def engine(self) -> ModelEngine:
        return ModelEngine()

    def test_zero_gad7(self, engine: ModelEngine) -> None:
        """GAD-7=0 应返回 0 分."""
        result = engine._anxiety_only_fallback(0.0)
        assert result["risk_score"] == 0.0
        assert result["prediction"] == 0
        assert result["probability"] == 0.0
        assert result["model_used"] == "anxiety_only_heuristic"
        assert result["fallback_used"] is True
        assert result["model_family"] == "fallback"

    def test_low_gad7(self, engine: ModelEngine) -> None:
        """GAD-7=5 应返回 ~23.89 分."""
        result = engine._anxiety_only_fallback(5.0)
        expected = round(5.0 * 1.29 / 27.0 * 100, 2)
        assert result["risk_score"] == expected
        assert result["prediction"] == 0  # 23.89 < 50

    def test_high_gad7(self, engine: ModelEngine) -> None:
        """GAD-7=15 应返回 ~71.67 分, prediction=1."""
        result = engine._anxiety_only_fallback(15.0)
        expected = round(15.0 * 1.29 / 27.0 * 100, 2)
        assert result["risk_score"] == expected
        assert result["prediction"] == 1  # 71.67 >= 50

    def test_capped_gad7(self, engine: ModelEngine) -> None:
        """GAD-7≥21 (estimated 被裁剪到 27) 应返回 100 分."""
        result = engine._anxiety_only_fallback(21.0)
        assert result["risk_score"] == 100.0
        assert result["probability"] == 1.0
        assert result["prediction"] == 1

    def test_extreme_gad7_capped(self, engine: ModelEngine) -> None:
        """极高 GAD-7 (如 100) 也应被裁剪到 27, 返回 100 分."""
        result = engine._anxiety_only_fallback(100.0)
        assert result["risk_score"] == 100.0

    def test_risk_level_uses_structured_threshold(self, engine: ModelEngine) -> None:
        """risk_level 应使用默认阈值 (无 modality 参数)."""
        # gad7=10 -> score=47.78 -> level=2 (moderate>=40)
        result = engine._anxiety_only_fallback(10.0)
        # 默认 RISK_LEVEL_THRESHOLDS: mild=20, moderate=40, high=60, critical=80
        assert result["risk_level"] == 2


# ═══════════════════════════════════════════════════════════════════════
# 3. _text_heuristic_fallback (4 层回退 - 文本)
# ═══════════════════════════════════════════════════════════════════════


class TestTextHeuristicFallback:
    """测试文本启发式回退 (_text_heuristic_fallback).

    依赖 self.text_analyzer.analyze(text).heuristic_sentiment_score.
    prediction=1 if score>=0.5 else 0.
    """

    @pytest.fixture
    def engine(self) -> ModelEngine:
        return ModelEngine()

    def test_negative_text(self, engine: ModelEngine) -> None:
        """负面文本 (heuristic_score>=0.5) 应返回 prediction=1."""
        with patch.object(
            engine.text_analyzer,
            "analyze",
            return_value={
                "heuristic_sentiment_score": 0.8,
            },
        ):
            result = engine._text_heuristic_fallback("我感觉很绝望, 不想活了")
        assert result["prediction"] == 1
        assert result["sentiment_label"] == "negative"
        assert result["sentiment_score"] == 0.8
        assert result["model_used"] == "text_heuristic_fallback"

    def test_positive_text(self, engine: ModelEngine) -> None:
        """正面文本 (heuristic_score<0.5) 应返回 prediction=0."""
        with patch.object(
            engine.text_analyzer,
            "analyze",
            return_value={
                "heuristic_sentiment_score": 0.2,
            },
        ):
            result = engine._text_heuristic_fallback("今天心情不错")
        assert result["prediction"] == 0
        assert result["sentiment_label"] == "positive"
        assert result["sentiment_score"] == 0.2

    def test_threshold_at_05(self, engine: ModelEngine) -> None:
        """heuristic_score=0.5 时 prediction=1 (>=0.5)."""
        with patch.object(
            engine.text_analyzer,
            "analyze",
            return_value={
                "heuristic_sentiment_score": 0.5,
            },
        ):
            result = engine._text_heuristic_fallback("阈值测试")
        assert result["prediction"] == 1

    def test_increments_fallback_counter(self, engine: ModelEngine) -> None:
        """应递增 _fallback_count."""
        initial = engine._fallback_count
        with patch.object(
            engine.text_analyzer,
            "analyze",
            return_value={
                "heuristic_sentiment_score": 0.6,
            },
        ):
            engine._text_heuristic_fallback("测试")
        assert engine._fallback_count == initial + 1

    def test_missing_heuristic_score_defaults_zero(self, engine: ModelEngine) -> None:
        """analyze 返回缺少 heuristic_sentiment_score 时应默认 0.0."""
        with patch.object(engine.text_analyzer, "analyze", return_value={}):
            result = engine._text_heuristic_fallback("测试")
        assert result["sentiment_score"] == 0.0
        assert result["prediction"] == 0


# ═══════════════════════════════════════════════════════════════════════
# 4. _physiological_heuristic_fallback (4 层回退 - 生理)
# ═══════════════════════════════════════════════════════════════════════


class TestPhysiologicalHeuristicFallback:
    """测试生理启发式回退 (_physiological_heuristic_fallback).

    5 维加权: sleep*0.25 + hr*0.20 + bp*0.20 + exercise*0.20 + steps*0.15.
    """

    @pytest.fixture
    def engine(self) -> ModelEngine:
        return ModelEngine()

    def test_healthy_data_low_score(self, engine: ModelEngine) -> None:
        """健康数据应返回低分 (<20)."""
        data = {
            "sleep_hours": 7.5,
            "sleep_quality": 9,
            "exercise_minutes": 45,
            "heart_rate": 70,
            "systolic_bp": 115,
            "diastolic_bp": 75,
            "steps": 8000,
        }
        score = engine._physiological_heuristic_fallback(data)
        assert 0 <= score < 20, f"健康数据分数 {score} 应 <20"

    def test_poor_sleep_raises_score(self, engine: ModelEngine) -> None:
        """睡眠不足应显著提升分数."""
        healthy = {
            "sleep_hours": 7.5,
            "sleep_quality": 9,
            "exercise_minutes": 45,
            "heart_rate": 70,
            "systolic_bp": 115,
            "diastolic_bp": 75,
            "steps": 8000,
        }
        poor_sleep = dict(healthy)
        poor_sleep["sleep_hours"] = 3
        poor_sleep["sleep_quality"] = 2

        healthy_score = engine._physiological_heuristic_fallback(healthy)
        poor_score = engine._physiological_heuristic_fallback(poor_sleep)
        assert poor_score > healthy_score * 2

    def test_high_heart_rate_raises_score(self, engine: ModelEngine) -> None:
        """心率过高应提升分数."""
        base = {
            "sleep_hours": 7.5,
            "sleep_quality": 9,
            "exercise_minutes": 45,
            "heart_rate": 70,
            "systolic_bp": 115,
            "diastolic_bp": 75,
            "steps": 8000,
        }
        high_hr = dict(base)
        high_hr["heart_rate"] = 110

        base_score = engine._physiological_heuristic_fallback(base)
        high_hr_score = engine._physiological_heuristic_fallback(high_hr)
        assert high_hr_score > base_score

    def test_high_bp_raises_score(self, engine: ModelEngine) -> None:
        """高血压 (≥140/90) 应提升分数."""
        base = {
            "sleep_hours": 7.5,
            "sleep_quality": 9,
            "exercise_minutes": 45,
            "heart_rate": 70,
            "systolic_bp": 115,
            "diastolic_bp": 75,
            "steps": 8000,
        }
        high_bp = dict(base)
        high_bp["systolic_bp"] = 150
        high_bp["diastolic_bp"] = 95

        base_score = engine._physiological_heuristic_fallback(base)
        high_bp_score = engine._physiological_heuristic_fallback(high_bp)
        assert high_bp_score > base_score

    def test_no_exercise_raises_score(self, engine: ModelEngine) -> None:
        """无运动应提升分数."""
        base = {
            "sleep_hours": 7.5,
            "sleep_quality": 9,
            "exercise_minutes": 45,
            "heart_rate": 70,
            "systolic_bp": 115,
            "diastolic_bp": 75,
            "steps": 8000,
        }
        no_exercise = dict(base)
        no_exercise["exercise_minutes"] = 0

        base_score = engine._physiological_heuristic_fallback(base)
        no_ex_score = engine._physiological_heuristic_fallback(no_exercise)
        assert no_ex_score > base_score

    def test_low_steps_raises_score(self, engine: ModelEngine) -> None:
        """低步数应提升分数."""
        base = {
            "sleep_hours": 7.5,
            "sleep_quality": 9,
            "exercise_minutes": 45,
            "heart_rate": 70,
            "systolic_bp": 115,
            "diastolic_bp": 75,
            "steps": 8000,
        }
        low_steps = dict(base)
        low_steps["steps"] = 1000

        base_score = engine._physiological_heuristic_fallback(base)
        low_steps_score = engine._physiological_heuristic_fallback(low_steps)
        assert low_steps_score > base_score

    def test_empty_input_uses_defaults(self, engine: ModelEngine) -> None:
        """空输入应使用默认值, 返回合法分数."""
        score = engine._physiological_heuristic_fallback({})
        assert 0 <= score <= 100

    def test_reason_param_logged_not_affecting_score(self, engine: ModelEngine) -> None:
        """reason 参数仅用于日志, 不影响分数计算."""
        data = {
            "sleep_hours": 5,
            "sleep_quality": 4,
            "exercise_minutes": 10,
            "heart_rate": 85,
            "systolic_bp": 130,
            "diastolic_bp": 85,
            "steps": 3000,
        }
        score_no_reason = engine._physiological_heuristic_fallback(data)
        score_with_reason = engine._physiological_heuristic_fallback(
            data, reason="model_not_found"
        )
        assert score_no_reason == score_with_reason

    def test_score_clamped_to_100(self, engine: ModelEngine) -> None:
        """极端数据应被裁剪到 100."""
        data = {
            "sleep_hours": 0,
            "sleep_quality": 0,
            "exercise_minutes": 0,
            "heart_rate": 200,
            "systolic_bp": 250,
            "diastolic_bp": 150,
            "steps": 0,
        }
        score = engine._physiological_heuristic_fallback(data)
        assert score <= 100


# ═══════════════════════════════════════════════════════════════════════
# 5. _route_structured (4 层路由)
# ═══════════════════════════════════════════════════════════════════════


class TestRouteStructured:
    """测试 4 层路由 (_route_structured).

    路由优先级:
    1. f_coverage >= 0.80 -> structured (返回 None)
    2. gad7 + transcript (len>=20) -> lite
    3. gad7 only -> anxiety_only
    4. 否则 -> insufficient
    """

    @pytest.fixture
    def engine(self) -> ModelEngine:
        return ModelEngine()

    @pytest.fixture
    def full_features(self) -> dict:
        """14 个结构化特征 (f_coverage=1.0)."""
        return {
            "age": 22,
            "gender": 1,
            "study_year": 3,
            "cgpa": 3.5,
            "stress_level": 3,
            "sleep_duration": 7,
            "social_support": 4,
            "financial_pressure": 2,
            "family_history": 0,
            "academic_pressure": 3,
            "exercise_frequency": 2,
            "anxiety": 2,
            "panic_attack": 0,
            "treatment_seeking": 1,
        }

    def test_full_coverage_routes_to_structured(
        self, engine: ModelEngine, full_features
    ) -> None:
        """f_coverage=1.0 -> structured, 返回 (routing_info, None)."""
        info, routed = engine._route_structured(full_features)
        assert routed is None
        assert info["selected_model_family"] == "structured"
        assert info["selected_model_id"] == "structured_logistic_regression_v1.20"
        assert info["routing_reason"] == "feature_coverage_sufficient"
        assert info["prediction_confidence_band"] == "high"
        assert info["feature_coverage_ratio"] == 1.0

    def test_80_percent_coverage_routes_to_structured(
        self, engine: ModelEngine, full_features
    ) -> None:
        """f_coverage=0.80 (阈值) -> structured."""
        # 移除 2 个特征 (12/14 = 0.857 >= 0.80)
        del full_features["panic_attack"]
        del full_features["treatment_seeking"]
        info, routed = engine._route_structured(full_features)
        assert routed is None
        assert info["routing_reason"] == "feature_coverage_sufficient"
        assert info["prediction_confidence_band"] == "medium"  # 0.80<=coverage<0.90

    def test_insufficient_coverage_with_gad7_and_text_routes_to_lite(
        self, engine: ModelEngine, full_features
    ) -> None:
        """f_coverage<0.80 + gad7 + transcript(>=20) -> lite."""
        # 仅保留少量特征使 f_coverage<0.80, transcript 长度需 >=20 字符
        raw = {
            "age": 22,
            "gender": 1,
            "gad7_score": 10,
            "audio_transcript": "最近感觉心情很低落, 什么都不想做, 感觉生活没有意义",
        }
        info, routed = engine._route_structured(raw)
        assert routed == "lite"
        assert info["selected_model_family"] == "lite"
        assert info["routing_reason"] == "feature_coverage_insufficient_text_available"
        assert info["prediction_confidence_band"] == "medium"

    def test_short_transcript_not_routed_to_lite(self, engine: ModelEngine) -> None:
        """transcript 长度 <20 时不能路由到 lite, 应走 anxiety_only 或 insufficient."""
        raw = {"age": 22, "gad7_score": 10, "audio_transcript": "短文本"}
        info, routed = engine._route_structured(raw)
        # gad7 存在但 transcript 太短 -> anxiety_only
        assert routed == "anxiety_only"

    def test_gad7_only_routes_to_anxiety_only(self, engine: ModelEngine) -> None:
        """f_coverage<0.80 + gad7 (无有效 transcript) -> anxiety_only."""
        raw = {"age": 22, "gad7_score": 10}
        info, routed = engine._route_structured(raw)
        assert routed == "anxiety_only"
        assert info["selected_model_family"] == "anxiety_only"
        assert info["routing_reason"] == "only_gad7_available"
        assert info["prediction_confidence_band"] == "low"

    def test_no_gad7_no_text_routes_to_insufficient(self, engine: ModelEngine) -> None:
        """f_coverage<0.80 + 无 gad7 -> insufficient."""
        raw = {"age": 22, "gender": 1}  # 仅 2 个特征
        info, routed = engine._route_structured(raw)
        assert routed == "insufficient"
        assert info["selected_model_family"] == "insufficient"
        assert info["routing_reason"] == "insufficient_information"
        assert info["prediction_confidence_band"] == "low"

    def test_empty_input_routes_to_insufficient(self, engine: ModelEngine) -> None:
        """空输入 -> insufficient."""
        info, routed = engine._route_structured({})
        assert routed == "insufficient"
        assert info["feature_coverage_ratio"] == 0.0

    def test_none_values_excluded_from_coverage(
        self, engine: ModelEngine, full_features
    ) -> None:
        """None 值不应计入覆盖率."""
        full_features["age"] = None  # 13/14
        info, routed = engine._route_structured(full_features)
        assert routed is None  # 13/14=0.929 >= 0.80
        assert info["feature_coverage_ratio"] == round(13 / 14, 4)

    def test_empty_string_values_excluded_from_coverage(
        self, engine: ModelEngine, full_features
    ) -> None:
        """空字符串值不应计入覆盖率."""
        full_features["age"] = ""
        info, routed = engine._route_structured(full_features)
        assert info["feature_coverage_ratio"] == round(13 / 14, 4)

    def test_increments_routing_stats(self, engine: ModelEngine, full_features) -> None:
        """应递增对应的路由统计计数器."""
        initial_structured = engine._routing_stats["structured"]
        engine._route_structured(full_features)
        assert engine._routing_stats["structured"] == initial_structured + 1

    def test_text_field_alias_for_transcript(self, engine: ModelEngine) -> None:
        """audio_transcript 或 text 字段都可作为 transcript."""
        raw_text_field = {
            "age": 22,
            "gad7_score": 10,
            "text": "最近感觉心情很低落, 什么都不想做, 感觉生活没有意义",
        }
        info, routed = engine._route_structured(raw_text_field)
        assert routed == "lite"


# ═══════════════════════════════════════════════════════════════════════
# 6. LiteFeatureExtractor.extract
# ═══════════════════════════════════════════════════════════════════════


class TestLiteFeatureExtractor:
    """测试 LiteFeatureExtractor.extract.

    7 类关键词扫描, self_harm_crisis 计数 ×2.
    """

    def test_empty_text(self) -> None:
        """空文本应返回全零计数."""
        result = LiteFeatureExtractor.extract("")
        assert result["total_keywords"] == 0
        assert result["unique_categories"] == 0
        assert all(c == 0 for c in result["keyword_counts"].values())

    def test_single_category_match(self) -> None:
        """单类关键词匹配."""
        result = LiteFeatureExtractor.extract("我最近失眠了, 总是睡不着")
        assert result["keyword_counts"]["sleep_problem"] >= 2
        assert result["total_keywords"] >= 2
        assert result["unique_categories"] >= 1

    def test_self_harm_crisis_doubled(self) -> None:
        """self_harm_crisis 类关键词计数应 ×2."""
        text = "我想自杀"
        result = LiteFeatureExtractor.extract(text)
        # "自杀" 在 self_harm_crisis 类中出现 1 次, 计数 ×2 = 2
        assert result["keyword_counts"]["self_harm_crisis"] == 2
        # total_keywords 包含 ×2 后的值
        assert result["total_keywords"] == 2

    def test_multiple_self_harm_keywords(self) -> None:
        """多个 self_harm_crisis 关键词都应 ×2."""
        text = "我想自杀也想自残"
        result = LiteFeatureExtractor.extract(text)
        # "自杀" + "自残" = 2 次, ×2 = 4
        assert result["keyword_counts"]["self_harm_crisis"] == 4

    def test_multiple_categories(self) -> None:
        """多类关键词匹配应增加 unique_categories."""
        text = "我最近失眠, 感觉很难过, 也不想见人"
        result = LiteFeatureExtractor.extract(text)
        # 至少匹配 sleep_problem + low_mood + social_withdrawal
        assert result["unique_categories"] >= 3

    def test_crisis_keywords_not_in_counts(self) -> None:
        """CRISIS_KEYWORDS 列表仅用于危机检测, 不计入 KEYWORD_CATEGORIES."""
        # "一死了之" 在 CRISIS_KEYWORDS 但不在 KEYWORD_CATEGORIES
        assert "一死了之" not in [
            kw for kws in LiteFeatureExtractor.KEYWORD_CATEGORIES.values() for kw in kws
        ]

    def test_all_seven_categories_present(self) -> None:
        """应包含 7 个关键词类别."""
        assert len(LiteFeatureExtractor.KEYWORD_CATEGORIES) == 7
        expected = {
            "academic_pressure",
            "sleep_problem",
            "social_withdrawal",
            "self_harm_crisis",
            "exercise_deficit",
            "low_mood",
            "anxiety_somatic",
        }
        assert set(LiteFeatureExtractor.KEYWORD_CATEGORIES.keys()) == expected

    def test_repeated_keyword_counted_multiple_times(self) -> None:
        """重复出现的关键词应被多次计数."""
        text = "失眠失眠失眠"
        result = LiteFeatureExtractor.extract(text)
        assert result["keyword_counts"]["sleep_problem"] == 3

    def test_chinese_text_extraction(self) -> None:
        """中文文本提取应正常工作."""
        text = "考试挂科了, 论文也写不完, 导师催得很紧"
        result = LiteFeatureExtractor.extract(text)
        assert result["keyword_counts"]["academic_pressure"] >= 3

    def test_returns_correct_structure(self) -> None:
        """返回结构应包含三个必需字段."""
        result = LiteFeatureExtractor.extract("测试文本")
        assert "keyword_counts" in result
        assert "total_keywords" in result
        assert "unique_categories" in result
        assert isinstance(result["keyword_counts"], dict)
        assert isinstance(result["total_keywords"], int)
        assert isinstance(result["unique_categories"], int)


# ═══════════════════════════════════════════════════════════════════════
# 7. _build_structured_input (特征预处理)
# ═══════════════════════════════════════════════════════════════════════


class TestBuildStructuredInput:
    """测试特征预处理 (_build_structured_input).

    将 API 入参 (snake_case) 映射为模型特征名 (PascalCase + 派生特征).
    """

    @pytest.fixture
    def engine(self) -> ModelEngine:
        return ModelEngine()

    @pytest.fixture
    def mock_model(self) -> MagicMock:
        """构造模拟 Pipeline, numeric_pipe_cols 含一个 dummy 列避免回退到全部特征.

        源码逻辑: 当 numeric_pipe_cols 为空且 model_feature_names 非空时,
        会回退到 set(model_feature_names), 导致所有字符串特征被 _STR_TO_NUM 转换为数字.
        通过提供非空 numeric_pipe_cols (不含目标字符串特征) 避免此回退,
        从而正确测试派生映射逻辑.
        """
        model = MagicMock()
        model.named_steps = {"preprocessor": MagicMock()}
        preprocessor = model.named_steps["preprocessor"]
        # 仅含 dummy numeric 列, 不含目标字符串特征
        preprocessor.transformers_ = [
            ("num", MagicMock(named_steps={}), ["dummy_numeric_col"])
        ]
        return model

    def test_returns_dict_for_each_feature_name(
        self, engine: ModelEngine, mock_model
    ) -> None:
        """应为 model_feature_names 中每个特征返回一个值."""
        feature_names = ["Age", "Gender", "CGPA", "Sleep Duration"]
        raw = {"age": 22, "gender": 1, "cgpa": 3.5, "sleep_duration": 7}
        result = engine._build_structured_input(raw, feature_names, mock_model)
        assert set(result.keys()) == set(feature_names)
        for v in result.values():
            assert v is not None

    def test_gender_mapping(self, engine: ModelEngine, mock_model) -> None:
        """gender=1 -> Male, gender=0 -> Female."""
        feature_names = ["Gender"]
        result_male = engine._build_structured_input(
            {"gender": 1}, feature_names, mock_model
        )
        result_female = engine._build_structured_input(
            {"gender": 0}, feature_names, mock_model
        )
        assert result_male["Gender"] == "Male"
        assert result_female["Gender"] == "Female"

    def test_sleep_duration_categorical_mapping(
        self, engine: ModelEngine, mock_model
    ) -> None:
        """sleep_duration 数值应映射为 4 档分类字符串."""
        feature_names = ["Sleep Duration"]
        # <5 -> Less than 5 hours
        assert (
            engine._build_structured_input(
                {"sleep_duration": 4}, feature_names, mock_model
            )["Sleep Duration"]
            == "Less than 5 hours"
        )
        # 5-7 -> 5-6 hours
        assert (
            engine._build_structured_input(
                {"sleep_duration": 6}, feature_names, mock_model
            )["Sleep Duration"]
            == "5-6 hours"
        )
        # 7-8 -> 7-8 hours
        assert (
            engine._build_structured_input(
                {"sleep_duration": 7.5}, feature_names, mock_model
            )["Sleep Duration"]
            == "7-8 hours"
        )
        # >8 -> More than 8 hours
        assert (
            engine._build_structured_input(
                {"sleep_duration": 10}, feature_names, mock_model
            )["Sleep Duration"]
            == "More than 8 hours"
        )

    def test_age_group_mapping(self, engine: ModelEngine, mock_model) -> None:
        """age 应映射为 6 档 AgeGroup."""
        feature_names = ["AgeGroup"]
        assert (
            engine._build_structured_input({"age": 17}, feature_names, mock_model)[
                "AgeGroup"
            ]
            == "<=18"
        )
        assert (
            engine._build_structured_input({"age": 22}, feature_names, mock_model)[
                "AgeGroup"
            ]
            == "19-25"
        )
        assert (
            engine._build_structured_input({"age": 30}, feature_names, mock_model)[
                "AgeGroup"
            ]
            == "26-35"
        )
        assert (
            engine._build_structured_input({"age": 40}, feature_names, mock_model)[
                "AgeGroup"
            ]
            == "36-45"
        )
        assert (
            engine._build_structured_input({"age": 55}, feature_names, mock_model)[
                "AgeGroup"
            ]
            == "46-60"
        )
        assert (
            engine._build_structured_input({"age": 65}, feature_names, mock_model)[
                "AgeGroup"
            ]
            == "60+"
        )

    def test_cgpa_normalization_to_10_scale(
        self, engine: ModelEngine, mock_model
    ) -> None:
        """CGPA 应归一化到 10 分制 (cgpa/gpa_scale*10)."""
        feature_names = ["CGPA"]
        # cgpa=3.5 (4分制) -> 3.5/4*10 = 8.75
        result = engine._build_structured_input(
            {"cgpa": 3.5}, feature_names, mock_model
        )
        assert abs(result["CGPA"] - 8.75) < 0.01

    def test_cgpa_already_10_scale(self, engine: ModelEngine, mock_model) -> None:
        """cgpa>4 视为 10 分制, gpa_scale 默认 10."""
        feature_names = ["CGPA"]
        result = engine._build_structured_input(
            {"cgpa": 8.5}, feature_names, mock_model
        )
        # 8.5/10*10 = 8.5
        assert abs(result["CGPA"] - 8.5) < 0.01

    def test_family_history_mapping(self, engine: ModelEngine, mock_model) -> None:
        """family_history=1 -> Yes, 0 -> No."""
        feature_names = ["Family History of Mental Illness"]
        assert (
            engine._build_structured_input(
                {"family_history": 1}, feature_names, mock_model
            )["Family History of Mental Illness"]
            == "Yes"
        )
        assert (
            engine._build_structured_input(
                {"family_history": 0}, feature_names, mock_model
            )["Family History of Mental Illness"]
            == "No"
        )

    def test_suicidal_thoughts_mapping(self, engine: ModelEngine, mock_model) -> None:
        """suicidal_thoughts=1 -> Yes, 0 -> No."""
        feature_names = ["Have you ever had suicidal thoughts ?"]
        assert (
            engine._build_structured_input(
                {"suicidal_thoughts": 1}, feature_names, mock_model
            )["Have you ever had suicidal thoughts ?"]
            == "Yes"
        )
        assert (
            engine._build_structured_input(
                {"suicidal_thoughts": 0}, feature_names, mock_model
            )["Have you ever had suicidal thoughts ?"]
            == "No"
        )

    def test_missing_values_use_defaults(self, engine: ModelEngine, mock_model) -> None:
        """缺失的特征值应使用 _DEFAULTS, 派生值覆盖默认值."""
        feature_names = ["Age", "Gender", "CGPA"]
        result = engine._build_structured_input({}, feature_names, mock_model)
        # _DEFAULTS["Age"]=20, _DEFAULTS["Gender"]="Male"
        # 但 derived_map 在 _DEFAULTS 之后应用, 会覆盖:
        # Age: derived_map["Age"] = age (默认 20.0)
        # Gender: derived_map["Gender"] = "Male" (gender 默认 1)
        # CGPA: derived_map["CGPA"] = max(0, min(10, cgpa_src/gpa_scale*10))
        #   cgpa_src = _get_num("cgpa", 3.0) = 3.0 (默认)
        #   gpa_scale_default = 4.0 (3.0 <= 4)
        #   gpa_scale = _get_num("gpa_scale", 4.0) = 4.0
        #   cgpa = 3.0 / 4.0 * 10 = 7.5
        assert result["Age"] == 20
        assert result["Gender"] == "Male"
        assert result["CGPA"] == 7.5

    def test_raw_values_then_derived_overrides(
        self, engine: ModelEngine, mock_model
    ) -> None:
        """源码设计: derived_map 在 raw 之后应用, 会覆盖 raw 中的同名值.

        源码 L785-790:
            for col, val in raw.items(): if col in model_feature_names: input_dict[col] = val
            for col, val in derived_map.items(): if col in model_feature_names: input_dict[col] = val
        因此当 raw 和 derived_map 同时提供同名特征时, derived_map 胜出.
        """
        feature_names = ["Age", "Gender"]
        raw = {"age": 22, "gender": 1, "Age": 30, "Gender": "Female"}
        result = engine._build_structured_input(raw, feature_names, mock_model)
        # Age: raw=30 被 derived_map["Age"]=22.0 (从 age=22 派生) 覆盖
        assert result["Age"] == 22.0
        # Gender: raw="Female" 被 derived_map["Gender"]="Male" (从 gender=1 派生) 覆盖
        assert result["Gender"] == "Male"

    def test_sleep_duration_ordinal_derived(
        self, engine: ModelEngine, mock_model
    ) -> None:
        """SleepDurationOrdinal 应根据 sleep_duration 数值派生 (0-3)."""
        feature_names = ["SleepDurationOrdinal"]
        assert (
            engine._build_structured_input(
                {"sleep_duration": 4}, feature_names, mock_model
            )["SleepDurationOrdinal"]
            == 0
        )
        assert (
            engine._build_structured_input(
                {"sleep_duration": 6}, feature_names, mock_model
            )["SleepDurationOrdinal"]
            == 1
        )
        assert (
            engine._build_structured_input(
                {"sleep_duration": 7.5}, feature_names, mock_model
            )["SleepDurationOrdinal"]
            == 2
        )
        assert (
            engine._build_structured_input(
                {"sleep_duration": 10}, feature_names, mock_model
            )["SleepDurationOrdinal"]
            == 3
        )

    def test_string_features_get_str_to_num_mapping(self, engine: ModelEngine) -> None:
        """numeric_pipe_cols 中的字符串特征应通过 _STR_TO_NUM 转换为数字."""
        # 构造 mock_model, numeric_pipe_cols 包含 "Gender" (字符串特征在 num 列中)
        mock_model = MagicMock()
        mock_model.named_steps = {"preprocessor": MagicMock()}
        preprocessor = mock_model.named_steps["preprocessor"]
        preprocessor.transformers_ = [
            ("num", MagicMock(named_steps={}), ["Gender"]),
        ]
        feature_names = ["Gender"]
        raw = {"gender": 1}  # -> "Male" -> _STR_TO_NUM["Gender"]["Male"] = 1
        result = engine._build_structured_input(raw, feature_names, mock_model)
        assert result["Gender"] == 1


# ═══════════════════════════════════════════════════════════════════════
# 8. score_to_level / _score_to_level (风险映射)
# ═══════════════════════════════════════════════════════════════════════


class TestScoreToLevel:
    """测试 score_to_level / _score_to_level.

    默认阈值: mild=20, moderate=40, high=60, critical=80.
    structured 阈值: mild=25, moderate=45, high=65, critical=85.
    physiological 阈值: mild=35, moderate=55, high=75, critical=90.
    """

    def test_default_thresholds(self) -> None:
        """无 modality 参数时使用默认阈值."""
        assert ModelEngine._score_to_level(0) == 0
        assert ModelEngine._score_to_level(19) == 0
        assert ModelEngine._score_to_level(20) == 1  # mild
        assert ModelEngine._score_to_level(39) == 1
        assert ModelEngine._score_to_level(40) == 2  # moderate
        assert ModelEngine._score_to_level(59) == 2
        assert ModelEngine._score_to_level(60) == 3  # high
        assert ModelEngine._score_to_level(79) == 3
        assert ModelEngine._score_to_level(80) == 4  # critical
        assert ModelEngine._score_to_level(100) == 4

    def test_structured_thresholds(self) -> None:
        """structured 模态使用专用阈值."""
        assert ModelEngine._score_to_level(24, modality="structured") == 0
        assert ModelEngine._score_to_level(25, modality="structured") == 1  # mild=25
        assert ModelEngine._score_to_level(44, modality="structured") == 1
        assert (
            ModelEngine._score_to_level(45, modality="structured") == 2
        )  # moderate=45
        assert ModelEngine._score_to_level(64, modality="structured") == 2
        assert ModelEngine._score_to_level(65, modality="structured") == 3  # high=65
        assert ModelEngine._score_to_level(84, modality="structured") == 3
        assert (
            ModelEngine._score_to_level(85, modality="structured") == 4
        )  # critical=85

    def test_physiological_thresholds(self) -> None:
        """physiological 模态使用专用阈值 (更高)."""
        assert ModelEngine._score_to_level(34, modality="physiological") == 0
        assert ModelEngine._score_to_level(35, modality="physiological") == 1  # mild=35
        assert ModelEngine._score_to_level(54, modality="physiological") == 1
        assert (
            ModelEngine._score_to_level(55, modality="physiological") == 2
        )  # moderate=55
        assert ModelEngine._score_to_level(74, modality="physiological") == 2
        assert ModelEngine._score_to_level(75, modality="physiological") == 3  # high=75
        assert ModelEngine._score_to_level(89, modality="physiological") == 3
        assert (
            ModelEngine._score_to_level(90, modality="physiological") == 4
        )  # critical=90

    def test_unknown_modality_falls_back_to_default(self) -> None:
        """未知 modality 应回退到默认阈值."""
        assert ModelEngine._score_to_level(20, modality="unknown") == 1
        assert ModelEngine._score_to_level(80, modality="unknown") == 4

    def test_public_alias_matches_private(self) -> None:
        """公开接口 score_to_level 应与 _score_to_level 一致."""
        for score in (0, 20, 40, 60, 80, 100):
            assert ModelEngine.score_to_level(score) == ModelEngine._score_to_level(
                score
            )

    def test_boundary_exactly_at_threshold(self) -> None:
        """分数恰好等于阈值时应归入更高等级 (>=)."""
        assert ModelEngine._score_to_level(20) == 1  # == mild
        assert ModelEngine._score_to_level(40) == 2  # == moderate
        assert ModelEngine._score_to_level(60) == 3  # == high
        assert ModelEngine._score_to_level(80) == 4  # == critical

    def test_negative_score_returns_zero(self) -> None:
        """负分应返回 0."""
        assert ModelEngine._score_to_level(-10) == 0
        assert ModelEngine._score_to_level(-100) == 0

    def test_score_over_100_returns_critical(self) -> None:
        """超过 100 的分数应归入 critical."""
        assert ModelEngine._score_to_level(150) == 4


# ═══════════════════════════════════════════════════════════════════════
# 9. _build_intervention_plan (干预计划)
# ═══════════════════════════════════════════════════════════════════════


class TestBuildInterventionPlan:
    """测试干预计划生成 (_build_intervention_plan).

    5 档干预: none / low / medium / high / critical.
    """

    def test_level_0_none(self) -> None:
        """level=0 -> none, 2 个基础动作."""
        level, actions = ModelEngine._build_intervention_plan(0, 10, {})
        assert level == "none"
        assert len(actions) == 2
        assert "保持日常心理健康维护" in actions

    def test_level_1_low(self) -> None:
        """level=1 -> low, 3 个动作."""
        level, actions = ModelEngine._build_intervention_plan(1, 25, {})
        assert level == "low"
        assert len(actions) == 3
        assert "推送轻度风险提醒" in actions

    def test_level_2_medium(self) -> None:
        """level=2 -> medium, 3 个基础动作."""
        level, actions = ModelEngine._build_intervention_plan(2, 50, {})
        assert level == "medium"
        assert len(actions) == 3
        assert "触发咨询师关注" in actions

    def test_level_2_medium_with_physiological_dominant(self) -> None:
        """level=2 + physiological 主导 -> medium + 4 个动作 (含生理建议)."""
        modality_scores = {"physiological": {"score": 60.0, "model": "physio"}}
        level, actions = ModelEngine._build_intervention_plan(2, 50, modality_scores)
        assert level == "medium"
        assert len(actions) == 4
        assert "建议关注生理指标变化并规律作息" in actions

    def test_level_3_high(self) -> None:
        """level=3 -> high, 3 个基础动作."""
        level, actions = ModelEngine._build_intervention_plan(3, 70, {})
        assert level == "high"
        assert len(actions) == 3
        assert "发送高风险预警" in actions

    def test_level_3_high_with_physiological_dominant(self) -> None:
        """level=3 + physiological 主导 -> high + 4 个动作 (插入生理复查)."""
        modality_scores = {"physiological": {"score": 75.0, "model": "physio"}}
        level, actions = ModelEngine._build_intervention_plan(3, 75, modality_scores)
        assert level == "high"
        assert len(actions) == 4
        assert "建议进行生理指标专项复查" in actions
        # 应插入到位置 1
        assert actions[1] == "建议进行生理指标专项复查"

    def test_level_3_high_with_text_dominant(self) -> None:
        """level=3 + text 主导 -> high + 4 个动作 (插入情绪支持)."""
        modality_scores = {"text": {"score": 70.0, "model": "text_model"}}
        level, actions = ModelEngine._build_intervention_plan(3, 70, modality_scores)
        assert level == "high"
        assert len(actions) == 4
        assert "建议关注情绪表达并提供心理支持资源" in actions
        assert actions[1] == "建议关注情绪表达并提供心理支持资源"

    def test_level_4_critical(self) -> None:
        """level=4 -> critical, 3 个基础动作."""
        level, actions = ModelEngine._build_intervention_plan(4, 90, {})
        assert level == "critical"
        assert len(actions) == 3
        assert "立即触发紧急预警" in actions

    def test_level_4_critical_with_physiological_dominant(self) -> None:
        """level=4 + physiological 主导 -> critical + 4 个动作 (插入紧急排查)."""
        modality_scores = {"physiological": {"score": 95.0, "model": "physio"}}
        level, actions = ModelEngine._build_intervention_plan(4, 95, modality_scores)
        assert level == "critical"
        assert len(actions) == 4
        assert "紧急排查生理异常并建议就医检查" in actions
        assert actions[1] == "紧急排查生理异常并建议就医检查"

    def test_dominant_modality_selection(self) -> None:
        """应选择分数最高的模态作为主导."""
        modality_scores = {
            "structured": {"score": 30.0, "model": "s"},
            "text": {"score": 70.0, "model": "t"},
            "physiological": {"score": 50.0, "model": "p"},
        }
        # text 分数最高, level=3 应插入情绪支持
        level, actions = ModelEngine._build_intervention_plan(3, 70, modality_scores)
        assert "建议关注情绪表达并提供心理支持资源" in actions


# ═══════════════════════════════════════════════════════════════════════
# 10. _level_to_severity (等级转严重度)
# ═══════════════════════════════════════════════════════════════════════


class TestLevelToSeverity:
    """测试 _level_to_severity.

    RISK_LEVEL_LABELS: {0: "none", 1: "mild", 2: "moderate", 3: "high", 4: "critical"}.
    """

    def test_all_known_levels(self) -> None:
        assert ModelEngine._level_to_severity(0) == "none"
        assert ModelEngine._level_to_severity(1) == "mild"
        assert ModelEngine._level_to_severity(2) == "moderate"
        assert ModelEngine._level_to_severity(3) == "high"
        assert ModelEngine._level_to_severity(4) == "critical"

    def test_unknown_level_returns_unknown(self) -> None:
        """未知等级应返回 'unknown'."""
        assert ModelEngine._level_to_severity(5) == "unknown"
        assert ModelEngine._level_to_severity(-1) == "unknown"
        assert ModelEngine._level_to_severity(99) == "unknown"


# ═══════════════════════════════════════════════════════════════════════
# 11. _check_crisis_safety (危机安全检查)
# ═══════════════════════════════════════════════════════════════════════


class TestCheckCrisisSafety:
    """测试危机安全检查 (_check_crisis_safety).

    匹配 settings.crisis_keywords 时返回 crisis_override=True.
    """

    @pytest.fixture
    def engine(self) -> ModelEngine:
        return ModelEngine()

    def test_no_crisis_keywords(self, engine: ModelEngine) -> None:
        """无危机关键词应返回空安全标志."""
        result = engine._check_crisis_safety("今天心情不错, 想出去散步")
        assert result["crisis_override"] is False
        assert result["requires_human_review"] is False
        assert result["crisis_keywords_matched"] == []
        assert result["safety_flags"] == []

    def test_single_crisis_keyword(self, engine: ModelEngine) -> None:
        """单个危机关键词应触发危机覆盖."""
        result = engine._check_crisis_safety("我想自杀")
        assert result["crisis_override"] is True
        assert result["requires_human_review"] is True
        assert "自杀" in result["crisis_keywords_matched"]
        assert "crisis_keyword_detected" in result["safety_flags"]

    def test_multiple_crisis_keywords(self, engine: ModelEngine) -> None:
        """多个危机关键词应全部返回."""
        result = engine._check_crisis_safety("我想自杀也想自残")
        assert result["crisis_override"] is True
        assert len(result["crisis_keywords_matched"]) >= 2
        assert "自杀" in result["crisis_keywords_matched"]
        assert "自残" in result["crisis_keywords_matched"]

    def test_empty_text(self, engine: ModelEngine) -> None:
        """空文本不应触发危机."""
        result = engine._check_crisis_safety("")
        assert result["crisis_override"] is False
        assert result["crisis_keywords_matched"] == []

    def test_increments_crisis_override_counter(self, engine: ModelEngine) -> None:
        """应递增 _crisis_override_count."""
        initial = engine._crisis_override_count
        engine._check_crisis_safety("我想自杀")
        assert engine._crisis_override_count == initial + 1

    def test_no_increment_when_no_crisis(self, engine: ModelEngine) -> None:
        """无危机关键词时不应递增计数器."""
        initial = engine._crisis_override_count
        engine._check_crisis_safety("今天天气真好")
        assert engine._crisis_override_count == initial


# ═══════════════════════════════════════════════════════════════════════
# 12. _attention_gate (注意力门控)
# ═══════════════════════════════════════════════════════════════════════


class TestAttentionGate:
    """测试注意力门控 (_attention_gate).

    Softmax + 温度系数, 最小权重不低于 0.05.
    """

    def test_empty_input(self) -> None:
        assert ModelEngine._attention_gate([]) == []

    def test_single_score(self) -> None:
        """单个分数应返回权重 1.0."""
        weights = ModelEngine._attention_gate([50.0])
        assert len(weights) == 1
        assert abs(weights[0] - 1.0) < 0.01

    def test_multiple_scores_sum_to_one(self) -> None:
        """多分数权重应归一化到 1."""
        weights = ModelEngine._attention_gate([10.0, 20.0, 30.0])
        assert len(weights) == 3
        assert abs(sum(weights) - 1.0) < 0.01

    def test_higher_score_gets_higher_weight(self) -> None:
        """分数越高权重应越大."""
        weights = ModelEngine._attention_gate([10.0, 50.0, 90.0])
        assert weights[0] < weights[1] < weights[2]

    def test_min_weight_floor_applied(self) -> None:
        """源码应用 min_weight=0.05 作为软下限, 归一化后可能略低于 0.05.

        源码 L1933-1937:
            min_weight = 0.05
            weights = [max(w, min_weight) for w in weights]  # 应用下限
            total = sum(weights) or 1.0
            return [float(v / total) for v in weights]  # 归一化可能使权重略低于下限
        因此验证归一化前 min_weight 已被应用: 极端输入下小权重应接近 0.05 (允许 0.04+).
        """
        weights = ModelEngine._attention_gate([0.0, 0.0, 100.0])
        # 归一化后小权重应接近 0.05 (允许 0.04+ 因归一化缩小)
        for w in weights:
            assert (
                w >= 0.04
            ), f"权重 {w} 应 >= 0.04 (min_weight=0.05 软下限, 归一化后可能略低)"
        # 最大权重应远大于小权重
        assert max(weights) > 0.8

    def test_all_weights_positive(self) -> None:
        """所有权重应为正数."""
        weights = ModelEngine._attention_gate([10.0, 20.0, 30.0])
        for w in weights:
            assert w > 0


# ═══════════════════════════════════════════════════════════════════════
# 13. _boost_gate_for_physiology (生理增强门控)
# ═══════════════════════════════════════════════════════════════════════


class TestBoostGateForPhysiology:
    """测试生理增强门控 (_boost_gate_for_physiology).

    最后一个权重 (physiological) 应被增强到 min(0.85, +0.15).
    """

    def test_empty_input(self) -> None:
        assert ModelEngine._boost_gate_for_physiology([], []) == []

    def test_mismatched_lengths(self) -> None:
        """scores 和 gate_weights 长度不一致时返回原 gate_weights."""
        result = ModelEngine._boost_gate_for_physiology([1.0, 2.0], [0.5, 0.3, 0.2])
        assert result == [0.5, 0.3, 0.2]

    def test_three_scores_boost_last(self) -> None:
        """3 个分数时最后一个权重应被增强."""
        gate_weights = [0.4, 0.3, 0.3]
        scores = [10.0, 20.0, 30.0]
        result = ModelEngine._boost_gate_for_physiology(scores, gate_weights)
        assert len(result) == 3
        assert abs(sum(result) - 1.0) < 0.01
        # 最后一个权重应被增强到 min(0.85, 0.3+0.15) = 0.45
        assert result[2] >= 0.45 - 0.01

    def test_sum_normalizes_to_one(self) -> None:
        """增强后权重应归一化到 1."""
        gate_weights = [0.5, 0.3, 0.2]
        scores = [10.0, 20.0, 30.0]
        result = ModelEngine._boost_gate_for_physiology(scores, gate_weights)
        assert abs(sum(result) - 1.0) < 0.01

    def test_boost_capped_at_085(self) -> None:
        """最后一个权重的上限应为 0.85."""
        gate_weights = [0.1, 0.1, 0.8]
        scores = [10.0, 20.0, 30.0]
        result = ModelEngine._boost_gate_for_physiology(scores, gate_weights)
        assert result[2] <= 0.85 + 0.001  # 允许浮点误差

    def test_less_than_three_scores_no_boost(self) -> None:
        """少于 3 个分数时不执行增强逻辑, 仅归一化."""
        gate_weights = [0.6, 0.4]
        scores = [10.0, 20.0]
        result = ModelEngine._boost_gate_for_physiology(scores, gate_weights)
        assert len(result) == 2
        assert abs(sum(result) - 1.0) < 0.01
