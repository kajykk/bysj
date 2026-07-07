"""Extended tests for FusionEngine."""

from __future__ import annotations

import tempfile
from pathlib import Path

from app.ml.fusion_engine import CONFIDENCE_THRESHOLDS, DEFAULT_WEIGHTS, FusionEngine


class TestFusionEngine:
    """Test FusionEngine."""

    def test_init_default(self):
        """TC-COV-ML-029: Default initialization."""
        engine = FusionEngine()
        assert engine.weights == DEFAULT_WEIGHTS
        assert engine.use_confidence_weighting is True
        assert engine.use_modality_missing_handling is True

    def test_init_custom_weights(self):
        """TC-COV-ML-030: Custom weights initialization."""
        weights = {"structured": 0.5, "text": 0.3, "physiological": 0.2}
        engine = FusionEngine(weights=weights)
        assert engine.weights == weights

    def test_init_weight_normalization(self):
        """TC-COV-ML-031: Weight normalization when sum != 1.0."""
        weights = {"structured": 1.0, "text": 1.0, "physiological": 1.0}
        engine = FusionEngine(weights=weights)
        total = sum(engine.weights.values())
        assert abs(total - 1.0) < 0.01

    def test_compute_confidence_no_weighting(self):
        """TC-COV-ML-032: Confidence without weighting returns 1.0."""
        engine = FusionEngine(use_confidence_weighting=False)
        confidence = engine.compute_confidence("structured", 50)
        assert confidence == 1.0

    def test_compute_confidence_extreme_score(self):
        """TC-COV-ML-033: Confidence for extreme scores."""
        engine = FusionEngine()
        high_conf = engine.compute_confidence("structured", 100)
        low_conf = engine.compute_confidence("structured", 50)
        assert high_conf > low_conf

    def test_compute_confidence_text_length(self):
        """TC-COV-ML-034: Text confidence with length metadata."""
        engine = FusionEngine()
        short_conf = engine.compute_confidence("text", 70, {"text_length": 5})
        long_conf = engine.compute_confidence("text", 70, {"text_length": 200})
        assert long_conf >= short_conf

    def test_compute_confidence_physiological_missing(self):
        """TC-COV-ML-035: Physiological confidence with missing fields."""
        engine = FusionEngine()
        conf = engine.compute_confidence("physiological", 70, {"missing_fields": 2})
        assert conf < 1.0

    def test_redistribute_weights_all_available(self):
        """TC-COV-ML-036: Redistribute weights when all available."""
        engine = FusionEngine()
        weights = engine.redistribute_weights({"structured", "text", "physiological"})
        assert len(weights) == 3
        assert abs(sum(weights.values()) - 1.0) < 0.01

    def test_redistribute_weights_one_missing(self):
        """TC-COV-ML-037: Redistribute weights when one missing."""
        engine = FusionEngine()
        weights = engine.redistribute_weights({"structured", "text"})
        assert len(weights) == 2
        assert abs(sum(weights.values()) - 1.0) < 0.01

    def test_redistribute_weights_none_available(self):
        """TC-COV-ML-038: Redistribute weights when none available."""
        engine = FusionEngine()
        weights = engine.redistribute_weights(set())
        assert weights == {}

    def test_fuse_empty(self):
        """TC-COV-ML-039: Fuse with empty scores."""
        engine = FusionEngine()
        result = engine.fuse({})
        assert result["risk_score"] == 0.0
        assert result["fusion_scheme"] == "empty"

    def test_fuse_single_modality(self):
        """TC-COV-ML-040: Fuse with single modality."""
        engine = FusionEngine()
        result = engine.fuse({"structured": 80})
        assert result["fusion_scheme"] == "single_modality"
        assert result["risk_score"] > 0

    def test_fuse_dual_modality(self):
        """TC-COV-ML-041: Fuse with dual modalities."""
        engine = FusionEngine()
        result = engine.fuse({"structured": 80, "text": 60})
        assert result["fusion_scheme"] == "dual_modality"
        assert result["risk_score"] > 0

    def test_fuse_full_three_modality(self):
        """TC-COV-ML-042: Fuse with all three modalities."""
        engine = FusionEngine()
        result = engine.fuse({"structured": 80, "text": 60, "physiological": 70})
        assert result["fusion_scheme"] == "full_three_modality"
        assert result["risk_score"] > 0
        assert "modality_contributions" in result

    def test_fuse_with_metadata(self):
        """TC-COV-ML-043: Fuse with metadata."""
        engine = FusionEngine()
        result = engine.fuse(
            {"structured": 80, "text": 60},
            {"text": {"text_length": 200}},
        )
        assert result["risk_score"] > 0

    def test_score_to_level(self):
        """TC-COV-ML-044: Score to level conversion (v1.31: 适配 fusion 阈值 22/42/62/82)."""
        engine = FusionEngine()
        # fusion 阈值: mild=22, moderate=42, high=62, critical=82
        assert engine._score_to_level(0) == 0
        assert engine._score_to_level(19) == 0
        assert engine._score_to_level(20) == 0
        assert engine._score_to_level(22) == 1
        assert engine._score_to_level(41) == 1
        assert engine._score_to_level(42) == 2
        assert engine._score_to_level(61) == 2
        assert engine._score_to_level(62) == 3
        assert engine._score_to_level(81) == 3
        assert engine._score_to_level(82) == 4
        assert engine._score_to_level(100) == 4

    def test_save_and_load_config(self):
        """TC-COV-ML-045: Save and load config."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "config.json"
            engine = FusionEngine(weights={"structured": 0.5, "text": 0.5})
            engine.save_config(path)
            assert path.exists()

            # M25 修复：load_config 现在强制要求 .sha256 校验文件
            import hashlib

            sha = hashlib.sha256()
            with open(path, "rb") as f:
                sha.update(f.read())
            checksum_path = path.with_suffix(path.suffix + ".sha256")
            checksum_path.write_text(sha.hexdigest(), encoding="utf-8")

            loaded = FusionEngine.load_config(path)
            assert loaded.weights == engine.weights

    def test_confidence_thresholds(self):
        """TC-COV-ML-046: Confidence thresholds constants."""
        assert "high" in CONFIDENCE_THRESHOLDS
        assert "medium" in CONFIDENCE_THRESHOLDS
        assert "low" in CONFIDENCE_THRESHOLDS
