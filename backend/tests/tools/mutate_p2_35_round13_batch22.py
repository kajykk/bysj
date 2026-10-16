"""P2-35 第二十二批变异验证（纯裁定批 + 计数器修复：4 条变异）。

M1 把锁计数器调用改回 prometheus_client 形态 `.labels(outcome=...).inc()`
   → 计数器真涨回归 + API 形态防回退钉 + 运行时锁/心跳可观测必须红
M2 删 pii_crypto Fernet 末端 raise ValueError → 回退链 witness（raise 计数
   2→1）+ 运行时 decrypt 耗尽显式 raise 必须红
M3 删 P2_13「一之二十三」节标题行 → 文档结构钉必须红
M4 删 P2_11 第二十二批条目头行 → 文档登记钉必须红

纪律：锚点先读实际落盘文本（CRLF 文件经 read_text/write_text 通用换行，
锚点一律写 \\n）；每条变异 RED-OK（returncode!=0）+ 还原 GREEN-OK
（returncode==0）；日志落盘（须 git add -f 入版本库）。
"""

from __future__ import annotations

import pathlib
import subprocess
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
PY = BACKEND / ".venv" / "Scripts" / "python.exe"
ARS = BACKEND / "app" / "services" / "auto_rollback_service.py"
PII = BACKEND / "app" / "core" / "pii_crypto.py"
DOC13 = REPO / "docs" / "P2_13_ROUND13_AUDIT.md"
DOC11 = REPO / "docs" / "P2_11_ROUND11_AUDIT.md"
TEST_CLASS = "tests/test_p2_11_round11.py::TestP235Round13Batch22Declined"

PYTEST_BASE = [
    "-m", "pytest",
    "-o", "addopts=--strict-markers --import-mode=importlib --cov=app "
    "--cov-report=xml:coverage.xml --ignore=functional_test.py "
    "--ignore-glob=test_result*.txt --ignore=test_final.txt",
    "-p", "no:cacheprovider", "-q",
]


def run_gate() -> int:
    """跑 Batch22 测试类，返回 returncode（0 = 通过）。"""
    proc = subprocess.run(
        [str(PY), *PYTEST_BASE, TEST_CLASS],
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
    print("P2-35 第二十二批变异验证（锚点均为落盘实读文本）")
    print("=" * 72)

    # M1：计数器调用改回 prometheus_client 形态（死计数回归）
    m1_old = "canary_rollback_check_lock_total.inc(outcome=outcome)"
    m1_new = "canary_rollback_check_lock_total.labels(outcome=outcome).inc()"
    mutate("M1 计数器 API 回退", ARS, m1_old, m1_new)

    # M2：删 pii_crypto Fernet 末端 raise（回退链显式终点消失）
    m2_old = (
        "    # 3. 全部密钥都失败\n"
        "    logger.error(\n"
        "        \"PII v1 decryption failed (exhausted current + %d previous keys): field=%s, len=%d\",\n"
        "        len(previous_fernets),\n"
        "        field,\n"
        "        len(ciphertext),\n"
        "    )\n"
        "    raise ValueError(\"PII 解密失败（密钥错误或数据损坏）\")\n"
    )
    m2_new = (
        "    # 3. 全部密钥都失败\n"
        "    logger.error(\n"
        "        \"PII v1 decryption failed (exhausted current + %d previous keys): field=%s, len=%d\",\n"
        "        len(previous_fernets),\n"
        "        field,\n"
        "        len(ciphertext),\n"
        "    )\n"
    )
    mutate("M2 删 Fernet 末端 raise", PII, m2_old, m2_new)

    # M3：删 P2_13「一之二十三」节标题行（文档结构钉）
    doc13_original = DOC13.read_text(encoding="utf-8")
    m3_line = (
        "## 一之二十三、#35 X 桶第二十二批：纯裁定批（0 接线，W=96 / X=119 不变）"
        "+ 连带修复「自出生即死」的专用计数器"
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

    # M4：删 P2_11 第二十二批条目头行（文档登记钉）
    doc11_original = DOC11.read_text(encoding="utf-8")
    m4_line = "- **第十三轮第二十二批（纯裁定批，0 接线，W=96 / X=119 不变 +"
    assert doc11_original.count(m4_line) == 1, "M4 锚点不唯一或不在"
    print("  [M4 删 P2_11 条目头行] 变异注入…")
    DOC11.write_text(doc11_original.replace(m4_line + "\n", ""), encoding="utf-8")
    rc = run_gate()
    assert rc != 0, "M4: 变异态闸门仍绿 —— 文档登记钉假绿！"
    print(f"  [M4 删 P2_11 条目头行] RED-OK（returncode={rc}）")
    DOC11.write_text(doc11_original, encoding="utf-8")
    rc2 = run_gate()
    assert rc2 == 0, "M4: 还原态闸门仍红"
    print("  [M4 删 P2_11 条目头行] GREEN-OK（还原后 returncode=0）")

    print("=" * 72)
    print("四条变异全部 RED-OK / GREEN-OK")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    sys.exit(main())
