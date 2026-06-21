"""Tests for data_loader module."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import pytest

from app.ml.data_loader import get_dataset_stats, load_depresjon_data, load_kaggle_data, merge_datasets


class TestLoadDepresjonData:
    """Test load_depresjon_data."""

    def test_file_not_found(self):
        """TC-COV-ML-013: Raises FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError, match="Depresjon"):
            load_depresjon_data("/nonexistent/path.csv")

    def test_load_valid(self):
        """TC-COV-ML-014: Loads valid Depresjon data."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w", newline="") as f:
            f.write("sleep_hours,sleep_quality,exercise_minutes,heart_rate,systolic_bp,diastolic_bp,steps,depression_label\n")
            f.write("7,3,30,70,120,80,5000,0\n")
            f.write("8,4,45,75,130,85,8000,1\n")
            path = f.name

        result = load_depresjon_data(path)
        assert len(result) == 2
        assert "source" in result.columns
        assert result["source"].iloc[0] == "depresjon"
        Path(path).unlink()

    def test_missing_columns(self):
        """TC-COV-ML-015: Raises ValueError for missing columns."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w", newline="") as f:
            f.write("sleep_hours,heart_rate\n")
            f.write("7,70\n")
            path = f.name

        with pytest.raises(ValueError, match="missing columns"):
            load_depresjon_data(path)
        Path(path).unlink()


class TestLoadKaggleData:
    """Test load_kaggle_data."""

    def test_file_not_found(self):
        """TC-COV-ML-016: Raises FileNotFoundError for missing file."""
        with pytest.raises(FileNotFoundError, match="Kaggle"):
            load_kaggle_data("/nonexistent/path.csv")

    def test_load_valid(self):
        """TC-COV-ML-017: Loads valid Kaggle data with column mapping."""
        with tempfile.NamedTemporaryFile(suffix=".csv", delete=False, mode="w", newline="") as f:
            f.write("Sleep_Duration_Hours,Heart_Rate_BPM,Physical_Activity_Steps,Mental_Health_Condition\n")
            f.write("7,70,5000,0\n")
            f.write("8,75,8000,1\n")
            path = f.name

        result = load_kaggle_data(path)
        assert len(result) == 2
        assert "source" in result.columns
        assert result["source"].iloc[0] == "kaggle"
        assert "sleep_hours" in result.columns
        Path(path).unlink()


class TestMergeDatasets:
    """Test merge_datasets."""

    def test_merge(self):
        """TC-COV-ML-018: Merges two datasets."""
        df1 = pd.DataFrame({
            "sleep_hours": [7.0],
            "sleep_quality": [3],
            "exercise_minutes": [30],
            "heart_rate": [70],
            "systolic_bp": [120],
            "diastolic_bp": [80],
            "steps": [5000],
            "depression_label": [0],
            "source": ["depresjon"],
        })
        df2 = pd.DataFrame({
            "sleep_hours": [8.0],
            "sleep_quality": [4],
            "exercise_minutes": [45],
            "heart_rate": [75],
            "systolic_bp": [130],
            "diastolic_bp": [85],
            "steps": [8000],
            "depression_label": [1],
            "source": ["kaggle"],
        })
        result = merge_datasets(df1, df2)
        assert len(result) == 2
        assert set(result["source"].tolist()) == {"depresjon", "kaggle"}


class TestGetDatasetStats:
    """Test get_dataset_stats."""

    def test_stats(self):
        """TC-COV-ML-019: Computes dataset statistics."""
        df = pd.DataFrame({
            "sleep_hours": [7.0, 8.0],
            "sleep_quality": [3, 4],
            "exercise_minutes": [30, 45],
            "heart_rate": [70, 75],
            "systolic_bp": [120, 130],
            "diastolic_bp": [80, 85],
            "steps": [5000, 8000],
            "depression_label": [0, 1],
            "source": ["depresjon", "kaggle"],
        })
        stats = get_dataset_stats(df)
        assert stats["total_samples"] == 2
        assert stats["depresjon_samples"] == 1
        assert stats["kaggle_samples"] == 1
        assert stats["depression_positive"] == 1
        assert stats["depression_negative"] == 1
