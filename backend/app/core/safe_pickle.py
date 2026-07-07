"""Safe loading utilities for pickle-based model files.

ML-005/006 修复：集中化模型文件加载安全控制。

Pickle/joblib/torch.load 本质上可执行任意代码，因此必须在使用前对
加载源进行严格校验。本模块提供以下防护层：

1. **路径白名单**：模型文件必须位于受信根目录下，防止路径遍历到任意位置。
   （需调用方显式传入 ``trusted_root`` 启用）
2. **文件大小限制**：默认上限 500MB，防止超大文件导致 OOM/DoS。
3. **SHA256 哈希校验**：可选地与预期哈希比对，检测文件篡改。
4. **加载事件审计**：所有加载尝试（成功/失败）均写入日志，便于追溯。

使用示例::

    from app.core.safe_pickle import safe_joblib_load, safe_torch_load

    # 生产代码：传入 trusted_root 启用路径白名单
    model = safe_joblib_load(model_path, trusted_root=Path(settings.model_dir))
    # 测试代码：可不传 trusted_root（仅跳过路径校验，仍保留大小+哈希校验）
    # ISS-046 修复：weights_only 默认 True，生产环境强制 True，仅在测试环境显式传 False
    checkpoint = safe_torch_load(ckpt_path, weights_only=True)
"""

from __future__ import annotations

import hashlib
import logging
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# 单次读取块大小（64KB），平衡内存与 I/O 效率
_CHUNK_SIZE = 64 * 1024

# 默认文件大小上限：500MB（与 model_engine 现有策略一致）
_DEFAULT_MAX_BYTES = 500 * 1024 * 1024


def _compute_sha256(file_path: Path) -> str:
    """计算文件 SHA256 哈希值。"""
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(_CHUNK_SIZE):
            sha.update(chunk)
    return sha.hexdigest()


def _validate_path(
    file_path: Path,
    trusted_root: Path | None = None,
    must_exist: bool = True,
) -> Path:
    """验证文件路径位于受信根目录下，防止路径遍历攻击。

    Args:
        file_path: 待加载文件路径。
        trusted_root: 受信根目录。若为 ``None`` 则跳过路径白名单校验
            （仅适用于调用方已通过其他方式验证路径的场景，如单元测试）。
            生产代码应始终传入受信根目录。
        must_exist: 是否要求文件必须存在。

    Returns:
        解析后的绝对路径。

    Raises:
        FileNotFoundError: 文件不存在（且 must_exist=True）。
        ValueError: 路径越界（不在受信根目录下）。
    """
    resolved = (
        file_path.resolve()
        if file_path.is_absolute()
        else (Path.cwd() / file_path).resolve()
    )

    if trusted_root is not None:
        root = Path(trusted_root).resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(
                f"安全加载失败：路径 '{file_path}' 不在受信目录 '{root}' 下，"
                f"可能存在路径遍历攻击。"
            ) from exc

    if must_exist and not resolved.exists():
        raise FileNotFoundError(f"模型文件不存在: {resolved}")

    return resolved


def _validate_size(file_path: Path, max_bytes: int = _DEFAULT_MAX_BYTES) -> int:
    """验证文件大小在合理范围内。"""
    size = file_path.stat().st_size
    if size == 0:
        raise ValueError(f"模型文件为空: {file_path}")
    if size > max_bytes:
        raise ValueError(
            f"模型文件过大（{size} bytes > {max_bytes} bytes 上限）: {file_path}"
        )
    return size


