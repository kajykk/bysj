"""第十三轮第二十批闸门变异验证（接线 1 处 + 14 条不接线反向钉）。

用法（仓库根目录）：
    backend/.venv/Scripts/python.exe backend/tests/tools/mutate_p2_35_round13_batch20.py

变异目标（每条都让断言真值翻转，且期望红的测试逐一列名）：
- M1 删 alerts/__init__.py 的 record_silent_degradation 接线行
  → 红：test_locations_wired_in_code_and_doc + test_runtime_paths_increment
    （证明「接了线」与「计数 +1」两条断言都不是恒真）；
- M2 把 location 字面量改成 api.alerts.history_detail_parse_failed_x
  → 红：同上两条（字面量双钉：源码侧找不到 + 运行时计数对不上）；
- M3 删 P2_13「一之二十一」节标题行
  → 红：test_doc_registered_batch20（节标题结构钉，正文提及不算）；
- M4 删 P2_11 附录第二十批条目头行
  → 红：test_doc_registered_batch20（P2_11 侧条目断言）。

注：与第十二~十九批同口径 —— 磁盘上是 CRLF，但 read_text 通用换行归一为 \n、
write_text 再写回 CRLF，故锚点一律写 \n。所有锚点均断言「恰好命中 1 处」。
判据命名诚实：run_gate() 返回 returncode==0（通过），变量名 passed；
变异态必须 returncode!=0 且期望测试命中，还原态必须 returncode==0。
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[3]
PY = REPO / "backend" / ".venv" / "Scripts" / "python.exe"
GATE = "tests/test_p2_11_round11.py::TestP235Round13Batch20Wiring"
LOG = REPO / "backend" / "tests" / "tools" / "mutate_p2_35_round13_batch20_result.log"

ALERTS = REPO / "backend" / "app" / "api" / "v1" / "alerts" / "__init__.py"
AUDIT13 = REPO / "docs" / "P2_13_ROUND13_AUDIT.md"
AUDIT11 = REPO / "docs" / "P2_11_ROUND11_AUDIT.md"

# M1：删接线行（保留注释与 logger.warning，只删计数调用）
M1_OLD = '            record_silent_degradation("api.alerts.history_detail_parse_failed")\n'
M1_NEW = ""
# M2：location 字面量漂移（接线还在，但计到了错误的位置）
M2_OLD = '"api.alerts.history_detail_parse_failed"'
M2_NEW = '"api.alerts.history_detail_parse_failed_x"'
# M3：删 P2_13「一之二十一」节标题行
M3_OLD = "## 一之二十一、#35 X 桶第二十批：1 处接线（X 120 → 119）+ 14 处不接线\n"
M3_NEW = ""
# M4：删 P2_11 附录第二十批条目头行
M4_OLD = "- **第十三轮第二十批（接线 1 处 + 不接线 14 处，W 95→96 / X 120→119）**：\n"
M4_NEW = ""

MUTATIONS = [
    (
        "M1 删 alerts list_alert_history 的 record_silent_degradation 接线行",
        "强（整行删除，语义级；直接推翻「已接线」事实）",
        ALERTS,
        M1_OLD,
        M1_NEW,
        ["test_locations_wired_in_code_and_doc", "test_runtime_paths_increment"],
    ),
    (
        "M2 改 location 字面量（history_detail_parse_failed → _x 后缀）",
        "强（整串替换，语义级；字面量双钉两侧同时失真）",
        ALERTS,
        M2_OLD,
        M2_NEW,
        ["test_locations_wired_in_code_and_doc", "test_runtime_paths_increment"],
    ),
    (
        "M3 删 P2_13「一之二十一」节标题行",
        "强（整行删除，文档登记结构钉）",
        AUDIT13,
        M3_OLD,
        M3_NEW,
        ["test_doc_registered_batch20"],
    ),
    (
        "M4 删 P2_11 附录第二十批条目头行",
        "强（整行删除，P2_11 侧条目断言）",
        AUDIT11,
        M4_OLD,
        M4_NEW,
        ["test_doc_registered_batch20"],
    ),
]


def run_gate() -> tuple[bool, str]:
    proc = subprocess.run(
        [
            str(PY), "-m", "pytest", GATE,
            "-o", "addopts=--strict-markers --import-mode=importlib",
            "-p", "no:cacheprovider", "-q", "--basetemp=p2_13_b20mut",
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
        "# 第十三轮第二十批（#35 接线 1 处 + 14 条不接线）闸门变异验证\n"
        "# 判据：变异态必须红且在期望测试上红；还原态必须全绿。\n\n" + "\n".join(lines),
        encoding="utf-8",
    )
    print(f"\n落盘: {LOG}")
    print("总结:", "全部 RED-OK/GREEN-OK" if ok_all else "存在作废变异，结论不成立")
    return 0 if ok_all else 1


if __name__ == "__main__":
    sys.exit(main())
