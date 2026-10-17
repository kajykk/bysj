"""P2-35 第三十五批变异验证（0 接线批，8 条变异）。

本批 0 接线，所以验证对象是**8 条「不接」判据**是否真能翻转 —— 若某条
变异态下闸门仍绿，说明那条断言钉的是个恒真的东西，本批的裁定理由不成立。

M1 `cached_or_compute` 降级态改返回 6 键结构化空响应
   → E1 必须红（键集合变得不可分辨 ⇒ 同形性成立 ⇒ 该条本该接）
M2 在生产文件里加一处 `CanaryController()` 实例化
   → E2 必须红（死代码定性被推翻）
M3 在 `risk_service.py` 里加一处 `consume_flushed_logs` 生产消费者
   → E3 必须红（死缓冲区定性被推翻）
M4 删 `record_scheduled` 的内层 `except Exception`
   → E4 必须红（外层 except 变为可达 ⇒ P 型裁定被推翻）
M5 删 `event_bus.publish` 的内层 `except asyncio.QueueFull`
   → E5 必须红（外层 except 变为可达）
M6 在 `app/core/cache.py` 里加一行 `PROMETHEUS_MULTIPROC_DIR`
   → E6 必须红（跨进程收集器出现 ⇒ 计数不再恒 0）
M7 把 `degradation.py` 的 `from app.core.metrics import` 改成别的来源
   → E7 必须红（同源失效前提消失 ⇒ S 型裁定被推翻）
M8 删 `track_model_inference` 里 `except` 块的 `raise`
   → E8 必须红（业务异常不再外抛 ⇒ V 型定性被推翻）

纪律：锚点先读实际落盘文本；`mutate()` 用 try/finally 保证**无论 RED 还是
假绿都还原**；日志落盘（须 git add -f）。
"""

from __future__ import annotations

import pathlib
import subprocess

BACKEND = pathlib.Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
PY = BACKEND / ".venv" / "Scripts" / "python.exe"
OBS = BACKEND / "app" / "api" / "v1" / "observability" / "__init__.py"
CANARY = BACKEND / "app" / "ml" / "canary_controller.py"
FFM = BACKEND / "app" / "core" / "fire_forget_metrics.py"
BUS = BACKEND / "app" / "core" / "event_bus.py"
CACHE = BACKEND / "app" / "core" / "cache.py"
DEG = BACKEND / "app" / "core" / "degradation.py"
METRICS = BACKEND / "app" / "core" / "metrics.py"
DOC13 = REPO / "docs" / "P2_13_ROUND13_AUDIT.md"

TARGETS = [
    "tests/test_p2_11_round11.py::TestP235Round13Batch35Declined",
]

PYTEST_BASE = [
    "-m", "pytest",
    "-o", "addopts=--strict-markers --import-mode=importlib",
    "-p", "no:cacheprovider", "-q", "--basetemp=.pytest_tmp_b35mut",
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
    print("第三十五批变异验证（0 接线批，8 条）")
    print("=" * 78)

    # M1 —— 让降级态与空数据同形（键集合不可分辨）
    mutate(
        "M1", OBS,
        "            return {}, False",
        "            return {\n"
        '                "total_fired": 0,\n'
        '                "total_acked": 0,\n'
        '                "total_pending": 0,\n'
        '                "response_time": {},\n'
        '                "by_severity": {},\n'
        '                "ack_rate": 0.0,\n'
        "            }, False",
    )

    # M2 —— 给 CanaryController 造一个生产实例化点
    mutate(
        "M2", CANARY,
        "def get_comparison_summary(self) -> dict[str, Any]:",
        "_MUT_B35_PROBE = CanaryController()\n\n"
        "    def get_comparison_summary(self) -> dict[str, Any]:",
    )

    # M3 —— 给 _flushed_buffer 造一个生产消费者
    mutate(
        "M3", FFM,
        "logger = logging.getLogger(__name__)",
        "logger = logging.getLogger(__name__)\n\n"
        "def _mut_b35_consume() -> None:\n"
        "    from app.services.observability_service import observability_collector\n\n"
        "    observability_collector.consume_flushed_logs()",
    )

    # M4 —— 拆掉 record_scheduled 的内层全捕获
    mutate(
        "M4", FFM,
        "    try:\n"
        "        from app.core.metrics import fire_forget_tasks_total\n\n"
        "        fire_forget_tasks_total.inc(task_type=task_type, status=\"scheduled\")\n"
        "    except Exception as exc:\n"
        '        logger.debug("fire_forget record_scheduled failed: %s", exc)',
        "    from app.core.metrics import fire_forget_tasks_total\n\n"
        "    fire_forget_tasks_total.inc(task_type=task_type, status=\"scheduled\")",
    )

    # M5 —— 拆掉 event_bus.publish 的内层全捕获
    mutate(
        "M5", BUS,
        "        try:\n"
        "            self._ensure_queue().put_nowait(event)\n"
        "            self.events_published += 1\n"
        "        except asyncio.QueueFull:\n",
        "        if True:\n"
        "            self._ensure_queue().put_nowait(event)\n"
        "            self.events_published += 1\n"
        "        else:\n",
    )

    # M6 —— 造一个多进程收集器（跨进程计数从此可读）
    mutate(
        "M6", CACHE,
        "from __future__ import annotations",
        "from __future__ import annotations\n\n"
        "# PROMETHEUS_MULTIPROC_DIR 变异探针\n"
        "from prometheus_client import MultiProcessCollector  # noqa: F401",
    )

    # M7 —— 让 degradation 不再走 app.core.metrics（同源前提消失）
    mutate(
        "M7", DEG,
        "from app.core.metrics import silent_degradation_total",
        "silent_degradation_total = None\n"
        "from app.core.degradation_probe import silent_degradation_total  # noqa: F811",
    )

    # M8 —— 让 track_model_inference 不再转发业务异常
    mutate(
        "M8", METRICS,
        "    except Exception:\n"
        "        status = \"error\"\n"
        "        raise\n",
        "    except Exception:\n"
        "        status = \"error\"\n",
    )

    print("=" * 78)
    print("8 条变异全部 RED-OK / 还原后 GREEN-OK")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
