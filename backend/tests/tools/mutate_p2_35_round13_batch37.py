"""P2-35 第三十七批变异验证（1 接线 + 14 不接，6 条变异）。

验证对象：fusion 接线的「必须接」断言 + 不接点的反向钉 + 结构钉 + 文档钉。
若某条变异态下闸门仍绿，说明对应断言钉的是恒真的东西，裁定理由不成立。

M1 删 fusion 的接线调用（保留 warning）
   → location 字面量钉 + 运行时 E1 + 反向钉（必接项）必须红
M2 把 location 字面量改错（canary_event_log_failed → canary_event_log_faild）
   → 字面量钉 + E1（计数对不上）必须红（第二十六批 `_typo` 教训）
M3 删 P2_13「一之三十八」节标题行
   → 文档登记必须红（节标题结构钉，正文提及不算）
M4 给 `validation.py:254` 的 D 型不接 handler 注入 record_silent_degradation
   → 块级反向钉必须红（脏数据跳过路径接线即重复计数）
M5 在 main.py 增加一个 `flush_to_db` 生产调用点（不可执行的 async def 内）
   → fusion 唯一落库方结构钉必须红（数据源唯一性前提被推翻）
M6 把 P2_11 附录条目的「第十三轮第三十七批」标识改掉
   → 文档登记必须红

纪律：锚点先读实际落盘文本；`mutate()` 用 try/finally 保证**无论 RED 还是
假绿都还原**；日志落盘（须 git add -f）。磁盘上是 CRLF，锚点写 `\n`
（read_text 通用换行归一为 \\n、write_text 再写回 CRLF）。
"""

from __future__ import annotations

import pathlib
import subprocess

BACKEND = pathlib.Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
PY = BACKEND / ".venv" / "Scripts" / "python.exe"
FUSION = BACKEND / "app" / "services" / "model_predict" / "fusion.py"
VALIDATION = BACKEND / "app" / "api" / "v1" / "validation.py"
MAIN = BACKEND / "app" / "main.py"
DOC13 = REPO / "docs" / "P2_13_ROUND13_AUDIT.md"
AUDIT11 = REPO / "docs" / "P2_11_ROUND11_AUDIT.md"

TARGETS = [
    "tests/test_p2_11_round11.py::TestP235Round13Batch37Wiring",
]

PYTEST_BASE = [
    "-m", "pytest",
    "-o", "addopts=--strict-markers --import-mode=importlib",
    "-p", "no:cacheprovider", "-q", "--basetemp=.pytest_tmp_b37mut",
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
    print("第三十七批变异验证（1 接线 + 14 不接，6 条）")
    print("=" * 78)

    # M1 —— 删 fusion 接线调用（保留 warning 与注释）
    mutate(
        "M1", FUSION,
        '            record_silent_degradation(\n'
        '                "services.model_predict.fusion.canary_event_log_failed"\n'
        '            )\n',
        "",
    )

    # M2 —— location 字面量 typo
    mutate(
        "M2", FUSION,
        '"services.model_predict.fusion.canary_event_log_failed"',
        '"services.model_predict.fusion.canary_event_log_faild"',
    )

    # M3 —— 删 P2_13「一之三十八」节标题行
    mutate(
        "M3", DOC13,
        "## 一之三十八、#35 X 桶第三十七批：1 接线（fusion canary 事件落库失败），W=103 / X=116\n",
        "",
    )

    # M4 —— 给 D 型不接 handler（validation:254）注入接线
    mutate(
        "M4", VALIDATION,
        "            except (ValueError, TypeError):\n                continue\n",
        "            except (ValueError, TypeError):\n"
        "                record_silent_degradation(\"x.b37.m4\")\n"
        "                continue\n",
    )

    # M5 —— main.py 增加 flush_to_db 生产调用点（模块级 async def，永不执行）
    mutate(
        "M5", MAIN,
        "def _warn_redis_missing_for_multiworker() -> None:",
        "async def _b37_mutation_flush_probe(db):\n"
        "    return await _observability_service.flush_to_db(db)\n"
        "\n"
        "\n"
        "def _warn_redis_missing_for_multiworker() -> None:",
    )

    # M6 —— 改掉 P2_11 附录批次标识（完整移除 token，追加 X 仍含子串会假绿）
    mutate(
        "M6", AUDIT11,
        "第十三轮第三十七批",
        "本轮",
    )

    print("=" * 78)
    print("第三十七批变异验证完成：6/6 RED-OK + GREEN-OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