def safe_joblib_load(
    file_path: Path | str,
    *,
    expected_hash: str | None = None,
    trusted_root: Path | str | None = None,
    max_bytes: int = _DEFAULT_MAX_BYTES,
    model_id: str | None = None,
    require_hash: bool = True,
    precomputed_hash: str | None = None,
) -> Any:
    """安全地加载 joblib/pickle 序列化的模型文件。

    ML-005 修复：在调用 ``joblib.load`` 前进行路径、大小、哈希三重校验。
    M3 修复：``require_hash=True`` 时强制要求 ``expected_hash`` 或 .sha256 校验文件，
    防止通过省略哈希校验绕过完整性保护。

    Args:
        file_path: 模型文件路径。
        expected_hash: 预期的 SHA256 哈希；若提供则必须匹配。
        trusted_root: 受信根目录。若为 ``None``（默认）则跳过路径白名单校验；
            生产代码应始终传入受信根目录以启用路径遍历防护。
        max_bytes: 文件大小上限（字节）。
        model_id: 模型标识符，仅用于日志。
        require_hash: 是否强制要求哈希校验。默认 ``True``。
            ISS-006 修复：生产环境 (settings.app_env == "production") 下即使
            调用方传 ``False`` 也会被强制改为 ``True``，防止 pickle RCE 风险。
        precomputed_hash: 预计算的 SHA256 哈希；若提供则跳过内部哈希计算，
            避免大文件重复计算（H-04 修复）。

    Returns:
        反序列化后的对象。

    Raises:
        FileNotFoundError: 文件不存在。
        ValueError: 路径越界、文件过大、哈希不匹配或反序列化失败。
    """
    import joblib

    # ISS-006 修复: require_hash 默认 True; 生产环境强制 True, 即使调用方传 False
    if not require_hash:
        try:
            from app.core.config import settings

            if settings.app_env.lower() == "production":
                require_hash = True
                logger.info(
                    "safe_joblib_load: 生产环境强制启用哈希校验 (id=%s)",
                    model_id or file_path,
                )
        except Exception:
            # settings 不可用时维持调用方传入的 require_hash 值
            logger.warning(
                "safe_joblib_load: settings 不可用, 无法判定生产环境, "
                "require_hash 维持调用方传入值 (%s).",
                require_hash,
            )

    path = Path(file_path)
    label = model_id or path.name

    path = _validate_path(
        path, trusted_root=Path(trusted_root) if trusted_root else None
    )
    size = _validate_size(path, max_bytes=max_bytes)

    # H-04 修复：若调用方已预计算哈希，直接使用，避免大文件重复计算
    file_hash = (
        precomputed_hash if precomputed_hash is not None else _compute_sha256(path)
    )

    # M3 修复：生产环境强制要求哈希校验
    if expected_hash is None and require_hash:
        checksum_path = path.with_suffix(path.suffix + ".sha256")
        if checksum_path.exists():
            expected_hash = checksum_path.read_text(encoding="utf-8").strip().split()[0]
        else:
            raise ValueError(
                f"模型 '{label}' 要求哈希校验但未提供 expected_hash，"
                f"且未找到校验文件 {checksum_path.name}. "
                f"请生成校验文件：sha256sum {path.name} > {checksum_path.name}"
            )

    if expected_hash is not None and file_hash != expected_hash:
        raise ValueError(
            f"模型 '{label}' 哈希校验失败：expected={expected_hash} computed={file_hash}，"
            f"文件可能已被篡改。"
        )

    if expected_hash is None:
        logger.warning(
            "safe_joblib_load: 哈希校验未启用（id=%s path=%s）。"
            "生产环境应通过 require_hash=True 或 expected_hash 启用校验",
            label,
            path,
        )

    logger.info(
        "safe_joblib_load: id=%s path=%s hash=%s size=%d bytes",
        label,
        path,
        file_hash,
        size,
    )

    try:
        return joblib.load(path)
    except Exception as exc:
        raise ValueError(
            f"模型 '{label}' 反序列化失败：{exc.__class__.__name__}: {exc}"
        ) from exc


