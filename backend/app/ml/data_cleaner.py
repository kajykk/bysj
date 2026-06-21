from __future__ import annotations

import json
import logging
import warnings
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from pandas import DataFrame

logger = logging.getLogger(__name__)

# Extreme value thresholds for clipping
EXTREME_THRESHOLDS = {
    "heart_rate": (30, 200),
    "sleep_hours": (0, 12),
    "steps": (0, 50000),
    "exercise_minutes": (0, 300),
    "systolic_bp": (80, 220),
    "diastolic_bp": (50, 140),
    "sleep_quality": (1, 10),
}

# Winsorization percentiles
WINSOR_LOW = 0.01
WINSOR_HIGH = 0.99


class DataCleaner:
    """数据清洗器，使用 fit/transform 模式防止数据泄漏。

    遵循 Ralph 规则 5/7：
    - 缺失值填充策略基于训练集统计量（中位数）
    - 异常值裁剪阈值基于训练集分布（1st/99th 百分位）
    - fit 仅在训练集上调用，transform 可应用于任意数据集
    """

    def __init__(self, missing_threshold: float = 0.3) -> None:
        self.missing_threshold = missing_threshold
        self._medians: dict[str, float] = {}
        self._winsor_bounds: dict[str, tuple[float, float]] = {}
        self._fitted = False

    def fit(self, train_df: DataFrame) -> DataCleaner:
        """在训练集上拟合预处理参数。

        Args:
            train_df: 训练集 DataFrame。

        Returns:
            self（支持链式调用）。
        """
        feature_cols = [c for c in train_df.columns if c not in ("source", "depression_label")]
        numeric_cols = [c for c in feature_cols if pd.api.types.is_numeric_dtype(train_df[c])]

        # 计算中位数（仅训练集）
        self._medians = {}
        for col in numeric_cols:
            if train_df[col].isnull().sum() > 0:
                self._medians[col] = float(train_df[col].median())
                logger.info("Fitted median for %s: %.2f", col, self._medians[col])

        # 计算 Winsorization 边界（仅训练集）
        self._winsor_bounds = {}
        for col in numeric_cols:
            low_val = float(train_df[col].quantile(WINSOR_LOW))
            high_val = float(train_df[col].quantile(WINSOR_HIGH))
            self._winsor_bounds[col] = (low_val, high_val)
            logger.info("Fitted winsor bounds for %s: [%.2f, %.2f]", col, low_val, high_val)

        self._fitted = True
        return self

    def transform(self, df: DataFrame) -> DataFrame:
        """应用拟合的预处理参数到数据集。

        Args:
            df: 待转换的 DataFrame（训练集/验证集/测试集）。

        Returns:
            清洗后的 DataFrame。
        """
        if not self._fitted:
            raise RuntimeError("DataCleaner must be fitted before transform. Call fit() first.")

        df_clean = df.copy()

        # 1. 丢弃高缺失样本（基于样本自身缺失率，无泄漏风险）
        df_clean = drop_high_missing_samples(df_clean, self.missing_threshold)

        # 2. 使用训练集中位数填充缺失值
        for col, median_val in self._medians.items():
            if col in df_clean.columns and df_clean[col].isnull().sum() > 0:
                fill_count = df_clean[col].isnull().sum()
                df_clean[col] = df_clean[col].fillna(median_val)
                logger.info("Filled %d missing values in %s with train median %.2f", fill_count, col, median_val)

        # 3. 裁剪极端值（使用固定生理阈值，无泄漏风险）
        df_clean = clip_extreme_values(df_clean)

        # 4. 使用训练集 Winsorization 边界
        for col, (low_val, high_val) in self._winsor_bounds.items():
            if col in df_clean.columns:
                before_count = ((df_clean[col] < low_val) | (df_clean[col] > high_val)).sum()
                if before_count > 0:
                    df_clean[col] = df_clean[col].clip(lower=low_val, upper=high_val)
                    logger.info("Winsorized %d values in %s to train bounds [%.2f, %.2f]", before_count, col, low_val, high_val)

        return df_clean

    def fit_transform(self, train_df: DataFrame) -> DataFrame:
        """在训练集上拟合并转换。

        Args:
            train_df: 训练集 DataFrame。

        Returns:
            清洗后的训练集 DataFrame。
        """
        return self.fit(train_df).transform(train_df)

    def save(self, path: str | Path) -> None:
        """P1-ML-005 修复：保存 DataCleaner 拟合参数到 JSON 文件。

        保存内容:
        - _medians: 训练集中位数字典
        - _winsor_bounds: 训练集 Winsorization 边界字典

        Args:
            path: JSON 文件路径。
        """
        path = Path(path)
        data = {
            "medians": self._medians,
            "winsor_bounds": {
                col: list(bounds) for col, bounds in self._winsor_bounds.items()
            },
            "missing_threshold": self.missing_threshold,
        }
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        logger.info("Saved DataCleaner stats to %s", path)

    def load(self, path: str | Path) -> DataCleaner:
        """P1-ML-005 修复：从 JSON 文件加载 DataCleaner 拟合参数。

        Args:
            path: JSON 文件路径。

        Returns:
            self（支持链式调用）。
        """
        path = Path(path)
        with path.open("r", encoding="utf-8") as f:
            data = json.load(f)
        self._medians = {k: float(v) for k, v in data["medians"].items()}
        self._winsor_bounds = {
            col: (float(bounds[0]), float(bounds[1]))
            for col, bounds in data["winsor_bounds"].items()
        }
        self.missing_threshold = data.get("missing_threshold", 0.3)
        self._fitted = True
        logger.info("Loaded DataCleaner stats from %s", path)
        return self

    def transform_single(self, data: dict[str, float | int]) -> dict[str, float | int]:
        """P1-ML-005 修复：对单样本推理数据应用与训练一致的清洗。

        执行步骤（与 transform 一致，但针对单样本优化）:
        1. 用训练集中位数填充缺失值（NaN 或 None）
        2. 裁剪极端值到生理阈值
        3. 用训练集 Winsorization 边界裁剪

        Args:
            data: 原始特征字典。

        Returns:
            清洗后的特征字典。
        """
        if not self._fitted:
            raise RuntimeError("DataCleaner must be fitted before transform_single.")

        cleaned: dict[str, float | int] = {}
        for col, val in data.items():
            # 1. 缺失值填充（用训练集中位数）
            if val is None or (isinstance(val, float) and np.isnan(val)):
                cleaned[col] = self._medians.get(col, 0.0)
            else:
                cleaned[col] = float(val)

            # 2. 极端值裁剪（固定生理阈值）
            if col in EXTREME_THRESHOLDS:
                low, high = EXTREME_THRESHOLDS[col]
                cleaned[col] = max(low, min(high, cleaned[col]))

            # 3. Winsorization 边界裁剪（训练集统计量）
            if col in self._winsor_bounds:
                low, high = self._winsor_bounds[col]
                cleaned[col] = max(low, min(high, cleaned[col]))

        return cleaned


