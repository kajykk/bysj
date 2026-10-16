"""P2-35 第二十六批变异验证（纯裁定批：0 接线，4 条变异）。

M1 给 `preload` L288 PermissionError handler 接线
   → 块级反向钉 + 运行时「零接线调用」必须红（消费点已接线，重复计数）
M2 把消费点 `structured_predict_fallback` 的 location 字面量改成错值
   → 消费点见证钉必须红（证明该钉非空转，同时牵 consistency 的往批钉）
M3 给 `_incr_model_fallback` L244 handler 接线
   → S 型块级反向钉必须红
M4 删 P2_13「一之二十七」节标题行 → 文档结构钉必须红

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
LD = BACKEND / "app" / "core" / "model_engine" / "loading.py"
RS = BACKEND / "app" / "services" / "risk_service_assessment.py"
DOC13 = REPO / "docs" / "P2_13_ROUND13_AUDIT.md"

TARGETS = [
    "tests/test_p2_11_round11.py::TestP235Round13Batch26Declined",
    "tests/test_model_integrity_anchor.py",
    "tests/test_model_path_resolution.py",
    "tests/test_regression_v128_quality.py",
    "tests/services/test_risk_service.py",
]

PYTEST_BASE = [
    "-m", "pytest",
    "-o", "addopts=--strict-markers --import-mode=importlib",
    "-p", "no:cacheprovider", "-q", "--basetemp=.pytest_tmp_b26mut",
]


def run_gate() -> int:
    """跑批次闸门类 + 受影响测试，返回 returncode（0 = 通过）。"""
    proc = subprocess.run(
        [str(PY), *PYTEST_BASE, *TARGETS],
        cwd=BACKEND, capture_output=True, text=True, timeout=900,
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
    print("P2-35 第二十六批变异验证（锚点均为落盘实读文本）")
    print("=" * 72)

    # 基线
    print("  [baseline] 变异前闸门应为绿…")
    assert run_gate() == 0, "基线不绿 —— 不许在红态下做变异验证"
    print("  [baseline] GREEN-OK")

    # M1：给 preload 的 PermissionError handler 接线
    m1_old = (
        '            except PermissionError as exc:\n'
        '                logger.critical(\n'
        '                    "Permission denied loading %s (NON-RECOVERABLE): %s. " "Check file permissions and process user.",\n'
        '                    model_id,\n'
        '                    exc,\n'
        '                )\n'
    )
    m1_new = m1_old + (
        '                record_silent_degradation("core.model_engine.loading.preload.permission_denied")\n'
    )
    mutate("M1 给 preload PermissionError handler 接线", LD, m1_old, m1_new)

    # M2：消费点 location 字面量改错值（消费点见证钉非空转）
    m2_old = '            record_silent_degradation(\n                "services.risk_service_assessment.structured_predict_fallback"\n            )\n'
    m2_new = '            record_silent_degradation(\n                "services.risk_service_assessment.structured_predict_fallback_typo"\n            )\n'
    mutate("M2 消费点 location 字面量改错值", RS, m2_old, m2_new)

    # M3：给 _incr_model_fallback 的指标 inc 失败 handler 接线
    m3_old = (
        '        logger.warning(\n'
        '            "model_fallback_total inc failed (model=%s reason=%s)",\n'
        '            model,\n'
        '            reason,\n'
        '            exc_info=True,\n'
        '        )\n'
    )
    m3_new = m3_old + (
        '        record_silent_degradation("core.model_engine.loading.model_fallback_metric_inc_failed")\n'
    )
    mutate("M3 给 _incr_model_fallback 指标 handler 接线", LD, m3_old, m3_new)

    # M4：删 P2_13「一之二十七」节标题行（文档结构钉）
    doc13_original = DOC13.read_text(encoding="utf-8")
    m4_line = (
        "## 一之二十七、#35 X 桶第二十六批：纯裁定批（0 接线，W=97 / X=119 "
        "不变，loading.py 收口）"
    )
    assert doc13_original.count(m4_line) == 1, "M4 锚点不唯一或不在"
    print("  [M4 删 P2_13 节标题] 变异注入…")
    DOC13.write_text(doc13_original.replace(m4_line + "\n", ""), encoding="utf-8")
    rc = run_gate()
    assert rc != 0, "M4: 变异态闸门仍绿 —— 文档结构钉假绿！"
    print(f"  [M4 删 P2_13 节标题] RED-OK（returncode={rc}）")
    DOC13.write_text(doc13_original, encoding="utf-8")
    rc2 = run_gate()
    assert rc2 == 0, "M4: 还原态闸门仍红"
    print("  [M4 删 P2_13 节标题] GREEN-OK（还原后 returncode=0）")

    print("=" * 72)
    print("四条变异全部 RED-OK / GREEN-OK")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
