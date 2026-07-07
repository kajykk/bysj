from __future__ import annotations

import json
import logging
from pathlib import Path
from typing import TYPE_CHECKING

import numpy as np

from app.ml.model import PhysiologicalMLP
from app.ml.scaler import SimpleStandardScaler

if TYPE_CHECKING:
    from app.ml.data_cleaner import DataCleaner
# 治理循环依赖：write_sha256_sidecar / _compute_sha256 提取到 app.utils.checksum，
# 避免 ml.{model,scaler,data_cleaner}.save() 反向 lazy import 本模块形成环。
from app.utils.checksum import _compute_sha256
from app.utils.checksum import write_sha256_sidecar as write_sha256_sidecar

logger = logging.getLogger(__name__)

# Artifact paths
ARTIFACTS_DIR = (
    Path(__file__).resolve().parent.parent.parent.parent
    / "models"
    / "artifacts"
    / "physiological_optimized"
)
MODEL_PATH = ARTIFACTS_DIR / "model.json"
SCALER_PATH = ARTIFACTS_DIR / "scaler.json"
FEATURE_NAMES_PATH = ARTIFACTS_DIR / "feature_names.json"
METRICS_PATH = ARTIFACTS_DIR / "metrics.json"
# P1-ML-005 修复：DataCleaner 统计量文件路径
CLEANER_STATS_PATH = ARTIFACTS_DIR / "cleaner_stats.json"


def _verify_integrity(
    path: Path, expected_sha256: str | None = None, require_checksum: bool = False
) -> None:
    """校验文件完整性.

    P1-ML-023 修复：加载模型前验证文件未被篡改.
    M16/M17 修复：对关键文件强制要求 .sha256 校验文件存在，防止通过删除校验文件绕过完整性校验.

    Args:
        path: 文件路径.
        expected_sha256: 期望的 SHA256 哈希值. 如果为 None, 则尝试读取同名 .sha256 文件.
        require_checksum: 是否强制要求 .sha256 校验文件存在. 生产环境对关键文件应设为 True.

    Raises:
        ValueError: 如果校验失败或校验文件缺失（当 require_checksum=True 时）.
    """
    if expected_sha256 is None:
        checksum_path = path.with_suffix(path.suffix + ".sha256")
        if not checksum_path.exists():
            if require_checksum:
                # M16 修复：关键文件强制要求校验文件存在，防止通过删除 .sha256 绕过校验
                raise ValueError(
                    f"文件完整性校验失败: {path.name} 缺少校验文件 {checksum_path.name}. "
                    f"请使用 'sha256sum {path.name} > {checksum_path.name}' 生成校验文件."
                )
            # 非关键文件：没有校验文件时跳过校验（向后兼容）
            logger.warning(
                "完整性校验跳过: %s 缺少 .sha256 校验文件，建议生成以确保文件未被篡改",
                path.name,
            )
            return
        expected_sha256 = checksum_path.read_text(encoding="utf-8").strip().split()[0]

    actual_sha256 = _compute_sha256(path)
    if actual_sha256 != expected_sha256:
        raise ValueError(
            f"文件完整性校验失败: {path.name}. "
            f"期望 SHA256={expected_sha256[:16]}..., 实际 SHA256={actual_sha256[:16]}..."
        )
    logger.debug("完整性校验通过: %s", path.name)


def check_model_exists() -> bool:
    """Check if model artifacts exist.

    Returns:
        True if all required files exist.
    """
    # M-ML-7 修复：增加 CLEANER_STATS_PATH 检查，推理时依赖 cleaner 统计量做特征工程，
    # 缺失会导致 transform_single 无法复用训练时填充/Winsorization 参数
    # 修订：cleaner_stats.json 为可选——_predict_physiological_sync 在缺失时
    # 回退到固定生理阈值裁剪（EXTREME_THRESHOLDS），仍可正常推理。
    # 仅 model/scaler/feature_names 为强依赖。
    required_files = [MODEL_PATH, SCALER_PATH, FEATURE_NAMES_PATH]
    exists = all(f.exists() for f in required_files)
    if not exists:
        missing = [f.name for f in required_files if not f.exists()]
        logger.warning("Model artifacts missing: %s", missing)
    if not CLEANER_STATS_PATH.exists():
        # 仅记录日志，不视为不可用——加载逻辑已有 fallback
        logger.info(
            "Optional cleaner_stats.json missing, will use EXTREME_THRESHOLDS fallback"
        )
    return exists


