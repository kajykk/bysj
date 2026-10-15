"""第十三轮第二批新闸门变异验证：删接线 / 改 location / 删文档登记，逐一红→恢复绿。

用法（仓库根目录）：
    backend/.venv/Scripts/python.exe backend/tests/tools/mutate_p2_35_round13_batch2.py

铁律（第十三轮提示词）：变异先审强度再看红绿——子串逃逸式弱变异直接作废。
三个变异都是**语义级**（整句删除 / 整个 location 字面量更换 / 整行文档登记删除）。

每个变异跑两轮：变异在位必须红且在期望测试上红；还原后必须全绿。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]  # backend/tests/tools/ → 仓库根
PY = REPO / "backend" / ".venv" / "Scripts" / "python.exe"
GATE = "tests/test_p2_11_round11.py"
LOG = REPO / "backend" / "tests" / "tools" / "mutate_p2_35_round13_batch2_result.log"

PREDICT = REPO / "backend" / "app" / "core" / "model_engine" / "predict.py"
AUTO_ROLLBACK = REPO / "backend" / "app" / "services" / "auto_rollback_service.py"
AUDIT = REPO / "docs" / "P2_11_ROUND11_AUDIT.md"

# (变异名, 强度自评, 文件, 原文, 变异文, 期望红的测试名子串)
MUTATIONS = [
    (
        "M1 删 auto_rollback 回滚 savepoint 整个接线语句",
        "强（整句删除，语义级）",
        AUTO_ROLLBACK,
        """                        # P2-35：回滚失败但 results 里追加的仍是 should_rollback=True
                        # 的原始 check_result——数据结构在说谎，调用方无从知道这次
                        # 自动回滚根本没有发生（坏金丝雀继续在生产提供服务），
                        # 唯一的痕迹就是这行日志，必须计数。
                        record_silent_degradation(
                            "services.auto_rollback_service.rollback_savepoint_failed"
                        )
""",
        "",
        [
            "test_locations_wired_in_code_and_doc",
            "test_rollback_savepoint_failure_increments_counter",
            "test_batch6_bucket_counts_pinned",
        ],
    ),
    (
        "M2 改影子触发 location 字面量",
        "强（整个 location 标识更换，非同串子串；运行时断言同步红）",
        PREDICT,
        'record_silent_degradation(\n                "core.model_engine.predict.shadow_predict_trigger_failed"\n            )',
        'record_silent_degradation(\n                "core.model_engine.predict.shadow_predict_trigger_error"\n            )',
        [
            "test_locations_wired_in_code_and_doc",
            "test_shadow_trigger_failure_increments_counter",
        ],
    ),
    (
        "M3 删审计文档一条 location 登记行",
        "强（整行删除，文档侧半断言）",
        AUDIT,
        "    core.model_engine.predict.physiological_cleaner_fallback\n",
        "",
        ["test_locations_wired_in_code_and_doc"],
    ),
]


def run_gate() -> tuple[bool, str]:
    proc = subprocess.run(
        [
            str(PY),
            "-m",
            "pytest",
            GATE,
            "-o",
            "addopts=--strict-markers --import-mode=importlib",
            "-p",
            "no:cacheprovider",
            "-q",
            "--basetemp=p2_13_b2mut",
        ],
        cwd=REPO / "backend",
        capture_output=True,
        text=True,
        encoding="utf-8",
    )
    tail = "\n".join(proc.stdout.strip().splitlines()[-16:])
    return proc.returncode == 0, tail


def main() -> int:
    lines: list[str] = []
    ok_all = True
    for name, strength, path, old, new, expect_red in MUTATIONS:
        original = path.read_text(encoding="utf-8")
        assert old in original, f"{name}: 原文未找到（锚点失效，结论作废）"
        # 变异在位 → 必须红（returncode != 0），且红在期望的测试上
        path.write_text(original.replace(old, new, 1), encoding="utf-8")
        passed, red_tail = run_gate()
        # 还原 → 必须绿（returncode == 0）
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
        "# 第十三轮第二批（#35 X 桶接线）闸门变异验证\n"
        "# 判据：变异态必须红且在期望测试上红；还原态必须绿。\n\n" + "\n".join(lines),
        encoding="utf-8",
    )
    print(f"\n落盘: {LOG}")
    print("总结:", "全部 RED-OK/GREEN-OK" if ok_all else "存在作废变异，结论不成立")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
