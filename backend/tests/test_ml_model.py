"""Tests for app/ml model and scaler modules."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import numpy as np
import pytest

from app.ml.loss import binary_cross_entropy_loss, compute_class_weights, focal_loss
from app.ml.model import PhysiologicalMLP, he_init, relu, relu_derivative, sigmoid
from app.ml.model_loader import (
    load_all_artifacts,
    load_metrics,
    load_model,
    write_sha256_sidecar,
)
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
from app.ml.trainer import (
    EarlyStopping,
    compute_auprc,
    compute_metrics,
    compute_roc_auc,
    evaluate,
    sgd_optimizer,
    train_epoch,
    train_model,
)


class TestActivationFunctions:
    """Test activation functions."""

    def test_relu_positive(self):
        """TC-COV-ML-001: ReLU with positive values."""
        x = np.array([1.0, 2.0, 3.0])
        result = relu(x)
        np.testing.assert_array_equal(result, x)

    def test_relu_negative(self):
        """TC-COV-ML-002: ReLU with negative values."""
        x = np.array([-1.0, -2.0, -3.0])
        result = relu(x)
        np.testing.assert_array_equal(result, np.array([0.0, 0.0, 0.0]))

    def test_relu_mixed(self):
        """TC-COV-ML-003: ReLU with mixed values."""
        x = np.array([-1.0, 0.0, 1.0])
        result = relu(x)
        np.testing.assert_array_equal(result, np.array([0.0, 0.0, 1.0]))

    def test_relu_derivative(self):
        """TC-COV-ML-004: ReLU derivative."""
        x = np.array([-1.0, 0.0, 1.0])
        result = relu_derivative(x)
        np.testing.assert_array_equal(result, np.array([0.0, 0.0, 1.0]))

    def test_sigmoid_zero(self):
        """TC-COV-ML-005: Sigmoid at zero."""
        result = sigmoid(np.array([0.0]))
        assert abs(result[0] - 0.5) < 0.001

    def test_sigmoid_large_negative(self):
        """TC-COV-ML-006: Sigmoid with large negative value."""
        result = sigmoid(np.array([-500.0]))
        assert result[0] < 0.01

    def test_sigmoid_large_positive(self):
        """TC-COV-ML-007: Sigmoid with large positive value."""
        result = sigmoid(np.array([500.0]))
        assert result[0] > 0.99

    def test_he_init_shape(self):
        """TC-COV-ML-008: He initialization shape."""
        shape = (10, 5)
        result = he_init(shape)
        assert result.shape == shape

    def test_he_init_distribution(self):
        """TC-COV-ML-009: He initialization distribution."""
        shape = (100, 50)
        result = he_init(shape)
        std = np.sqrt(2.0 / shape[0])
        assert np.std(result) < std * 2  # Loose check


class TestPhysiologicalMLP:
    """Test PhysiologicalMLP model."""

    def test_init_default(self):
        """TC-COV-ML-010: Default initialization."""
        model = PhysiologicalMLP()
        assert model.input_dim == 13
        assert model.hidden_dims == [64, 32, 16]
        assert model.dropout_rate == 0.4
        assert model.use_batch_norm is True

    def test_init_custom(self):
        """TC-COV-ML-011: Custom initialization."""
        model = PhysiologicalMLP(
            input_dim=5, hidden_dims=[10, 5], dropout_rate=0.2, use_batch_norm=False
        )
        assert model.input_dim == 5
        assert model.hidden_dims == [10, 5]
        assert model.dropout_rate == 0.2
        assert model.use_batch_norm is False

    def test_count_parameters(self):
        """TC-COV-ML-012: Count parameters."""
        model = PhysiologicalMLP(input_dim=2, hidden_dims=[3, 2], use_batch_norm=False)
        count = model.count_parameters()
        # 2*3 + 3 + 3*2 + 2 + 2*1 + 1 = 6+3+6+2+2+1 = 20
        assert count > 0

    def test_forward(self):
        """TC-COV-ML-013: Forward pass."""
        model = PhysiologicalMLP(input_dim=3, hidden_dims=[4, 2], use_batch_norm=False)
        X = np.array([[1.0, 2.0, 3.0]])
        output, caches = model.forward(X)
        assert output.shape == (1, 1)
        assert len(caches) == 3  # 2 hidden + 1 output

    def test_predict_proba(self):
        """TC-COV-ML-014: Predict probabilities."""
        model = PhysiologicalMLP(input_dim=3, hidden_dims=[4], use_batch_norm=False)
        X = np.array([[1.0, 2.0, 3.0]])
        proba = model.predict_proba(X)
        assert proba.shape == (1, 1)
        assert 0 <= proba[0, 0] <= 1

    def test_predict(self):
        """TC-COV-ML-015: Predict class labels."""
        model = PhysiologicalMLP(input_dim=3, hidden_dims=[4], use_batch_norm=False)
        X = np.array([[1.0, 2.0, 3.0]])
        labels = model.predict(X)
        assert labels.shape == (1, 1)
        assert labels[0, 0] in [0, 1]

    def test_predict_with_threshold(self):
        """TC-COV-ML-016: Predict with custom threshold."""
        model = PhysiologicalMLP(input_dim=3, hidden_dims=[4], use_batch_norm=False)
        X = np.array([[1.0, 2.0, 3.0]])
        labels = model.predict(X, threshold=0.9)
        assert labels[0, 0] in [0, 1]

    def test_save_and_load(self):
        """TC-COV-ML-017: Save and load model."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "model.json"
            model = PhysiologicalMLP(input_dim=3, hidden_dims=[4], use_batch_norm=False)
            model.save(path)
            assert path.exists()

            loaded = PhysiologicalMLP.load(path)
            assert loaded.input_dim == model.input_dim
            assert loaded.hidden_dims == model.hidden_dims

    def test_training_mode(self):
        """TC-COV-ML-018: Training mode flag."""
        model = PhysiologicalMLP(input_dim=3, hidden_dims=[4], use_batch_norm=False)
        assert model.training is True
        model.predict_proba(np.array([[1.0, 2.0, 3.0]]))
        assert model.training is True  # Should be reset to True


