"""P2-35 第二十八批变异验证（纯裁定批：0 接线，4 条变异）。

M1 把 `_incr_model_fallback` 内层 `except Exception` 改成 `raise`
   → `test_incr_model_fallback_inner_handler_keeps_full_capture` 必须红
   （内层不再全捕获 ⇒ fallback.py 四处外层 except 变为唯一防线，P 型判据失效）
M2 把 `_safe_set_alert_total` 里 `self._prev_total_fired = total_fired`
   提到 `_compute_trend` 之前（基线提前推进）
   → 结构钉+ 运行时 E2 双重必红（退避期间告警增量永久丢失）
M3 给 `fallback.py` L199 的 handler 接线
   → 块级反向钉必须红（含直调式 silent_degradation_total 禁现）
M4 删 P2_13「一之二十九」节标题行 → 文档结构钉必须红

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
FALLBACK = BACKEND / "app" / "core" / "model_engine" / "fallback.py"
LOADING = BACKEND / "app" / "core" / "model_engine" / "loading.py"
EXPORTER = BACKEND / "app" / "services" / "observability_exporter.py"
DOC13 = REPO / "docs" / "P2_13_ROUND13_AUDIT.md"

TARGETS = [
    "tests/test_p2_11_round11.py::TestP235Round13Batch28Declined",
]

PYTEST_BASE = [
    "-m", "pytest",
    "-o", "addopts=--strict-markers --import-mode=importlib",
    "-p", "no:cacheprovider", "-q", "--basetemp=.pytest_tmp_b28mut",
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
    rc = run_gate()
    assert rc != 0, f"{label}: 变异态闸门仍绿（returncode=0）—— 断言假绿！"
    print(f"  [{label}] RED-OK（returncode={rc}）")
    path.write_text(original, encoding="utf-8")
    rc2 = run_gate()
    assert rc2 == 0, f"{label}: 还原态闸门仍红（returncode={rc2}）—— 还原不完整！"
    print(f"  [{label}] GREEN-OK（还原后 returncode=0）")


def main() -> int:
    print("=" * 72)
    print("P2-35 第二十八批变异验证（锚点均为落盘实读文本）")
    print("=" * 72)

    # 基线
    print("  [baseline] 变异前闸门应为绿…")
    assert run_gate() == 0, "基线不绿 —— 不许在红态下做变异验证"
    print("  [baseline] GREEN-OK")

    # M1：_incr_model_fallback 内层 except改为重新抛出
    m1_old = (
        '        # 降级路径本身已在调用方打 error 日志, 此处 warning 补齐指标侧盲区。\n'
        '        logger.warning(\n'
        '            "model_fallback_total inc failed (model=%s reason=%s)",\n'
        '            model,\n'
        '            reason,\n'
        '            exc_info=True,\n'
        '        )\n'
    )
    m1_new = (
        '        # 降级路径本身已在调用方打 error 日志, 此处 warning 补齐指标侧盲区。\n'
        '        logger.warning(\n'
        '            "model_fallback_total inc failed (model=%s reason=%s)",\n'
        '            model,\n'
        '            reason,\n'
        '            exc_info=True,\n'
        '        )\n'
        '        raise\n'
    )
    mutate("M1 让 _incr_model_fallback 内层重新抛出", LOADING, m1_old, m1_new)

    # M2：失败轮推进基线（最典型的真实 bug：以为"采集过了"就把基线往前推）
    m2_old = (
        '        except Exception as e:\n'
        '            self._record_export_failure("alert_total", e)\n'
    )
    m2_new = (
        '        except Exception as e:\n'
        '            self._prev_total_fired += 1  # MUTATION: 失败轮误推进基线\n'
        '            self._record_export_failure("alert_total", e)\n'
    )
    mutate("M2 失败轮误推进 _prev_total_fired", EXPORTER, m2_old, m2_new)

    # M3：给 fallback.py L199 的 handler 接线
    m3_old = (
        '        except Exception:\n'
        '            logger.warning("model_fallback_total inc failed (text/heuristic)", exc_info=True)\n'
    )
    m3_new = (
        '        except Exception:\n'
        '            record_silent_degradation("core.model_engine.fallback.text_incr_failed")\n'
        '            logger.warning("model_fallback_total inc failed (text/heuristic)", exc_info=True)\n'
    )
    mutate("M3 给 fallback.py 文本回退 inc handler 接线", FALLBACK, m3_old, m3_new)

    # M4：删 P2_13「一之二十九」节标题行（文档结构钉）
    doc13_original = DOC13.read_text(encoding="utf-8")
    m4_line = (
        "## 一之二十九、#35 X 桶第二十八批：纯裁定批（0 接线，W=97 / X=119不变，"
        "fallback.py + observability_exporter.py + notifier.py复核）"
    )
    if m4_line not in doc13_original:
        # 文档实际可能带空格差异，改为按前缀定位唯一标题行
        candidates = [
            ln for ln in doc13_original.splitlines()
            if ln.startswith("## 一之二十九、")
        ]
        assert len(candidates) == 1, f"M4锚点定位失败：{candidates}"
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