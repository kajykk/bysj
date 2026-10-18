"""PERF-P2-002 计时容差机制的变异验证。

用法（仓库根目录）：
    backend/.venv/Scripts/python.exe backend/tests/tools/mutate_perf_p2_002.py

三个变异（全部语义级，针对"取最小值 + 统一走 measure_ms"这一被钉住的语义）：
- M1 把 `return min(samples), result` 改成 `return samples[-1], result`（取末次）
  → 红：test_measure_ms_uses_min_of_best_of_and_consumes_warmup
        + test_measure_ms_not_fooled_by_single_spike；
- M2 把 `min(samples)` 改成 `sum(samples) / len(samples)`（取均值）
  → 红：同两条；
- M3 把 response_time 用例改回裸 perf_counter 差值
  → 红：test_perf_file_has_no_bare_wallclock_assertions。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PY = REPO / "backend" / ".venv" / "Scripts" / "python.exe"
PERF = REPO / "backend" / "tests" / "performance" / "test_observability_perf.py"
LOG = REPO / "backend" / "tests" / "tools" / "mutate_perf_p2_002_result.log"

TARGET = "tests/performance/test_observability_perf.py"

M1_OLD = "    return min(samples), result"
M1_NEW = "    return samples[-1], result"

M2_OLD = "    return min(samples), result"
M2_NEW = "    return sum(samples) / len(samples), result"

# M3: 把 response_time 的 measure_ms 调用还原成裸计时
M3_OLD = (
    "    elapsed_ms, result = await measure_ms(\n"
    "        lambda: _compute_response_time(db_session, start, end, None)\n"
    "    )"
)
M3_NEW = (
    "    _t0 = time.perf_counter()\n"
    "    result = await _compute_response_time(db_session, start, end, None)\n"
    "    elapsed_ms = (time.perf_counter() - _t0) * 1000"
)

MUTATIONS = [
    (
        "M1 measure_ms 取末次而非最小值",
        "强（语义级：把容差机制换成取末次）",
        M1_OLD,
        M1_NEW,
        [
            "test_measure_ms_uses_min_of_best_of_and_consumes_warmup",
            "test_measure_ms_not_fooled_by_single_spike",
        ],
    ),
    (
        "M2 measure_ms 取均值而非最小值",
        "强（语义级：把容差机制换成取均值）",
        M2_OLD,
        M2_NEW,
        [
            "test_measure_ms_uses_min_of_best_of_and_consumes_warmup",
            "test_measure_ms_not_fooled_by_single_spike",
        ],
    ),
    (
        "M3 response_time 用例改回裸 perf_counter 差值",
        "强（语义级：绕开 measure_ms）",
        M3_OLD,
        M3_NEW,
        ["test_perf_file_has_no_bare_wallclock_assertions"],
    ),
]


def run_gate() -> tuple[bool, str]:
    proc = subprocess.run(
        [
            str(PY), "-m", "pytest", TARGET,
            "-o", "addopts=--strict-markers --import-mode=importlib",
            "-p", "no:cacheprovider", "-q", "--basetemp=perf_p2_002_mut",
        ],
        cwd=REPO / "backend",
        capture_output=True, text=True, encoding="utf-8",
    )
    return proc.returncode == 0, "\n".join(proc.stdout.strip().splitlines()[-16:])


def main() -> int:
    lines: list[str] = []
    ok_all = True
    for name, strength, old, new, expect_red in MUTATIONS:
        original = PERF.read_text(encoding="utf-8")
        assert old in original, f"{name}: 原文未找到（锚点失效，结论作废）"
        PERF.write_text(original.replace(old, new, 1), encoding="utf-8")
        passed, red_tail = run_gate()
        PERF.write_text(original, encoding="utf-8")
        green, green_tail = run_gate()
        red_hits = [t for t in expect_red if t in red_tail]
        verdict = (
            "RED-OK/GREEN-OK"
            if ((not passed) and green and len(red_hits) == len(expect_red))
            else "作废"
        )
        if verdict == "作废":
            ok_all = False
        lines.append(
            f"== {name}\n   强度自评：{strength}\n   变异态 returncode==0? {passed}（应为 False）\n"
            f"   期望红的测试命中：{len(red_hits)}/{len(expect_red)} {red_hits}\n"
            f"   还原态 returncode==0? {green}（应为 True）\n   判定：{verdict}\n"
            f"   --- 变异态输出尾部 ---\n{red_tail}\n   --- 还原态输出尾部 ---\n{green_tail}\n"
        )
        print(lines[-1])
    LOG.write_text(
        "# PERF-P2-002 计时容差机制 闸门变异验证\n"
        "# 判据：变异态必须红且在期望测试上红；还原态必须全绿。\n\n" + "\n".join(lines),
        encoding="utf-8",
    )
    print(f"\n落盘: {LOG}")
    print("总结:", "全部 RED-OK/GREEN-OK" if ok_all else "存在作废变异，结论不成立")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
