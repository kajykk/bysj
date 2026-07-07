"""Tests for model_loader module."""

from __future__ import annotations

import hashlib
import json
import tempfile
from pathlib import Path

import pytest

from app.ml.model_loader import (
    check_model_exists,
    load_all_artifacts,
    load_feature_names,
    load_metrics,
    load_model,
    load_scaler,
)


def _create_checksum_file(file_path: Path) -> None:
    """为测试文件创建 .sha256 校验文件（M16/M17 修复后必需）."""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        sha.update(f.read())
    checksum_path = file_path.with_suffix(file_path.suffix + ".sha256")
    checksum_path.write_text(sha.hexdigest(), encoding="utf-8")


class TestCheckModelExists:
    """Test check_model_exists."""

    def test_all_exist(self):
        """TC-COV-ML-042: Returns True when all files exist."""
        with tempfile.TemporaryDirectory() as tmpdir:
            (Path(tmpdir) / "model.json").write_text("{}")
            (Path(tmpdir) / "scaler.json").write_text("{}")
            (Path(tmpdir) / "feature_names.json").write_text("[]")
            # M-ML-7: check_model_exists 现也要求 cleaner_stats.json 存在
            (Path(tmpdir) / "cleaner_stats.json").write_text("{}")
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(
                    "app.ml.model_loader.MODEL_PATH", Path(tmpdir) / "model.json"
                )
                mp.setattr(
                    "app.ml.model_loader.SCALER_PATH", Path(tmpdir) / "scaler.json"
                )
                mp.setattr(
                    "app.ml.model_loader.FEATURE_NAMES_PATH",
                    Path(tmpdir) / "feature_names.json",
                )
                mp.setattr(
                    "app.ml.model_loader.CLEANER_STATS_PATH",
                    Path(tmpdir) / "cleaner_stats.json",
                )
                assert check_model_exists() is True

    def test_missing(self):
        """TC-COV-ML-043: Returns False when files missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            with pytest.MonkeyPatch.context() as mp:
                mp.setattr(
                    "app.ml.model_loader.MODEL_PATH", Path(tmpdir) / "model.json"
                )
                mp.setattr(
                    "app.ml.model_loader.SCALER_PATH", Path(tmpdir) / "scaler.json"
                )
                mp.setattr(
                    "app.ml.model_loader.FEATURE_NAMES_PATH",
                    Path(tmpdir) / "feature_names.json",
                )
                assert check_model_exists() is False


class TestLoadModel:
    """Test load_model."""

    def test_file_not_found(self):
        """TC-COV-ML-044: Raises FileNotFoundError for missing model."""
        with pytest.raises(FileNotFoundError, match="Model not found"):
            load_model("/nonexistent/model.json")

    def test_load_valid(self):
        """TC-COV-ML-045: Loads valid model JSON."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json.dump(
                {
                    "input_dim": 7,
                    "hidden_dims": [16, 8],
                    "dropout_rate": 0.3,
                    "layers": [
                        {"W": [[0.1] * 7] * 16, "b": [0.0] * 16},
                        {"W": [[0.1] * 16] * 8, "b": [0.0] * 8},
                    ],
                },
                f,
            )
            path = f.name

        # M16 修复：load_model 现在强制要求 .sha256 校验文件
        _create_checksum_file(Path(path))

        result = load_model(path)
        assert result is not None
        Path(path).unlink()
        Path(path).with_suffix(".json.sha256").unlink(missing_ok=True)


class TestLoadScaler:
    """Test load_scaler."""

    def test_file_not_found(self):
        """TC-COV-ML-046: Raises FileNotFoundError for missing scaler."""
        with pytest.raises(FileNotFoundError, match="Scaler not found"):
            load_scaler("/nonexistent/scaler.json")

    def test_load_valid(self):
        """TC-COV-ML-047: Loads valid scaler JSON."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json.dump({"mean": [0.0, 1.0], "scale": [1.0, 1.0], "n_features_in": 2}, f)
            path = f.name

        # M17 修复：load_scaler 现在强制要求 .sha256 校验文件
        _create_checksum_file(Path(path))

        result = load_scaler(path)
        assert result is not None
        Path(path).unlink()
        Path(path).with_suffix(".json.sha256").unlink(missing_ok=True)


class TestLoadFeatureNames:
    """Test load_feature_names."""

    def test_file_not_found(self):
        """TC-COV-ML-048: Raises FileNotFoundError for missing feature names."""
        with pytest.raises(FileNotFoundError, match="Feature names not found"):
            load_feature_names("/nonexistent/features.json")

    def test_load_valid(self):
        """TC-COV-ML-049: Loads valid feature names JSON."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json.dump(["f1", "f2", "f3"], f)
            path = f.name

        # H-9 修复后 load_feature_names 要求 .sha256 校验文件存在
        checksum = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        checksum_path = Path(path).with_suffix(Path(path).suffix + ".sha256")
        checksum_path.write_text(checksum, encoding="utf-8")

        result = load_feature_names(path)
        assert result == ["f1", "f2", "f3"]
        Path(path).unlink()
        checksum_path.unlink(missing_ok=True)


