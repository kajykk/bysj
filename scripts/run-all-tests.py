from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def run(cmd: list[str], cwd: Path) -> None:
    subprocess.run(cmd, cwd=str(cwd), check=True)


def npm_command() -> str:
    return 'npm.cmd' if os.name == 'nt' else 'npm'


def main() -> None:
    try:
        run([sys.executable, '-m', 'pytest', 'backend/tests/test_harness_integration.py', '-q'], ROOT)
        run([sys.executable, str(ROOT / 'scripts' / 'update-test-overview.py')], ROOT)
        run([npm_command(), '--prefix', 'frontend', 'run', 'test:e2e:report'], ROOT)
        run([sys.executable, str(ROOT / 'scripts' / 'update-test-overview.py')], ROOT)
    finally:
        print('Backend report: backend/test-artifacts/harness-report.md')
        print('Frontend report: frontend/playwright-report')
        print('Overview: docs/test-overview.md')


if __name__ == '__main__':
    main()
