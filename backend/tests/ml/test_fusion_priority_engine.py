"""Tests for app/ml/fusion_priority_engine.py.

覆盖模块: app.ml.fusion_priority_engine (当前 6% → 目标 >90%).
关键路径:
- 规则 1: 文本危机表达 -> crisis_override
- 规则 2: 多模型一致高风险 -> 提升等级
- 规则 3: 单模型 high + 其他 low -> review_required
- 规则 4: 模型分歧 (>40 分) -> review_required
- 规则 5: 低置信度 + 高风险 -> review_required
- 边界: 全 None / None result / 0/0.0 falsy 值 (L-24 修复)
"""

from __future__ import annotations

import pytest

from app.ml.fusion_priority_engine import FusionPriorityEngine


class TestFusionPriorityEngineBasic:
    """Test FusionPriorityEngine basic behavior."""

    def test_all_none_results(self):
        """TC-FPE-001: 全部 result 为 None -> 不触发任何规则."""
        engine = FusionPriorityEngine()
        result = engine.apply_priority_rules(
            structured_result=None,
            text_result=None,
            physio_result=None,
            base_fused_score=30.0,
            base_risk_level=1,
        )
        assert result["risk_score"] == 30.0
        assert result["risk_level"] == 1
        assert result["review_required"] is False
        assert result["review_triggers"] == []
        assert result["crisis_override"] is False

    def test_empty_results_dict(self):
        """TC-FPE-002: 空字典 result (无 crisis_detected/risk_level) -> 不触发."""
        engine = FusionPriorityEngine()
        result = engine.apply_priority_rules(
            structured_result={},
            text_result={},
            physio_result={},
            base_fused_score=30.0,
            base_risk_level=1,
        )
        assert result["review_required"] is False


class TestRule1CrisisOverride:
    """Test 规则 1: 文本危机表达优先级最高."""

    def test_crisis_detected_override(self):
        """TC-FPE-003: text_result.crisis_detected=True -> critical."""
        engine = FusionPriorityEngine()
        result = engine.apply_priority_rules(
            structured_result={"risk_level": 0, "risk_score": 10.0},
            text_result={"crisis_detected": True, "risk_level": 1, "risk_score": 30.0},
            physio_result=None,
            base_fused_score=30.0,
            base_risk_level=1,
        )
        assert result["crisis_override"] is True
        assert result["risk_level"] == 4  # critical
        assert result["risk_score"] >= 90.0
        assert "crisis_override" in result["review_triggers"]
        assert result["review_required"] is True

    def test_crisis_score_floor_90(self):
        """TC-FPE-004: crisis 时分数提升到至少 90."""
        engine = FusionPriorityEngine()
        result = engine.apply_priority_rules(
            structured_result=None,
            text_result={"crisis_detected": True},
            physio_result=None,
            base_fused_score=50.0,  # 原 50
            base_risk_level=2,
        )
        assert result["risk_score"] >= 90.0

    def test_crisis_keeps_higher_score(self):
        """TC-FPE-005: crisis 时若 base_fused_score 已 > 90, 保留更高分."""
        engine = FusionPriorityEngine()
        result = engine.apply_priority_rules(
            structured_result=None,
            text_result={"crisis_detected": True},
            physio_result=None,
            base_fused_score=95.0,
            base_risk_level=4,
        )
        assert result["risk_score"] == 95.0


