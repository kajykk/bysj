"""P2-35 第三十六批变异验证（2 接线 + 16 不接，8 条变异）。

验证对象：两条接线的「必须接」断言 + 不接点的反向钉 + 结构钉 + 文档钉。
若某条变异态下闸门仍绿，说明对应断言钉的是恒真的东西，裁定理由不成立。

M1 删 `text_m2_bert_predictor` 的接线行
   → 字面量钉 + 运行时 E1 + 反向钉（必接项）必须红
M2 把 predictor 的 location 字面量改错（predict_failed → predict_faild）
   → 字面量钉 + E1（计数对不上）必须红（第二十六批 `_typo` 教训）
M3 删 `log_sanitizer` 的接线行
   → 字面量钉 + 运行时 E3 + 反向钉（必接项）必须红
M4 把 log_sanitizer 的 location 字面量改错
   → 字面量钉 + E3 必须红
M5 删 `_resolve_artifacts_dir` 的内层 `except Exception`
   → scaler P 型结构钉必须红（外层 except 变为可达 ⇒ P 型裁定被推翻）
M6 删 `shadow_mode_service` 的 compare_failed 接线
   → 同族互锁钉必须红
M7 删 P2_13「一之三十七」节标题行
   → 文档登记必须红（节标题结构钉，正文提及不算）
M8 给 `startup_status.py:100` 的不接 handler 注入 record_silent_degradation
   → 块级反向钉必须红（S 同源路径接线即恒 0 假设施）

纪律：锚点先读实际落盘文本；`mutate()` 用 try/finally 保证**无论 RED 还是
假绿都还原**；日志落盘（须 git add -f）。磁盘上是 CRLF，锚点写 `\n`
（read_text 通用换行归一为 \n、write_text 再写回 CRLF）。
"""

from __future__ import annotations

import pathlib
import subprocess

BACKEND = pathlib.Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
PY = BACKEND / ".venv" / "Scripts" / "python.exe"
PRED = BACKEND / "app" / "core" / "text_m2_bert_predictor.py"
LS = BACKEND / "app" / "core" / "log_sanitizer.py"
ML = BACKEND / "app" / "ml" / "model_loader.py"
SMS = BACKEND / "app" / "services" / "shadow_mode_service.py"
STARTUP = BACKEND / "app" / "core" / "startup_status.py"
DOC13 = REPO / "docs" / "P2_13_ROUND13_AUDIT.md"
AUDIT11 = REPO / "docs" / "P2_11_ROUND11_AUDIT.md"

TARGETS = [
    "tests/test_p2_11_round11.py::TestP235Round13Batch36Wiring",
]

PYTEST_BASE = [
    "-m", "pytest",
    "-o", "addopts=--strict-markers --import-mode=importlib",
    "-p", "no:cacheprovider", "-q", "--basetemp=.pytest_tmp_b36mut",
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
    print("第三十六批变异验证（2 接线 + 16 不接，8 条）")
    print("=" * 78)

    # M1 —— 删 predictor 接线行（保留 warning 与 return None）
    mutate(
        "M1", PRED,
        '            record_silent_degradation("core.text_m2_bert_predictor.predict_failed")\n',
        "",
    )

    # M2 —— predictor location 字面量 typo
    mutate(
        "M2", PRED,
        'record_silent_degradation("core.text_m2_bert_predictor.predict_failed")',
        'record_silent_degradation("core.text_m2_bert_predictor.predict_faild")',
    )

    # M3 —— 删 log_sanitizer 接线行（保留 debug 日志）
    mutate(
        "M3", LS,
        '            record_silent_degradation("core.log_sanitizer.filter_failed")\n',
        "",
    )

    # M4 —— log_sanitizer location 字面量 typo
    mutate(
        "M4", LS,
        'record_silent_degradation("core.log_sanitizer.filter_failed")',
        'record_silent_degradation("core.log_sanitizer.filter_faild")',
    )

    # M5 —— 拆掉 _resolve_artifacts_dir 的内层全捕获（外层变为可达）
    mutate(
        "M5", ML,
        "    try:\n"
        "        from app.core.config import settings\n"
        "\n"
        "        candidate = Path(settings.model_dir).resolve() / \"artifacts\" / \"physiological_optimized\"\n"
        "        if candidate.exists():\n"
        "            return candidate\n"
        "    except Exception:\n"
        '        logger.warning("artifacts dir resolution failed, fallback to default", exc_info=True)\n',
        "    from app.core.config import settings\n"
        "\n"
        "    candidate = Path(settings.model_dir).resolve() / \"artifacts\" / \"physiological_optimized\"\n"
        "    if candidate.exists():\n"
        "        return candidate\n",
    )

    # M6 —— 删第十六批同族互锁锚点 compare_failed
    mutate(
        "M6", SMS,
        '            record_silent_degradation("services.shadow_mode.compare_failed")\n',
        "",
    )

    # M7 —— 删 P2_13「一之三十七」节标题行
    mutate(
        "M7", DOC13,
        "## 一之三十七、#35 X 桶第三十六批：2 接线（text_m2_bert_predictor + log_sanitizer），W=102 / X=117 / S=34\n",
        "",
    )

    # M8 —— 给 startup_status.py:100 的 S 同源 handler 注入接线
    mutate(
        "M8", STARTUP,
        "            except Exception:\n"
        "                # 优雅降级: metrics 注册失败不影响启动状态收集\n"
        "                logger.debug(\n"
        "                    \"startup.metrics.increment.failed for %s\", name, exc_info=True\n"
        "                )\n",
        "            except Exception:\n"
        "                # 优雅降级: metrics 注册失败不影响启动状态收集\n"
        "                logger.debug(\n"
        "                    \"startup.metrics.increment.failed for %s\", name, exc_info=True\n"
        "                )\n"
        "                record_silent_degradation(\"mut.b36.startup_metrics_inc_failed\")\n",
    )

    print("=" * 78)
    print("8 条变异全部 RED-OK / 还原后 GREEN-OK")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
