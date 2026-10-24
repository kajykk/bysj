"""P2-35 第二十九批变异验证（纯裁定批：0 接线，4 条变异）。

M1 把 `otel_enabled` 真的接进`init_otel`（新增消费点）
   → `test_otel_enabled_is_dead_config` 必须红（死配置发现被推翻）
M2 给 `otel.py` L205 `instrument_app` 的 Exception handler 接线
   → 块级反向钉必须红（含直调式 silent_degradation_total 禁现）
M3 把 `_common.py` L261 的 `continue` 改成 `break`（裁掉脏数据跳过）
   → `test_runtime_e4_dirty_data_same_shape` 必须红（脏数据将污染后续特征）
M4 删 P2_13「一之三十」节标题行 → 文档结构钉必须红

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
OTEL = BACKEND / "app" / "core" / "otel.py"
COMMON = BACKEND / "app" / "api" / "v1" / "model_predict" / "_common.py"
DOC13 = REPO / "docs" / "P2_13_ROUND13_AUDIT.md"

TARGETS = [
    "tests/test_p2_11_round11.py::TestP235Round13Batch29Declined",
]

PYTEST_BASE = [
    "-m", "pytest",
    "-o", "addopts=--strict-markers --import-mode=importlib",
    "-p", "no:cacheprovider", "-q", "--basetemp=.pytest_tmp_b29mut",
]


def run_gate() -> int:
    """跑批次闸门类，返回 returncode（0 = 通过）。"""
    proc = subprocess.run(
        [str(PY), *PYTEST_BASE, *TARGETS],
        cwd=BACKEND, capture_output=True, text=True, timeout=1200,
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
    try:
        rc = run_gate()
        assert rc != 0, (
            f"{label}: 变异态闸门仍绿（returncode=0）—— 断言假绿！"
        )
        print(f"  [{label}] RED-OK（returncode={rc}）")
    finally:
        # 无论 RED/假绿都必须还原：残留变异会污染后续批次的工作树
        path.write_text(original, encoding="utf-8")
    rc2 = run_gate()
    assert rc2 == 0, f"{label}: 还原态闸门仍红（returncode={rc2}）—— 还原不完整！"
    print(f"  [{label}] GREEN-OK（还原后 returncode=0）")


def main() -> int:
    print("=" * 72)
    print("P2-35 第二十九批变异验证（锚点均为落盘实读文本）")
    print("=" * 72)

    print("  [baseline] 变异前闸门应为绿…")
    assert run_gate() == 0, "基线不绿—— 不许在红态下做变异验证"
    print("  [baseline] GREEN-OK")

    # M1：给 otel_enabled 造一个真实消费点（死配置发现被推翻）
    m1_old = (
        "    if _otel_initialized:\n"
        "        logger.debug(\"STAB-P2-009: OpenTelemetry already initialized, skipping\")\n"
        "        return OtelInit.OK\n"
    )
    m1_new = (
        "    from app.core.config import settings as _settings\n"
        "\n"
        "    if not getattr(_settings, \"otel_enabled\", False):\n"
        "        return OtelInit.SKIPPED\n"
        "\n"
        "    if _otel_initialized:\n"
        "        logger.debug(\"STAB-P2-009: OpenTelemetry already initialized, skipping\")\n"
        "        return OtelInit.OK\n"
    )
    mutate("M1 给 otel_enabled 造真实消费点", OTEL, m1_old, m1_new)

    # M2：给 instrument_app 的 Exception handler 接线
    m2_old = (
        '    except Exception as exc:\n'
        '        logger.warning(\n'
        '            "STAB-P2-009: FastAPI instrumentation failed: %s", exc, exc_info=True\n'
        '        )\n'
    )
    m2_new = (
        '    except Exception as exc:\n'
        '        record_silent_degradation("core.otel.fastapi_instrumentation_failed")\n'
        '        logger.warning(\n'
        '            "STAB-P2-009: FastAPI instrumentation failed: %s", exc, exc_info=True\n'
        '        )\n'
    )
    mutate("M2 给 instrument_app handler 接线", OTEL, m2_old, m2_new)

    # M3：把结构化因子的脏数据 continue 改成 break（裁掉跳过）
    m3_old = (
        "        try:\n"
        "            v = float(value)\n"
        "        except (TypeError, ValueError):\n"
        "            continue\n"
    )
    m3_new = (
        "        try:\n"
        "            v = float(value)\n"
        "        except (TypeError, ValueError):\n"
        "            break  # MUTATION:裁掉脏数据跳过\n"
    )
    mutate("M3 把脏数据 continue 改成 break", COMMON, m3_old, m3_new)

    # M4：删 P2_13「一之三十」节标题行（文档结构钉）
    doc13_original = DOC13.read_text(encoding="utf-8")
    candidates = [
        ln for ln in doc13_original.splitlines() if ln.startswith("## 一之三十、")
    ]
    assert len(candidates) == 1, f"M4 锚点定位失败：{candidates}"
    m4_line = candidates[0]
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