class TestRule2MultiModelHighRisk:
    """Test 规则 2: 多模型一致高风险 (>=2 个 risk_level>=3) -> 提升."""

    def test_two_high_risk_promote(self):
        """TC-FPE-006: 2 个模型 risk_level>=3, base_level<3 -> 提升到 3."""
        engine = FusionPriorityEngine()
        result = engine.apply_priority_rules(
            structured_result={"risk_level": 3, "risk_score": 60.0},
            text_result={"risk_level": 3, "risk_score": 65.0},
            physio_result={"risk_level": 0, "risk_score": 10.0},
            base_fused_score=50.0,
            base_risk_level=2,
        )
        assert result["risk_level"] == 3
        assert result["risk_score"] >= 65.0  # max(50, 65)

    def test_three_high_risk_promote(self):
        """TC-FPE-007: 3 个模型都高风险 -> 提升."""
        engine = FusionPriorityEngine()
        result = engine.apply_priority_rules(
            structured_result={"risk_level": 3, "risk_score": 70.0},
            text_result={"risk_level": 4, "risk_score": 80.0},
            physio_result={"risk_level": 3, "risk_score": 75.0},
            base_fused_score=50.0,
            base_risk_level=1,
        )
        assert result["risk_level"] == 3

    def test_already_high_level_no_promote(self):
        """TC-FPE-008: base_risk_level 已 >=3 时不再提升."""
        engine = FusionPriorityEngine()
        result = engine.apply_priority_rules(
            structured_result={"risk_level": 3, "risk_score": 60.0},
            text_result={"risk_level": 3, "risk_score": 65.0},
            physio_result=None,
            base_fused_score=70.0,
            base_risk_level=4,  # 已 critical, 不降级
        )
        # 仍为 4, 不被规则 2 改写 (规则 2 仅当 base_level < 3 时提升)
        assert result["risk_level"] == 4

    def test_zero_risk_level_not_high(self):
        """TC-FPE-009: risk_level=0 (falsy) 不被误判为高风险 (L-24 修复)."""
        engine = FusionPriorityEngine()
        # 3 个模型 risk_level=0 -> high_risk_count=0 -> 不触发规则 2
        result = engine.apply_priority_rules(
            structured_result={"risk_level": 0, "risk_score": 0.0},
            text_result={"risk_level": 0, "risk_score": 0.0},
            physio_result={"risk_level": 0, "risk_score": 0.0},
            base_fused_score=10.0,
            base_risk_level=1,
        )
        assert result["risk_level"] == 1


class TestRule3SingleModalityHighRisk:
    """Test 规则 3: 单个模型 high, 其他 low -> review."""

    def test_single_high_triggers_review(self):
        """TC-FPE-010: 单个 high_risk -> review_required + trigger."""
        engine = FusionPriorityEngine()
        result = engine.apply_priority_rules(
            structured_result={"risk_level": 3, "risk_score": 60.0},
            text_result={"risk_level": 0, "risk_score": 10.0},
            physio_result={"risk_level": 0, "risk_score": 10.0},
            base_fused_score=30.0,
            base_risk_level=1,
        )
        # 1 个 high -> 触发规则 3
        assert result["review_required"] is True
        assert "single_modality_high_risk" in result["review_triggers"]


class TestRule4ModelDisagreement:
    """Test 规则 4: 模型分歧 (>40 分) -> review."""

    def test_disagreement_triggers_review(self):
        """TC-FPE-011: 模型分数分歧 > 40 -> review."""
        engine = FusionPriorityEngine()
        result = engine.apply_priority_rules(
            structured_result={"risk_level": 1, "risk_score": 80.0},
            text_result={"risk_level": 1, "risk_score": 10.0},  # 分差 70 > 40
            physio_result={"risk_level": 1, "risk_score": 30.0},
            base_fused_score=30.0,
            base_risk_level=1,
        )
        assert result["review_required"] is True
        triggers_str = " ".join(result["review_triggers"])
        assert "model_disagreement" in triggers_str

    def test_no_disagreement_no_trigger(self):
        """TC-FPE-012: 分歧 <= 40 不触发规则 4."""
        engine = FusionPriorityEngine()
        result = engine.apply_priority_rules(
            structured_result={"risk_level": 1, "risk_score": 30.0},
            text_result={"risk_level": 1, "risk_score": 50.0},  # 分差 20 < 40
            physio_result={"risk_level": 1, "risk_score": 40.0},
            base_fused_score=40.0,
            base_risk_level=1,
        )
        # 无规则触发 (1 个 high_risk_count=0, 分差 20)
        triggers_str = " ".join(result["review_triggers"])
        assert "model_disagreement" not in triggers_str

    def test_zero_score_not_replaced(self):
        """TC-FPE-013: risk_score=0.0 不被 None 替换为 0 (L-24 修复)."""
        engine = FusionPriorityEngine()
        # 测试 score=0.0 被正确包含 (而非 None 触发替换)
        result = engine.apply_priority_rules(
            structured_result={"risk_level": 1, "risk_score": 0.0},
            text_result={"risk_level": 1, "risk_score": 50.0},
            physio_result=None,
            base_fused_score=20.0,
            base_risk_level=1,
        )
        # 分差 = 50 - 0 = 50 > 40 -> 触发规则 4
        triggers_str = " ".join(result["review_triggers"])
        assert "model_disagreement" in triggers_str