class TestLoadMetrics:
    """Test load_metrics."""

    def test_file_not_found(self):
        """TC-COV-ML-050: Raises FileNotFoundError for missing metrics."""
        with pytest.raises(FileNotFoundError, match="Metrics not found"):
            load_metrics("/nonexistent/metrics.json")

    def test_load_valid(self):
        """TC-COV-ML-051: Loads valid metrics JSON."""
        with tempfile.NamedTemporaryFile(suffix=".json", delete=False, mode="w") as f:
            json.dump({"accuracy": 0.9, "f1": 0.85}, f)
            path = f.name

        # H-9 修复后 load_metrics 要求 .sha256 校验文件存在
        checksum = hashlib.sha256(Path(path).read_bytes()).hexdigest()
        checksum_path = Path(path).with_suffix(Path(path).suffix + ".sha256")
        checksum_path.write_text(checksum, encoding="utf-8")

        result = load_metrics(path)
        assert result["accuracy"] == 0.9
        Path(path).unlink()
        checksum_path.unlink(missing_ok=True)


class TestLoadAllArtifacts:
    """Test load_all_artifacts."""

    def test_load_all_success(self):
        """TC-COV-ML-052: load_all_artifacts loads all artifacts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Create model.json
            model_path = tmpdir_path / "model.json"
            with open(model_path, "w") as f:
                json.dump(
                    {
                        "input_dim": 3,
                        "hidden_dims": [4, 2],
                        "dropout_rate": 0.3,
                        "layers": [
                            {"W": [[0.1] * 3] * 4, "b": [0.0] * 4},
                            {"W": [[0.1] * 4] * 2, "b": [0.0] * 2},
                        ],
                    },
                    f,
                )

            # Create scaler.json
            scaler_path = tmpdir_path / "scaler.json"
            with open(scaler_path, "w") as f:
                json.dump(
                    {
                        "mean": [0.0, 1.0, 2.0],
                        "scale": [1.0, 1.0, 1.0],
                        "n_features_in": 3,
                    },
                    f,
                )

            # Create feature_names.json
            feature_names_path = tmpdir_path / "feature_names.json"
            with open(feature_names_path, "w") as f:
                json.dump(["f1", "f2", "f3"], f)

            # Create metrics.json
            metrics_path = tmpdir_path / "metrics.json"
            with open(metrics_path, "w") as f:
                json.dump({"accuracy": 0.95, "f1": 0.92}, f)

            # M16/M17/H-9 修复：为所有关键文件创建 .sha256 校验文件
            _create_checksum_file(model_path)
            _create_checksum_file(scaler_path)
            _create_checksum_file(feature_names_path)
            _create_checksum_file(metrics_path)

            with pytest.MonkeyPatch.context() as mp:
                mp.setattr("app.ml.model_loader.MODEL_PATH", model_path)
                mp.setattr("app.ml.model_loader.SCALER_PATH", scaler_path)
                mp.setattr("app.ml.model_loader.FEATURE_NAMES_PATH", feature_names_path)
                mp.setattr("app.ml.model_loader.METRICS_PATH", metrics_path)

                model, scaler, feature_names, metrics = load_all_artifacts()

                assert model is not None
                assert scaler is not None
                assert feature_names == ["f1", "f2", "f3"]
                assert metrics["accuracy"] == 0.95

    def test_load_all_missing_model(self):
        """TC-COV-ML-053: load_all_artifacts raises when model missing."""
        with tempfile.TemporaryDirectory() as tmpdir:
            tmpdir_path = Path(tmpdir)

            # Only create scaler and feature_names, not model
            scaler_path = tmpdir_path / "scaler.json"
            with open(scaler_path, "w") as f:
                json.dump(
                    {
                        "mean": [0.0, 1.0],
                        "scale": [1.0, 1.0],
                        "n_features_in": 2,
                    },
                    f,
                )

            feature_names_path = tmpdir_path / "feature_names.json"
            with open(feature_names_path, "w") as f:
                json.dump(["f1", "f2"], f)

            metrics_path = tmpdir_path / "metrics.json"
            with open(metrics_path, "w") as f:
                json.dump({"accuracy": 0.9}, f)

            with pytest.MonkeyPatch.context() as mp:
                mp.setattr("app.ml.model_loader.MODEL_PATH", tmpdir_path / "model.json")
                mp.setattr("app.ml.model_loader.SCALER_PATH", scaler_path)
                mp.setattr("app.ml.model_loader.FEATURE_NAMES_PATH", feature_names_path)
                mp.setattr("app.ml.model_loader.METRICS_PATH", metrics_path)

                with pytest.raises(FileNotFoundError, match="Model not found"):
                    load_all_artifacts()
