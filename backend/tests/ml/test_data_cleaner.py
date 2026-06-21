"""Tests for data_cleaner module."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.ml.data_cleaner import (
    clean_dataset,
    clip_extreme_values,
    DataCleaner,
    drop_high_missing_samples,
    handle_all_nan_columns,
    handle_missing_values,
    winsorize_features,
)


class TestHandleAllNanColumns:
    """Test handle_all_nan_columns."""

    def test_no_all_nan(self):
        """TC-COV-ML-001: No all-NaN columns returns unchanged."""
        df = pd.DataFrame({"a": [1, 2, 3], "b": [4, 5, 6]})
        result, dropped = handle_all_nan_columns(df)
        assert list(result.columns) == ["a", "b"]
        assert dropped == []

    def test_drop_all_nan(self):
        """TC-COV-ML-002: Drops all-NaN columns."""
        df = pd.DataFrame({"a": [1, 2, 3], "b": [np.nan, np.nan, np.nan]})
        result, dropped = handle_all_nan_columns(df)
        assert "b" not in result.columns
        assert dropped == ["b"]


class TestHandleMissingValues:
    """Test handle_missing_values."""

    def test_fill_numeric_median(self):
        """TC-COV-ML-003: Fills numeric missing with median."""
        df = pd.DataFrame({"a": [1.0, 2.0, np.nan, 4.0]})
        result = handle_missing_values(df)
        assert result["a"].isnull().sum() == 0
        assert result["a"].iloc[2] == 2.0  # median of [1, 2, 4] (sorted middle value)

    def test_no_missing(self):
        """TC-COV-ML-004: No missing values returns unchanged."""
        df = pd.DataFrame({"a": [1.0, 2.0, 3.0]})
        result = handle_missing_values(df)
        assert result["a"].tolist() == [1.0, 2.0, 3.0]


class TestDropHighMissingSamples:
    """Test drop_high_missing_samples."""

    def test_drop_high_missing(self):
        """TC-COV-ML-005: Drops samples with >30% missing.

        Row 0: 0/3 missing (0%)  -> keep
        Row 1: 2/3 missing (66%) -> drop (66% > 30%)
        Row 2: 3/3 missing (100%)-> drop (100% > 30%)
        Row 3: 0/3 missing (0%)  -> keep
        Expected: 2 rows kept.
        """
        df = pd.DataFrame({
            "a": [1.0, np.nan, np.nan, 4.0],
            "b": [1.0, np.nan, np.nan, 4.0],
            "c": [1.0, 2.0, np.nan, 4.0],
            "source": ["x", "x", "x", "x"],
            "depression_label": [0, 0, 0, 1],
        })
        result = drop_high_missing_samples(df)
        assert len(result) == 2

    def test_no_drop_needed(self):
        """TC-COV-ML-006: No high-missing samples returns all."""
        df = pd.DataFrame({
            "a": [1.0, 2.0, 3.0],
            "b": [4.0, 5.0, 6.0],
            "source": ["x", "x", "x"],
            "depression_label": [0, 0, 1],
        })
        result = drop_high_missing_samples(df)
        assert len(result) == 3


class TestClipExtremeValues:
    """Test clip_extreme_values."""

    def test_clip_heart_rate(self):
        """TC-COV-ML-007: Clips heart_rate to [30, 200]."""
        df = pd.DataFrame({"heart_rate": [10, 80, 250]})
        result = clip_extreme_values(df)
        assert result["heart_rate"].tolist() == [30, 80, 200]

    def test_no_extreme_values(self):
        """TC-COV-ML-008: No extreme values returns unchanged."""
        df = pd.DataFrame({"heart_rate": [60, 80, 100]})
        result = clip_extreme_values(df)
        assert result["heart_rate"].tolist() == [60, 80, 100]

    def test_unknown_column_ignored(self):
        """TC-COV-ML-009: Unknown columns are ignored."""
        df = pd.DataFrame({"unknown_col": [1, 2, 3]})
        result = clip_extreme_values(df)
        assert result["unknown_col"].tolist() == [1, 2, 3]


class TestWinsorizeFeatures:
    """Test winsorize_features."""

    def test_winsorize(self):
        """TC-COV-ML-010: Winsorizes numeric features."""
        df = pd.DataFrame({
            "a": [1.0, 2.0, 3.0, 100.0],
            "source": ["x", "x", "x", "x"],
            "depression_label": [0, 0, 0, 1],
        })
        result = winsorize_features(df)
        assert result["a"].max() < 100.0

    def test_no_numeric(self):
        """TC-COV-ML-011: No numeric features returns unchanged."""
        df = pd.DataFrame({
            "source": ["x", "y", "z"],
            "depression_label": [0, 0, 1],
        })
        result = winsorize_features(df)
        assert len(result) == 3


class TestCleanDataset:
    """Test clean_dataset pipeline."""

    def test_full_pipeline(self):
        """TC-COV-ML-012: Full cleaning pipeline runs."""
        df = pd.DataFrame({
            "sleep_hours": [7.0, 8.0, np.nan, 6.0],
            "heart_rate": [60, 80, 70, 300],
            "steps": [5000, 8000, 6000, 10000],
            "source": ["x", "x", "x", "x"],
            "depression_label": [0, 0, 0, 1],
        })
        result = clean_dataset(df)
        assert len(result) <= 4
        assert result["heart_rate"].max() <= 200
        assert result["sleep_hours"].isnull().sum() == 0


# ===== P1-ML-005 数据泄漏修复测试 =====


class TestDeprecationWarnings:
    """P1-ML-005: 验证泄漏函数发出 DeprecationWarning."""

    def test_handle_missing_values_emits_deprecation_warning(self):
        """handle_missing_values 应发出 DeprecationWarning."""
        df = pd.DataFrame({"a": [1.0, 2.0, np.nan, 4.0]})
        with pytest.warns(DeprecationWarning, match="数据泄漏风险"):
            handle_missing_values(df)

    def test_winsorize_features_emits_deprecation_warning(self):
        """winsorize_features 应发出 DeprecationWarning."""
        df = pd.DataFrame(
            {"a": [1.0, 2.0, 3.0, 4.0], "depression_label": [0, 0, 0, 1]}
        )
        with pytest.warns(DeprecationWarning, match="数据泄漏风险"):
            winsorize_features(df)

    def test_clean_dataset_emits_deprecation_warning(self):
        """clean_dataset 应发出 DeprecationWarning."""
        df = pd.DataFrame(
            {
                "heart_rate": [60, 80, 70, 90],
                "steps": [5000, 8000, 6000, 10000],
                "source": ["x", "x", "x", "x"],
                "depression_label": [0, 0, 0, 1],
            }
        )
        with pytest.warns(DeprecationWarning, match="数据泄漏风险"):
            clean_dataset(df)


class TestDataCleanerLeakagePrevention:
    """P1-ML-005: 验证 DataCleaner 防止数据泄漏."""

    def test_fit_transform_on_train_only(self):
        """DataCleaner.fit_transform 应仅在训练集上计算统计量."""
        # 构造训练集和测试集，测试集值在训练集范围内（避免 Winsorization 干扰）
        train_df = pd.DataFrame(
            {
                "heart_rate": [60.0, 70.0, 80.0, 90.0, 85.0, 75.0],
                "steps": [5000.0, 6000.0, 7000.0, 8000.0, 7500.0, 6500.0],
                "depression_label": [0, 0, 1, 1, 0, 1],
            }
        )
        test_df = pd.DataFrame(
            {
                "heart_rate": [65.0, 85.0],
                "steps": [5500.0, 7500.0],
                "depression_label": [0, 1],
            }
        )

        cleaner = DataCleaner(missing_threshold=0.3)
        # 仅在训练集上 fit
        train_clean = cleaner.fit_transform(train_df)
        # 用训练集统计量 transform 测试集
        test_clean = cleaner.transform(test_df)

        # 验证测试集无缺失值时保持原值（未被训练集统计量"污染"）
        assert test_clean["heart_rate"].iloc[0] == 65.0
        assert test_clean["heart_rate"].iloc[1] == 85.0

    def test_train_test_isolation(self):
        """训练集和测试集的缺失值应分别用训练集统计量填充."""
        # 训练集有缺失值（4 个特征列，1 个缺失 = 0.25 < 0.3，不会被丢弃）
        train_df = pd.DataFrame(
            {
                "heart_rate": [60.0, np.nan, 80.0, 90.0, 85.0, 75.0],
                "steps": [5000.0, 6000.0, 7000.0, 8000.0, 7500.0, 6500.0],
                "sleep_hours": [7.0, 8.0, 6.5, 7.5, 8.0, 7.0],
                "exercise_minutes": [30.0, 45.0, 60.0, 20.0, 40.0, 50.0],
                "depression_label": [0, 0, 1, 1, 0, 1],
            }
        )
        # 测试集也有缺失值（1/4 = 0.25 < 0.3，不会被丢弃）
        test_df = pd.DataFrame(
            {
                "heart_rate": [70.0, np.nan],
                "steps": [5500.0, 7500.0],
                "sleep_hours": [7.0, 8.0],
                "exercise_minutes": [35.0, 45.0],
                "depression_label": [0, 1],
            }
        )

        cleaner = DataCleaner(missing_threshold=0.3)
        train_clean = cleaner.fit_transform(train_df)
        test_clean = cleaner.transform(test_df)

        # 训练集缺失值应填充为训练集中位数
        train_median = train_df["heart_rate"].dropna().median()
        assert train_clean["heart_rate"].iloc[1] == train_median

        # 测试集缺失值也应填充为训练集中位数（而非测试集中位数）
        # 训练集中位数 = 80.0，测试集中位数 = 70.0
        test_median = test_df["heart_rate"].dropna().median()
        assert train_median != test_median  # 80 ≠ 70
        assert test_clean["heart_rate"].iloc[1] == train_median  # 填充的是 80 而非 70

    def test_winsorization_uses_train_bounds(self):
        """Winsorization 应使用训练集边界，而非测试集边界."""
        # 训练集范围 60-90
        train_df = pd.DataFrame(
            {
                "heart_rate": [60.0, 70.0, 80.0, 90.0, 85.0, 75.0],
                "steps": [5000.0, 6000.0, 7000.0, 8000.0, 7500.0, 6500.0],
                "depression_label": [0, 0, 1, 1, 0, 1],
            }
        )
        # 测试集有超出训练集范围的值（200）
        test_df = pd.DataFrame(
            {
                "heart_rate": [70.0, 200.0],
                "steps": [5500.0, 7500.0],
                "depression_label": [0, 1],
            }
        )

        cleaner = DataCleaner(missing_threshold=0.3)
        cleaner.fit_transform(train_df)
        test_clean = cleaner.transform(test_df)

        # 测试集的 200 应被裁剪到训练集的 99th 百分位（约 90）
        # 而非测试集自己的 99th 百分位（约 200）
        assert test_clean["heart_rate"].iloc[1] < 200.0
        assert test_clean["heart_rate"].iloc[1] <= 95.0  # 训练集上界附近


class TestDataCleanerPersistSingle:
    """P1-ML-005: 验证 DataCleaner save/load 和 transform_single."""

    def test_save_load_roundtrip(self, tmp_path):
        """save/load 应完整保留训练统计量."""
        train_df = pd.DataFrame(
            {
                "heart_rate": [60.0, np.nan, 80.0, 90.0, 85.0, 75.0],
                "steps": [5000.0, 6000.0, 7000.0, 8000.0, 7500.0, 6500.0],
                "depression_label": [0, 0, 1, 1, 0, 1],
            }
        )
        cleaner = DataCleaner()
        cleaner.fit(train_df)

        stats_file = tmp_path / "cleaner_stats.json"
        cleaner.save(stats_file)

        # 加载到新实例
        loaded = DataCleaner()
        loaded.load(stats_file)

        assert loaded._medians == cleaner._medians
        assert loaded._winsor_bounds == cleaner._winsor_bounds
        assert loaded._fitted is True

    def test_transform_single_fills_missing_with_train_median(self):
        """transform_single 应使用训练集中位数填充缺失值."""
        train_df = pd.DataFrame(
            {
                "heart_rate": [60.0, np.nan, 80.0, 90.0, 85.0, 75.0],
                "steps": [5000.0, 6000.0, 7000.0, 8000.0, 7500.0, 6500.0],
                "depression_label": [0, 0, 1, 1, 0, 1],
            }
        )
        cleaner = DataCleaner()
        cleaner.fit(train_df)

        train_median = train_df["heart_rate"].dropna().median()
        # 单样本推理：heart_rate 缺失
        result = cleaner.transform_single({"heart_rate": np.nan, "steps": 5500.0})
        assert result["heart_rate"] == train_median

    def test_transform_single_clips_extreme_values(self):
        """transform_single 应裁剪极端值到生理阈值，再应用 Winsor 边界."""
        train_df = pd.DataFrame(
            {
                "heart_rate": [60.0, 70.0, 80.0, 90.0, 85.0, 75.0],
                "steps": [5000.0, 6000.0, 7000.0, 8000.0, 7500.0, 6500.0],
                "depression_label": [0, 0, 1, 1, 0, 1],
            }
        )
        cleaner = DataCleaner()
        cleaner.fit(train_df)

        # heart_rate=300 超出生理阈值 [30, 200]，应先裁剪到 200
        # 然后若 200 超出 Winsor 上界，再裁剪到 Winsor 上界
        result = cleaner.transform_single({"heart_rate": 300.0, "steps": 5500.0})
        winsor_high = cleaner._winsor_bounds["heart_rate"][1]
        # 最终值不应超过 Winsor 上界
        assert result["heart_rate"] <= winsor_high
        # 也应在生理阈值内
        assert result["heart_rate"] <= 200.0

    def test_transform_single_clips_below_physiological_threshold(self):
        """transform_single 应裁剪低于生理阈值的值."""
        train_df = pd.DataFrame(
            {
                "heart_rate": [60.0, 70.0, 80.0, 90.0, 85.0, 75.0],
                "steps": [5000.0, 6000.0, 7000.0, 8000.0, 7500.0, 6500.0],
                "depression_label": [0, 0, 1, 1, 0, 1],
            }
        )
        cleaner = DataCleaner()
        cleaner.fit(train_df)

        # heart_rate=10 低于生理阈值 [30, 200]
        result = cleaner.transform_single({"heart_rate": 10.0, "steps": 5500.0})
        winsor_low = cleaner._winsor_bounds["heart_rate"][0]
        # 最终值不应低于 Winsor 下界（若 Winsor 下界 > 30）
        # 或不应低于生理阈值 30
        assert result["heart_rate"] >= 30.0
        assert result["heart_rate"] >= winsor_low

    def test_transform_single_applies_winsor_bounds(self):
        """transform_single 应应用训练集 Winsorization 边界."""
        train_df = pd.DataFrame(
            {
                "heart_rate": [60.0, 70.0, 80.0, 90.0, 85.0, 75.0],
                "steps": [5000.0, 6000.0, 7000.0, 8000.0, 7500.0, 6500.0],
                "depression_label": [0, 0, 1, 1, 0, 1],
            }
        )
        cleaner = DataCleaner()
        cleaner.fit(train_df)

        # 训练集 heart_rate 范围 60-90，Winsor 边界应在此范围附近
        # 提供一个超出 Winsor 边界但在生理阈值内的值
        result = cleaner.transform_single({"heart_rate": 100.0, "steps": 5500.0})
        # 100 在生理阈值 [30, 200] 内，但可能超出 Winsor 上界
        winsor_high = cleaner._winsor_bounds["heart_rate"][1]
        if 100.0 > winsor_high:
            assert result["heart_rate"] == winsor_high
        else:
            assert result["heart_rate"] == 100.0

    def test_transform_single_raises_when_not_fitted(self):
        """未 fit 的 DataCleaner 调用 transform_single 应抛出异常."""
        cleaner = DataCleaner()
        with pytest.raises(RuntimeError, match="must be fitted"):
            cleaner.transform_single({"heart_rate": 70.0})
