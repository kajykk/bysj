"""P2-35 第三十四批变异验证（1 接线批，7 条变异）。

验证对象：本批新增判据是否**真能翻转**（不是换个同样假绿的写法）。

M1 删 `_parse_detail_json` 的 `record_silent_degradation` 调用
   → location 字面量钉 + 块级钉 + E5 计数 + 棘轮必须红（本批唯一接线点）
M2 location 改 typo（`detail_json_parse_faild`）
   → 完整字面量钉 + E5 必须红（第二十六批 `_typo` 型变异的常规复查）
M3 给 `dedup.py:103`（同源失效路径）接线
   → 块级反向钉必须红（保护计数设施自身的路径接线即假设施）
M4 把 `_parse_detail_json` 的降级 `return {}` 改成 `raise`
   → E1/E2 同形性必须红（接线判据本身的反证：不回退就没有"假数据"）
M5 给 `OperationLog.detail` 加 JSON 合法性 CHECK 约束
   → E3 可达性结构钉必须红（判据前提被移除 ⇒ 损坏不再可达）
M6 删 P2_13「一之三十五」节标题
   → 文档登记必须红
M7 删同族互锁锚点 `_fetch_lock_memory_stats` 的接线
   → 互锁钉 + 块级钉必须红（第六批锚点消失 ⇒ 本批裁定失去参照）

纪律：锚点先读实际落盘文本；`mutate()` 用 try/finally 保证**无论 RED 还是
假绿都还原**；日志落盘（须 git add -f）。
"""

from __future__ import annotations

import pathlib
import subprocess

BACKEND = pathlib.Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
PY = BACKEND / ".venv" / "Scripts" / "python.exe"
AGG = BACKEND / "app" / "services" / "observability" / "aggregate.py"
DEDUP = BACKEND / "app" / "monitoring" / "dedup.py"
MODEL = BACKEND / "app" / "models" / "admin.py"
DOC13 = REPO / "docs" / "P2_13_ROUND13_AUDIT.md"

TARGETS = [
    "tests/test_p2_11_round11.py::TestP235Round13Batch34Wiring",
]

PYTEST_BASE = [
    "-m", "pytest",
    "-o", "addopts=--strict-markers --import-mode=importlib",
    "-p", "no:cacheprovider", "-q", "--basetemp=.pytest_tmp_b34mut",
]


def run_gate() -> int:
    """跑批次闸门类，返回 returncode（0 = 通过）。"""
    proc = subprocess.run(
        [str(PY), *PYTEST_BASE, *TARGETS],
        cwd=BACKEND, capture_output=True, text=True, timeout=1800,
    )
    tail = [ln for ln in proc.stdout.splitlines() if "passed" in ln or "failed" in ln]
    print("    gate:", tail[-1] if tail else proc.stdout[-200:])
    return proc.returncode


def mutate(label: str, path: pathlib.Path, old: str, new: str) -> None:
    original = path.read_text(encoding="utf-8")
    assert old in original, (
        f"{label}: 锚点不在落盘文本中（先读实际文本再写脚本）: {old[:70]!r}"
    )
    assert original.count(old) == 1, f"{label}: 锚点不唯一（{original.count(old)} 处）"
    print(f"  [{label}] 变异注入…")
    path.write_text(new.join(original.split(old)), encoding="utf-8")
    try:
        rc = run_gate()
        assert rc != 0, f"{label}: 变异态闸门仍绿（returncode=0）—— 断言假绿！"
        print(f"  [{label}] RED-OK（returncode={rc}）")
    finally:
        # 无论 RED/假绿都必须还原：残留变异会污染后续批次的工作树
        path.write_text(original, encoding="utf-8")
    rc2 = run_gate()
    assert rc2 == 0, f"{label}: 还原后闸门仍红（returncode={rc2}）—— 还原不干净！"
    print(f"  [{label}] GREEN-OK（还原后 returncode={rc2}）")


def main() -> int:
    print("=" * 78)
    print("第三十四批变异验证（7 条）")
    print("=" * 78)

    # M1 删接线
    mutate(
        "M1", AGG,
        '        record_silent_degradation(\n'
        '            "services.observability.aggregate.detail_json_parse_failed"\n'
        '        )\n',
        '        # MUTANT M1: 接线被删\n',
    )

    # M2 location typo
    mutate(
        "M2", AGG,
        '"services.observability.aggregate.detail_json_parse_failed"',
        '"services.observability.aggregate.detail_json_parse_faild"',
    )

    # M3 给同源失效路径（dedup 计数设施自身失败）接线
    mutate(
        "M3", DEDUP,
        '            except Exception:  # noqa: BLE001 - 计数失败绝不能影响去重主流程\n'
        '                logger.debug("告警 detail 解析失败计数上报失败", exc_info=True)\n',
        '            except Exception:  # noqa: BLE001\n'
        '                logger.debug("告警 detail 解析失败计数上报失败", exc_info=True)\n'
        '                from app.core.degradation import record_silent_degradation\n'
        '                record_silent_degradation("monitoring.dedup.counter_failed")\n',
    )

    # M4 破坏同形性：不回退空 dict，直接抛出
    mutate(
        "M4", AGG,
        '            "services.observability.aggregate.detail_json_parse_failed"\n'
        '        )\n'
        '        return {}\n',
        '            "services.observability.aggregate.detail_json_parse_failed"\n'
        '        )\n'
        '        raise  # MUTANT M4: 不再回退空 dict\n',
    )

    # M5 给 detail 列加 JSON 合法性约束（破坏可达性前提）
    mutate(
        "M5", MODEL,
        '        CheckConstraint("operator_role IS NULL OR LENGTH(operator_role) <= 20",'
        ' name="ck_operation_logs_operator_role_length"),\n',
        '        CheckConstraint("operator_role IS NULL OR LENGTH(operator_role) <= 20",'
        ' name="ck_operation_logs_operator_role_length"),\n'
        '        CheckConstraint("detail IS NULL OR 1=1",'
        ' name="ck_operation_logs_detail_json"),\n',
    )

    # M6 删节标题
    mutate(
        "M6", DOC13,
        "## 一之三十五、",
        "## MUTANT 一之三十五、",
    )

    # M7 删同族互锁锚点（第六批接线）
    mutate(
        "M7", AGG,
        '        record_silent_degradation(\n'
        '            "services.observability.aggregate.lock_stats_unavailable"\n'
        '        )\n',
        '        # MUTANT M7: 同族互锁锚点被删\n',
    )

    print("=" * 78)
    print("7 条变异全部 RED-OK / GREEN-OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
