"""Tests for feature_engineering module."""

from __future__ import annotations

import pandas as pd

from app.ml.feature_engineering import (
    ALL_FEATURES,
    compute_activity_intensity,
    compute_bp_category,
    compute_cardiovascular_risk,
    compute_hr_sleep_interaction,
    compute_overall_activity,
    compute_sleep_efficiency,
    engineer_features,
    get_feature_matrix,
    get_target_vector,
)


class TestComputeSleepEfficiency:
    """Test compute_sleep_efficiency."""

    def test_basic(self):
        """TC-COV-ML-020: Computes sleep efficiency."""
        df = pd.DataFrame({"sleep_hours": [7.0], "sleep_quality": [3.5]})
        result = compute_sleep_efficiency(df)
        assert "sleep_efficiency" in result.columns
        assert result["sleep_efficiency"].iloc[0] > 0

    def test_division_by_zero(self):
        """TC-COV-ML-021: Handles division by zero."""
        df = pd.DataFrame({"sleep_hours": [0.0], "sleep_quality": [3.5]})
        result = compute_sleep_efficiency(df)
        assert result["sleep_efficiency"].iloc[0] >= 0


class TestComputeActivityIntensity:
    """Test compute_activity_intensity."""

    def test_basic(self):
        """TC-COV-ML-022: Computes activity intensity."""
        df = pd.DataFrame({"steps": [5000], "exercise_minutes": [30]})
        result = compute_activity_intensity(df)
        assert "activity_intensity" in result.columns
        assert result["activity_intensity"].iloc[0] > 0

    def test_zero_exercise(self):
        """TC-COV-ML-023: Handles zero exercise minutes."""
        df = pd.DataFrame({"steps": [5000], "exercise_minutes": [0]})
        result = compute_activity_intensity(df)
        assert result["activity_intensity"].iloc[0] == 5000


class TestComputeCardiovascularRisk:
    """Test compute_cardiovascular_risk."""

    def test_basic(self):
        """TC-COV-ML-024: Computes cardiovascular risk."""
        df = pd.DataFrame({"systolic_bp": [120], "diastolic_bp": [80]})
        result = compute_cardiovascular_risk(df)
        assert "cardiovascular_risk" in result.columns
        assert result["cardiovascular_risk"].iloc[0] > 0


class TestComputeHrSleepInteraction:
    """Test compute_hr_sleep_interaction."""

    def test_basic(self):
        """TC-COV-ML-025: Computes HR sleep interaction."""
        df = pd.DataFrame({"heart_rate": [70], "sleep_hours": [7.0]})
        result = compute_hr_sleep_interaction(df)
        assert "hr_sleep_interaction" in result.columns
        assert result["hr_sleep_interaction"].iloc[0] == 70 * 3


class TestComputeOverallActivity:
    """Test compute_overall_activity."""

    def test_basic(self):
        """TC-COV-ML-026: Computes overall activity."""
        df = pd.DataFrame({"steps": [5000], "exercise_minutes": [30]})
        result = compute_overall_activity(df)
        assert "overall_activity" in result.columns
        assert result["overall_activity"].iloc[0] == 150000


class TestComputeBpCategory:
    """Test compute_bp_category."""

    def test_normal(self):
        """TC-COV-ML-027: Normal BP category."""
        df = pd.DataFrame({"systolic_bp": [110], "diastolic_bp": [70]})
        result = compute_bp_category(df)
        assert result["bp_category"].iloc[0] == 0

    def test_prehypertension(self):
        """TC-COV-ML-028: Prehypertension category."""
        df = pd.DataFrame({"systolic_bp": [130], "diastolic_bp": [85]})
        result = compute_bp_category(df)
        assert result["bp_category"].iloc[0] == 1

    def test_hypertension(self):
        """TC-COV-ML-029: Hypertension category."""
        df = pd.DataFrame({"systolic_bp": [150], "diastolic_bp": [95]})
        result = compute_bp_category(df)
        assert result["bp_category"].iloc[0] == 2


class TestEngineerFeatures:
    """Test engineer_features pipeline."""

    def test_full_pipeline(self):
        """TC-COV-ML-030: Full feature engineering pipeline."""
        df = pd.DataFrame(
            {
                "sleep_hours": [7.0],
                "sleep_quality": [3],
                "exercise_minutes": [30],
                "heart_rate": [70],
                "systolic_bp": [120],
                "diastolic_bp": [80],
                "steps": [5000],
                "depression_label": [0],
            }
        )
        result = engineer_features(df)
        for feat in ALL_FEATURES:
            assert feat in result.columns


class TestGetFeatureMatrix:
    """Test get_feature_matrix."""

    def test_extract_features(self):
        """TC-COV-ML-031: Extracts feature matrix."""
        df = pd.DataFrame(
            {
                "sleep_hours": [7.0],
                "sleep_quality": [3],
                "exercise_minutes": [30],
                "heart_rate": [70],
                "systolic_bp": [120],
                "diastolic_bp": [80],
                "steps": [5000],
                "sleep_efficiency": [0.5],
                "activity_intensity": [166.7],
                "cardiovascular_risk": [1.5],
                "hr_sleep_interaction": [210.0],
                "overall_activity": [150000],
                "bp_category": [0],
                "depression_label": [0],
            }
        )
        result = get_feature_matrix(df)
        assert list(result.columns) == ALL_FEATURES


class TestGetTargetVector:
    """Test get_target_vector."""

    def test_extract_target(self):
        """TC-COV-ML-032: Extracts target vector."""
        df = pd.DataFrame({"depression_label": [0, 1, 0]})
        result = get_target_vector(df)
        assert result.tolist() == [0, 1, 0]
