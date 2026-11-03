"""生成部署必需制品的清单（含 sha256），供启动期完整性校验使用。

用法（在 backend/ 下）：
    .venv/Scripts/python.exe scripts/artifact_manifest.py

产物：backend/models/DEPLOYMENT_MANIFEST.json
    - schema: dws-deployment-artifacts/v1
    - 每条含 model_id / path / bytes / sha256
清单需与制品一同分发；启动期 audit_deployment_artifacts 依据它判定
missing / hash_mismatch / unverified（生产失败即拒绝启动）。
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.model_registry import (  # noqa: E402
    DEPLOYMENT_MANIFEST_FILENAME,
    build_deployment_manifest,
)


def main() -> int:
    models_dir = BACKEND_ROOT / "models"
    manifest = build_deployment_manifest(models_dir)
    output = models_dir / DEPLOYMENT_MANIFEST_FILENAME
    output.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    print(f"wrote {output} ({len(manifest['artifacts'])} artifacts)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
