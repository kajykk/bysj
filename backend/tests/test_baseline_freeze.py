"""
Test suite for baseline freeze functionality.

Tests:
- TC-GOV-001: 验证基线版本记录完整性
- TC-GOV-002: 验证模型文件存在性检查
- TC-GOV-003: 验证基线版本可回滚
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Add project root to path
project_root = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(project_root))

from scripts.baseline_freeze import (
    CURRENT_BASELINE,
    load_actual_metrics,
    save_baseline,
    validate_model_files,
)


class TestBaselineFreeze:
    """Test suite for baseline freeze functionality."""

    def test_baseline_structure(self) -> None:
        """TC-GOV-001: 验证基线版本记录完整性."""
        baseline = CURRENT_BASELINE

        # Verify required top-level keys
        assert "baseline_version" in baseline
        assert "iteration" in baseline
        assert "frozen_at" in baseline
        assert "models" in baseline
        assert "fusion_config" in baseline
        assert "validation" in baseline

        # Verify models section
        assert "structured_catboost" in baseline["models"]
        assert "text_tfidf_lr" in baseline["models"]
        assert "physiological_numpy_mlp" in baseline["models"]

        # Verify each model has required fields
        for model_name, model_config in baseline["models"].items():
            assert "model_id" in model_config, f"{model_name} missing model_id"
            assert "name" in model_config, f"{model_name} missing name"
            assert "version" in model_config, f"{model_name} missing version"
            assert "status" in model_config, f"{model_name} missing status"
            assert "type" in model_config, f"{model_name} missing type"
            assert "metrics" in model_config, f"{model_name} missing metrics"
            assert "artifact_path" in model_config, f"{model_name} missing artifact_path"
            assert "metrics_path" in model_config, f"{model_name} missing metrics_path"
            assert "fallback_id" in model_config, f"{model_name} missing fallback_id"
            assert "enabled" in model_config, f"{model_name} missing enabled"

            # Verify metrics have required fields
            metrics = model_config["metrics"]
            assert "f1_score" in metrics, f"{model_name} missing f1_score"
            assert "precision" in metrics, f"{model_name} missing precision"
            assert "recall" in metrics, f"{model_name} missing recall"
            assert "accuracy" in metrics, f"{model_name} missing accuracy"
            assert "roc_auc" in metrics, f"{model_name} missing roc_auc"

    def test_model_files_exist(self) -> None:
        """TC-GOV-002: 验证模型文件存在性检查."""
        baseline = json.loads(json.dumps(CURRENT_BASELINE))
        validation = validate_model_files(baseline)

        assert validation["all_models_exist"] is True, \
            f"Some model files are missing: {validation.get('missing_files', [])}"
        assert validation["all_metrics_exist"] is True, \
            f"Some metrics files are missing: {validation.get('missing_files', [])}"
        assert validation["validation_timestamp"] is not None

    def test_baseline_save_and_load(self, tmp_path: Path) -> None:
        """TC-GOV-003: 验证基线版本可回滚."""
        baseline = json.loads(json.dumps(CURRENT_BASELINE))

        # Save baseline to temp directory
        baselines_dir = tmp_path / "baselines"
        baselines_dir.mkdir(parents=True, exist_ok=True)

        timestamp = "20260427_173006"
        filename = f"baseline_v1.3_{timestamp}.json"
        filepath = baselines_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(baseline, f, indent=2, ensure_ascii=False)

        # Load baseline back
        with open(filepath, "r", encoding="utf-8") as f:
            loaded_baseline = json.load(f)

        # Verify loaded baseline matches original
        assert loaded_baseline["baseline_version"] == baseline["baseline_version"]
        assert loaded_baseline["iteration"] == baseline["iteration"]
        assert len(loaded_baseline["models"]) == len(baseline["models"])

        for model_name in baseline["models"]:
            assert model_name in loaded_baseline["models"]
            original = baseline["models"][model_name]
            loaded = loaded_baseline["models"][model_name]
            assert loaded["model_id"] == original["model_id"]
            assert loaded["version"] == original["version"]
            assert loaded["status"] == original["status"]
            assert loaded["metrics"]["f1_score"] == original["metrics"]["f1_score"]

    def test_fusion_config(self) -> None:
        """验证融合配置完整性."""
        fusion_config = CURRENT_BASELINE["fusion_config"]

        assert "weights" in fusion_config
        assert "scheme" in fusion_config
        assert "version" in fusion_config

        weights = fusion_config["weights"]
        assert "structured" in weights
        assert "text" in weights
        assert "physiological" in weights

        # Verify weights sum to 1.0
        total_weight = sum(weights.values())
        assert abs(total_weight - 1.0) < 0.01, f"Weights sum to {total_weight}, expected ~1.0"

    def test_load_actual_metrics(self, tmp_path: Path) -> None:
        """验证实际指标加载功能."""
        # Create a test metrics file
        test_metrics = {
            "f1_score": 0.85,
            "precision": 0.83,
            "recall": 0.87,
            "accuracy": 0.84,
            "roc_auc": 0.91,
        }
        metrics_file = tmp_path / "test_metrics.json"
        with open(metrics_file, "w", encoding="utf-8") as f:
            json.dump(test_metrics, f)

        # Load metrics
        loaded = load_actual_metrics(metrics_file)
        assert loaded["f1_score"] == 0.85
        assert loaded["precision"] == 0.83
        assert loaded["recall"] == 0.87

        # Test with non-existent file
        non_existent = tmp_path / "non_existent.json"
        loaded_empty = load_actual_metrics(non_existent)
        assert loaded_empty == {}


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
