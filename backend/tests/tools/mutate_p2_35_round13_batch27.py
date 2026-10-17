"""P2-35 第二十七批变异验证（纯裁定批：0 接线，4 条变异）。

M1 给 `init_sentry` L103 SDK import 失败 handler 接线
   → 11 处块级反向钉必须红（含直调式 silent_degradation_total 禁现）
M2 把 `_set_redis_metrics` 的 `redis_circuit_state.set(2)` 改成纯 warning
   → 文件内正确范式互锁钉必须红（Redis 不可达将从可观测退化为静默）
M3 删 `_extract_status_code` 三条 handler 之一（`pass` → `return None`）
   → 三路径结构钉必须红（handler 数变 2）
M4 删 P2_13「一之二十八」节标题行 → 文档结构钉必须红

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
SENTRY = BACKEND / "app" / "core" / "sentry.py"
METRICS = BACKEND / "app" / "api" / "v1" / "metrics.py"
DOC13 = REPO / "docs" / "P2_13_ROUND13_AUDIT.md"

TARGETS = [
    "tests/test_p2_11_round11.py::TestP235Round13Batch27Declined",
    "tests/test_sentry.py",
    "tests/api/test_metrics.py",
    "tests/test_iss02_startup_status.py",
]

PYTEST_BASE = [
    "-m", "pytest",
    "-o", "addopts=--strict-markers --import-mode=importlib",
    "-p", "no:cacheprovider", "-q", "--basetemp=.pytest_tmp_b27mut",
]


def run_gate() -> int:
    """跑批次闸门类 + 受影响测试，返回 returncode（0 = 通过）。"""
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
    rc = run_gate()
    assert rc != 0, f"{label}: 变异态闸门仍绿（returncode=0）—— 断言假绿！"
    print(f"  [{label}] RED-OK（returncode={rc}）")
    path.write_text(original, encoding="utf-8")
    rc2 = run_gate()
    assert rc2 == 0, f"{label}: 还原态闸门仍红（returncode={rc2}）—— 还原不完整！"
    print(f"  [{label}] GREEN-OK（还原后 returncode=0）")


def main() -> int:
    print("=" * 72)
    print("P2-35 第二十七批变异验证（锚点均为落盘实读文本）")
    print("=" * 72)

    # 基线
    print("  [baseline] 变异前闸门应为绿…")
    assert run_gate() == 0, "基线不绿 —— 不许在红态下做变异验证"
    print("  [baseline] GREEN-OK")

    # M1：给 init_sentry 的 SDK import 失败 handler 接线
    m1_old = (
        '    except Exception:\n'
        '        logger.warning("sentry_sdk not available, skipping Sentry initialization")\n'
        '        return\n'
    )
    m1_new = (
        '    except Exception:\n'
        '        logger.warning("sentry_sdk not available, skipping Sentry initialization")\n'
        '        record_silent_degradation("core.sentry.init_sdk_unavailable")\n'
        '        return\n'
    )
    mutate("M1 给 init_sentry SDK import handler 接线", SENTRY, m1_old, m1_new)

    # M2：把 _set_redis_metrics 的 set(2) 改成纯 warning（正确范式互锁）
    m2_old = (
        '    except Exception:\n'
        '        redis_circuit_state.set(2)\n'
    )
    m2_new = (
        '    except Exception:\n'
        '        logger.warning("redis metric collection failed")\n'
    )
    mutate("M2 把 _set_redis_metrics 的 set(2) 改成纯 warning", METRICS, m2_old, m2_new)

    # M3：_extract_status_code 路径 3 的 handler 由 pass 改为 return None
    m3_old = (
        '    code = trace_tags.get("http.response.status_code")\n'
        '    if code is not None:\n'
        '        try:\n'
        '            return int(code)\n'
        '        except (ValueError, TypeError):\n'
        '            pass\n'
    )
    m3_new = (
        '    code = trace_tags.get("http.response.status_code")\n'
        '    if code is not None:\n'
        '        try:\n'
        '            return int(code)\n'
        '        except (ValueError, TypeError):\n'
        '            return None\n'
    )
    mutate("M3 裁掉 _extract_status_code 路径 3 的穷举降级", SENTRY, m3_old, m3_new)

    # M4：删 P2_13「一之二十八」节标题行（文档结构钉）
    doc13_original = DOC13.read_text(encoding="utf-8")
    m4_line = (
        "## 一之二十八、#35 X 桶第二十七批：纯裁定批（0 接线，W=97 / X=119 "
        "不变，sentry.py + api/v1/metrics.py 收口）"
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