def handle_all_nan_columns(df: DataFrame) -> tuple[DataFrame, list[str]]:
    """Detect and drop columns that are entirely NaN.

    Args:
        df: Input DataFrame.

    Returns:
        Tuple of (DataFrame with all-NaN columns dropped, list of dropped column names).
    """
    all_nan_cols = df.columns[df.isna().all()].tolist()
    if all_nan_cols:
        logger.warning("Dropping all-NaN columns: %s", all_nan_cols)
        df = df.drop(columns=all_nan_cols)
    return df, all_nan_cols


def handle_missing_values(df: DataFrame) -> DataFrame:
    """Fill missing values using median for numeric, mode for categorical.

    Handles all-NaN columns by dropping them before imputation to avoid sklearn warnings.

    .. deprecated::
        此函数在全量数据上计算中位数，存在数据泄漏风险（违反 Ralph 规则 7）。
        生产环境应使用 ``DataCleaner.fit/transform`` 模式。
        将在 v2.0 移除。

    Args:
        df: Input DataFrame.

    Returns:
        DataFrame with missing values filled.
    """
    # P1-ML-005 修复：添加 DeprecationWarning，引导使用 DataCleaner
    warnings.warn(
        "handle_missing_values 在全量数据上计算中位数，存在数据泄漏风险。"
        "请使用 DataCleaner.fit_transform(train_df) + DataCleaner.transform(val_df) 替代。"
        "此函数将在 v2.0 移除。",
        DeprecationWarning,
        stacklevel=2,
    )
    df_clean = df.copy()

    # Drop all-NaN columns first to avoid sklearn SimpleImputer warnings
    df_clean, dropped_cols = handle_all_nan_columns(df_clean)
    if dropped_cols:
        logger.info("Dropped %d all-NaN columns before imputation", len(dropped_cols))

    numeric_cols = df_clean.select_dtypes(include=[np.number]).columns

    for col in numeric_cols:
        if df_clean[col].isnull().sum() > 0:
            median_val = df_clean[col].median()
            df_clean[col] = df_clean[col].fillna(median_val)
            logger.info("Filled %d missing values in %s with median %.2f",
                       df[col].isnull().sum(), col, median_val)

    return df_clean


