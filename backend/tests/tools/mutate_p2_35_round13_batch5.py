"""第十三轮第五批闸门变异验证，含**死接线复现**（第五批真实犯过的错）。

用法（仓库根目录）：
    backend/.venv/Scripts/python.exe backend/tests/tools/mutate_p2_35_round13_batch5.py

三个变异：
- M1 删save_job_to_redis 接线 → 红：locations / 运行时计数器 / 桶计数；
- M2 **把 list_jobs 的接线挪到 `return []` 之后**（＝本批真实犯的错：脚本按
  "logger 块 + return"做锚点插入，接线被插到 return 之后，语法合法、字面量断言
  也过，但运行时永远执行不到）→ 红：死接线闸门 + 运行时计数器；
- M3 删审计文档登记行 → 红：locations。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PY = REPO / "backend" / ".venv" / "Scripts" / "python.exe"
GATE = "tests/test_p2_11_round11.py"
LOG = REPO / "backend" / "tests" / "tools" / "mutate_p2_35_round13_batch5_result.log"

MT = REPO / "backend" / "app" / "tasks" / "model_training.py"
AUDIT = REPO / "docs" / "P2_11_ROUND11_AUDIT.md"

SAVE_WIRING = (
    '        # P2-35 第五批：任务状态写失败 → 轮询查不到这个训练任务（报告/产物侧\n'
    '        # 孪生点见 tasks.pdf_report.save_job_to_redis_failed），必须计数。\n'
    '        record_silent_degradation("tasks.model_training.save_job_to_redis_failed")\n'
)

# M2：正确形态 = 接线在 return 之前
LIST_OK = (
    '        # P2-35 第五批：列表读失败返回 [] → 训练任务列表凭空变空（部分数据），必须计数。\n'
    '        record_silent_degradation("tasks.model_training.list_jobs_from_redis_failed")\n'
    '        return []\n'
)
# M2：变异形态 = 接线被挪到 return 之后（死代码）
LIST_DEAD = (
    '        return []\n'
    '        # P2-35 第五批：列表读失败返回 [] → 训练任务列表凭空变空（部分数据），必须计数。\n'
    '        record_silent_degradation("tasks.model_training.list_jobs_from_redis_failed")\n'
)

MUTATIONS = [
    (
        "M1 删 save_job_to_redis 接线",
        "强（整块删除，语义级）",
        MT,
        SAVE_WIRING,
        "",
        [
            "test_locations_wired_in_code_and_doc",
            "test_all_six_increment_counters",
            "test_batch6_bucket_counts_pinned",
        ],
    ),
    (
        "M2 把 list_jobs 接线挪到 return 之后（死接线复现）",
        "强（语句顺序调换＝本批真实犯的错，语义级）",
        MT,
        LIST_OK,
        LIST_DEAD,
        [
            "test_no_wiring_after_return_or_raise",
            "test_all_six_increment_counters",
        ],
    ),
    (
        "M3 删审计文档登记行",
        "强（整行删除，文档侧半断言）",
        AUDIT,
        "    tasks.model_training.artifact_dir_missing\n",
        "",
        ["test_locations_wired_in_code_and_doc"],
    ),
]


def run_gate() -> tuple[bool, str]:
    proc = subprocess.run(
        [
            str(PY), "-m", "pytest", GATE,
            "-o", "addopts=--strict-markers --import-mode=importlib",
            "-p", "no:cacheprovider", "-q", "--basetemp=p2_13_b5mut",
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
        "# 第十三轮第五批（#35 X 桶接线）闸门变异验证\n"
        "# 判据：变异态必须红且在期望测试上红；还原态必须全绿。\n\n" + "\n".join(lines),
        encoding="utf-8",
    )
    print(f"\n落盘: {LOG}")
    print("总结:", "全部 RED-OK/GREEN-OK" if ok_all else "存在作废变异，结论不成立")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())