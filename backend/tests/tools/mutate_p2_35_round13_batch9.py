"""第十三轮第九批闸门变异验证（canary_fallback_monitor.py 2 接线 + 文档登记）。

用法（仓库根目录）：
    backend/.venv/Scripts/python.exe backend/tests/tools/mutate_p2_35_round13_batch9.py

三个变异（全部强：整块/整行删除或整串改名，语义级；子串逃逸式弱变异直接作废）：
- M1 删 rollback_check_failed 接线 → 红：locations / 运行时计数器；
- M2 改 loop_unexpected_error 的 location 字面量 → 红：locations / 运行时计数器；
- M3 删 P2_11 附录登记行 → 红：locations。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PY = REPO / "backend" / ".venv" / "Scripts" / "python.exe"
GATE = "tests/test_p2_11_round11.py::TestP235Round13Batch9Wiring"
LOG = REPO / "backend" / "tests" / "tools" / "mutate_p2_35_round13_batch9_result.log"

SVC = REPO / "backend" / "app" / "services" / "canary_fallback_monitor.py"
AUDIT = REPO / "docs" / "P2_11_ROUND11_AUDIT.md"

RB_WIRING = (
    '                    record_silent_degradation(\n'
    '                        "services.canary_fallback_monitor.rollback_check_failed"\n'
    '                    )\n'
)
LOOP_LIT = '"services.canary_fallback_monitor.loop_unexpected_error"'
LOOP_MUT = '"services.canary_fallback_monitor.loop_unexpected_error_RENAMED"'

MUTATIONS = [
    (
        "M1 删 rollback_check_failed 接线",
        "强（整块删除，语义级）",
        SVC,
        RB_WIRING,
        "",
        [
            "test_locations_wired_in_code_and_doc",
            "test_rollback_check_failure_increments",
        ],
    ),
    (
        "M2 改 loop_unexpected_error 的 location 字面量",
        "强（整串改名，语义级；因含闭合引号不触发子串逃逸）",
        SVC,
        LOOP_LIT,
        LOOP_MUT,
        [
            "test_locations_wired_in_code_and_doc",
            "test_loop_unexpected_error_increments",
        ],
    ),
    (
        "M3 删 P2_11 附录登记行",
        "强（整行删除，文档侧半断言）",
        AUDIT,
        "    services.canary_fallback_monitor.loop_unexpected_error\n",
        "",
        ["test_locations_wired_in_code_and_doc"],
    ),
]


def run_gate() -> tuple[bool, str]:
    proc = subprocess.run(
        [
            str(PY), "-m", "pytest", GATE,
            "-o", "addopts=--strict-markers --import-mode=importlib",
            "-p", "no:cacheprovider", "-q", "--basetemp=p2_13_b9mut",
        ],
        cwd=REPO / "backend",
        capture_output=True, text=True, encoding="utf-8",
    )
    return proc.returncode == 0, "\n".join(proc.stdout.strip().splitlines()[-16:])


def main() -> int:
    lines: list[str] = []
    ok_all = True
    for name, strength, path, old, new, expect_red in MUTATIONS:
        original = path.read_text(encoding="utf-8")
        assert old in original, f"{name}: 原文未找到（锚点失效，结论作废）"
        path.write_text(original.replace(old, new, 1), encoding="utf-8")
        passed, red_tail = run_gate()
        path.write_text(original, encoding="utf-8")
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
        "# 第十三轮第九批（#35 X 桶接线）闸门变异验证\n"
        "# 判据：变异态必须红且在期望测试上红；还原态必须全绿。\n\n" + "\n".join(lines),
        encoding="utf-8",
    )
    print(f"\n落盘: {LOG}")
    print("总结:", "全部 RED-OK/GREEN-OK" if ok_all else "存在作废变异，结论不成立")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