class TestSimpleStandardScaler:
    """Test SimpleStandardScaler."""

    def test_fit(self):
        """TC-COV-ML-019: Fit scaler."""
        scaler = SimpleStandardScaler()
        X = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
        result = scaler.fit(X)
        assert result is scaler
        assert scaler.mean_ is not None
        assert scaler.scale_ is not None
        assert scaler.n_features_in_ == 2

    def test_transform(self):
        """TC-COV-ML-020: Transform data."""
        scaler = SimpleStandardScaler()
        X = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
        scaler.fit(X)
        X_scaled = scaler.transform(X)
        assert X_scaled.shape == X.shape

    def test_fit_transform(self):
        """TC-COV-ML-021: Fit and transform."""
        scaler = SimpleStandardScaler()
        X = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
        X_scaled = scaler.fit_transform(X)
        assert X_scaled.shape == X.shape

    def test_zero_variance(self):
        """TC-COV-ML-022: Handle zero variance features."""
        scaler = SimpleStandardScaler()
        X = np.array([[1.0, 2.0], [1.0, 4.0], [1.0, 6.0]])
        scaler.fit(X)
        # First feature has zero variance, scale should be 1.0
        assert scaler.scale_[0] == 1.0

    def test_to_dict(self):
        """TC-COV-ML-023: Serialize to dict."""
        scaler = SimpleStandardScaler()
        X = np.array([[1.0, 2.0], [3.0, 4.0]])
        scaler.fit(X)
        data = scaler.to_dict()
        assert "mean" in data
        assert "scale" in data
        assert "n_features_in" in data

    def test_from_dict(self):
        """TC-COV-ML-024: Deserialize from dict."""
        scaler = SimpleStandardScaler()
        X = np.array([[1.0, 2.0], [3.0, 4.0]])
        scaler.fit(X)
        data = scaler.to_dict()
        loaded = SimpleStandardScaler.from_dict(data)
        np.testing.assert_array_equal(loaded.mean_, scaler.mean_)
        np.testing.assert_array_equal(loaded.scale_, scaler.scale_)

    def test_save_and_load(self):
        """TC-COV-ML-025: Save and load scaler."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "scaler.json"
            scaler = SimpleStandardScaler()
            X = np.array([[1.0, 2.0], [3.0, 4.0]])
            scaler.fit(X)
            scaler.save(path)
            assert path.exists()

    def test_transform_before_fit(self):
        """TC-COV-ML-026: Transform before fit raises error."""
        scaler = SimpleStandardScaler()
        X = np.array([[1.0, 2.0]])
        with pytest.raises((TypeError, AttributeError, RuntimeError)):
            scaler.transform(X)


class TestModelLoader:
    """Test model loader utilities."""

    def test_check_model_exists_no_artifacts(self):
        """TC-COV-ML-027: check_model_exists when no artifacts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from app.ml import model_loader as ml

            orig_dir = ml.ARTIFACTS_DIR
            try:
                ml.ARTIFACTS_DIR = Path(tmpdir) / "artifacts"
                ml.MODEL_PATH = ml.ARTIFACTS_DIR / "model.json"
                ml.SCALER_PATH = ml.ARTIFACTS_DIR / "scaler.json"
                ml.FEATURE_NAMES_PATH = ml.ARTIFACTS_DIR / "feature_names.json"
                result = ml.check_model_exists()
                assert result is False
            finally:
                ml.ARTIFACTS_DIR = orig_dir
                ml.MODEL_PATH = orig_dir / "model.json"
                ml.SCALER_PATH = orig_dir / "scaler.json"
                ml.FEATURE_NAMES_PATH = orig_dir / "feature_names.json"

    def test_ensure_artifacts_dir(self):
        """TC-COV-ML-028: ensure_artifacts_dir creates directory."""
        ensure_artifacts_dir()
        from app.ml.scaler import ARTIFACTS_DIR

        assert ARTIFACTS_DIR.exists()

    def test_forward_with_batch_norm(self):
        """TC-COV-ML-029: Forward pass with batch normalization."""
        model = PhysiologicalMLP(input_dim=3, hidden_dims=[4], use_batch_norm=True)
        X = np.array([[1.0, 2.0, 3.0]])
        output, caches = model.forward(X)
        assert output.shape == (1, 1)
        assert len(caches) == 2
        assert "bn" in caches[0]

    def test_predict_proba_eval_mode(self):
        """TC-COV-ML-030: predict_proba sets eval mode temporarily."""
        model = PhysiologicalMLP(input_dim=3, hidden_dims=[4], use_batch_norm=True)
        model.training = True
        X = np.array([[1.0, 2.0, 3.0]])
        proba = model.predict_proba(X)
        assert proba.shape == (1, 1)
        assert 0 <= proba[0, 0] <= 1
        assert model.training is True  # Reset back to training

    def test_save_and_load_with_batch_norm(self):
        """TC-COV-ML-031: Save/load with batch norm parameters."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "model.json"
            model = PhysiologicalMLP(input_dim=3, hidden_dims=[4], use_batch_norm=True)
            model.save(path)
            loaded = PhysiologicalMLP.load(path)
            assert loaded.use_batch_norm is True
            assert "bn_gamma" in loaded.layers[0]
            np.testing.assert_array_equal(
                loaded.layers[0]["bn_gamma"], model.layers[0]["bn_gamma"]
            )

    def test_predict_multi_sample(self):
        """TC-COV-ML-032: Predict on multiple samples."""
        model = PhysiologicalMLP(input_dim=3, hidden_dims=[4], use_batch_norm=False)
        X = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
        labels = model.predict(X)
        assert labels.shape == (2, 1)
        assert all(label in [0, 1] for label in labels.flatten())

    def test_predict_proba_multi_sample(self):
        """TC-COV-ML-033: Predict probabilities on multiple samples."""
        model = PhysiologicalMLP(input_dim=3, hidden_dims=[4], use_batch_norm=False)
        X = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
        proba = model.predict_proba(X)
        assert proba.shape == (2, 1)
        assert all(0 <= p <= 1 for p in proba.flatten())


class TestTrainer:
    """Test trainer module functions."""

    def test_compute_metrics_basic(self):
        """TC-COV-TRAINER-001: Compute metrics with basic data."""
        y_true = np.array([[0], [1], [0], [1]])
        y_pred = np.array([[0.1], [0.9], [0.2], [0.8]])
        metrics = compute_metrics(y_true, y_pred)
        assert "accuracy" in metrics
        assert "precision" in metrics
        assert "recall" in metrics
        assert "f1" in metrics
        assert "roc_auc" in metrics
        assert "auprc" in metrics
        assert metrics["accuracy"] == 1.0

    def test_compute_metrics_all_negative(self):
        """TC-COV-TRAINER-002: Compute metrics with all negative labels."""
        y_true = np.array([[0], [0], [0]])
        y_pred = np.array([[0.1], [0.2], [0.3]])
        metrics = compute_metrics(y_true, y_pred)
        assert metrics["roc_auc"] == 0.5

    def test_compute_roc_auc_perfect(self):
        """TC-COV-TRAINER-003: ROC-AUC with perfect separation."""
        y_true = np.array([0, 0, 1, 1])
        y_scores = np.array([0.1, 0.2, 0.8, 0.9])
        auc = compute_roc_auc(y_true, y_scores)
        assert auc == 1.0

    def test_compute_roc_auc_random(self):
        """TC-COV-TRAINER-004: ROC-AUC with random scores."""
        y_true = np.array([0, 1, 0, 1])
        y_scores = np.array([0.5, 0.5, 0.5, 0.5])
        auc = compute_roc_auc(y_true, y_scores)
        assert 0.0 <= auc <= 1.0

    def test_compute_auprc_basic(self):
        """TC-COV-TRAINER-005: AUPRC basic computation."""
        y_true = np.array([0, 1, 0, 1, 1])
        y_scores = np.array([0.1, 0.9, 0.2, 0.8, 0.7])
        auprc = compute_auprc(y_true, y_scores)
        assert 0.0 <= auprc <= 1.0

    def test_compute_auprc_no_positives(self):
        """TC-COV-TRAINER-006: AUPRC with no positive labels."""
        y_true = np.array([0, 0, 0])
        y_scores = np.array([0.5, 0.6, 0.7])
        auprc = compute_auprc(y_true, y_scores)
        assert auprc == 0.0

    def test_early_stopping_init(self):
        """TC-COV-TRAINER-007: Early stopping initialization."""
        es = EarlyStopping(patience=5, min_delta=0.01)
        assert es.patience == 5
        assert es.min_delta == 0.01
        assert es.best_score is None
        assert es.early_stop is False

    def test_early_stopping_improvement(self):
        """TC-COV-TRAINER-008: Early stopping with improvement."""
        es = EarlyStopping(patience=3)
        model = PhysiologicalMLP(input_dim=3, hidden_dims=[4], use_batch_norm=False)
        assert es(0.5, model) is False
        assert es.best_score == 0.5
        assert es(0.6, model) is False
        assert es.best_score == 0.6

    def test_early_stopping_trigger(self):
        """TC-COV-TRAINER-009: Early stopping triggers after patience."""
        es = EarlyStopping(patience=2, min_delta=0.01)
        model = PhysiologicalMLP(input_dim=3, hidden_dims=[4], use_batch_norm=False)
        es(0.5, model)
        assert es(0.5, model) is False  # No improvement
        assert es(0.5, model) is True  # Patience exceeded
        assert es.early_stop is True

    def test_early_stopping_restore_weights(self):
        """TC-COV-TRAINER-010: Restore best weights."""
        es = EarlyStopping(patience=2)
        model = PhysiologicalMLP(input_dim=3, hidden_dims=[4], use_batch_norm=False)
        original_W = model.layers[0]["W"].copy()
        es(0.5, model)
        # Modify weights
        model.layers[0]["W"] += 1.0
        es.restore_best_weights(model)
        np.testing.assert_array_equal(model.layers[0]["W"], original_W)

    def test_train_epoch_basic(self):
        """TC-COV-TRAINER-011: Train for one epoch."""
        model = PhysiologicalMLP(input_dim=3, hidden_dims=[4], use_batch_norm=False)
        X_train = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0], [7.0, 8.0, 9.0]])
        y_train = np.array([[0], [1], [0]])
        loss, metrics = train_epoch(
            model,
            X_train,
            y_train,
            batch_size=2,
            learning_rate=0.01,
            weight_decay=0.0,
            loss_fn=binary_cross_entropy_loss,
        )
        assert isinstance(loss, float)
        assert "accuracy" in metrics

    def test_evaluate_basic(self):
        """TC-COV-TRAINER-012: Evaluate model."""
        model = PhysiologicalMLP(input_dim=3, hidden_dims=[4], use_batch_norm=False)
        X = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
        y = np.array([[0], [1]])
        loss, metrics = evaluate(model, X, y, binary_cross_entropy_loss)
        assert isinstance(loss, float)
        assert "accuracy" in metrics

    def test_train_model_basic(self):
        """TC-COV-TRAINER-013: Train model with early stopping."""
        model = PhysiologicalMLP(input_dim=3, hidden_dims=[4], use_batch_norm=False)
        X_train = np.random.randn(20, 3).astype(np.float32)
        y_train = np.random.randint(0, 2, size=(20, 1)).astype(np.float32)
        X_val = np.random.randn(10, 3).astype(np.float32)
        y_val = np.random.randint(0, 2, size=(10, 1)).astype(np.float32)
        history = train_model(
            model, X_train, y_train, X_val, y_val, epochs=5, batch_size=5, patience=2
        )
        assert "train_loss" in history
        assert "val_loss" in history
        assert "best_epoch" in history
        assert len(history["train_loss"]) <= 5

    def test_binary_cross_entropy_loss(self):
        """TC-COV-LOSS-001: Binary cross-entropy loss computation."""
        y_pred = np.array([[0.9], [0.1]])
        y_true = np.array([[1], [0]])
        loss, grad = binary_cross_entropy_loss(y_pred, y_true)
        assert isinstance(loss, float)
        assert loss > 0
        assert grad.shape == y_pred.shape

    def test_focal_loss(self):
        """TC-COV-LOSS-002: Focal loss computation."""
        y_pred = np.array([[0.9], [0.1]])
        y_true = np.array([[1], [0]])
        loss, grad = focal_loss(y_pred, y_true)
        assert isinstance(loss, float)
        assert loss > 0
        assert grad.shape == y_pred.shape

    def test_compute_class_weights(self):
        """TC-COV-LOSS-003: Compute class weights."""
        y = np.array([0, 0, 1, 1, 1])
        weights = compute_class_weights(y)
        assert 0 in weights
        assert 1 in weights
        assert weights[0] > weights[1]  # Fewer 0s, so weight for 0 is higher

    def test_sgd_optimizer_updates_weights(self):
        """TC-COV-TRAINER-014: SGD optimizer updates weights."""
        model = PhysiologicalMLP(input_dim=3, hidden_dims=[4], use_batch_norm=False)
        original_W = model.layers[0]["W"].copy()
        X = np.array([[1.0, 2.0, 3.0]])
        y = np.array([[1]])
        output, caches = model.forward(X)
        loss, grad = binary_cross_entropy_loss(output, y)
        sgd_optimizer(model, caches, grad, learning_rate=0.1, weight_decay=0.01)
        assert not np.array_equal(model.layers[0]["W"], original_W)


class TestScalerFunctions:
    """Test scaler utility functions."""

    def test_fit_scaler(self):
        """TC-COV-SCALER-001: fit_scaler returns fitted scaler."""
        import pandas as pd

        X = pd.DataFrame([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]], columns=["a", "b"])
        scaler = fit_scaler(X)
        assert scaler.mean_ is not None
        assert scaler.scale_ is not None
        assert scaler.n_features_in_ == 2

    def test_save_and_load_scaler(self):
        """TC-COV-SCALER-002: save_scaler and load_scaler roundtrip."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "scaler.json"
            scaler = SimpleStandardScaler()
            X = np.array([[1.0, 2.0], [3.0, 4.0]])
            scaler.fit(X)
            save_scaler(scaler, path)
            assert path.exists()
            loaded = load_scaler(path)
            np.testing.assert_array_equal(loaded.mean_, scaler.mean_)
            np.testing.assert_array_equal(loaded.scale_, scaler.scale_)

    def test_load_scaler_not_found(self):
        """TC-COV-SCALER-003: load_scaler raises FileNotFoundError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nonexistent.json"
            with pytest.raises(FileNotFoundError):
                load_scaler(path)

    def test_save_and_load_feature_names(self):
        """TC-COV-SCALER-004: save_feature_names and load_feature_names roundtrip."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "features.json"
            names = ["feat1", "feat2", "feat3"]
            save_feature_names(names, path)
            assert path.exists()
            loaded = load_feature_names(path)
            assert loaded == names

    def test_load_feature_names_not_found(self):
        """TC-COV-SCALER-005: load_feature_names raises FileNotFoundError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nonexistent.json"
            with pytest.raises(FileNotFoundError):
                load_feature_names(path)

    def test_scale_features_with_scaler(self):
        """TC-COV-SCALER-006: scale_features with provided scaler."""
        import pandas as pd

        X = pd.DataFrame([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]], columns=["a", "b"])
        scaler = fit_scaler(X)
        X_scaled = scale_features(X, scaler)
        assert isinstance(X_scaled, np.ndarray)
        assert X_scaled.shape == (3, 2)

    def test_scale_features_without_scaler(self):
        """TC-COV-SCALER-007: scale_features without scaler fits new one."""
        import pandas as pd

        X = pd.DataFrame([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]], columns=["a", "b"])
        X_scaled = scale_features(X)
        assert isinstance(X_scaled, np.ndarray)
        assert X_scaled.shape == (3, 2)


class TestModelLoaderFunctions:
    """Test model loader utility functions."""

    def test_load_model_not_found(self):
        """TC-COV-LOADER-001: load_model raises FileNotFoundError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nonexistent.json"
            with pytest.raises(FileNotFoundError):
                load_model(path)

    def test_load_model_success(self):
        """TC-COV-LOADER-002: load_model loads model correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "model.json"
            model = PhysiologicalMLP(input_dim=3, hidden_dims=[4], use_batch_norm=False)
            model.save(path)
            loaded = load_model(path)
            assert loaded.input_dim == model.input_dim
            assert loaded.hidden_dims == model.hidden_dims

    def test_load_metrics_not_found(self):
        """TC-COV-LOADER-003: load_metrics raises FileNotFoundError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "nonexistent.json"
            with pytest.raises(FileNotFoundError):
                load_metrics(path)

    def test_load_metrics_success(self):
        """TC-COV-LOADER-004: load_metrics loads metrics correctly."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "metrics.json"
            metrics_data = {"accuracy": 0.95, "f1": 0.94}
            with open(path, "w", encoding="utf-8") as f:
                json.dump(metrics_data, f)
            # Phase 1 C-ML-2: load_metrics 强制要求 .sha256 校验文件
            write_sha256_sidecar(path)
            loaded = load_metrics(path)
            assert loaded == metrics_data

    def test_load_all_artifacts_success(self):
        """TC-COV-LOADER-005: load_all_artifacts loads all artifacts."""
        with tempfile.TemporaryDirectory() as tmpdir:
            model_path = Path(tmpdir) / "model.json"
            scaler_path = Path(tmpdir) / "scaler.json"
            feature_path = Path(tmpdir) / "feature_names.json"
            metrics_path = Path(tmpdir) / "metrics.json"

            model = PhysiologicalMLP(input_dim=2, hidden_dims=[3], use_batch_norm=False)
            model.save(model_path)

            scaler = SimpleStandardScaler()
            scaler.fit(np.array([[1.0, 2.0], [3.0, 4.0]]))
            scaler.save(scaler_path)

            feature_names = ["feat1", "feat2"]
            with open(feature_path, "w", encoding="utf-8") as f:
                json.dump(feature_names, f)
            # Phase 1 C-ML-2: feature_names 文件需 .sha256 校验
            write_sha256_sidecar(feature_path)

            metrics_data = {"accuracy": 0.95}
            with open(metrics_path, "w", encoding="utf-8") as f:
                json.dump(metrics_data, f)
            # Phase 1 C-ML-2: metrics 文件需 .sha256 校验
            write_sha256_sidecar(metrics_path)

            from app.ml import model_loader as ml

            orig_model_path = ml.MODEL_PATH
            orig_scaler_path = ml.SCALER_PATH
            orig_feature_path = ml.FEATURE_NAMES_PATH
            orig_metrics_path = ml.METRICS_PATH
            try:
                ml.MODEL_PATH = model_path
                ml.SCALER_PATH = scaler_path
                ml.FEATURE_NAMES_PATH = feature_path
                ml.METRICS_PATH = metrics_path
                loaded_model, loaded_scaler, loaded_features, loaded_metrics = (
                    load_all_artifacts()
                )
                assert loaded_model.input_dim == 2
                assert loaded_scaler.n_features_in_ == 2
                assert loaded_features == feature_names
                assert loaded_metrics == metrics_data
            finally:
                ml.MODEL_PATH = orig_model_path
                ml.SCALER_PATH = orig_scaler_path
                ml.FEATURE_NAMES_PATH = orig_feature_path
                ml.METRICS_PATH = orig_metrics_path

    def test_load_all_artifacts_missing(self):
        """TC-COV-LOADER-006: load_all_artifacts raises FileNotFoundError."""
        with tempfile.TemporaryDirectory() as tmpdir:
            from app.ml import model_loader as ml

            orig_model_path = ml.MODEL_PATH
            orig_scaler_path = ml.SCALER_PATH
            orig_feature_path = ml.FEATURE_NAMES_PATH
            orig_metrics_path = ml.METRICS_PATH
            try:
                ml.MODEL_PATH = Path(tmpdir) / "model.json"
                ml.SCALER_PATH = Path(tmpdir) / "scaler.json"
                ml.FEATURE_NAMES_PATH = Path(tmpdir) / "feature_names.json"
                ml.METRICS_PATH = Path(tmpdir) / "metrics.json"
                with pytest.raises(FileNotFoundError):
                    load_all_artifacts()
            finally:
                ml.MODEL_PATH = orig_model_path
                ml.SCALER_PATH = orig_scaler_path
                ml.FEATURE_NAMES_PATH = orig_feature_path
                ml.METRICS_PATH = orig_metrics_path


class TestModelCoverageExtras:
    """Additional tests for model.py coverage gaps."""

    def test_he_init_multidim(self):
        """TC-COV-ML-034: He init with multi-dimensional shape."""
        shape = (10, 5, 3)
        result = he_init(shape)
        assert result.shape == shape
        fan_in = np.prod(shape[1:])
        std = np.sqrt(2.0 / fan_in)
        assert np.std(result) < std * 3

    def test_dropout_eval_mode(self):
        """TC-COV-ML-035: Dropout disabled in eval mode."""
        model = PhysiologicalMLP(input_dim=3, hidden_dims=[4], use_batch_norm=False)
        model.training = False
        X = np.array([[1.0, 2.0, 3.0]])
        output, caches = model.forward(X)
        assert output.shape == (1, 1)
        for cache in caches[:-1]:
            if "dropout_mask" in cache:
                np.testing.assert_array_equal(
                    cache["dropout_mask"], np.ones_like(cache["dropout_mask"])
                )

    def test_dropout_zero_rate(self):
        """TC-COV-ML-036: Dropout with zero rate."""
        model = PhysiologicalMLP(
            input_dim=3, hidden_dims=[4], dropout_rate=0.0, use_batch_norm=False
        )
        X = np.array([[1.0, 2.0, 3.0]])
        output, caches = model.forward(X)
        assert output.shape == (1, 1)

    def test_batch_norm_eval_mode(self):
        """TC-COV-ML-037: BatchNorm uses running stats in eval mode."""
        model = PhysiologicalMLP(input_dim=3, hidden_dims=[4], use_batch_norm=True)
        X = np.array([[1.0, 2.0, 3.0]])
        model.training = True
        output1, _ = model.forward(X)
        model.training = False
        output2, _ = model.forward(X)
        assert output1.shape == output2.shape

    def test_forward_single_layer(self):
        """TC-COV-ML-038: Forward with single layer (no hidden)."""
        model = PhysiologicalMLP(input_dim=3, hidden_dims=[], use_batch_norm=False)
        X = np.array([[1.0, 2.0, 3.0]])
        output, caches = model.forward(X)
        assert output.shape == (1, 1)
        assert len(caches) == 1

    def test_save_load_no_batch_norm(self):
        """TC-COV-ML-039: Save/load without batch norm params."""
        with tempfile.TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "model.json"
            model = PhysiologicalMLP(input_dim=3, hidden_dims=[4], use_batch_norm=False)
            model.save(path)
            loaded = PhysiologicalMLP.load(path)
            assert loaded.use_batch_norm is False
            assert "bn_gamma" not in loaded.layers[0]


class TestTrainerCoverageExtras:
    """Additional tests for trainer.py coverage gaps."""

    def test_compute_metrics_zero_division(self):
        """TC-COV-TRAINER-015: Metrics with zero division cases."""
        y_true = np.array([[0], [0], [0]])
        y_pred = np.array([[0.1], [0.2], [0.3]])
        metrics = compute_metrics(y_true, y_pred)
        assert metrics["precision"] == 0.0
        assert metrics["recall"] == 0.0
        assert metrics["f1"] == 0.0

    def test_compute_metrics_all_positive(self):
        """TC-COV-TRAINER-016: Metrics with all positive labels."""
        y_true = np.array([[1], [1], [1]])
        y_pred = np.array([[0.9], [0.8], [0.7]])
        metrics = compute_metrics(y_true, y_pred)
        assert metrics["recall"] == 1.0

    def test_sgd_optimizer_dropout_mask_mismatch(self):
        """TC-COV-TRAINER-017: SGD with dropout mask shape mismatch."""
        model = PhysiologicalMLP(input_dim=3, hidden_dims=[4, 2], use_batch_norm=False)
        X = np.array([[1.0, 2.0, 3.0]])
        y = np.array([[1]])
        output, caches = model.forward(X)
        loss, grad = binary_cross_entropy_loss(output, y)
        sgd_optimizer(model, caches, grad, learning_rate=0.1, weight_decay=0.01)
        assert True

    def test_train_model_overfitting_detection(self):
        """TC-COV-TRAINER-018: Train model overfitting detection."""
        model = PhysiologicalMLP(input_dim=2, hidden_dims=[8, 4], use_batch_norm=False)
        np.random.seed(42)
        X_train = np.random.randn(50, 2).astype(np.float32)
        y_train = np.random.randint(0, 2, size=(50, 1)).astype(np.float32)
        X_val = np.random.randn(10, 2).astype(np.float32)
        y_val = np.random.randint(0, 2, size=(10, 1)).astype(np.float32)
        history = train_model(
            model, X_train, y_train, X_val, y_val, epochs=10, batch_size=5, patience=5
        )
        assert "overfitting_detected" in history
        assert "overfitting_epoch" in history

    def test_early_stopping_no_improvement(self):
        """TC-COV-TRAINER-019: Early stopping with no improvement."""
        es = EarlyStopping(patience=2, min_delta=0.1)
        model = PhysiologicalMLP(input_dim=3, hidden_dims=[4], use_batch_norm=False)
        es(0.5, model)
        assert es(0.4, model) is False
        assert es(0.35, model) is True

    def test_evaluate_with_batch_norm(self):
        """TC-COV-TRAINER-020: Evaluate with batch norm enabled."""
        model = PhysiologicalMLP(input_dim=3, hidden_dims=[4], use_batch_norm=True)
        X = np.array([[1.0, 2.0, 3.0], [4.0, 5.0, 6.0]])
        y = np.array([[0], [1]])
        loss, metrics = evaluate(model, X, y, binary_cross_entropy_loss)
        assert isinstance(loss, float)
        assert "accuracy" in metrics
