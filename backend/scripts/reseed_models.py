"""P0-1.5: 模型重序列化脚本

将所有 .pkl 模型文件用当前环境 (joblib 1.5.3 + sklearn 1.8.0) 重新序列化，
消除 InconsistentVersionWarning 并确保 Python 3.14 兼容性。

操作步骤:
1. 遍历 models/ 下所有 .pkl 文件
2. 用 joblib.load 加载 (允许版本不匹配警告)
3. 用 joblib.dump 重新序列化 (写入临时文件后原子替换)
4. 若存在 .sha256 sidecar 文件则更新哈希值

使用:
    cd backend
    python reseed_models.py            # 预演 (dry-run)
    python reseed_models.py --apply    # 实际执行
"""
from __future__ import annotations

import argparse
import hashlib
import shutil
import sys
import warnings
from pathlib import Path

# 抑制 sklearn 版本不匹配警告 (重序列化过程中预期会出现)
warnings.filterwarnings("ignore", category=UserWarning, module="sklearn.*")
warnings.filterwarnings("ignore", message=".*InconsistentVersionWarning.*")

import joblib

BACKEND_DIR = Path(__file__).resolve().parents[1]
MODELS_DIR = BACKEND_DIR / "models"
CHUNK_SIZE = 64 * 1024

# v1.24_adapter/score_adapter.pkl 在序列化时类定义位于 __main__ 命名空间
# (训练脚本以 python 04_train_adapter.py 方式运行)。
# 反序列化时 pickle 会查找 __main__.ScoreAdapter，因此需要将其注入当前 __main__。
import importlib.util as _importlib_util

_adapter_spec = _importlib_util.spec_from_file_location(
    "_v124_adapter_train",
    BACKEND_DIR / "scripts" / "modeling" / "v1_24" / "04_train_adapter.py",
)
if _adapter_spec is not None and _adapter_spec.loader is not None:
    _adapter_mod = _importlib_util.module_from_spec(_adapter_spec)
    _adapter_spec.loader.exec_module(_adapter_mod)
    # 注入到 __main__ 命名空间，使 pickle 反序列化可找到 ScoreAdapter
    import __main__ as _main_module
    _main_module.ScoreAdapter = _adapter_mod.ScoreAdapter  # type: ignore[attr-defined]
    # 重写 __module__ 为 __main__，使重新序列化后仍保持 __main__.ScoreAdapter 引用
    # (与原始 pickle 格式一致，避免加载时再次找不到类)
    _adapter_mod.ScoreAdapter.__module__ = "__main__"


def compute_sha256(file_path: Path) -> str:
    sha = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(CHUNK_SIZE):
            sha.update(chunk)
    return sha.hexdigest()


def reseed_one(pkl_path: Path, apply: bool) -> tuple[bool, str]:
    """重序列化单个 .pkl 文件，返回 (是否变更, 消息)。"""
    rel = pkl_path.relative_to(BACKEND_DIR)
    try:
        # 用当前环境加载旧格式文件
        obj = joblib.load(pkl_path)
    except Exception as exc:
        return False, f"加载失败: {exc.__class__.__name__}: {exc}"

    # 写入临时文件
    tmp_path = pkl_path.with_suffix(pkl_path.suffix + ".tmp")
    try:
        joblib.dump(obj, tmp_path, compress=3)
    except Exception as exc:
        if tmp_path.exists():
            tmp_path.unlink()
        return False, f"序列化失败: {exc.__class__.__name__}: {exc}"

    # 计算新旧哈希
    old_hash = compute_sha256(pkl_path)
    new_hash = compute_sha256(tmp_path)
    size_before = pkl_path.stat().st_size
    size_after = tmp_path.stat().st_size

    if not apply:
        tmp_path.unlink()
        return True, (
            f"[DRY-RUN] {rel}: 旧 {size_before}B/{old_hash[:8]} -> "
            f"新 {size_after}B/{new_hash[:8]}"
        )

    # 原子替换
    backup_path = pkl_path.with_suffix(pkl_path.suffix + ".bak")
    if backup_path.exists():
        backup_path.unlink()
    shutil.move(str(pkl_path), str(backup_path))
    shutil.move(str(tmp_path), str(pkl_path))

    # 更新 .sha256 sidecar 文件
    sidecar = pkl_path.with_suffix(pkl_path.suffix + ".sha256")
    if sidecar.exists():
        sidecar.write_text(f"{new_hash}  {pkl_path.name}\n", encoding="utf-8")
        sidecar_msg = f" (已更新 {sidecar.name})"
    else:
        sidecar_msg = ""

    # 清理备份
    backup_path.unlink()

    return True, (
        f"[APPLIED]  {rel}: {size_before}B -> {size_after}B "
        f"hash={new_hash[:8]}{sidecar_msg}"
    )


def main() -> int:
    parser = argparse.ArgumentParser(description="重序列化 .pkl 模型文件")
    parser.add_argument("--apply", action="store_true", help="实际执行 (默认 dry-run)")
    args = parser.parse_args()

    if not MODELS_DIR.exists():
        print(f"错误: 模型目录不存在: {MODELS_DIR}")
        return 1

    pkl_files = sorted(MODELS_DIR.rglob("*.pkl"))
    if not pkl_files:
        print(f"错误: 未找到任何 .pkl 文件于 {MODELS_DIR}")
        return 1

    print(f"模式: {'APPLY (实际执行)' if args.apply else 'DRY-RUN (预演)'}")
    print(f"找到 {len(pkl_files)} 个 .pkl 文件")
    print(f"环境: joblib={joblib.__version__}")
    import sklearn
    print(f"       sklearn={sklearn.__version__}")
    print("-" * 70)

    success, failed = 0, 0
    for pkl in pkl_files:
        ok, msg = reseed_one(pkl, apply=args.apply)
        print(msg)
        if ok:
            success += 1
        else:
            failed += 1

    print("-" * 70)
    print(f"成功: {success}  失败: {failed}")
    if not args.apply and success > 0:
        print("\n这是预演结果。若确认无误，运行: python reseed_models.py --apply")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
