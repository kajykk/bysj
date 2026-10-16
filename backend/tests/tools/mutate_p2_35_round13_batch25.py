"""P2-35 第二十五批变异验证（纯裁定批：0 接线，4 条变异）。

M1 给 `_notify_warning` L81 重试 handler 接线
   → 块级反向钉 + 运行时「通用计数器零调用」必须红
M2 给 `_cleanup_experiment_artifacts_impl` L1134 目录 resolve handler 接线
   → F 型块级反向钉必须红
M3 删 L1134 handler 的 `is_active = True` 保守跳过赋值（F 型见证）
   → AST 见证断言 + 运行时差分实验（removed=0 / 目录保留）必须红
M4 删 P2_13「一之二十六」节标题行 → 文档结构钉必须红

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
SCHED = BACKEND / "app" / "tasks" / "scheduler.py"
DOC13 = REPO / "docs" / "P2_13_ROUND13_AUDIT.md"

TARGETS = [
    "tests/test_p2_11_round11.py::TestP235Round13Batch25Declined",
    "tests/tasks/test_scheduler.py",
    "tests/test_resource_cleanup.py",
]

PYTEST_BASE = [
    "-m", "pytest",
    "-o", "addopts=--strict-markers --import-mode=importlib",
    "-p", "no:cacheprovider", "-q", "--basetemp=.pytest_tmp_b25mut",
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
    print("P2-35 第二十五批变异验证（锚点均为落盘实读文本）")
    print("=" * 72)

    # 基线
    print("  [baseline] 变异前闸门应为绿…")
    assert run_gate() == 0, "基线不绿 —— 不许在红态下做变异验证"
    print("  [baseline] GREEN-OK")

    # M1：给 _notify_warning 重试 handler 接线（M 型裁定反向验证）
    m1_old = (
        "            last_exc = exc\n"
        "            logger.warning(\n"
        '                "WebSocket notification attempt %d/%d failed for warning %d: %s",\n'
        "                attempt,\n"
        "                _NOTIFY_MAX_ATTEMPTS,\n"
        "                warning_id,\n"
        "                exc,\n"
        "                exc_info=True,\n"
        "            )\n"
    )
    m1_new = m1_old + (
        '            record_silent_degradation("tasks.scheduler.notify_warning_retry_failed")\n'
    )
    mutate("M1 给 _notify_warning 重试 handler 接线", SCHED, m1_old, m1_new)

    # M2：给产物目录 resolve 失败 handler 接线（F 型裁定反向验证）
    m2_old = (
        "                logger.warning(\n"
        '                    "AUDIT-P0-3 无法解析产物目录真实路径, 保守跳过删除: "\n'
        '                    "entry=%s error=%s",\n'
        "                    entry,\n"
        "                    exc,\n"
        "                )\n"
        "                is_active = True\n"
    )
    m2_new = (
        "                logger.warning(\n"
        '                    "AUDIT-P0-3 无法解析产物目录真实路径, 保守跳过删除: "\n'
        '                    "entry=%s error=%s",\n'
        "                    entry,\n"
        "                    exc,\n"
        "                )\n"
        "                is_active = True\n"
        '                record_silent_degradation("tasks.scheduler.cleanup_dir_resolve_failed")\n'
    )
    mutate("M2 给产物目录 resolve handler 接线", SCHED, m2_old, m2_new)

    # M3：删掉 except 内的保守跳过赋值（F 型见证 / 安全方向）
    m3_old = (
        "                    entry,\n"
        "                    exc,\n"
        "                )\n"
        "                is_active = True\n"
    )
    m3_new = (
        "                    entry,\n"
        "                    exc,\n"
        "                )\n"
        "                pass\n"
    )
    mutate("M3 删 L1134 保守跳过 is_active = True", SCHED, m3_old, m3_new)

    # M4：删 P2_13「一之二十六」节标题行（文档结构钉）
    doc13_original = DOC13.read_text(encoding="utf-8")
    m4_line = (
        "## 一之二十六、#35 X 桶第二十五批：纯裁定批（0 接线，W=97 / X=119 "
        "不变，scheduler.py 5 条新候选）"
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
