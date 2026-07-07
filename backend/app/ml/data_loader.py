from __future__ import annotations

import logging
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from pandas import DataFrame

logger = logging.getLogger(__name__)

# Dataset paths (relative to project root)
_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent.parent
DEPRESJON_PATH = (
    _PROJECT_ROOT
    / "datasets/physiological/external/depresjon_processed/depresjon_physiological.csv"
)
KAGGLE_PATH = (
    _PROJECT_ROOT
    / "datasets/physiological/external/kaggle_wearable/mental_health_wearable_data.csv"
)

# Required columns for the model
REQUIRED_COLUMNS = [
    "sleep_hours",
    "sleep_quality",
    "exercise_minutes",
    "heart_rate",
    "systolic_bp",
    "diastolic_bp",
    "steps",
    "depression_label",
]

# Column mapping from raw datasets to unified schema
DEPRESJON_COLUMN_MAP = {
    "sleep_hours": "sleep_hours",
    "sleep_quality": "sleep_quality",
    "exercise_minutes": "exercise_minutes",
    "heart_rate": "heart_rate",
    "systolic_bp": "systolic_bp",
    "diastolic_bp": "diastolic_bp",
    "steps": "steps",
    "depression_label": "depression_label",
}

KAGGLE_COLUMN_MAP = {
    "Sleep_Duration_Hours": "sleep_hours",
    "Heart_Rate_BPM": "heart_rate",
    "Physical_Activity_Steps": "steps",
    "Mental_Health_Condition": "depression_label",
}


def load_depresjon_data(path: Path | str | None = None) -> DataFrame:
    """Load and validate Depresjon dataset.

    Args:
        path: Path to depresjon_physiological.csv. Defaults to DEPRESJON_PATH.

    Returns:
        DataFrame with unified column names.

    Raises:
        FileNotFoundError: If dataset file does not exist.
        ValueError: If required columns are missing.
    """
    path = Path(path) if path else DEPRESJON_PATH

    if not path.exists():
        raise FileNotFoundError(f"Depresjon dataset not found: {path}")

    df = pd.read_csv(path)
    logger.info(
        "Loaded Depresjon dataset: %d rows, %d columns", len(df), len(df.columns)
    )

    # Rename columns to unified schema
    df = df.rename(columns=DEPRESJON_COLUMN_MAP)

    # Select only required columns
    missing = set(REQUIRED_COLUMNS) - set(df.columns)
    if missing:
        raise ValueError(f"Depresjon dataset missing columns: {missing}")

    df = df[REQUIRED_COLUMNS].copy()
    df["source"] = "depresjon"

    logger.info("Depresjon dataset validated: %d samples", len(df))
    return df


def load_kaggle_data(path: Path | str | None = None) -> DataFrame:
    """Load and validate Kaggle Wearable dataset.

    Missing columns (sleep_quality, exercise_minutes, systolic_bp, diastolic_bp)
    are filled with Depresjon dataset medians.

    Args:
        path: Path to mental_health_wearable_data.csv. Defaults to KAGGLE_PATH.

    Returns:
        DataFrame with unified column names.

    Raises:
        FileNotFoundError: If dataset file does not exist.
    """
    path = Path(path) if path else KAGGLE_PATH

    if not path.exists():
        raise FileNotFoundError(f"Kaggle dataset not found: {path}")

    df = pd.read_csv(path)
    logger.info("Loaded Kaggle dataset: %d rows, %d columns", len(df), len(df.columns))

    # Rename columns to unified schema
    df = df.rename(columns=KAGGLE_COLUMN_MAP)

    # P1-ML-005 修复：跨数据集填充改为 NaN，避免数据泄漏
    # 旧实现使用 Depresjon 全量中位数填充 Kaggle 缺失列，违反 Ralph 规则 7
    # （Depresjon 后续会参与训练/验证/测试划分，用其全量统计量填充 Kaggle 属于未来信息泄漏）
    # 正确做法：用 NaN 填充缺失列，由 DataCleaner.fit_transform 在训练集上计算中位数后填充
    missing_columns = set(REQUIRED_COLUMNS) - set(df.columns)
    for col in missing_columns:
        df[col] = np.nan
        logger.info(
            "Filled %s with NaN (will be imputed by DataCleaner using train median)",
            col,
        )

    # Select required columns
    df = df[REQUIRED_COLUMNS].copy()
    df["source"] = "kaggle"

    logger.info("Kaggle dataset validated: %d samples", len(df))
    return df


def merge_datasets(
    depresjon_df: DataFrame | None = None,
    kaggle_df: DataFrame | None = None,
) -> DataFrame:
    """Merge Depresjon and Kaggle datasets into unified training data.

    Args:
        depresjon_df: Depresjon dataset. Loaded if None.
        kaggle_df: Kaggle dataset. Loaded if None.

    Returns:
        Merged DataFrame with source column.
    """
    if depresjon_df is None:
        depresjon_df = load_depresjon_data()
    if kaggle_df is None:
        kaggle_df = load_kaggle_data()

    merged = pd.concat([depresjon_df, kaggle_df], ignore_index=True)
    logger.info(
        "Merged datasets: %d total (Depresjon: %d, Kaggle: %d)",
        len(merged),
        len(depresjon_df),
        len(kaggle_df),
    )

    return merged


def get_dataset_stats(df: DataFrame) -> dict:
    """Compute dataset statistics.

    Args:
        df: Merged dataset.

    Returns:
        Dictionary with dataset statistics.
    """
    stats = {
        "total_samples": len(df),
        "depresjon_samples": int((df["source"] == "depresjon").sum()),
        "kaggle_samples": int((df["source"] == "kaggle").sum()),
        "depression_positive": int(df["depression_label"].sum()),
        "depression_negative": int((df["depression_label"] == 0).sum()),
        "depression_ratio": float(df["depression_label"].mean()),
        "columns": list(df.columns),
    }
    return stats
