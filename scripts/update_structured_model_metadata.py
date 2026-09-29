from __future__ import annotations

import json
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SOURCE = ROOT / "model_assessment" / "structured_run" / "metrics.json"
TARGET = ROOT / "models" / "artifacts" / "depression_tabular" / "metadata.json"


def main() -> None:
    payload = json.loads(SOURCE.read_text(encoding="utf-8"))
    metadata = {
        "model_id": "structured_logistic_regression_quick",
        "dataset": payload.get("dataset"),
        "target": payload.get("target"),
        "best": payload.get("best"),
        "best_metrics": payload.get("best_metrics"),
        "source_metrics_path": str(SOURCE),
        "updated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
    }
    TARGET.write_text(json.dumps(metadata, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps(metadata, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
