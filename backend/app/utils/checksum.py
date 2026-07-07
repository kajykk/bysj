"""文件 SHA256 校验工具.

提取自 app/ml/model_loader.py，用于消除 ml 模块内部的循环依赖：
- model_loader 顶层 import model / scaler
- model / scaler / data_cleaner 的 save() 方法需要 write_sha256_sidecar

原结构导致 save() 方法内 lazy import app.ml.model_loader，形成双向循环。
提取到独立 utils 模块后，所有 save() 改为顶层 import 本模块，循环消除。

C-ML-2 / P1-ML-023 / M16 / M17 修复链路详见 app/ml/model_loader.py。
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def _compute_sha256(path: Path) -> str:
    """计算文件的 SHA256 哈希值.

    Args:
        path: 文件路径.

    Returns:
        十六进制哈希字符串.
    """
    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def write_sha256_sidecar(path: Path | str) -> str:
    """为指定文件生成 .sha256 侧车校验文件.

    load_model/load_scaler/load_feature_names/load_metrics/load_cleaner 等
    加载方法均调用 _verify_integrity(path, require_checksum=True) 强制要求
    .sha256 文件存在。但对应的 save() 方法未生成校验文件，导致训练后
    直接加载会抛 ValueError: 缺少校验文件。

    本函数在 save() 末尾调用，确保保存与校验文件同步生成。

    Args:
        path: 已保存的原始文件路径.

    Returns:
        计算得到的 SHA256 哈希值.
    """
    path = Path(path)
    sha256 = _compute_sha256(path)
    checksum_path = path.with_suffix(path.suffix + ".sha256")
    # 格式：<sha256>  <filename>（兼容 sha256sum 命令输出格式）
    checksum_path.write_text(f"{sha256}  {path.name}\n", encoding="utf-8")
    logger.debug("Generated SHA256 sidecar: %s", checksum_path.name)
    return sha256
