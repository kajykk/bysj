"""
Test suite for expanded fusion test scenarios (v2).

Tests:
- TC-FUSION-001~017: 融合引擎测试场景
- TC-FUSION-018~083: 扩展融合测试场景
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root / "backend"))

from app.core.model_engine import ModelEngine


class TestFusionScenariosV2:
    """Test suite for expanded fusion scenarios."""

    def setup_method(self) -> None:
        """Set up test fixtures."""
        self.engine = ModelEngine()
        project_root = Path(__file__).resolve().parents[2]
        self.scenarios_path = project_root / "datasets" / "fusion" / "fusion_test_scenarios_v2.json"

        with open(self.scenarios_path, "r", encoding="utf-8") as f:
            self.scenarios = json.load(f)

    def test_scenario_count(self) -> None:
        """验证场景数量."""
        assert len(self.scenarios) >= 49, f"Expected at least 49 scenarios, got {len(self.scenarios)}"

    def test_all_scenarios_have_required_fields(self) -> None:
        """验证所有场景包含必要字段."""
        for scenario in self.scenarios:
            assert "scenario" in scenario, "Missing scenario name"
            assert "label" in scenario, "Missing label"
            assert "payload" in scenario, "Missing payload"
            assert "note" in scenario, "Missing note"

    def test_single_modality_scenarios(self) -> None:
        """验证单模态场景."""
        single_modality = [
            "structured_low_only", "structured_mid_only", "structured_high_only",
            "text_low_only", "text_mid_only", "text_high_only",
            "physio_low_only", "physio_mid_only", "physio_high_only",
        ]

        for scenario_name in single_modality:
            scenario = next((s for s in self.scenarios if s["scenario"] == scenario_name), None)
            assert scenario is not None, f"Missing scenario: {scenario_name}"

            payload = scenario["payload"]
            modalities = [k for k in payload.keys() if k in ["features", "text", "physiological"]]
            assert len(modalities) == 1, f"{scenario_name} should have exactly 1 modality, got {len(modalities)}"

    def test_dual_modality_scenarios(self) -> None:
        """验证双模态场景."""
        dual_modality = [
            "structured_text_low_low", "structured_text_low_high",
            "structured_text_high_low", "structured_text_high_high",
            "structured_physio_low_low", "structured_physio_low_high",
            "structured_physio_high_low", "structured_physio_high_high",
            "text_physio_low_low", "text_physio_low_high",
            "text_physio_high_low", "text_physio_high_high",
        ]

        for scenario_name in dual_modality:
            scenario = next((s for s in self.scenarios if s["scenario"] == scenario_name), None)
            assert scenario is not None, f"Missing scenario: {scenario_name}"

            payload = scenario["payload"]
            modalities = [k for k in payload.keys() if k in ["features", "text", "physiological"]]
            assert len(modalities) == 2, f"{scenario_name} should have exactly 2 modalities, got {len(modalities)}"

    def test_triple_modality_scenarios(self) -> None:
        """验证三模态场景."""
        triple_modality = [
            "all_modalities_low_low_low", "all_modalities_high_high_high",
            "all_modalities_mixed_1", "all_modalities_mixed_2", "all_modalities_mixed_3",
        ]

        for scenario_name in triple_modality:
            scenario = next((s for s in self.scenarios if s["scenario"] == scenario_name), None)
            assert scenario is not None, f"Missing scenario: {scenario_name}"

            payload = scenario["payload"]
            modalities = [k for k in payload.keys() if k in ["features", "text", "physiological"]]
            assert len(modalities) == 3, f"{scenario_name} should have exactly 3 modalities, got {len(modalities)}"

    def test_missing_modality_scenarios(self) -> None:
        """验证模态缺失场景."""
        missing_modality = [
            "missing_structured", "missing_text", "missing_physiological",
            "missing_text_physio", "missing_structured_physio", "missing_structured_text",
            "all_missing",
        ]

        for scenario_name in missing_modality:
            scenario = next((s for s in self.scenarios if s["scenario"] == scenario_name), None)
            assert scenario is not None, f"Missing scenario: {scenario_name}"

    def test_boundary_scenarios(self) -> None:
        """验证边界值场景."""
        boundary_scenarios = [
            "boundary_age_min", "boundary_age_max",
            "boundary_cgpa_min", "boundary_cgpa_max",
            "boundary_sleep_min", "boundary_sleep_max",
            "boundary_heart_rate_min", "boundary_heart_rate_max",
            "boundary_steps_min", "boundary_steps_max",
            "boundary_bp_min", "boundary_bp_max",
        ]

        for scenario_name in boundary_scenarios:
            scenario = next((s for s in self.scenarios if s["scenario"] == scenario_name), None)
            assert scenario is not None, f"Missing scenario: {scenario_name}"

    def test_scenario_labels(self) -> None:
        """验证场景标签合理性."""
        for scenario in self.scenarios:
            label = scenario["label"]
            assert label in [0, 1], f"Invalid label {label} for {scenario['scenario']}"

    def test_scenario_notes(self) -> None:
        """验证场景注释."""
        for scenario in self.scenarios:
            note = scenario["note"]
            assert len(note) > 0, f"Empty note for {scenario['scenario']}"

    def test_payload_structure(self) -> None:
        """验证 payload 结构."""
        for scenario in self.scenarios:
            payload = scenario["payload"]

            if "features" in payload:
                features = payload["features"]
                required_features = [
                    "age", "gender", "study_year", "cgpa", "stress_level",
                    "sleep_duration", "social_support", "financial_pressure",
                    "family_history", "academic_pressure", "exercise_frequency",
                    "anxiety", "panic_attack", "treatment_seeking",
                ]
                for feat in required_features:
                    assert feat in features, f"Missing feature {feat} in {scenario['scenario']}"

            if "physiological" in payload:
                physio = payload["physiological"]
                required_physio = [
                    "sleep_hours", "sleep_quality", "exercise_minutes",
                    "heart_rate", "systolic_bp", "diastolic_bp", "steps",
                ]
                for p in required_physio:
                    assert p in physio, f"Missing physiological {p} in {scenario['scenario']}"

    def test_high_risk_scenarios(self) -> None:
        """验证高风险场景确实标记为高风险."""
        high_risk_scenarios = [
            "structured_high_only", "text_high_only", "physio_high_only",
            "structured_text_high_high", "structured_physio_high_high",
            "text_physio_high_high", "all_modalities_high_high_high",
        ]

        for scenario_name in high_risk_scenarios:
            scenario = next((s for s in self.scenarios if s["scenario"] == scenario_name), None)
            assert scenario is not None, f"Missing scenario: {scenario_name}"
            assert scenario["label"] == 1, f"{scenario_name} should be high risk (label=1)"

    def test_low_risk_scenarios(self) -> None:
        """验证低风险场景确实标记为低风险."""
        low_risk_scenarios = [
            "structured_low_only", "text_low_only", "physio_low_only",
            "all_modalities_low_low_low",
        ]

        for scenario_name in low_risk_scenarios:
            scenario = next((s for s in self.scenarios if s["scenario"] == scenario_name), None)
            assert scenario is not None, f"Missing scenario: {scenario_name}"
            assert scenario["label"] == 0, f"{scenario_name} should be low risk (label=0)"


if __name__ == "__main__":
    import pytest
    pytest.main([__file__, "-v"])
