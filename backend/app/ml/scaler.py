from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from pandas import DataFrame

logger = logging.getLogger(__name__)

# Artifact paths
ARTIFACTS_DIR = Path(__file__).resolve().parent.parent.parent.parent / "models" / "artifacts" / "physiological"
SCALER_PATH = ARTIFACTS_DIR / "scaler.json"
FEATURE_NAMES_PATH = ARTIFACTS_DIR / "feature_names.json"


class SimpleStandardScaler:
    """Simple StandardScaler implementation using numpy only.
    
    Avoids sklearn dependency issues.
    """
    
    def __init__(self):
        self.mean_: np.ndarray | None = None
        self.scale_: np.ndarray | None = None
        self.n_features_in_: int = 0
    
    def fit(self, X: np.ndarray | DataFrame) -> SimpleStandardScaler:
        """Fit scaler to data."""
        if hasattr(X, 'values'):
            X = X.values
        self.mean_ = np.mean(X, axis=0)
        self.scale_ = np.std(X, axis=0)
        # Avoid division by zero
        self.scale_[self.scale_ == 0] = 1.0
        self.n_features_in_ = X.shape[1]
        return self
    
    def transform(self, X: np.ndarray | DataFrame) -> np.ndarray:
        """Transform data."""
        if self.mean_ is None or self.scale_ is None:
            raise RuntimeError("Scaler must be fitted before transform")
        if hasattr(X, 'values'):
            X = X.values
        return (X - self.mean_) / self.scale_
    
    def fit_transform(self, X: np.ndarray | DataFrame) -> np.ndarray:
        """Fit and transform data."""
        self.fit(X)
        return self.transform(X)
    
    def to_dict(self) -> dict:
        """Serialize to dictionary."""
        return {
            "mean": self.mean_.tolist(),
            "scale": self.scale_.tolist(),
            "n_features_in": self.n_features_in_,
        }
    
    @classmethod
    def from_dict(cls, data: dict) -> SimpleStandardScaler:
        """Deserialize from dictionary."""
        scaler = cls()
        scaler.mean_ = np.array(data["mean"])
        scaler.scale_ = np.array(data["scale"])
        scaler.n_features_in_ = data["n_features_in"]
        return scaler

    def save(self, path: Path | str) -> None:
        """Save scaler to JSON file.

        Args:
            path: Path to save the scaler.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            json.dump(self.to_dict(), f, indent=2)
        logger.info("Saved scaler to %s", path)


def ensure_artifacts_dir() -> None:
    """Create artifacts directory if it doesn't exist."""
    ARTIFACTS_DIR.mkdir(parents=True, exist_ok=True)


def fit_scaler(X: DataFrame) -> SimpleStandardScaler:
    """Fit StandardScaler on feature matrix.

    Args:
        X: Feature matrix (n_samples, n_features).

    Returns:
        Fitted SimpleStandardScaler.
    """
    scaler = SimpleStandardScaler()
    scaler.fit(X)
    logger.info("Fitted StandardScaler on %d features", X.shape[1])
    return scaler


def save_scaler(scaler: SimpleStandardScaler, path: Path | str | None = None) -> None:
    """Save fitted scaler to disk.

    Args:
        scaler: Fitted SimpleStandardScaler.
        path: Save path. Defaults to SCALER_PATH.
    """
    ensure_artifacts_dir()
    path = Path(path) if path else SCALER_PATH
    with open(path, "w", encoding="utf-8") as f:
        json.dump(scaler.to_dict(), f, indent=2)
    logger.info("Saved scaler to %s", path)


def load_scaler(path: Path | str | None = None) -> SimpleStandardScaler:
    """Load scaler from disk.

    Args:
        path: Load path. Defaults to SCALER_PATH.

    Returns:
        Loaded SimpleStandardScaler.

    Raises:
        FileNotFoundError: If scaler file does not exist.
    """
    path = Path(path) if path else SCALER_PATH
    if not path.exists():
        raise FileNotFoundError(f"Scaler not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    scaler = SimpleStandardScaler.from_dict(data)
    logger.info("Loaded scaler from %s", path)
    return scaler


def save_feature_names(feature_names: list[str], path: Path | str | None = None) -> None:
    """Save feature names to JSON.

    Args:
        feature_names: List of feature names.
        path: Save path. Defaults to FEATURE_NAMES_PATH.
    """
    ensure_artifacts_dir()
    path = Path(path) if path else FEATURE_NAMES_PATH
    with open(path, "w", encoding="utf-8") as f:
        json.dump(feature_names, f, indent=2)
    logger.info("Saved %d feature names to %s", len(feature_names), path)


def load_feature_names(path: Path | str | None = None) -> list[str]:
    """Load feature names from JSON.

    Args:
        path: Load path. Defaults to FEATURE_NAMES_PATH.

    Returns:
        List of feature names.

    Raises:
        FileNotFoundError: If feature names file does not exist.
    """
    path = Path(path) if path else FEATURE_NAMES_PATH
    if not path.exists():
        raise FileNotFoundError(f"Feature names not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        feature_names = json.load(f)
    logger.info("Loaded %d feature names from %s", len(feature_names), path)
    return feature_names


def scale_features(X: DataFrame, scaler: SimpleStandardScaler | None = None) -> np.ndarray:
    """Scale features using StandardScaler.

    P1-ML-005 修复：当 scaler 为 None 时发出警告，提示潜在的数据泄漏风险。
    生产环境应始终传入在训练集上 fit 的 scaler，避免在验证集/测试集上 fit。

    Args:
        X: Feature matrix.
        scaler: Fitted scaler. If None, fits a new scaler on X (有数据泄漏风险，
            仅应在训练集上使用)。

    Returns:
        Scaled feature matrix as numpy array.
    """
    if scaler is None:
        # P1-ML-005 修复：警告 scaler=None 的数据泄漏风险
        import warnings

        warnings.warn(
            "scale_features 在 scaler=None 时会在传入的 X 上 fit，"
            "若 X 是验证集或测试集将造成数据泄漏。"
            "请始终传入在训练集上 fit 的 scaler。",
            UserWarning,
            stacklevel=2,
        )
        scaler = fit_scaler(X)
    X_scaled = scaler.transform(X)
    logger.info("Scaled features: mean=%.4f, std=%.4f", np.mean(X_scaled), np.std(X_scaled))
    return X_scaled