def load_model(path: Path | str | None = None) -> PhysiologicalMLP:
    """Load trained model from JSON.

    Args:
        path: Path to model.json. Defaults to MODEL_PATH.

    Returns:
        Loaded PhysiologicalMLP model.

    Raises:
        FileNotFoundError: If model file does not exist.
        ValueError: If integrity check fails.
    """
    path = Path(path) if path else MODEL_PATH
    if not path.exists():
        raise FileNotFoundError(f"Model not found: {path}")

    # P1-ML-023 修复：加载前校验文件完整性
    # M16 修复：模型文件是关键文件，强制要求 .sha256 校验文件存在
    _verify_integrity(path, require_checksum=True)

    with open(path, "r", encoding="utf-8") as f:
        try:
            model_data = json.load(f)
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in model file {path}: {e}") from e

    # Create model
    model = PhysiologicalMLP(
        input_dim=model_data["input_dim"],
        hidden_dims=model_data["hidden_dims"],
        dropout_rate=model_data["dropout_rate"],
        use_batch_norm=model_data.get("use_batch_norm", False),
    )

    # Load weights
    for i, layer_data in enumerate(model_data["layers"]):
        model.layers[i]["W"] = np.array(layer_data["W"], dtype=np.float32)
        model.layers[i]["b"] = np.array(layer_data["b"], dtype=np.float32)
        if "bn_gamma" in layer_data:
            model.layers[i]["bn_gamma"] = np.array(
                layer_data["bn_gamma"], dtype=np.float32
            )
            model.layers[i]["bn_beta"] = np.array(
                layer_data["bn_beta"], dtype=np.float32
            )
            model.layers[i]["bn_running_mean"] = np.array(
                layer_data["bn_running_mean"], dtype=np.float32
            )
            model.layers[i]["bn_running_var"] = np.array(
                layer_data["bn_running_var"], dtype=np.float32
            )

    logger.info("Loaded model from %s", path)
    return model


def load_scaler(path: Path | str | None = None) -> SimpleStandardScaler:
    """Load fitted scaler from JSON.

    Args:
        path: Path to scaler.json. Defaults to SCALER_PATH.

    Returns:
        Loaded SimpleStandardScaler.

    Raises:
        FileNotFoundError: If scaler file does not exist.
        ValueError: If integrity check fails.
    """
    path = Path(path) if path else SCALER_PATH
    if not path.exists():
        raise FileNotFoundError(f"Scaler not found: {path}")

    # M17 修复：scaler 的均值/方差直接影响推理结果，必须校验完整性
    _verify_integrity(path, require_checksum=True)

    with open(path, "r", encoding="utf-8") as f:
        data = json.load(f)

    scaler = SimpleStandardScaler.from_dict(data)
    logger.info("Loaded scaler from %s", path)
    return scaler


def load_feature_names(path: Path | str | None = None) -> list[str]:
    """Load feature names from JSON.

    Args:
        path: Path to feature_names.json. Defaults to FEATURE_NAMES_PATH.

    Returns:
        List of feature names.

    Raises:
        FileNotFoundError: If feature names file does not exist.
        ValueError: If integrity check fails.
    """
    path = Path(path) if path else FEATURE_NAMES_PATH
    if not path.exists():
        raise FileNotFoundError(f"Feature names not found: {path}")

    # M17/H-9 修复：feature_names 决定特征顺序，被篡改会导致模型输入错位。
    # 与 load_model/load_scaler/load_cleaner 保持一致，强制要求 checksum 校验。
    _verify_integrity(path, require_checksum=True)

    with open(path, "r", encoding="utf-8") as f:
        feature_names = json.load(f)

    logger.info("Loaded %d feature names from %s", len(feature_names), path)
    return feature_names


def load_metrics(path: Path | str | None = None) -> dict:
    """Load model metrics from JSON.

    Args:
        path: Path to metrics.json. Defaults to METRICS_PATH.

    Returns:
        Dictionary with model metrics.

    Raises:
        FileNotFoundError: If metrics file does not exist.
    """
    path = Path(path) if path else METRICS_PATH
    if not path.exists():
        raise FileNotFoundError(f"Metrics not found: {path}")

    # M17/H-9 修复：metrics 文件也需校验完整性，防止被篡改误导模型评估。
    # 与 load_model/load_scaler/load_cleaner 保持一致，强制要求 checksum 校验。
    _verify_integrity(path, require_checksum=True)

    with open(path, "r", encoding="utf-8") as f:
        metrics = json.load(f)

    logger.info("Loaded metrics from %s", path)
    return metrics


def load_all_artifacts() -> (
    tuple[PhysiologicalMLP, SimpleStandardScaler, list[str], dict]
):
    """Load all model artifacts.

    Returns:
        Tuple of (model, scaler, feature_names, metrics).

    Raises:
        FileNotFoundError: If any artifact is missing.
    """
    model = load_model()
    scaler = load_scaler()
    feature_names = load_feature_names()
    metrics = load_metrics()
    return model, scaler, feature_names, metrics


def load_cleaner(path: Path | str | None = None) -> "DataCleaner":
    """P1-ML-005 修复：加载训练时的 DataCleaner 统计量。

    用于推理时严格复用训练时的缺失值填充中位数和 Winsorization 边界，
    确保特征工程一致性。

    Args:
        path: Path to cleaner_stats.json. Defaults to CLEANER_STATS_PATH.

    Returns:
        Loaded DataCleaner instance (fitted).

    Raises:
        FileNotFoundError: If cleaner stats file does not exist.
        ValueError: If integrity check fails.
    """
    from app.ml.data_cleaner import DataCleaner

    path = Path(path) if path else CLEANER_STATS_PATH
    if not path.exists():
        raise FileNotFoundError(f"Cleaner stats not found: {path}")

    # M24 修复：cleaner_stats 包含训练集中位数和 Winsorization 边界，
    # 直接影响推理时的特征工程，必须校验完整性
    _verify_integrity(path, require_checksum=True)

    cleaner = DataCleaner()
    cleaner.load(path)
    return cleaner
