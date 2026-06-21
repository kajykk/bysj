"""Tests for ML utility modules: data_split, dataset, evaluation."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.ml.data_split import stratified_split, verify_split_integrity
from app.ml.dataset import PhysiologicalDataset
from app.ml.evaluation import compute_confusion_matrix, compute_roc_curve


class TestDataSplit:
    """Test data split functions."""

    def test_stratified_split_basic(self):
        """TC-COV-SPLIT-001: Basic stratified split."""
        X = np.random.randn(100, 5)
        y = np.array([0] * 50 + [1] * 50)
        X_train, X_val, X_test, y_train, y_val, y_test = stratified_split(X, y)
        assert len(X_train) + len(X_val) + len(X_test) == 100
        assert len(y_train) + len(y_val) + len(y_test) == 100

    def test_stratified_split_ratios(self):
        """TC-COV-SPLIT-002: Custom ratios."""
        X = np.random.randn(100, 5)
        y = np.array([0] * 50 + [1] * 50)
        X_train, X_val, X_test, y_train, y_val, y_test = stratified_split(
            X, y, train_ratio=0.6, val_ratio=0.2, test_ratio=0.2
        )
        assert len(X_train) == 60
        assert len(X_val) == 20
        assert len(X_test) == 20

    def test_stratified_split_invalid_ratios(self):
        """TC-COV-SPLIT-003: Invalid ratios raise ValueError."""
        X = np.random.randn(10, 2)
        y = np.array([0] * 5 + [1] * 5)
        with pytest.raises(ValueError, match="Ratios must sum to 1.0"):
            stratified_split(X, y, train_ratio=0.5, val_ratio=0.5, test_ratio=0.5)

    def test_stratified_split_reproducibility(self):
        """TC-COV-SPLIT-004: Same random_state gives same split."""
        X = np.random.randn(50, 3)
        y = np.array([0] * 25 + [1] * 25)
        result1 = stratified_split(X, y, random_state=42)
        result2 = stratified_split(X, y, random_state=42)
        for a, b in zip(result1, result2):
            np.testing.assert_array_equal(a, b)

    def test_verify_split_integrity(self):
        """TC-COV-SPLIT-005: Verify split integrity."""
        X = np.random.randn(30, 2)
        y = np.array([0] * 15 + [1] * 15)
        splits = stratified_split(X, y, train_ratio=0.6, val_ratio=0.2, test_ratio=0.2)
        assert verify_split_integrity(X, y, *splits) is True


class TestDataset:
    """Test PhysiologicalDataset."""

    def test_init(self):
        """TC-COV-DATASET-001: Basic initialization."""
        X = np.array([[1.0, 2.0], [3.0, 4.0], [5.0, 6.0]])
        y = np.array([0, 1, 0])
        ds = PhysiologicalDataset(X, y)
        assert ds.n_samples == 3
        assert ds.n_features == 2

    def test_init_mismatched_length(self):
        """TC-COV-DATASET-002: Mismatched X/y raises ValueError."""
        X = np.array([[1.0, 2.0], [3.0, 4.0]])
        y = np.array([0, 1, 0])
        with pytest.raises(ValueError, match="X and y must have same length"):
            PhysiologicalDataset(X, y)

    def test_len(self):
        """TC-COV-DATASET-003: len returns sample count."""
        X = np.random.randn(10, 3)
        y = np.random.randint(0, 2, size=10)
        ds = PhysiologicalDataset(X, y)
        assert len(ds) == 10

    def test_getitem(self):
        """TC-COV-DATASET-004: Get item by index."""
        X = np.array([[1.0, 2.0], [3.0, 4.0]])
        y = np.array([0, 1])
        ds = PhysiologicalDataset(X, y)
        x_i, y_i = ds[0]
        np.testing.assert_array_equal(x_i, np.array([1.0, 2.0]))
        assert y_i == 0

    def test_get_class_distribution(self):
        """TC-COV-DATASET-005: Class distribution."""
        X = np.random.randn(10, 2)
        y = np.array([0] * 7 + [1] * 3)
        ds = PhysiologicalDataset(X, y)
        dist = ds.get_class_distribution()
        assert dist[0] == 7
        assert dist[1] == 3

    def test_get_batch(self):
        """TC-COV-DATASET-006: Get batch."""
        X = np.random.randn(10, 3)
        y = np.random.randint(0, 2, size=10)
        ds = PhysiologicalDataset(X, y)
        X_batch, y_batch = ds.get_batch([0, 2, 4])
        assert X_batch.shape == (3, 3)
        assert y_batch.shape == (3,)


class TestDataset:
    """Test dataset and dataloader."""

    def test_simple_dataloader_init(self):
        """TC-COV-DATASET-007: SimpleDataLoader initialization."""
        from app.ml.dataset import SimpleDataLoader
        X = np.random.randn(20, 3)
        y = np.random.randint(0, 2, size=20)
        ds = PhysiologicalDataset(X, y)
        loader = SimpleDataLoader(ds, batch_size=5, shuffle=False)
        assert len(loader) == 4

    def test_simple_dataloader_iteration(self):
        """TC-COV-DATASET-008: SimpleDataLoader iteration."""
        from app.ml.dataset import SimpleDataLoader
        X = np.random.randn(10, 2)
        y = np.random.randint(0, 2, size=10)
        ds = PhysiologicalDataset(X, y)
        loader = SimpleDataLoader(ds, batch_size=3, shuffle=False)
        batches = list(loader)
        assert len(batches) == 4  # 3+3+3+1
        assert batches[0][0].shape == (3, 2)
        assert batches[-1][0].shape == (1, 2)

    def test_simple_dataloader_shuffle(self):
        """TC-COV-DATASET-009: SimpleDataLoader shuffling."""
        from app.ml.dataset import SimpleDataLoader
        X = np.random.randn(10, 2)
        y = np.random.randint(0, 2, size=10)
        ds = PhysiologicalDataset(X, y)
        loader1 = SimpleDataLoader(ds, batch_size=10, shuffle=True, random_state=42)
        loader2 = SimpleDataLoader(ds, batch_size=10, shuffle=True, random_state=42)
        batch1 = next(iter(loader1))
        batch2 = next(iter(loader2))
        np.testing.assert_array_equal(batch1[0], batch2[0])

    def test_create_dataloaders(self):
        """TC-COV-DATASET-010: create_dataloaders."""
        from app.ml.dataset import create_dataloaders
        X_train = np.random.randn(30, 3)
        X_val = np.random.randn(10, 3)
        X_test = np.random.randn(10, 3)
        y_train = np.random.randint(0, 2, size=30)
        y_val = np.random.randint(0, 2, size=10)
        y_test = np.random.randint(0, 2, size=10)
        train_loader, val_loader, test_loader = create_dataloaders(
            X_train, X_val, X_test, y_train, y_val, y_test, batch_size=5
        )
        assert len(train_loader) == 6
        assert len(val_loader) == 2
        assert len(test_loader) == 2


class TestDataCleaner:
    """Test data cleaning functions."""

    def test_handle_all_nan_columns(self):
        """TC-COV-CLEANER-001: Handle all-NaN columns."""
        from app.ml.data_cleaner import handle_all_nan_columns
        df = pd.DataFrame({
            "a": [1.0, 2.0, 3.0],
            "b": [np.nan, np.nan, np.nan],
            "c": [4.0, np.nan, 6.0],
        })
        result, dropped = handle_all_nan_columns(df)
        assert "b" not in result.columns
        assert "b" in dropped
        assert "a" in result.columns

    def test_handle_missing_values(self):
        """TC-COV-CLEANER-002: Fill missing values."""
        from app.ml.data_cleaner import handle_missing_values
        df = pd.DataFrame({
            "a": [1.0, np.nan, 3.0],
            "b": [4.0, 5.0, 6.0],
        })
        result = handle_missing_values(df)
        assert not result["a"].isnull().any()
        assert result["a"].iloc[1] == 2.0  # median

    def test_drop_high_missing_samples(self):
        """TC-COV-CLEANER-003: Drop high-missing samples."""
        from app.ml.data_cleaner import drop_high_missing_samples
        df = pd.DataFrame({
            "feat1": [1.0, np.nan, 3.0, np.nan],
            "feat2": [4.0, np.nan, 6.0, np.nan],
            "depression_label": [0, 1, 0, 1],
        })
        result = drop_high_missing_samples(df, threshold=0.3)
        assert len(result) == 2

    def test_clip_extreme_values(self):
        """TC-COV-CLEANER-004: Clip extreme values."""
        from app.ml.data_cleaner import clip_extreme_values
        df = pd.DataFrame({
            "heart_rate": [30, 100, 250],
            "sleep_hours": [-1, 6, 15],
        })
        result = clip_extreme_values(df)
        assert result["heart_rate"].max() == 200
        assert result["heart_rate"].min() == 30
        assert result["sleep_hours"].max() == 12
        assert result["sleep_hours"].min() == 0

    def test_winsorize_features(self):
        """TC-COV-CLEANER-005: Winsorize features."""
        from app.ml.data_cleaner import winsorize_features
        df = pd.DataFrame({
            "feat1": list(range(100)) + [1000],
            "depression_label": [0] * 101,
        })
        result = winsorize_features(df)
        assert result["feat1"].max() < 1000

    def test_clean_dataset_pipeline(self):
        """TC-COV-CLEANER-006: Full cleaning pipeline."""
        from app.ml.data_cleaner import clean_dataset
        df = pd.DataFrame({
            "heart_rate": [30.0, 100.0, np.nan, 250.0],
            "sleep_hours": [6.0, np.nan, 8.0, 15.0],
            "depression_label": [0, 1, 0, 1],
        })
        result = clean_dataset(df)
        assert not result.isnull().any().any()
        assert len(result) <= 4


class TestFeatureEngineering:
    """Test feature engineering functions."""

    def test_compute_sleep_efficiency(self):
        """TC-COV-FE-001: Compute sleep efficiency."""
        from app.ml.feature_engineering import compute_sleep_efficiency
        df = pd.DataFrame({"sleep_hours": [6.0, 8.0], "sleep_quality": [6.0, 8.0]})
        result = compute_sleep_efficiency(df)
        assert "sleep_efficiency" in result.columns
        assert abs(result["sleep_efficiency"].iloc[0] - 1.0) < 0.001

    def test_compute_activity_intensity(self):
        """TC-COV-FE-002: Compute activity intensity."""
        from app.ml.feature_engineering import compute_activity_intensity
        df = pd.DataFrame({"steps": [1000, 5000], "exercise_minutes": [0, 30]})
        result = compute_activity_intensity(df)
        assert "activity_intensity" in result.columns
        assert result["activity_intensity"].iloc[0] == 1000

    def test_compute_cardiovascular_risk(self):
        """TC-COV-FE-003: Compute cardiovascular risk."""
        from app.ml.feature_engineering import compute_cardiovascular_risk
        df = pd.DataFrame({"systolic_bp": [120, 140], "diastolic_bp": [80, 90]})
        result = compute_cardiovascular_risk(df)
        assert "cardiovascular_risk" in result.columns

    def test_compute_hr_sleep_interaction(self):
        """TC-COV-FE-004: Compute HR sleep interaction."""
        from app.ml.feature_engineering import compute_hr_sleep_interaction
        df = pd.DataFrame({"heart_rate": [70, 80], "sleep_hours": [6, 8]})
        result = compute_hr_sleep_interaction(df)
        assert "hr_sleep_interaction" in result.columns
        assert result["hr_sleep_interaction"].iloc[0] == 70 * 4

    def test_compute_overall_activity(self):
        """TC-COV-FE-005: Compute overall activity."""
        from app.ml.feature_engineering import compute_overall_activity
        df = pd.DataFrame({"steps": [1000, 5000], "exercise_minutes": [10, 30]})
        result = compute_overall_activity(df)
        assert "overall_activity" in result.columns
        assert result["overall_activity"].iloc[0] == 10000

    def test_compute_bp_category(self):
        """TC-COV-FE-006: Compute BP category."""
        from app.ml.feature_engineering import compute_bp_category
        df = pd.DataFrame({"systolic_bp": [110, 130, 150], "diastolic_bp": [70, 85, 95]})
        result = compute_bp_category(df)
        assert "bp_category" in result.columns
        assert result["bp_category"].tolist() == [0, 1, 2]

    def test_engineer_features(self):
        """TC-COV-FE-007: Full feature engineering pipeline."""
        from app.ml.feature_engineering import engineer_features, ALL_FEATURES
        df = pd.DataFrame({
            "sleep_hours": [6.0, 8.0],
            "sleep_quality": [6.0, 8.0],
            "exercise_minutes": [30, 45],
            "heart_rate": [70, 75],
            "systolic_bp": [120, 130],
            "diastolic_bp": [80, 85],
            "steps": [5000, 8000],
        })
        result = engineer_features(df)
        for feat in ALL_FEATURES:
            assert feat in result.columns

    def test_get_feature_matrix(self):
        """TC-COV-FE-008: Get feature matrix."""
        from app.ml.feature_engineering import get_feature_matrix, ALL_FEATURES
        df = pd.DataFrame({
            "sleep_hours": [6.0],
            "sleep_quality": [6.0],
            "exercise_minutes": [30],
            "heart_rate": [70],
            "systolic_bp": [120],
            "diastolic_bp": [80],
            "steps": [5000],
            "sleep_efficiency": [1.0],
            "activity_intensity": [166.7],
            "cardiovascular_risk": [1.5],
            "hr_sleep_interaction": [280.0],
            "overall_activity": [150000.0],
            "bp_category": [0],
            "depression_label": [0],
        })
        X = get_feature_matrix(df)
        assert list(X.columns) == ALL_FEATURES

    def test_get_target_vector(self):
        """TC-COV-FE-009: Get target vector."""
        from app.ml.feature_engineering import get_target_vector
        df = pd.DataFrame({"depression_label": [0, 1, 0]})
        y = get_target_vector(df)
        assert y.tolist() == [0, 1, 0]


class TestStatisticalTests:
    """Test statistical tests."""

    def test_bootstrap_ci(self):
        """TC-COV-STAT-001: Bootstrap confidence interval."""
        from app.ml.statistical_tests import bootstrap_ci, compute_accuracy
        y_true = np.array([0, 0, 1, 1, 0, 1])
        y_pred = np.array([0.1, 0.2, 0.8, 0.9, 0.3, 0.7])
        result = bootstrap_ci(y_true, y_pred, compute_accuracy, n_bootstrap=100, random_state=42)
        assert "metric" in result
        assert "ci_lower" in result
        assert "ci_upper" in result
        assert result["confidence"] == 0.95

    def test_mcnemar_test(self):
        """TC-COV-STAT-002: McNemar test."""
        from app.ml.statistical_tests import mcnemar_test
        y_true = np.array([0, 0, 1, 1, 0, 1])
        y_pred1 = np.array([0, 1, 1, 1, 0, 0])
        y_pred2 = np.array([0, 0, 1, 1, 1, 1])
        result = mcnemar_test(y_true, y_pred1, y_pred2)
        assert "statistic" in result
        assert "p_value" in result
        assert "significant" in result

    def test_mcnemar_test_no_difference(self):
        """TC-COV-STAT-003: McNemar test with identical predictions."""
        from app.ml.statistical_tests import mcnemar_test
        y_true = np.array([0, 0, 1, 1])
        y_pred = np.array([0, 0, 1, 1])
        result = mcnemar_test(y_true, y_pred, y_pred)
        assert result["b"] == 0
        assert result["c"] == 0
        assert result["p_value"] == 1.0

    def test_bonferroni_correction(self):
        """TC-COV-STAT-004: Bonferroni correction."""
        from app.ml.statistical_tests import bonferroni_correction
        p_values = [0.01, 0.04, 0.1, 0.2]
        result = bonferroni_correction(p_values, alpha=0.05)
        assert result["n_tests"] == 4
        assert result["corrected_alpha"] == 0.0125
        assert result["significant"] == [True, False, False, False]

    def test_compute_f1(self):
        """TC-COV-STAT-005: Compute F1 helper."""
        from app.ml.statistical_tests import compute_f1
        y_true = np.array([0, 0, 1, 1])
        y_pred = np.array([0.1, 0.2, 0.8, 0.9])
        f1 = compute_f1(y_true, y_pred)
        assert f1 == 1.0

    def test_compute_accuracy(self):
        """TC-COV-STAT-006: Compute accuracy helper."""
        from app.ml.statistical_tests import compute_accuracy
        y_true = np.array([0, 0, 1, 1])
        y_pred = np.array([0.1, 0.2, 0.8, 0.9])
        acc = compute_accuracy(y_true, y_pred)
        assert acc == 1.0


class TestSmote:
    """Test SMOTE functions."""

    def test_simple_smote_basic(self):
        """TC-COV-SMOTE-001: Basic SMOTE application."""
        from app.ml.smote import simple_smote
        X = np.random.randn(20, 3)
        y = np.array([0] * 15 + [1] * 5)
        X_res, y_res = simple_smote(X, y, sampling_strategy=0.5, k_neighbors=3)
        assert len(X_res) > len(X)
        assert np.sum(y_res == 1) == int(15 * 0.5)

    def test_simple_smote_no_change(self):
        """TC-COV-SMOTE-002: SMOTE when already balanced."""
        from app.ml.smote import simple_smote
        X = np.random.randn(20, 3)
        y = np.array([0] * 10 + [1] * 10)
        X_res, y_res = simple_smote(X, y, sampling_strategy=0.5)
        assert len(X_res) == len(X)

    def test_simple_smote_single_minority(self):
        """TC-COV-SMOTE-003: SMOTE with very few minority samples."""
        from app.ml.smote import simple_smote
        X = np.random.randn(10, 2)
        y = np.array([0] * 9 + [1])
        X_res, y_res = simple_smote(X, y, sampling_strategy=0.5, k_neighbors=1)
        assert len(X_res) >= len(X)

    def test_apply_smote_if_needed_imbalanced(self):
        """TC-COV-SMOTE-004: Apply SMOTE when imbalanced."""
        from app.ml.smote import apply_smote_if_needed
        X = np.random.randn(20, 3)
        y = np.array([0] * 15 + [1] * 5)
        X_res, y_res = apply_smote_if_needed(X, y, min_imbalance_ratio=0.8)
        assert len(X_res) > len(X)

    def test_apply_smote_if_needed_balanced(self):
        """TC-COV-SMOTE-005: Skip SMOTE when balanced."""
        from app.ml.smote import apply_smote_if_needed
        X = np.random.randn(20, 3)
        y = np.array([0] * 10 + [1] * 10)
        X_res, y_res = apply_smote_if_needed(X, y, min_imbalance_ratio=0.8)
        assert len(X_res) == len(X)

    def test_apply_smote_if_needed_single_class(self):
        """TC-COV-SMOTE-006: Skip SMOTE with single class."""
        from app.ml.smote import apply_smote_if_needed
        X = np.random.randn(10, 2)
        y = np.array([0] * 10)
        X_res, y_res = apply_smote_if_needed(X, y)
        assert len(X_res) == len(X)


class TestEvaluation:
    """Test evaluation functions."""

    def test_compute_confusion_matrix(self):
        """TC-COV-EVAL-001: Confusion matrix computation."""
        y_true = np.array([[1], [0], [1], [0], [1]])
        y_pred = np.array([[0.8], [0.2], [0.7], [0.6], [0.9]])
        cm = compute_confusion_matrix(y_true, y_pred)
        assert cm["tp"] == 3
        assert cm["tn"] == 1
        assert cm["fp"] == 1
        assert cm["fn"] == 0
        assert cm["total"] == 5

    def test_compute_confusion_matrix_all_correct(self):
        """TC-COV-EVAL-002: All correct predictions."""
        y_true = np.array([[1], [0], [1], [0]])
        y_pred = np.array([[0.9], [0.1], [0.8], [0.2]])
        cm = compute_confusion_matrix(y_true, y_pred)
        assert cm["tp"] == 2
        assert cm["tn"] == 2
        assert cm["fp"] == 0
        assert cm["fn"] == 0

    def test_compute_roc_curve(self):
        """TC-COV-EVAL-003: ROC curve computation."""
        y_true = np.array([0, 0, 1, 1])
        y_scores = np.array([0.1, 0.2, 0.8, 0.9])
        roc = compute_roc_curve(y_true, y_scores)
        assert "fpr" in roc
        assert "tpr" in roc
        assert "auc" in roc
        assert 0.0 <= roc["auc"] <= 1.0

    def test_compute_roc_curve_no_positives(self):
        """TC-COV-EVAL-004: ROC with no positives."""
        y_true = np.array([0, 0, 0])
        y_scores = np.array([0.1, 0.2, 0.3])
        roc = compute_roc_curve(y_true, y_scores)
        assert roc["auc"] == 0.5

    def test_compute_roc_curve_no_negatives(self):
        """TC-COV-EVAL-005: ROC with no negatives."""
        y_true = np.array([1, 1, 1])
        y_scores = np.array([0.1, 0.2, 0.3])
        roc = compute_roc_curve(y_true, y_scores)
        assert roc["auc"] == 0.5

    def test_compute_calibration_curve(self):
        """TC-COV-EVAL-006: Calibration curve computation."""
        from app.ml.evaluation import compute_calibration_curve
        y_true = np.array([0, 0, 1, 1, 0, 1, 0, 1])
        y_scores = np.array([0.1, 0.2, 0.8, 0.9, 0.3, 0.7, 0.15, 0.85])
        cal = compute_calibration_curve(y_true, y_scores, n_bins=5)
        assert "bin_centers" in cal
        assert "bin_accuracies" in cal
        assert "expected_calibration_error" in cal
        assert len(cal["bin_centers"]) == 5

    def test_compute_shap_values(self):
        """TC-COV-EVAL-007: SHAP values approximation."""
        from app.ml.evaluation import compute_shap_values_approximation
        X = np.random.randn(20, 3)
        feature_names = ["a", "b", "c"]

        def mock_predict(X):
            return np.mean(X, axis=1)

        result = compute_shap_values_approximation(X, feature_names, mock_predict)
        assert "feature_importances" in result
        assert "sorted_features" in result
        assert len(result["sorted_features"]) == 3

    def test_generate_evaluation_report(self):
        """TC-COV-EVAL-008: Full evaluation report."""
        from app.ml.evaluation import generate_evaluation_report
        y_true = np.array([0, 0, 1, 1])
        y_pred = np.array([0.1, 0.2, 0.8, 0.9])
        report = generate_evaluation_report(y_true, y_pred)
        assert "confusion_matrix" in report
        assert "roc_curve" in report
        assert "calibration_curve" in report

    def test_generate_evaluation_report_with_shap(self):
        """TC-COV-EVAL-009: Evaluation report with SHAP."""
        from app.ml.evaluation import generate_evaluation_report
        y_true = np.array([0, 0, 1, 1])
        y_pred = np.array([0.1, 0.2, 0.8, 0.9])
        X = np.array([[0.1, 0.2], [0.3, 0.4], [0.5, 0.6], [0.7, 0.8]])

        def mock_predict(X):
            return np.mean(X, axis=1)

        report = generate_evaluation_report(
            y_true, y_pred, feature_names=["a", "b"], model_predict_fn=mock_predict, X=X
        )
        assert "shap_values" in report
