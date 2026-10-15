"""第十三轮第六批闸门变异验证（training_jobs 双接线 + aggregate + 文档登记）。

用法（仓库根目录）：
    backend/.venv/Scripts/python.exe backend/tests/tools/mutate_p2_35_round13_batch6.py

三个变异（全部强：整块/整行删除，语义级；子串逃逸式弱变异直接作废，见第十二轮第七批教训）：
- M1 删 training_jobs.load_failed 接线 → 红：locations / 运行时计数器；
- M2 删 aggregate.lock_stats_unavailable 接线 → 红：locations / 运行时计数器；
- M3 删 P2_11 附录登记行 → 红：locations。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PY = REPO / "backend" / ".venv" / "Scripts" / "python.exe"
GATE = "tests/test_p2_11_round11.py::TestP235Round13Batch6Wiring"
LOG = REPO / "backend" / "tests" / "tools" / "mutate_p2_35_round13_batch6_result.log"

TJ = REPO / "backend" / "app" / "services" / "model_predict" / "training_jobs.py"
AGG = REPO / "backend" / "app" / "services" / "observability" / "aggregate.py"
AUDIT = REPO / "docs" / "P2_11_ROUND11_AUDIT.md"

LOAD_WIRING = (
    '        # P2-35 第六批：启动时快照读失败 → TRAINING_JOBS 为空，重启后所有训练任务\n'
    '        # 在管理端"不存在"（用户以为任务从没跑过），必须计数。\n'
    '        record_silent_degradation("services.model_predict.training_jobs.load_failed")\n'
)

AGG_WIRING = (
    '        record_silent_degradation(\n'
    '            "services.observability.aggregate.lock_stats_unavailable"\n'
    '        )\n'
)

MUTATIONS = [
    (
        "M1 删 training_jobs.load_failed 接线",
        "强（整块删除，语义级）",
        TJ,
        LOAD_WIRING,
        "",
        [
            "test_locations_wired_in_code_and_doc",
            "test_training_jobs_snapshot_failures_increment",
        ],
    ),
    (
        "M2 删 aggregate.lock_stats_unavailable 接线",
        "强（整块删除，语义级）",
        AGG,
        AGG_WIRING,
        "",
        [
            "test_locations_wired_in_code_and_doc",
            "test_lock_stats_unavailable_increments",
        ],
    ),
    (
        "M3 删 P2_11 附录登记行",
        "强（整行删除，文档侧半断言；注：只改后缀如加 X 会因子串逃逸仍绿，作废）",
        AUDIT,
        "    services.observability.aggregate.lock_stats_unavailable\n",
        "",
        ["test_locations_wired_in_code_and_doc"],
    ),
]


def run_gate() -> tuple[bool, str]:
    proc = subprocess.run(
        [
            str(PY), "-m", "pytest", GATE,
            "-o", "addopts=--strict-markers --import-mode=importlib",
            "-p", "no:cacheprovider", "-q", "--basetemp=p2_13_b6mut",
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
        "# 第十三轮第六批（#35 X 桶接线）闸门变异验证\n"
        "# 判据：变异态必须红且在期望测试上红；还原态必须全绿。\n\n" + "\n".join(lines),
        encoding="utf-8",
    )
    print(f"\n落盘: {LOG}")
    print("总结:", "全部 RED-OK/GREEN-OK" if ok_all else "存在作废变异，结论不成立")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
