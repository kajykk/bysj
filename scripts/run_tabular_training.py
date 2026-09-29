from __future__ import annotations

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def main() -> None:
    cmd = [
        sys.executable,
        str(ROOT / "scripts" / "ml_training" / "train_tabular.py"),
        "--dataset",
        str(ROOT / "datasets" / "student_depression_dataset.csv"),
        "--output-dir",
        str(ROOT / "models" / "artifacts" / "depression_tabular"),
    ]
    subprocess.run(cmd, cwd=str(ROOT), check=True)


if __name__ == "__main__":
    main()
