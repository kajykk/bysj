from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

if TYPE_CHECKING:
    from pandas import DataFrame

logger = logging.getLogger(__name__)

# ── Artifact paths (AUDIT-2026-09-28-P1-14 统一) ──────────────────────────
# 原实现硬编码 ``.../models/artifacts/physiological``，而**推理侧**
# (app/ml/model_loader.py::_resolve_artifacts_dir) 读的是
# ``.../artifacts/physiological_optimized``，model_registry.py:42-44 注册的
# physiological_model_v2_dl / scaler_v2_dl / features_v2_dl 也指向后者。
#
# 后果：save_scaler()/save_feature_names() 写出的工件落在 physiological/，
# 推理时根本读不到 —— **重训后 scaler 与 feature_names 静默不生效**，
# 且没有任何报错（推理会继续用旧工件）。
#
# 现统一复用 model_loader 的解析结果作为单一权威源。
# 采用 PEP 562 模块级 __getattr__ 懒解析：本模块被 model_loader 导入
# (``from app.ml.scaler import SimpleStandardScaler``)，模块级再反向导入
# model_loader 会形成循环，故延迟到首次访问路径常量时才 import。
_LEGACY_ARTIFACTS_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "models"
    / "artifacts"
    / "physiological"
)

_ARTIFACT_PATH_NAMES = ("ARTIFACTS_DIR", "SCALER_PATH", "FEATURE_NAMES_PATH")


def __getattr__(name: str) -> Path:
    """懒解析工件路径常量（与 model_loader 保持同一权威源）."""
    if name not in _ARTIFACT_PATH_NAMES:
        raise AttributeError(f"module {__name__!r} has no attribute {name!r}")
    try:
        from app.ml.model_loader import _resolve_artifacts_dir

        artifacts_dir = _resolve_artifacts_dir()
    except Exception as exc:  # noqa: BLE001
        logger.warning(
            "无法解析统一工件目录, 回退遗留路径 %s: %s", _LEGACY_ARTIFACTS_DIR, exc
        )
        artifacts_dir = _LEGACY_ARTIFACTS_DIR
    values: dict[str, Path] = {
        "ARTIFACTS_DIR": artifacts_dir,
        "SCALER_PATH": artifacts_dir / "scaler.json",
        "FEATURE_NAMES_PATH": artifacts_dir / "feature_names.json",
    }
    globals().update(values)
    return values[name]


def _artifact_path(name: str) -> Path:
    """模块内部取懒加载路径常量.

    PEP 562 的 __getattr__ 只拦截**外部**属性访问（``scaler.SCALER_PATH``）；
    函数体内的裸名 ``SCALER_PATH`` 走普通 globals 查找，首次访问即 NameError。
    内部统一经此辅助取值（若 __getattr__ 已回写则命中缓存）。
    """
    cached = globals().get(name)
    if isinstance(cached, Path):
        return cached
    return __getattr__(name)


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
        if hasattr(X, "values"):
            X = X.values
        # L-ML-3 修复：fit 前检查 NaN，避免 NaN 传播到模型
        if np.isnan(X).any():
            logger.warning(
                "输入数据包含 NaN，StandardScaler 将产生 NaN 均值/方差并传播到模型"
            )
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
        if hasattr(X, "values"):
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
        # C-ML-2 修复：生成 .sha256 侧车校验文件，与 load_scaler 的 require_checksum=True 对齐
        # 治理循环依赖：改从 app.utils.checksum 导入，避免反向依赖 model_loader 形成环。
        from app.utils.checksum import write_sha256_sidecar

        write_sha256_sidecar(path)
        logger.info("Saved scaler to %s", path)


def ensure_artifacts_dir() -> None:
    """Create artifacts directory if it doesn't exist."""
    _artifact_path("ARTIFACTS_DIR").mkdir(parents=True, exist_ok=True)


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
        scaler: Fitted scaler.
        path: Save path. Defaults to SCALER_PATH.
    """
    if path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
    else:
        ensure_artifacts_dir()
        path = _artifact_path("SCALER_PATH")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(scaler.to_dict(), f, indent=2)
    # C-ML-2 修复：生成 .sha256 侧车校验文件
    from app.utils.checksum import write_sha256_sidecar

    write_sha256_sidecar(path)
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
    path = Path(path) if path else _artifact_path("SCALER_PATH")
    if not path.exists():
        raise FileNotFoundError(f"Scaler not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)
    scaler = SimpleStandardScaler.from_dict(data)
    logger.info("Loaded scaler from %s", path)
    return scaler


def save_feature_names(
    feature_names: list[str], path: Path | str | None = None
) -> None:
    """Save feature names to JSON.

    Args:
        feature_names: List of feature names.
        path: Save path. Defaults to FEATURE_NAMES_PATH.
    """
    if path:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
    else:
        ensure_artifacts_dir()
        path = _artifact_path("FEATURE_NAMES_PATH")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(feature_names, f, indent=2)
    # C-ML-2 修复：生成 .sha256 侧车校验文件
    from app.utils.checksum import write_sha256_sidecar

    write_sha256_sidecar(path)
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
    path = Path(path) if path else _artifact_path("FEATURE_NAMES_PATH")
    if not path.exists():
        raise FileNotFoundError(f"Feature names not found: {path}")
    with open(path, "r", encoding="utf-8") as f:
        feature_names = json.load(f)
    logger.info("Loaded %d feature names from %s", len(feature_names), path)
    return feature_names


def scale_features(
    X: DataFrame, scaler: SimpleStandardScaler | None = None
) -> np.ndarray:
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
    logger.info(
        "Scaled features: mean=%.4f, std=%.4f", np.mean(X_scaled), np.std(X_scaled)
    )
    return X_scaled
