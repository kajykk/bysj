"""L-23: 三个生理训练脚本共用的管线代码（仅收拢逐字重复部分）。

三个脚本 ``train_physiological.py`` / ``train_physiological_lightgbm.py`` /
``train_physiological_xgboost.py`` 中，以下代码块经 AST 比对为逐字一致，
统一收拢到本模块：

  * backend 路径注入、``app.ml.*`` 导入、logging 初始化
  * ``load_and_preprocess_data`` / ``compute_class_weight``（函数级 3/3 相同）
  * main() 中的「切分 / 标准化 / SMOTE」连续 25 行
  * evaluate_model() 中「指标计算」连续 9 行
  * save_artifacts() 中 scaler/feature_names/metrics/training_info/config
    落盘连续 19 行

保留在各自脚本（语义有差异，未收拢）：模型构造与超参、CLI 参数集合、
config 字段、模型文件名（model.json / model.txt / MODEL_ARTIFACT_NAMES）、
特征重要性提取、evaluate_model 的预测分支、main() 的编排差异。
"""

from __future__ import annotations

import json
import logging
import sys
from pathlib import Path

import numpy as np
import pandas as pd

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

from app.ml.data_cleaner import clean_dataset
from app.ml.data_loader import merge_datasets
from app.ml.data_split import stratified_split
from app.ml.feature_engineering import ALL_FEATURES, engineer_features, get_feature_matrix
from app.ml.scaler import SimpleStandardScaler, save_feature_names
from app.ml.smote import apply_smote_if_needed

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def load_and_preprocess_data() -> tuple[pd.DataFrame, pd.DataFrame, np.ndarray]:
    """Load and preprocess physiological data.

    Returns:
        Tuple of (feature_df, full_df, y_array).
    """
    logger.info("Loading datasets...")
    df = merge_datasets()
    logger.info("Loaded %d samples", len(df))

    logger.info("Cleaning data...")
    df = clean_dataset(df)
    logger.info("After cleaning: %d samples", len(df))

    logger.info("Engineering features...")
    df = engineer_features(df)

    # Get feature matrix
    X_df = get_feature_matrix(df)
    feature_names = list(X_df.columns)
    logger.info("Features (%d): %s", len(feature_names), feature_names)

    y = df["depression_label"].values.astype(np.int32)

    return X_df, df, y


def compute_class_weight(y: np.ndarray) -> float:
    """Compute scale_pos_weight for imbalanced data.

    Args:
        y: Target vector.

    Returns:
        scale_pos_weight value.
    """
    n_neg = np.sum(y == 0)
    n_pos = np.sum(y == 1)
    if n_pos == 0:
        return 1.0
    return n_neg / n_pos


def prepare_training_data(args, X_df, y):
    """Split / scale / SMOTE 管线（逐字取自三个脚本 main() 的 25 行连续块）。"""
    X = X_df.values.astype(np.float32)
    feature_names = list(X_df.columns)

    # Split data
    logger.info("Splitting data...")
    X_train, X_val, X_test, y_train, y_val, y_test = stratified_split(
        X, y, random_state=args.random_state
    )
    logger.info("Train: %d, Val: %d, Test: %d", len(X_train), len(X_val), len(X_test))

    # Scale features (fit on train only)
    logger.info("Scaling features...")
    scaler = SimpleStandardScaler()
    X_train = scaler.fit_transform(X_train)
    X_val = scaler.transform(X_val)
    X_test = scaler.transform(X_test)

    # Apply SMOTE if needed (on train only, max ratio 0.8 per Ralph rules)
    logger.info("Applying SMOTE (ratio <= 0.8)...")
    X_train, y_train = apply_smote_if_needed(
        X_train, y_train, sampling_strategy=min(args.smote_ratio, 0.8)
    )
    logger.info("After SMOTE: %d samples", len(X_train))

    return X_train, X_val, X_test, y_train, y_val, y_test, feature_names, scaler


def compute_eval_metrics(y, y_pred_proba):
    """评估指标计算（逐字取自三个脚本 evaluate_model() 的公共 9 行尾部）。"""
    y_pred = (y_pred_proba >= 0.5).astype(int)

    # Compute metrics
    from app.ml.trainer import compute_metrics

    metrics = compute_metrics(y.reshape(-1, 1), y_pred_proba.reshape(-1, 1))
    metrics["n_samples"] = len(y)

    return metrics


def save_json_artifacts(scaler, feature_names, metrics, training_info, config, output_dir):
    """scaler / feature_names / metrics / training_info / config 落盘
    （逐字取自三个脚本 save_artifacts() 的公共 19 行尾部）。

    ``output_dir.mkdir`` 与模型文件（model.json / model.txt）的保存
    保留在各自脚本中，因为三者的模型文件名与函数签名不同。
    """
    # Save scaler
    scaler.save(output_dir / "scaler.json")

    # Save feature names
    save_feature_names(feature_names, output_dir / "feature_names.json")

    # Save metrics
    with open(output_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(metrics, f, indent=2)

    # Save training info
    with open(output_dir / "training_info.json", "w", encoding="utf-8") as f:
        json.dump(training_info, f, indent=2)

    # Save config
    with open(output_dir / "config.json", "w", encoding="utf-8") as f:
        json.dump(config, f, indent=2)

    logger.info("All artifacts saved to %s", output_dir)
