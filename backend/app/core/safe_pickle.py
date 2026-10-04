"""Safe loading utilities for pickle-based model files.

ML-005/006 修复：集中化模型文件加载安全控制。

Pickle/joblib/torch.load 本质上可执行任意代码，因此必须在使用前对
加载源进行严格校验。本模块提供以下防护层：

1. **路径白名单**：模型文件必须位于受信根目录下，防止路径遍历到任意位置。
   （需调用方显式传入 ``trusted_root`` 启用）
2. **文件大小限制**：默认上限 500MB，防止超大文件导致 OOM/DoS。
3. **SHA256 哈希校验**：可选地与预期哈希比对，检测文件篡改。
4. **加载事件审计**：所有加载尝试（成功/失败）均写入日志，便于追溯。
5. **反序列化类白名单**（AUDIT-2026-10-01 / P0-2）：受限 Unpickler 只放行
   numpy/scipy/sklearn/joblib/xgboost/catboost/torch 等预期模块，把"pickle 任意
   代码执行"降级为"加载失败"。前三层只保证"加载的是预期文件"，本层才管"文件内容
   不会执行任意代码"—— 二者不可互相替代。

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
    resolved = file_path.resolve() if file_path.is_absolute() else (Path.cwd() / file_path).resolve()

    if trusted_root is not None:
        root = Path(trusted_root).resolve()
        try:
            resolved.relative_to(root)
        except ValueError as exc:
            raise ValueError(
                f"安全加载失败：路径 '{file_path}' 不在受信目录 '{root}' 下，" f"可能存在路径遍历攻击。"
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
        raise ValueError(f"模型文件过大（{size} bytes > {max_bytes} bytes 上限）: {file_path}")
    return size


def _validated_model_file(
    file_path: Path | str,
    *,
    trusted_root: Path | str | None,
    max_bytes: int,
    model_id: str | None,
    require_hash: bool,
    expected_hash: str | None,
    precomputed_hash: str | None,
    kind: str,
) -> tuple[Path, int, str, str | None]:
    """OPT-A5（M-5 修复）：safe_joblib_load / safe_torch_load 共享的加载前置校验。

    路径白名单 → 大小限制 → SHA256 计算（或复用预计算值）→ .sha256 校验文件
    解析 → 哈希比对。原实现两处约 45 行逐行复制，修 bug 需双写，收敛于此。

    Args:
        kind: 错误消息中的对象称谓（"模型" / "检查点"），保持既有文案不变。

    Returns:
        (解析后路径, 文件大小, 计算哈希, 生效的预期哈希)。
    """
    path = Path(file_path)
    label = model_id or path.name

    path = _validate_path(path, trusted_root=Path(trusted_root) if trusted_root else None)
    size = _validate_size(path, max_bytes=max_bytes)

    # H-04 修复：若调用方已预计算哈希，直接使用，避免大文件重复计算
    file_hash = precomputed_hash if precomputed_hash is not None else _compute_sha256(path)

    # M3 修复：生产环境强制要求哈希校验
    if expected_hash is None and require_hash:
        checksum_path = path.with_suffix(path.suffix + ".sha256")
        if checksum_path.exists():
            expected_hash = checksum_path.read_text(encoding="utf-8").strip().split()[0]
        else:
            raise ValueError(
                f"{kind} '{label}' 要求哈希校验但未提供 expected_hash，"
                f"且未找到校验文件 {checksum_path.name}. "
                f"请生成校验文件：sha256sum {path.name} > {checksum_path.name}"
            )

    if expected_hash is not None and file_hash != expected_hash:
        raise ValueError(
            f"{kind} '{label}' 哈希校验失败：expected={expected_hash} computed={file_hash}，" f"文件可能已被篡改。"
        )

    return path, size, file_hash, expected_hash


class ModelUnpicklingError(ValueError):
    """模型文件引用了不在白名单内的全局对象，已拒绝反序列化。

    AUDIT-2026-10-01 (P0-2)：pickle 的 ``GLOBAL`` / ``STACK_GLOBAL`` 操作码可以引用
    **任意可调用对象**，因此 ``joblib.load`` 等价于执行文件中的字节码。原先的
    路径白名单 / 大小上限 / SHA256 三层防护都防不住这一本质风险 —— 它们只保证
    "加载的是预期的那个文件"，不保证"文件内容不会执行任意代码"。
    """


# ── 反序列化白名单（AUDIT-2026-10-01 / P0-2）────────────────────────────
#
# 设计依据（数据驱动，非猜测）：用收集式 Unpickler 扫过仓库中全部真实模型工件
# （models/ 与 model_assessment/，51 个候选、49 个可解析），导出了实际被引用的
# 模块集合：numpy / scipy / sklearn / joblib / xgboost / catboost / _codecs /
# _loss / collections / builtins(slice,bytearray) + 本项目自有的 app.*。
#
# 放行策略：对 ML 库按**模块前缀**放行（含子模块），使重新训练后出现的**新模型类**
# 不会因为白名单过窄而加载失败；对 ``builtins`` 则收紧到具体名字。
#
# 明确的能力边界（不做过度承诺）：本白名单拦的是经典的
# ``os.system`` / ``builtins.eval`` / ``subprocess.Popen`` / ``ctypes`` 一类直接 RCE；
# 它**不能**防御"利用放行库内部既有可调用对象拼装 gadget"的高级攻击。
# 这类攻击需要更强的沙箱（子进程 + seccomp/容器隔离），不在本次改动范围内。
_ALLOWED_MODULE_PREFIXES: tuple[str, ...] = (
    "numpy",
    "scipy",
    "sklearn",
    "pandas",
    "joblib",
    "xgboost",
    "lightgbm",
    "catboost",
    "torch",
    "collections",
    "copyreg",
    "_codecs",
    "_loss",
    "app",  # 本项目自有类（如 app.core.score_adapter.ScoreAdapter）
)

#: ``builtins`` 中只放行基础容器/标量类型与切片对象（实测仅需 slice / bytearray）。
#: **不放行** eval / exec / compile / __import__ / open / globals / locals / getattr 等。
_ALLOWED_BUILTINS: frozenset[str] = frozenset(
    {
        "bytearray",
        "bytes",
        "slice",
        "str",
        "int",
        "float",
        "complex",
        "bool",
        "list",
        "dict",
        "set",
        "frozenset",
        "tuple",
        "object",
        "type",
        "NoneType",
        "range",
    }
)

#: 跨模块统一拒绝的高危名字（纵深防御：即使模块前缀命中也不放行）。
_DENIED_GLOBAL_NAMES: frozenset[str] = frozenset(
    {
        "eval",
        "exec",
        "execfile",
        "compile",
        "__import__",
        "system",
        "popen",
        "Popen",
        "spawn",
        "spawnl",
        "spawnv",
        "spawnve",
        "fork",
        "execv",
        "execve",
        "execl",
        "execlp",
        "check_output",
        "check_call",
        "call_command",
        "fromfile",
        "loadtxt",
        "genfromtxt",
        "memmap",
    }
)


def is_allowed_global(module: str, name: str) -> bool:
    """判断 ``(module, name)`` 是否在反序列化白名单内。"""
    if not isinstance(module, str) or not isinstance(name, str):
        return False
    if name in _DENIED_GLOBAL_NAMES:
        return False
    if module in ("builtins", "__builtin__"):
        return name in _ALLOWED_BUILTINS
    for prefix in _ALLOWED_MODULE_PREFIXES:
        if module == prefix or module.startswith(prefix + "."):
            return True
    return False


_restricted_unpickler_cls: type | None = None
_restricted_unpickler_probed = False


def _restricted_unpickler_class() -> type | None:
    """构造受限的 joblib ``NumpyUnpickler`` 子类。

    joblib 使用自带的 ``NumpyUnpickler``（其 ``find_class`` 源码注明
    "Subclasses may override this."）来重建 numpy 数组，所以**必须**继承它而不是
    ``pickle.Unpickler`` —— 实测仓库内有 8 个工件是 joblib 压缩格式，裸
    ``pickle.Unpickler`` 直接报 ``invalid load key``。

    注意：**只缓存成功结果**。早先版本用 ``@lru_cache`` 连失败一起缓存，导致一次
    导入失败会让白名单在进程内**永久失效**（实测：这会退化成执行任意 pickle 载荷）。

    Returns:
        受限 Unpickler 类；joblib 不可用时返回 ``None``（由调用方 fail-closed 拒绝加载）。
    """
    global _restricted_unpickler_cls, _restricted_unpickler_probed
    if _restricted_unpickler_probed:
        return _restricted_unpickler_cls
    try:
        from joblib.numpy_pickle import NumpyUnpickler
    except Exception as exc:  # noqa: BLE001
        logger.error("无法导入 joblib.NumpyUnpickler，反序列化白名单不可用: %s", exc)
        return None

    class _RestrictedNumpyUnpickler(NumpyUnpickler):  # type: ignore[misc,valid-type]
        """只允许白名单内全局对象的 NumpyUnpickler。"""

        def find_class(self, module: str, name: str) -> Any:
            if not is_allowed_global(module, name):
                logger.error(
                    "反序列化被拒绝：模型文件引用了非白名单对象 %s.%s", module, name
                )
                raise ModelUnpicklingError(
                    f"模型文件引用了不在白名单内的对象 {module}.{name}；"
                    "已拒绝反序列化（pickle GLOBAL 可执行任意代码）。"
                    "若这是重新训练后新增的合法模型类，请把它所属模块加入 "
                    "app/core/safe_pickle.py 的 _ALLOWED_MODULE_PREFIXES。"
                )
            return super().find_class(module, name)

    _restricted_unpickler_cls = _RestrictedNumpyUnpickler
    _restricted_unpickler_probed = True
    return _restricted_unpickler_cls


def _restricted_joblib_load(path: Path, label: str) -> Any:
    """用受限 Unpickler 加载 joblib 工件（保持与 ``joblib.load`` 相同的解压路径）。

    复刻 ``joblib.numpy_pickle.load`` 的流程：先经
    ``_validate_fileobject_and_memmap`` 完成压缩探测/解压，再把解压后的文件对象交给
    受限 Unpickler。这样既保留了 joblib 对 numpy 数组的特殊重建逻辑，又施加了白名单。

    **fail-closed**：若白名单无法施加（joblib 内部 API 变更/缺失），一律拒绝加载并说明
    原因 —— 绝不静默退回无白名单的 ``joblib.load``。实测过退回的后果：恶意载荷会被真的执行。
    """
    import joblib

    unpickler_cls = _restricted_unpickler_class()
    try:
        import joblib.numpy_pickle as jnp
    except Exception:  # noqa: BLE001
        jnp = None
    validate = getattr(jnp, "_validate_fileobject_and_memmap", None) if jnp is not None else None

    if unpickler_cls is None or validate is None:
        raise RuntimeError(
            "无法施加反序列化白名单：joblib 内部 API 不可用"
            f"（id={label}, joblib={getattr(joblib, '__version__', '?')}）。"
            "出于安全考虑拒绝加载模型，而不是退回无白名单的 joblib.load。"
            "请确认 joblib 版本未被降级/替换。"
        )

    filename = str(path)
    with open(filename, "rb") as fh:
        with validate(fh, filename, None) as (fobj, _mmap_mode):
            if isinstance(fobj, str):
                # joblib < 0.10 的旧格式（sidecar 文件），无法施加白名单 → fail-closed
                raise RuntimeError(
                    f"工件 {label} 使用 joblib < 0.10 的旧格式，无法施加反序列化白名单；"
                    "出于安全考虑拒绝加载，请用当前版本重新生成该工件。"
                )
            return unpickler_cls(filename, fobj, True).load()


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
                "safe_joblib_load: settings 不可用, 无法判定生产环境, " "require_hash 维持调用方传入值 (%s).",
                require_hash,
            )

    path, size, file_hash, expected_hash = _validated_model_file(
        file_path,
        trusted_root=trusted_root,
        max_bytes=max_bytes,
        model_id=model_id,
        require_hash=require_hash,
        expected_hash=expected_hash,
        precomputed_hash=precomputed_hash,
        kind="模型",
    )
    label = model_id or path.name

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
        return _restricted_joblib_load(path, label)
    except ModelUnpicklingError:
        # 白名单拒绝：语义上属于安全事件，原样上抛，不再包装成"反序列化失败"
        raise
    except Exception as exc:
        raise ValueError(f"模型 '{label}' 反序列化失败：{exc.__class__.__name__}: {exc}") from exc


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
                "safe_torch_load: settings 不可用, 无法判定生产环境, " "weights_only 维持调用方传入值 (%s).",
                weights_only,
            )

    path, size, file_hash, expected_hash = _validated_model_file(
        file_path,
        trusted_root=trusted_root,
        max_bytes=max_bytes,
        model_id=model_id,
        require_hash=require_hash,
        expected_hash=expected_hash,
        precomputed_hash=precomputed_hash,
        kind="检查点",
    )
    label = model_id or path.name

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
        return torch.load(path, map_location=map_location, weights_only=weights_only)  # nosec B614  controlled load with weights_only flag
    except Exception as exc:
        raise ValueError(f"检查点 '{label}' 加载失败：{exc.__class__.__name__}: {exc}") from exc
