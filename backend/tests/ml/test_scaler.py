"""Tests for app/ml/scaler module."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from app.ml.scaler import (
    SimpleStandardScaler,
    ensure_artifacts_dir,
    fit_scaler,
    load_feature_names,
    load_scaler,
    save_feature_names,
    save_scaler,
    scale_features,
)


class TestSimpleStandardScalerDataFrame:
    """Test SimpleStandardScaler with DataFrame input."""

    def test_fit_with_dataframe(self):
        """TC-COV-SCALER-001: Fit with DataFrame input."""
        scaler = SimpleStandardScaler()
        df = pd.DataFrame({"a": [1.0, 3.0, 5.0], "b": [2.0, 4.0, 6.0]})
        result = scaler.fit(df)
        assert result is scaler
        assert scaler.mean_ is not None
        assert scaler.n_features_in_ == 2

    def test_transform_with_dataframe(self):
        """TC-COV-SCALER-002: Transform with DataFrame input."""
        scaler = SimpleStandardScaler()
        df = pd.DataFrame({"a": [1.0, 3.0, 5.0], "b": [2.0, 4.0, 6.0]})
        scaler.fit(df)
        result = scaler.transform(df)
        assert isinstance(result, np.ndarray)
        assert result.shape == (3, 2)

    def test_fit_transform_with_dataframe(self):
        """TC-COV-SCALER-003: Fit and transform with DataFrame input."""
        scaler = SimpleStandardScaler()
        df = pd.DataFrame({"a": [1.0, 3.0, 5.0], "b": [2.0, 4.0, 6.0]})
        result = scaler.fit_transform(df)
        assert isinstance(result, np.ndarray)
        assert result.shape == (3, 2)


class TestFitScaler:
    """Test fit_scaler function."""

    def test_fit_scaler_with_array(self):
        """TC-COV-SCALER-004: fit_scaler with numpy array."""
        X = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
        scaler = fit_scaler(X)
        assert isinstance(scaler, SimpleStandardScaler)
        assert scaler.mean_ is not None
        assert scaler.n_features_in_ == 2

    def test_fit_scaler_with_dataframe(self):
        """TC-COV-SCALER-005: fit_scaler with DataFrame."""
        df = pd.DataFrame({"a": [1.0, 3.0, 5.0], "b": [2.0, 4.0, 6.0]})
        scaler = fit_scaler(df)
        assert isinstance(scaler, SimpleStandardScaler)
        assert scaler.n_features_in_ == 2


class TestSaveScaler:
    """Test save_scaler function."""

    def test_save_scaler_default_path(self):
        """TC-COV-SCALER-006: save_scaler with default path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scaler = SimpleStandardScaler()
            X = np.array([[1.0, 2.0], [3.0, 4.0]])
            scaler.fit(X)
            path = Path(tmpdir) / "scaler.json"
            save_scaler(scaler, path)
            assert path.exists()
            data = json.loads(path.read_text())
            assert "mean" in data
            assert "scale" in data

    def test_save_scaler_custom_path(self):
        """TC-COV-SCALER-007: save_scaler with custom path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scaler = SimpleStandardScaler()
            X = np.array([[1.0, 2.0], [3.0, 4.0]])
            scaler.fit(X)
            custom_path = Path(tmpdir) / "custom" / "scaler.json"
            custom_path.parent.mkdir(parents=True, exist_ok=True)
            save_scaler(scaler, custom_path)
            assert custom_path.exists()


class TestLoadScaler:
    """Test load_scaler function."""

    def test_load_scaler_success(self):
        """TC-COV-SCALER-008: load_scaler with valid file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            scaler = SimpleStandardScaler()
            X = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
            scaler.fit(X)
            path = Path(tmpdir) / "scaler.json"
            save_scaler(scaler, path)

            loaded = load_scaler(path)
            assert isinstance(loaded, SimpleStandardScaler)
            np.testing.assert_array_almost_equal(loaded.mean_, scaler.mean_)
            np.testing.assert_array_almost_equal(loaded.scale_, scaler.scale_)

    def test_load_scaler_file_not_found(self):
        """TC-COV-SCALER-009: load_scaler raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Scaler not found"):
            load_scaler("/nonexistent/scaler.json")


class TestSaveFeatureNames:
    """Test save_feature_names function."""

    def test_save_feature_names_default_path(self):
        """TC-COV-SCALER-010: save_feature_names with default path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "feature_names.json"
            save_feature_names(["f1", "f2", "f3"], path)
            assert path.exists()
            data = json.loads(path.read_text())
            assert data == ["f1", "f2", "f3"]

    def test_save_feature_names_custom_path(self):
        """TC-COV-SCALER-011: save_feature_names with custom path."""
        with tempfile.TemporaryDirectory() as tmpdir:
            custom_path = Path(tmpdir) / "custom" / "features.json"
            custom_path.parent.mkdir(parents=True, exist_ok=True)
            save_feature_names(["a", "b"], custom_path)
            assert custom_path.exists()


class TestLoadFeatureNames:
    """Test load_feature_names function."""

    def test_load_feature_names_success(self):
        """TC-COV-SCALER-012: load_feature_names with valid file."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "feature_names.json"
            save_feature_names(["f1", "f2", "f3"], path)

            result = load_feature_names(path)
            assert result == ["f1", "f2", "f3"]

    def test_load_feature_names_file_not_found(self):
        """TC-COV-SCALER-013: load_feature_names raises FileNotFoundError."""
        with pytest.raises(FileNotFoundError, match="Feature names not found"):
            load_feature_names("/nonexistent/features.json")


class TestScaleFeatures:
    """Test scale_features function."""

    def test_scale_features_with_scaler(self):
        """TC-COV-SCALER-014: scale_features with provided scaler."""
        scaler = SimpleStandardScaler()
        X = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
        scaler.fit(X)

        X_new = np.array([[1.0, 2.0], [3.0, 4.0]])
        result = scale_features(X_new, scaler)
        assert isinstance(result, np.ndarray)
        assert result.shape == (2, 2)

    def test_scale_features_without_scaler(self):
        """TC-COV-SCALER-015: scale_features without scaler fits new one."""
        X = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
        result = scale_features(X)
        assert isinstance(result, np.ndarray)
        assert result.shape == (3, 2)

    def test_scale_features_with_dataframe(self):
        """TC-COV-SCALER-016: scale_features with DataFrame input."""
        df = pd.DataFrame({"a": [1.0, 3.0, 5.0], "b": [2.0, 4.0, 6.0]})
        result = scale_features(df)
        assert isinstance(result, np.ndarray)
        assert result.shape == (3, 2)


class TestEnsureArtifactsDir:
    """Test ensure_artifacts_dir function."""

    def test_creates_directory(self):
        """TC-COV-SCALER-017: ensure_artifacts_dir creates directory."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from app.ml import scaler as scaler_module

            orig_dir = scaler_module.ARTIFACTS_DIR
            try:
                custom_dir = Path(tmpdir) / "artifacts" / "physiological"
                scaler_module.ARTIFACTS_DIR = custom_dir
                ensure_artifacts_dir()
                assert custom_dir.exists()
            finally:
                scaler_module.ARTIFACTS_DIR = orig_dir
