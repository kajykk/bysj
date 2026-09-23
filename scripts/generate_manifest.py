"""从本地产物生成 artifacts.manifest.json（第 3 步）。

扫描生产最小种子集（backend/models 下 LR v1.23 / TF-IDF / structured），
优先读取同目录 .sha256 sidecar（`sha256sum` 格式），缺失则现场计算。
`url` 填 null 占位——填入真实发布地址后 fetch_models.py 即有下载能力；
在此之前脚本按"本地校验"模式工作：已存在且校验通过即 ok。

用法：python scripts/generate_manifest.py
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND_MODELS = REPO_ROOT / "backend" / "models"
OUT = REPO_ROOT / "scripts" / "artifacts.manifest.json"
CHUNK = 1024 * 256

# 生产推理最小种子集（与 MODEL_REGISTRY.md 生产表对应）
SEED_FILES = [
    "v1.23_external_lr/model.pkl",
    "v1.23_external_lr/preprocessor.pkl",
    "v1.23_external_lr/feature_schema.json",
    "v1.23_external_lr/threshold_config.json",
    "v1.23_external_lr/metrics.json",
    "v1.23_external_lr/calibration_config.json",
    "text/improved_bilingual_model.pkl",
    "text/improved_bilingual_tfidf.pkl",
    "structured/Logistic_Regression_quick.pkl",
]


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(CHUNK), b""):
            h.update(chunk)
    return h.hexdigest()


def main() -> None:
    artifacts = []
    for rel in SEED_FILES:
        src = BACKEND_MODELS / rel
        if not src.exists():
            print(f"[skip] 缺失: {rel}")
            continue
        sidecar = src.with_name(src.name + ".sha256")
        sha = None
        if sidecar.exists():
            sha = sidecar.read_text(encoding="utf-8").split()[0]
        if not sha:
            sha = sha256_of(src)
        artifacts.append(
            {
                "dest": f"backend/models/{rel}",
                "sha256": sha,
                "bytes": src.stat().st_size,
                "seed": True,
                # TODO(第3步收尾): 填入发布地址后 fetch_models.py 即有下载能力，
                # 例 "url": "https://github.com/<org>/<repo>/releases/download/models-v3.1.0/model.pkl"
                "url": None,
            }
        )
        print(f"[ok] {rel} sha256={sha[:12]}... {src.stat().st_size}B")
    OUT.write_text(
        json.dumps(
            {
                "_comment": "url 为 null 表示尚未发布到外部存储；fetch_models 会校验本地文件并提示放置位置。",
                "artifacts": artifacts,
            },
            indent=2,
            ensure_ascii=False,
        )
        + "\n",
        encoding="utf-8",
    )
    print(f"written: {OUT} ({len(artifacts)} artifacts)")


if __name__ == "__main__":
    main()
