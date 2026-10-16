"""P2-35 第二十四批变异验证（接线 1 处：3 条变异）。

M1 删 `core.ws.pubsub_loop_crashed` 接线调用
   → location 双向核对（源码侧）+ 运行时「崩溃恰好 +1」必须红
M2 把 location 字面量改成错值
   → location 双向核对 + 运行时计数器必须红（证明断言非空转）
M3 删 P2_13「一之二十五」节标题行 → 文档结构钉必须红

纪律：锚点先读实际落盘文本（CRLF 文件经 read_text/write_text 通用换行，
锚点一律写 \\n）；每条变异 RED-OK（returncode!=0）+ 还原 GREEN-OK
（returncode==0）；判据命名诚实（run_gate 返回 returncode，0=通过）；
日志落盘（须 git add -f 入版本库）。
"""

from __future__ import annotations

import pathlib
import subprocess

BACKEND = pathlib.Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
PY = BACKEND / ".venv" / "Scripts" / "python.exe"
WS = BACKEND / "app" / "core" / "ws.py"
DOC13 = REPO / "docs" / "P2_13_ROUND13_AUDIT.md"

TARGETS = [
    "tests/test_p2_11_round11.py::TestP235Round13Batch24Wiring",
    "tests/test_ws_pubsub.py",
]

PYTEST_BASE = [
    "-m", "pytest",
    "-o", "addopts=--strict-markers --import-mode=importlib",
    "-p", "no:cacheprovider", "-q", "--basetemp=.pytest_tmp_b24mut",
]


def run_gate() -> int:
    """跑批次闸门类 + 受影响测试，返回 returncode（0 = 通过）。"""
    proc = subprocess.run(
        [str(PY), *PYTEST_BASE, *TARGETS],
        cwd=BACKEND, capture_output=True, text=True, timeout=600,
    )
    tail = [ln for ln in proc.stdout.splitlines() if "passed" in ln or "failed" in ln]
    print("    gate:", tail[-1] if tail else proc.stdout[-200:])
    return proc.returncode


def mutate(label: str, path: pathlib.Path, old: str, new: str) -> None:
    original = path.read_text(encoding="utf-8")
    assert old in original, f"{label}: 锚点不在落盘文本中（先读实际文本再写脚本）: {old[:60]!r}"
    assert original.count(old) == 1, f"{label}: 锚点不唯一（{original.count(old)} 处）"
    print(f"  [{label}] 变异注入…")
    path.write_text(new.join(original.split(old)), encoding="utf-8")
    rc = run_gate()
    assert rc != 0, f"{label}: 变异态闸门仍绿（returncode=0）—— 断言假绿！"
    print(f"  [{label}] RED-OK（returncode={rc}）")
    path.write_text(original, encoding="utf-8")
    rc2 = run_gate()
    assert rc2 == 0, f"{label}: 还原态闸门仍红（returncode={rc2}）—— 还原不完整！"
    print(f"  [{label}] GREEN-OK（还原后 returncode=0）")


def main() -> int:
    print("=" * 72)
    print("P2-35 第二十四批变异验证（锚点均为落盘实读文本）")
    print("=" * 72)

    # M1：删接线调用（location 双向核对源码侧 + 运行时计数红）
    m1_old = (
        '                record_silent_degradation("core.ws.pubsub_loop_crashed")\n'
    )
    m1_new = ""
    mutate("M1 删 pubsub_loop_crashed 接线", WS, m1_old, m1_new)

    # M2：location 字面量改错值（双向核对 + 运行时计数器红）
    m2_old = 'record_silent_degradation("core.ws.pubsub_loop_crashed")'
    m2_new = 'record_silent_degradation("core.ws.pubsub_loop_crashed_typo")'
    mutate("M2 location 字面量改错值", WS, m2_old, m2_new)

    # M3：删 P2_13「一之二十五」节标题行（文档结构钉）
    doc13_original = DOC13.read_text(encoding="utf-8")
    m3_line = (
        "## 一之二十五、#35 X 桶第二十四批：接线 1 处（W 96→97 / R 4→3 / "
        "X 119 不变，ws.py 13 条候选）"
    )
    assert doc13_original.count(m3_line) == 1, "M3 锚点不唯一或不在"
    print("  [M3 删 P2_13 节标题] 变异注入…")
    DOC13.write_text(doc13_original.replace(m3_line + "\n", ""), encoding="utf-8")
    rc = run_gate()
    assert rc != 0, "M3: 变异态闸门仍绿 —— 文档结构钉假绿！"
    print(f"  [M3 删 P2_13 节标题] RED-OK（returncode={rc}）")
    DOC13.write_text(doc13_original, encoding="utf-8")
    rc2 = run_gate()
    assert rc2 == 0, "M3: 还原态闸门仍红"
    print("  [M3 删 P2_13 节标题] GREEN-OK（还原后 returncode=0）")

    print("=" * 72)
    print("三条变异全部 RED-OK / GREEN-OK")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