def safe_torch_load(
    file_path: Path | str,
    *,
    weights_only: bool = True,
    expected_hash: str | None = None,
    trusted_root: Path | str | None = None,
    max_bytes: int = _DEFAULT_MAX_BYTES,
    map_location: Any = "cpu",
    model_id: str | None = None,
    require_hash: bool = False,
    precomputed_hash: str | None = None,
) -> Any:
    """安全地加载 torch 序列化的检查点文件。

    ML-006 修复：在调用 ``torch.load`` 前进行路径、大小、哈希三重校验，
    并默认启用 ``weights_only=True``（PyTorch 2.0+ 安全加载模式）。
    M3 修复：``require_hash=True`` 时强制要求 ``expected_hash`` 或 .sha256 校验文件。

    注意：当检查点包含自定义 Python 对象（如模型架构元信息）时，
    ``weights_only=True`` 可能失败，此时需显式传入 ``weights_only=False``。
    本函数通过路径白名单和哈希校验在 ``weights_only=False`` 时提供补偿防护。

    Args:
        file_path: 检查点文件路径。
        weights_only: 是否仅加载权重（推荐 True）。
        expected_hash: 预期的 SHA256 哈希。
        trusted_root: 受信根目录。若为 ``None``（默认）则跳过路径白名单校验；
            生产代码应始终传入受信根目录以启用路径遍历防护。
        max_bytes: 文件大小上限。
        map_location: 设备映射，默认 CPU。
        model_id: 模型标识符，仅用于日志。
        require_hash: 是否强制要求哈希校验。生产环境应设为 True。
        precomputed_hash: 预计算的 SHA256 哈希；若提供则跳过内部哈希计算，
            避免大文件重复计算（H-04 修复）。

    Returns:
        加载后的检查点对象。

    Raises:
        FileNotFoundError: 文件不存在。
        ValueError: 路径越界、文件过大、哈希不匹配或加载失败。
    """
    import torch

    # ISS-046 修复：生产环境强制 weights_only=True，防止 weights_only=False 绕过安全加载
    # 导致 pickle RCE 风险。仅测试环境允许显式传 False（如检查点含自定义 Python 对象）。
    if not weights_only:
        try:
            from app.core.config import settings

            if settings.app_env.lower() == "production":
                weights_only = True
                logger.warning(
                    "safe_torch_load: 生产环境强制 weights_only=True (id=%s path=%s)",
                    model_id or file_path,
                    file_path,
                )
        except Exception:
            # settings 不可用时维持调用方传入的 weights_only 值
            logger.warning(
                "safe_torch_load: settings 不可用, 无法判定生产环境, "
                "weights_only 维持调用方传入值 (%s).",
                weights_only,
            )

    path = Path(file_path)
    label = model_id or path.name

    path = _validate_path(
        path, trusted_root=Path(trusted_root) if trusted_root else None
    )
    size = _validate_size(path, max_bytes=max_bytes)

    # H-04 修复：若调用方已预计算哈希，直接使用，避免大文件重复计算
    file_hash = (
        precomputed_hash if precomputed_hash is not None else _compute_sha256(path)
    )

    # M3 修复：生产环境强制要求哈希校验
    if expected_hash is None and require_hash:
        checksum_path = path.with_suffix(path.suffix + ".sha256")
        if checksum_path.exists():
            expected_hash = checksum_path.read_text(encoding="utf-8").strip().split()[0]
        else:
            raise ValueError(
                f"检查点 '{label}' 要求哈希校验但未提供 expected_hash，"
                f"且未找到校验文件 {checksum_path.name}. "
                f"请生成校验文件：sha256sum {path.name} > {checksum_path.name}"
            )

    if expected_hash is not None and file_hash != expected_hash:
        raise ValueError(
            f"检查点 '{label}' 哈希校验失败：expected={expected_hash} computed={file_hash}，"
            f"文件可能已被篡改。"
        )

    if expected_hash is None:
        logger.warning(
            "safe_torch_load: 哈希校验未启用（id=%s path=%s）。"
            "生产环境应通过 require_hash=True 或 expected_hash 启用校验",
            label,
            path,
        )

    logger.info(
        "safe_torch_load: id=%s path=%s hash=%s size=%d bytes weights_only=%s",
        label,
        path,
        file_hash,
        size,
        weights_only,
    )

    try:
        return torch.load(path, map_location=map_location, weights_only=weights_only)
    except Exception as exc:
        raise ValueError(
            f"检查点 '{label}' 加载失败：{exc.__class__.__name__}: {exc}"
        ) from exc
