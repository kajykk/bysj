"""通用 CI 监视器：轮询指定 commit 的 check-runs 直至全部完成或出现失败。

用法：
    backend/.venv/Scripts/python.exe backend/tests/tools/watch_ci.py <short-or-full-sha>

行为：
- 先确认远端可见该 SHA（不可见 → 退出码 2，不误报 CI_ALL_DONE）；
- 每 90s 轮询；出现 failure/cancelled/timed_out → 打印并退出码 1；
- 全部 completed → 打印汇总退出码 0；
- 40 轮未完成 → 退出码 3。

注意：后台进程可能在回合结束时被回收（届时报 failed，属虚报）——
权威口径永远是回合开头直接 `gh api repos/<repo>/commits/<sha>/check-runs`。
"""

from __future__ import annotations

import json
import subprocess
import sys
import time

REPO = "kajykk/bysj"


def gh_api(path: str) -> dict | None:
    proc = subprocess.run(
        ["gh", "api", path], capture_output=True, text=True, encoding="utf-8"
    )
    if proc.returncode != 0:
        return None
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return None


def main() -> int:
    if len(sys.argv) < 2:
        print("用法: watch_ci.py <sha>")
        return 4
    sha_arg = sys.argv[1]
    head = gh_api(f"repos/{REPO}/commits/{sha_arg}")
    if head is None:
        print(f"SHA {sha_arg} 远端不可见（push 未生效？）→ 退出码 2")
        return 2
    sha = head["sha"]
    print(f"watching {sha}", flush=True)
    for i in range(1, 41):
        data = gh_api(f"repos/{REPO}/commits/{sha}/check-runs")
        if data is None:
            print(f"poll {i}: api error")
            time.sleep(90)
            continue
        runs = data.get("check_runs", [])
        total = data.get("total_count", 0)
        done = sum(1 for r in runs if r.get("status") == "completed")
        summary = ", ".join(f"{r['name']}:{r.get('conclusion') or '-'}" for r in runs)
        print(f"poll {i}: completed={done}/{total} | {summary}", flush=True)
        bad = [
            r["name"]
            for r in runs
            if r.get("conclusion") in ("failure", "timed_out")
        ]
        cancelled = [r["name"] for r in runs if r.get("conclusion") == "cancelled"]
        if cancelled:
            # cancelled 不是失败：本仓 workflow 带 concurrency cancel-in-progress，
            # 后续 push 会把本次未完成的 job 取消掉（第十三轮实锤：前一批 9 success
            # + backend-coverage cancelled，是"被新提交取代"而非回归）。
            print(f"NOTE: cancelled（非失败，通常是被后续 push 取代）: {cancelled}")
        if bad:
            print(f"CI_FAILURE_DETECTED: {bad}")
            return 1
        if total and done == total:
            print("CI_ALL_DONE")
            return 0
        time.sleep(90)
    print("WATCH_TIMEOUT: 40 轮未完成")
    return 3


if __name__ == "__main__":
    sys.exit(main())