class TestRule5LowConfidenceHighRisk:
    """Test 规则 5: 低置信度 + 高风险 -> review."""

    def test_low_confidence_high_risk_triggers_review(self):
        """TC-FPE-014: confidence<0.5 + risk_level>=3 -> review."""
        engine = FusionPriorityEngine()
        result = engine.apply_priority_rules(
            structured_result={"risk_level": 3, "risk_score": 60.0, "confidence": 0.3},
            text_result=None,
            physio_result=None,
            base_fused_score=30.0,
            base_risk_level=1,
        )
        # 触发规则 3 (单 high) + 规则 5 (low_confidence)
        assert result["review_required"] is True
        triggers_str = " ".join(result["review_triggers"])
        assert "low_confidence_high_risk_structured" in triggers_str

    def test_high_confidence_no_trigger(self):
        """TC-FPE-015: confidence>=0.5 不触发规则 5."""
        engine = FusionPriorityEngine()
        result = engine.apply_priority_rules(
            structured_result={"risk_level": 3, "risk_score": 60.0, "confidence": 0.8},
            text_result=None,
            physio_result=None,
            base_fused_score=30.0,
            base_risk_level=3,  # base_level=3 避免触发规则 2 提升逻辑
        )
        # 单 high -> 触发规则 3, 但不触发规则 5
        triggers_str = " ".join(result["review_triggers"])
        assert "low_confidence_high_risk_structured" not in triggers_str

    def test_low_confidence_low_risk_no_trigger(self):
        """TC-FPE-016: confidence<0.5 + risk_level<3 不触发规则 5."""
        engine = FusionPriorityEngine()
        result = engine.apply_priority_rules(
            structured_result={"risk_level": 1, "risk_score": 20.0, "confidence": 0.3},
            text_result=None,
            physio_result=None,
            base_fused_score=20.0,
            base_risk_level=1,
        )
        triggers_str = " ".join(result["review_triggers"])
        assert "low_confidence_high_risk" not in triggers_str

    def test_low_confidence_high_risk_each_modality(self):
        """TC-FPE-017: 规则 5 对 structured/text/physiological 各模态独立检查."""
        engine = FusionPriorityEngine()
        result = engine.apply_priority_rules(
            structured_result={"risk_level": 3, "risk_score": 60.0, "confidence": 0.3},
            text_result={"risk_level": 3, "risk_score": 60.0, "confidence": 0.4},
            physio_result={"risk_level": 3, "risk_score": 60.0, "confidence": 0.2},
            base_fused_score=60.0,
            base_risk_level=3,  # 避免规则 2 提升
        )
        triggers_str = " ".join(result["review_triggers"])
        # 3 个模态都应触发规则 5
        assert "low_confidence_high_risk_structured" in triggers_str
        assert "low_confidence_high_risk_text" in triggers_str
        assert "low_confidence_high_risk_physiological" in triggers_str


class TestResultStructure:
    """Test result structure completeness."""

    def test_returns_all_fields(self):
        """TC-FPE-018: 返回字典包含所有字段."""
        engine = FusionPriorityEngine()
        result = engine.apply_priority_rules(
            structured_result=None,
            text_result=None,
            physio_result=None,
            base_fused_score=10.0,
            base_risk_level=0,
        )
        assert "risk_score" in result
        assert "risk_level" in result
        assert "review_required" in result
        assert "review_triggers" in result
        assert "crisis_override" in result

    def test_risk_score_rounded(self):
        """TC-FPE-019: risk_score 保留 2 位小数."""
        engine = FusionPriorityEngine()
        result = engine.apply_priority_rules(
            structured_result=None,
            text_result=None,
            physio_result=None,
            base_fused_score=33.45678,
            base_risk_level=1,
        )
        assert result["risk_score"] == 33.46
