from __future__ import annotations

import logging
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from pandas import DataFrame

logger = logging.getLogger(__name__)

# Original feature columns (7)
ORIGINAL_FEATURES = [
    "sleep_hours",
    "sleep_quality",
    "exercise_minutes",
    "heart_rate",
    "systolic_bp",
    "diastolic_bp",
    "steps",
]

# Derived feature columns (6)
DERIVED_FEATURES = [
    "sleep_efficiency",
    "activity_intensity",
    "cardiovascular_risk",
    "hr_sleep_interaction",
    "overall_activity",
    "bp_category",
]

# All features (13)
ALL_FEATURES = ORIGINAL_FEATURES + DERIVED_FEATURES

# BP category thresholds (JNC 7 guidelines)
BP_CATEGORIES = {
    "normal": (0, 120, 0, 80),
    "prehypertension": (120, 139, 80, 89),
    "hypertension": (140, 999, 90, 999),
}


def compute_sleep_efficiency(df: DataFrame) -> DataFrame:
    """Compute sleep_efficiency = sleep_quality / sleep_hours.

    Handles division by zero by returning 0.
    """
    df = df.copy()
    df["sleep_efficiency"] = df["sleep_quality"] / (df["sleep_hours"] + 1e-6)
    df["sleep_efficiency"] = df["sleep_efficiency"].clip(lower=0, upper=10)
    return df


def compute_activity_intensity(df: DataFrame) -> DataFrame:
    """Compute activity_intensity = steps / exercise_minutes.

    Handles division by zero by returning steps value (steps per minute = steps when no exercise).
    """
    df = df.copy()
    # When exercise_minutes is 0, return steps as the intensity measure
    df["activity_intensity"] = np.where(
        df["exercise_minutes"] == 0,
        df["steps"],
        df["steps"] / df["exercise_minutes"]
    )
    df["activity_intensity"] = df["activity_intensity"].clip(lower=0, upper=10000)
    return df


def compute_cardiovascular_risk(df: DataFrame) -> DataFrame:
    """Compute cardiovascular_risk = systolic_bp / diastolic_bp."""
    df = df.copy()
    df["cardiovascular_risk"] = df["systolic_bp"] / (df["diastolic_bp"] + 1e-6)
    df["cardiovascular_risk"] = df["cardiovascular_risk"].clip(lower=0.5, upper=3.0)
    return df


def compute_hr_sleep_interaction(df: DataFrame) -> DataFrame:
    """Compute hr_sleep_interaction = heart_rate * (10 - sleep_hours)."""
    df = df.copy()
    df["hr_sleep_interaction"] = df["heart_rate"] * (10 - df["sleep_hours"])
    return df


def compute_overall_activity(df: DataFrame) -> DataFrame:
    """Compute overall_activity = steps * exercise_minutes."""
    df = df.copy()
    df["overall_activity"] = df["steps"] * df["exercise_minutes"]
    return df


def compute_bp_category(df: DataFrame) -> DataFrame:
    """Classify blood pressure into categories.

    Categories:
        0: normal (<120/80)
        1: prehypertension (120-139/80-89)
        2: hypertension (>=140/>=90)
    """
    df = df.copy()

    conditions = [
        (df["systolic_bp"] < 120) & (df["diastolic_bp"] < 80),
        (df["systolic_bp"] < 140) & (df["diastolic_bp"] < 90),
    ]
    choices = [0, 1]
    default = 2

    df["bp_category"] = np.select(conditions, choices, default=default)
    return df


def engineer_features(df: DataFrame) -> DataFrame:
    """Apply full feature engineering pipeline.

    Args:
        df: Cleaned DataFrame with original features.

    Returns:
        DataFrame with original + derived features (13 total).
    """
    logger.info("Starting feature engineering: %d samples", len(df))

    df = compute_sleep_efficiency(df)
    df = compute_activity_intensity(df)
    df = compute_cardiovascular_risk(df)
    df = compute_hr_sleep_interaction(df)
    df = compute_overall_activity(df)
    df = compute_bp_category(df)

    logger.info(
        "Feature engineering complete: %d features (%d original + %d derived)",
        len(ALL_FEATURES),
        len(ORIGINAL_FEATURES),
        len(DERIVED_FEATURES),
    )
    return df


def get_feature_matrix(df: DataFrame) -> DataFrame:
    """Extract feature matrix (X) from engineered DataFrame.

    Args:
        df: DataFrame with all features.

    Returns:
        DataFrame with only feature columns (no target, no source).
    """
    return df[ALL_FEATURES].copy()


def get_target_vector(df: DataFrame) -> DataFrame:
    """Extract target vector (y) from engineered DataFrame.

    Args:
        df: DataFrame with target column.

    Returns:
        Series with depression labels.
    """
    return df["depression_label"].copy()
