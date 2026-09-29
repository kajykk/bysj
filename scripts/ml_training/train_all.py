from __future__ import annotations

import argparse
from pathlib import Path
import sys

CURRENT_DIR = Path(__file__).resolve().parent
if str(CURRENT_DIR) not in sys.path:
    sys.path.insert(0, str(CURRENT_DIR))

from train_tabular import main as run_tabular  # noqa: E402
from train_text import main as run_text  # noqa: E402


def main():
    parser = argparse.ArgumentParser(description="Unified training entry point")
    parser.add_argument("--task", choices=["tabular", "text"], required=True)
    args, remaining = parser.parse_known_args()

    if args.task == "tabular":
        sys.argv = [sys.argv[0]] + remaining
        run_tabular()
    elif args.task == "text":
        sys.argv = [sys.argv[0]] + remaining
        run_text()


if __name__ == "__main__":
    main()