def drop_high_missing_samples(df: DataFrame, threshold: float = 0.3) -> DataFrame:
    """Drop samples with more than threshold proportion of missing values.

    Args:
        df: Input DataFrame.
        threshold: Maximum allowed proportion of missing values per sample.

    Returns:
        DataFrame with high-missing samples removed.
    """
    feature_cols = [c for c in df.columns if c not in ["source", "depression_label"]]
    missing_ratio = df[feature_cols].isnull().sum(axis=1) / len(feature_cols)

    to_drop = missing_ratio > threshold
    dropped_count = to_drop.sum()

    if dropped_count > 0:
        df_clean = df[~to_drop].copy()
        logger.info("Dropped %d samples with >%.0f%% missing values", dropped_count, threshold * 100)
    else:
        df_clean = df.copy()
        logger.info("No samples with >%.0f%% missing values found", threshold * 100)

    return df_clean


def clip_extreme_values(df: DataFrame) -> DataFrame:
    """Clip extreme values to physiologically plausible ranges.

    Args:
        df: Input DataFrame.

    Returns:
        DataFrame with extreme values clipped.
    """
    df_clean = df.copy()

    for col, (low, high) in EXTREME_THRESHOLDS.items():
        if col in df_clean.columns:
            before_count = ((df_clean[col] < low) | (df_clean[col] > high)).sum()
            df_clean[col] = df_clean[col].clip(lower=low, upper=high)
            if before_count > 0:
                logger.info("Clipped %d extreme values in %s to [%.0f, %.0f]",
                           before_count, col, low, high)

    return df_clean


def winsorize_features(df: DataFrame) -> DataFrame:
    """Apply Winsorization to numeric features (1st/99th percentile).

    .. deprecated::
        此函数在全量数据上计算百分位，存在数据泄漏风险（违反 Ralph 规则 7）。
        生产环境应使用 ``DataCleaner.fit/transform`` 模式。
        将在 v2.0 移除。

    Args:
        df: Input DataFrame.

    Returns:
        DataFrame with winsorized numeric features.
    """
    # P1-ML-005 修复：添加 DeprecationWarning，引导使用 DataCleaner
    warnings.warn(
        "winsorize_features 在全量数据上计算百分位，存在数据泄漏风险。"
        "请使用 DataCleaner.fit_transform(train_df) + DataCleaner.transform(val_df) 替代。"
        "此函数将在 v2.0 移除。",
        DeprecationWarning,
        stacklevel=2,
    )
    df_clean = df.copy()
    feature_cols = [c for c in df.columns if c not in ["source", "depression_label"]]

    for col in feature_cols:
        if pd.api.types.is_numeric_dtype(df_clean[col]):
            low_val = df_clean[col].quantile(WINSOR_LOW)
            high_val = df_clean[col].quantile(WINSOR_HIGH)

            before_count = ((df_clean[col] < low_val) | (df_clean[col] > high_val)).sum()
            df_clean[col] = df_clean[col].clip(lower=low_val, upper=high_val)

            if before_count > 0:
                logger.info("Winsorized %d values in %s to [%.2f, %.2f]",
                           before_count, col, low_val, high_val)

    return df_clean


def clean_dataset(df: DataFrame) -> DataFrame:
    """Full data cleaning pipeline.

    .. deprecated::
        此函数在全量数据上计算统计量，存在数据泄漏风险（违反 Ralph 规则 5/7）。
        生产环境应使用 ``DataCleaner.fit_transform``（训练集）+ ``DataCleaner.transform``（测试集）。
        将在 v2.0 移除。

    Steps:
        1. Drop samples with >30% missing values
        2. Fill remaining missing values (median/mode)
        3. Clip extreme values
        4. Winsorize features

    Args:
        df: Raw merged dataset.

    Returns:
        Cleaned DataFrame.
    """
    # P1-ML-005 修复：添加 DeprecationWarning，引导使用 DataCleaner
    warnings.warn(
        "clean_dataset 在全量数据上计算统计量，存在数据泄漏风险。"
        "请使用 DataCleaner.fit_transform(train_df) + DataCleaner.transform(val_df/test_df) 替代。"
        "此函数将在 v2.0 移除。",
        DeprecationWarning,
        stacklevel=2,
    )
    logger.info("Starting data cleaning: %d samples", len(df))

    df_clean = drop_high_missing_samples(df)
    df_clean = handle_missing_values(df_clean)
    df_clean = clip_extreme_values(df_clean)
    df_clean = winsorize_features(df_clean)

    logger.info("Data cleaning complete: %d samples remaining", len(df_clean))
    return df_clean
