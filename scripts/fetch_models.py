"""一键获取模型/数据产物（P1 可复现性）。

背景：models/、datasets/、data/ 因体积（1.4GB+）被 .gitignore 排除，
clone 后无法直接训练/推理。本脚本按 MANIFEST 拉取产物并校验 sha256，
支持最小种子模式（--seed-only，仅拉取生产推理必需的最小产物集）。

用法：
    python scripts/fetch_models.py --manifest scripts/artifacts.manifest.json
    python scripts/fetch_models.py --seed-only
"""
from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.request
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST = REPO_ROOT / "scripts" / "artifacts.manifest.json"
CHUNK = 1024 * 256


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def fetch_one(url: str | None, dest: Path, sha256: str | None) -> bool:
    dest.parent.mkdir(parents=True, exist_ok=True)
    if dest.exists() and sha256 and sha256_of(dest) == sha256:
        print(f"[ok] cached {dest}")
        return True
    if not url:
        # manifest 由 generate_manifest.py 生成但尚未填发布地址：
        # 按本地校验模式工作——文件缺失或校验失败即报错并指引放置位置。
        if not dest.exists():
            print(
                f"[missing] {dest} 不存在。请从发布页获取后放到该路径，"
                "或运行 python scripts/generate_manifest.py 重新生成 manifest。",
                file=sys.stderr,
            )
        else:
            print(f"[fail] checksum mismatch: {dest}", file=sys.stderr)
        return False
    print(f"[fetch] {url} -> {dest}")
    try:
        urllib.request.urlretrieve(url, dest)
    except Exception as exc:  # noqa: BLE001 - CLI 脚本：打印错误并继续下一项
        print(f"[fail] {url}: {exc}", file=sys.stderr)
        return False
    if sha256 and sha256_of(dest) != sha256:
        print(f"[fail] checksum mismatch: {dest}", file=sys.stderr)
        return False
    print(f"[ok] {dest}")
    return True


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--manifest", default=str(DEFAULT_MANIFEST))
    ap.add_argument("--seed-only", action="store_true")
    args = ap.parse_args()

    manifest_path = Path(args.manifest)
    if not manifest_path.exists():
        print(
            "[warn] manifest 不存在（离线/最小检出时属正常）: "
            f"{manifest_path}\n"
            "生产推理最小产物 = backend/models 下 LR v1.23 管道 + TF-IDF 向量化器；"
            "请从发布页/内部存储手动放置后重跑本脚本做校验。",
            file=sys.stderr,
        )
        return 2
    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    items = manifest.get("artifacts", [])
    if args.seed_only:
        items = [i for i in items if i.get("seed", False)]
    failed = 0
    for item in items:
        ok = fetch_one(
            item["url"], REPO_ROOT / item["dest"], item.get("sha256")
        )
        failed += 0 if ok else 1
    print(f"done: {len(items) - failed}/{len(items)} ok")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
