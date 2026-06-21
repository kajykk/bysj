"""
Test suite for text model comparison.

Tests:
- TC-TEXT-001: 验证对照指标计算
- TC-TEXT-002: 验证切换决策逻辑
- TC-TEXT-003: 验证阈值检查
- TC-TEXT-004: 验证报告生成
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Add backend to path
backend_root = Path(__file__).resolve().parents[1]
if str(backend_root) not in sys.path:
    sys.path.insert(0, str(backend_root))

from scripts.compare_text_models import make_switch_decision


class TestTextModelComparison:
    """Test suite for text model comparison."""

    def test_switch_decision_meets_thresholds(self) -> None:
        """TC-TEXT-001: 验证切换决策 - 满足阈值."""
        bert_metrics = {
            "f1": 0.98,
            "latency_ms": 5.0,
        }
        baseline_metrics = {
            "f1": 0.96,
            "latency_ms": 2.0,
        }

        decision = make_switch_decision(bert_metrics, baseline_metrics)

        assert decision["decision"] == "SWITCH"
        assert decision["f1_meets_threshold"] is True
        assert decision["latency_meets_threshold"] is True

    def test_switch_decision_improves_but_not_meets(self) -> None:
        """TC-TEXT-002: 验证切换决策 - 改善但未满足."""
        bert_metrics = {
            "f1": 0.965,
            "latency_ms": 5.0,
        }
        baseline_metrics = {
            "f1": 0.96,
            "latency_ms": 2.0,
        }

        decision = make_switch_decision(bert_metrics, baseline_metrics)

        # Decision depends on implementation thresholds
        assert decision["decision"] in ("CONSIDER", "KEEP_BASELINE")
        assert "f1_meets_threshold" in decision
        assert "latency_meets_threshold" in decision

    def test_switch_decision_high_latency(self) -> None:
        """TC-TEXT-003: 验证切换决策 - 高延迟."""
        bert_metrics = {
            "f1": 0.99,
            "latency_ms": 50.0,
        }
        baseline_metrics = {
            "f1": 0.90,
            "latency_ms": 2.0,
        }

        decision = make_switch_decision(bert_metrics, baseline_metrics)

        assert decision["decision"] == "CONSIDER_WITH_CAVEATS"
        assert decision["latency_meets_threshold"] is False

    def test_switch_decision_keep_baseline(self) -> None:
        """TC-TEXT-004: 验证切换决策 - 保持基线."""
        bert_metrics = {
            "f1": 0.95,
            "latency_ms": 50.0,
        }
        baseline_metrics = {
            "f1": 0.96,
            "latency_ms": 2.0,
        }

        decision = make_switch_decision(bert_metrics, baseline_metrics)

        assert decision["decision"] == "KEEP_BASELINE"

    def test_f1_improvement_calculation(self) -> None:
        """TC-TEXT-005: 验证 F1 改善计算."""
        bert_metrics = {
            "f1": 0.98,
            "latency_ms": 5.0,
        }
        baseline_metrics = {
            "f1": 0.96,
            "latency_ms": 2.0,
        }

        decision = make_switch_decision(bert_metrics, baseline_metrics)

        assert decision["f1_improvement"] == 0.02

    def test_latency_increase_calculation(self) -> None:
        """TC-TEXT-006: 验证延迟增加计算."""
        bert_metrics = {
            "f1": 0.98,
            "latency_ms": 8.0,
        }
        baseline_metrics = {
            "f1": 0.96,
            "latency_ms": 2.0,
        }

        decision = make_switch_decision(bert_metrics, baseline_metrics)

        assert decision["latency_increase_ms"] == 6.0

    def test_threshold_values(self) -> None:
        """TC-TEXT-007: 验证阈值配置."""
        from scripts.compare_text_models import SWITCH_F1_THRESHOLD, SWITCH_LATENCY_THRESHOLD_MS

        assert SWITCH_F1_THRESHOLD == 0.97
        assert SWITCH_LATENCY_THRESHOLD_MS == 10.0
