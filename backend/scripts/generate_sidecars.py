"""SEC-AUDIT-08: 为模型产物批量生成 .sha256 侧车校验文件.

背景: 生产/部署模型目录 (backend/models/) 中的产物 (pkl/json 等) 必须有
同目录 .sha256 侧车, app.ml.model_loader 的 _verify_integrity(require_checksum=True)
与 app.core.safe_pickle / model_engine 的哈希校验才真正生效.
此前侧车仅存在于根目录 models/ (训练产物), 部署目录缺失, 导致 P2 修复
"真实哈希校验" 在生产环境无锚点可依.

使用:
    python scripts/generate_sidecars.py [目标目录] [--cleanup] [--dry-run]

默认目标目录: backend/models (与 docker-compose 挂载的部署目录一致)

说明:
- 为所有 .pkl/.json/.md 产物生成缺失的 <file>.sha256 (sha256sum 格式)
- 已存在的侧车会重新核验: 不匹配则报错退出 (提示文件可能被篡改/侧车过期)
- --cleanup: 删除无主文件的孤立侧车 (复用 app.utils.checksum.cleanup_stale_sidecars)
- --dry-run: 只报告, 不写盘
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

# 需要侧车的产物扩展名 (与根目录 models/ 既有侧车覆盖范围一致)
_ARTIFACT_EXTS = {".pkl", ".json", ".md"}


def _compute_sha256(path: Path) -> str:
    import hashlib

    h = hashlib.sha256()
    with open(path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> int:
    parser = argparse.ArgumentParser(description="Generate .sha256 sidecars for model artifacts")
    parser.add_argument(
        "target_dir",
        nargs="?",
        default=str(Path(__file__).resolve().parents[1] / "models"),
        help="模型产物目录 (默认 backend/models)",
    )
    parser.add_argument("--cleanup", action="store_true", help="删除无主文件的孤立侧车")
    parser.add_argument("--dry-run", action="store_true", help="只报告, 不写盘")
    args = parser.parse_args()

    target = Path(args.target_dir).resolve()
    if not target.is_dir():
        print(f"错误: 目录不存在: {target}", file=sys.stderr)
        return 1

    from app.utils.checksum import cleanup_stale_sidecars, write_sha256_sidecar

    created = 0
    verified = 0
    mismatched: list[str] = []
    total_files = 0

    if args.cleanup:
        removed = cleanup_stale_sidecars(target)
        print(f"[cleanup] 已删除孤立侧车: {removed}")

    for file_path in sorted(target.rglob("*")):
        if not file_path.is_file() or file_path.suffix not in _ARTIFACT_EXTS:
            continue
        total_files += 1
        sidecar = file_path.with_suffix(file_path.suffix + ".sha256")
        computed = _compute_sha256(file_path)

        if sidecar.exists():
            expected = (
                sidecar.read_text(encoding="utf-8").strip().splitlines()[0].split()[0]
            )
            if expected == computed:
                verified += 1
                continue
            # 已存在但哈希不匹配: 文件被篡改或侧车过期, 必须人工确认
            mismatched.append(f"{file_path.relative_to(target)} (expected={expected} computed={computed})")
            continue

        if args.dry_run:
            print(f"[dry-run] 将生成: {file_path.relative_to(target)}")
            created += 1
            continue
        write_sha256_sidecar(file_path)
        created += 1

    print(
        f"完成: 目标={target} 产物文件={total_files} "
        f"新生成={created} 已核验={verified} 不匹配={len(mismatched)}"
    )
    for item in mismatched:
        print(f"  MISMATCH: {item}", file=sys.stderr)
    if mismatched:
        print("错误: 存在哈希不匹配的侧车, 请人工确认文件是否被篡改 (生产环境会拒绝加载)", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
