"""第十三轮第十六批闸门变异验证（4 处接线 + 文档登记）。

用法（仓库根目录）：
    backend/.venv/Scripts/python.exe backend/tests/tools/mutate_p2_35_round13_batch16.py

三个变异（全部强：整块/整行删除或整串改名，语义级；子串逃逸式弱变异直接作废）：
- M1 删 core.ws.local_send_failed 接线（含注释整块）→ 红：locations + 运行时计数器；
- M2 改 services.shadow_mode.predictor_unavailable 的 location 字面量 → 红：同上；
- M3 删 P2_11 附录登记行 → 红：locations。

注：与第十二~十五批同口径 —— 磁盘上是 CRLF，但 read_text 通用换行归一为 \n、
write_text 再写回 CRLF，故锚点一律写 \n。所有锚点均断言「恰好命中 1 处」。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PY = REPO / "backend" / ".venv" / "Scripts" / "python.exe"
GATE = "tests/test_p2_11_round11.py::TestP235Round13Batch16Wiring"
LOG = REPO / "backend" / "tests" / "tools" / "mutate_p2_35_round13_batch16_result.log"

WS = REPO / "backend" / "app" / "core" / "ws.py"
SMS = REPO / "backend" / "app" / "services" / "shadow_mode_service.py"
AUDIT = REPO / "docs" / "P2_11_ROUND11_AUDIT.md"

WS_WIRING = (
    "                # P2-35 第十六批：本进程投递失败 = 该用户这一次推送静默丢失，调用方\n"
    "                # （send_to_user / notify_*）从返回值里看不出任何异常，与送达成功同形\n"
    '                record_silent_degradation("core.ws.local_send_failed")\n'
)
SMS_LIT = '"services.shadow_mode.predictor_unavailable"'
SMS_MUT = '"services.shadow_mode.predictor_unavailable_RENAMED"'
DOC_LINE = "    core.ws.local_send_failed\n"

EXPECT_RUNTIME_RED = [
    "test_locations_wired_in_code_and_doc",
    "test_runtime_paths_increment",
]

MUTATIONS = [
    (
        "M1 删 core.ws.local_send_failed 接线（含注释整块删除）",
        "强（整块删除，语义级；删掉即无计数）",
        WS,
        WS_WIRING,
        "",
        EXPECT_RUNTIME_RED,
    ),
    (
        "M2 改 services.shadow_mode.predictor_unavailable 的 location 字面量",
        "强（整串改名，语义级；含闭合引号，不触发子串逃逸）",
        SMS,
        SMS_LIT,
        SMS_MUT,
        EXPECT_RUNTIME_RED,
    ),
    (
        "M3 删 P2_11 附录登记行",
        "强（整行删除，文档侧半断言）",
        AUDIT,
        DOC_LINE,
        "",
        ["test_locations_wired_in_code_and_doc"],
    ),
]


def run_gate() -> tuple[bool, str]:
    proc = subprocess.run(
        [
            str(PY), "-m", "pytest", GATE,
            "-o", "addopts=--strict-markers --import-mode=importlib",
            "-p", "no:cacheprovider", "-q", "--basetemp=p2_13_b16mut",
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
        assert original.count(old) == 1, (
            f"{name}: 锚点命中 {original.count(old)} 处，期望 1（锚点漂移 = 结论作废）"
        )
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
        "# 第十三轮第十六批（#35 X 桶接线）闸门变异验证\n"
        "# 判据：变异态必须红且在期望测试上红；还原态必须全绿。\n\n" + "\n".join(lines),
        encoding="utf-8",
    )
    print(f"\n落盘: {LOG}")
    print("总结:", "全部 RED-OK/GREEN-OK" if ok_all else "存在作废变异，结论不成立")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
