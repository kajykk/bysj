"""P2-35 第二十三批变异验证（纯裁定批：3 条变异）。

M1 给 calculate_metrics 内层 auc handler（L207）接线
   → D/V 型块级反向钉 + 运行时「内层零接线调用」必须红
M2 删 _calculate_small_classification_metrics 的 `total -= 1`
   → D 型见证钉 + 运行时「有效样本数如实」+ 既有设计行为测试
   （test_iss02::test_calculate_metrics_skips_non_numeric_labels）必须红
M3 删 P2_13「一之二十四」节标题行 → 文档结构钉必须红

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
VE = BACKEND / "app" / "services" / "validation_engine.py"
DOC13 = REPO / "docs" / "P2_13_ROUND13_AUDIT.md"

TARGETS = [
    "tests/test_p2_11_round11.py::TestP235Round13Batch23Declined",
    "tests/test_iss02_validation_engine.py",
    "tests/test_validation_engine.py",
]

PYTEST_BASE = [
    "-m", "pytest",
    "-o", "addopts=--strict-markers --import-mode=importlib",
    "-p", "no:cacheprovider", "-q", "--basetemp=.pytest_tmp_b23mut",
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
    print("P2-35 第二十三批变异验证（锚点均为落盘实读文本）")
    print("=" * 72)

    # M1：内层 auc handler 接线（块级反向钉 + 运行时零接线断言）
    m1_old = (
        "                    try:\n"
        "                        metrics.auc = float(roc_auc_score(y_true, probabilities))\n"
        "                    except ValueError:\n"
        "                        pass\n"
    )
    m1_new = (
        "                    try:\n"
        "                        metrics.auc = float(roc_auc_score(y_true, probabilities))\n"
        "                    except ValueError:\n"
        "                        record_silent_degradation(\n"
        "                            \"services.validation_engine.calculate_metrics_auc_failed\"\n"
        "                        )\n"
    )
    mutate("M1 内层 auc handler 接线", VE, m1_old, m1_new)

    # M2：删 `total -= 1`（有效样本数不再如实 → D 型见证 + 既有测试红）
    m2_old = (
        "                total -= 1\n"
        "                continue\n"
    )
    m2_new = "                continue\n"
    mutate("M2 删 total -= 1", VE, m2_old, m2_new)

    # M3：删 P2_13「一之二十四」节标题行（文档结构钉）
    doc13_original = DOC13.read_text(encoding="utf-8")
    m3_line = (
        "## 一之二十四、#35 X 桶第二十三批：纯裁定批（0 接线，W=96 / X=119 不变，"
        "validation_engine 5 条）"
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
