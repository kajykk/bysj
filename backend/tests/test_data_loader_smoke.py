"""Tests for data loader module."""

from __future__ import annotations

import tempfile
from pathlib import Path

import pandas as pd
import pytest

from app.ml.data_loader import (
    DEPRESJON_PATH,
    KAGGLE_PATH,
    REQUIRED_COLUMNS,
    get_dataset_stats,
    load_depresjon_data,
    load_kaggle_data,
    merge_datasets,
)

skip_no_datasets = pytest.mark.skipif(
    not DEPRESJON_PATH.exists() or not KAGGLE_PATH.exists(),
    reason="外部数据集文件不存在 (datasets/physiological/external/)",
)


class TestLoadDepresjonData:
    """Test load_depresjon_data."""

    @skip_no_datasets
    def test_load_default(self):
        """TC-COV-DL-001: Load default Depresjon dataset."""
        df = load_depresjon_data()
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0
        assert "source" in df.columns
        assert (df["source"] == "depresjon").all()

    def test_file_not_found(self):
        """TC-COV-DL-002: File not found raises error."""
        with pytest.raises(FileNotFoundError):
            load_depresjon_data("nonexistent.csv")

    def test_missing_columns(self):
        """TC-COV-DL-003: Missing columns raises error."""
        with tempfile.NamedTemporaryFile(suffix=".csv", mode="w", delete=False) as f:
            f.write("a,b\n1,2\n")
            tmp_path = f.name
        try:
            with pytest.raises(ValueError, match="missing columns"):
                load_depresjon_data(tmp_path)
        finally:
            Path(tmp_path).unlink(missing_ok=True)


class TestLoadKaggleData:
    """Test load_kaggle_data."""

    @skip_no_datasets
    def test_load_default(self):
        """TC-COV-DL-004: Load default Kaggle dataset."""
        df = load_kaggle_data()
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0
        assert "source" in df.columns
        assert (df["source"] == "kaggle").all()
        for col in REQUIRED_COLUMNS:
            assert col in df.columns

    def test_file_not_found(self):
        """TC-COV-DL-005: File not found raises error."""
        with pytest.raises(FileNotFoundError):
            load_kaggle_data("nonexistent.csv")


class TestMergeDatasets:
    """Test merge_datasets."""

    @skip_no_datasets
    def test_merge_default(self):
        """TC-COV-DL-006: Merge default datasets."""
        df = merge_datasets()
        assert isinstance(df, pd.DataFrame)
        assert len(df) > 0
        assert set(df["source"].unique()) == {"depresjon", "kaggle"}

    @skip_no_datasets
    def test_merge_with_provided_data(self):
        """TC-COV-DL-007: Merge with provided DataFrames."""
        depresjon = load_depresjon_data()
        kaggle = load_kaggle_data()
        df = merge_datasets(depresjon, kaggle)
        assert len(df) == len(depresjon) + len(kaggle)


class TestGetDatasetStats:
    """Test get_dataset_stats."""

    @skip_no_datasets
    def test_stats(self):
        """TC-COV-DL-008: Get dataset stats."""
        df = merge_datasets()
        stats = get_dataset_stats(df)
        assert stats["total_samples"] == len(df)
        assert stats["depresjon_samples"] > 0
        assert stats["kaggle_samples"] > 0
        assert 0 <= stats["depression_ratio"] <= 1
        assert "columns" in stats
