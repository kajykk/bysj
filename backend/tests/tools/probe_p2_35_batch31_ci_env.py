"""第三十一批：CI 等价环境下的**闸门自验证**（防止再次写出环境依赖断言）。

背景：第三十批 CI 红了（1 failed / 6904 passed），红项是新写的
`test_instrument_app_and_shutdown_gated_by_initialized_flag` —— 它用
「`_otel_initialized=True` 时日志数 > 0」反证闸门生效，而那条日志在
CI 里根本不会出现（`opentelemetry-api` 经 fastapi 已安装 ⇒
`from opentelemetry import trace` 成功 ⇒ 走 `hasattr(provider,"shutdown")`
分支，而 ProxyTracerProvider 无 `shutdown` ⇒ 零日志）。本机之所以绿，
是因为本机 venv 恰好没装 otel ⇒ import 直接失败 ⇒ 落到
`except Exception` ⇒ 产生 1 条 warning。

**同一个错误在同一批测试里犯了两次**：第三十批刚把E2 从「环境状态」
改成「等价环境」，紧接着 E5 又写回「环境状态」。

本脚本的作用：**把「CI 装了 opentelemetry」这件事变成本地可复现的**。
做法是把一个 fake `opentelemetry` 包装进 `PYTHONPATH`，让 pytest 进程
**从启动起**就认为 otel 可导入（等价于 CI），然后跑整批闸门。
若闸门在这种环境下仍全绿 ⇒ 断言确实与环境无关。

对照跑两次：
  A) 本机默认环境（本机 venv 未装 otel）
  B) 注入 fake opentelemetry 的「CI 等价」环境
两次都必须全绿，否则说明仍有环境依赖断言。

用法: .venv/Scripts/python.exe tests/tools/probe_p2_35_batch31_ci_env.py
"""

from __future__ import annotations

import pathlib
import subprocess
import sys
import tempfile

BACKEND = pathlib.Path(__file__).resolve().parents[2]
PY = BACKEND / ".venv" / "Scripts" / "python.exe"
GATE = "tests/test_p2_11_round11.py::TestP235Round13Batch29Declined"

PYTEST_BASE = [
    "-m", "pytest",
    "-o", "addopts=--strict-markers --import-mode=importlib",
    "-p", "no:cacheprovider", "-q",
]


def run_gate(pythonpath: str | None, basetemp: str) -> tuple[int, str]:
    env = None
    if pythonpath:
        import os

        env = dict(os.environ)
        env["PYTHONPATH"] = pythonpath
    proc = subprocess.run(
        [str(PY), *PYTEST_BASE, f"--basetemp={basetemp}", GATE],
        cwd=BACKEND, capture_output=True, text=True, timeout=1200, env=env,
    )
    tail = [ln for ln in proc.stdout.splitlines() if "passed" in ln or "failed" in ln]
    return proc.returncode, (tail[-1] if tail else proc.stdout[-400:])


def make_ci_like_otel(root: pathlib.Path) -> None:
    """造出「CI 等价」的 opentelemetry：顶层包 + trace 可导入，无 sdk/exporter。

    关键细节（第三十批 E2b 踩过）：`opentelemetry` 真实安装是**命名空间包**
    （目录下无 `__init__.py`）。若这里写成普通包，`import opentelemetry` 拿到的
    是它，但 `from opentelemetry import trace` 在真实命名空间包下会失败——
    两种形态的可达性结论不同，必须与真实安装一致。故此处**不写
    `__init__.py`**，只提供 `trace.py`，复现命名空间包 + 顶层可导入的形态。
    """
    pkg = root / "opentelemetry"
    pkg.mkdir(parents=True, exist_ok=True)
    # 不写 __init__.py ⇒ 命名空间包（与真实 opentelemetry-api 一致）
    (pkg / "trace.py").write_text(
        "def set_tracer_provider(p):\n    pass\n\n\n"
        "def get_tracer_provider():\n"
        "    class _P:\n"
        "        # 真实 ProxyTracerProvider 有 shutdown；这里刻意不带，\n"
        "        # 复现「hasattr(provider,'shutdown') 为 False ⇒ 零日志」\n"
        "        pass\n"
        "    return _P()\n",
        encoding="utf-8",
    )


def main() -> int:
    print("=" * 72)
    print("第三十一批：CI 等价环境下自验证整批闸门（查残留环境依赖断言）")
    print("=" * 72)

    # 先确认注入真的生效：同一解释器下import 成功且无 sdk
    sys.path.insert(0, str(BACKEND))
    with tempfile.TemporaryDirectory() as td:
        make_ci_like_otel(pathlib.Path(td))
        sys.path.insert(0, td)
        try:
            import importlib

            otel = importlib.import_module("app.core.otel")
            print(f"[sanity] 注入后 _check_otel_available() = "
                  f"{otel._check_otel_available()}")
            assert otel._check_otel_available() is True, "注入未生效，探测失真"
            for missing in (
                "opentelemetry.sdk.trace",
                "opentelemetry.exporter.otlp.proto.grpc.trace_exporter",
                "opentelemetry.instrumentation.fastapi",
            ):
                try:
                    importlib.import_module(missing)
                except ImportError:
                    print(f"[sanity]   {missing} → ImportError（与 CI 一致）")
                else:
                    raise AssertionError(f"{missing} 竟可导入，探测失真")
        finally:
            sys.path.remove(td)
            for key in list(sys.modules):
                if key.split(".")[0] == "opentelemetry":
                    del sys.modules[key]

    print("\n[A] 本机默认环境（本机 venv 未装 opentelemetry）…")
    rc_a, tail_a = run_gate(None, ".pytest_tmp_b31env_a")
    print(f"    rc={rc_a} :: {tail_a}")
    assert rc_a == 0, f"本机环境就不绿（{tail_a}）—— 基线不成立，先修本机"

    print("\n[B] CI 等价环境（注入命名空间包形态的 opentelemetry）…")
    with tempfile.TemporaryDirectory() as td:
        make_ci_like_otel(pathlib.Path(td))
        rc_b, tail_b = run_gate(td, ".pytest_tmp_b31env_b")
    print(f"    rc={rc_b} :: {tail_b}")
    assert rc_b == 0, (
        f"CI 等价环境下闸门红（{tail_b}）⇒ 仍有环境依赖断言，"
        "按「断言钉交付形态下不变的事实」纪律必须重写"
    )

    print("\n[C] 反向验证：临时制造一个环境依赖断言，闸门必须在 B 下变红")
    test_file = BACKEND / "tests" / "test_p2_11_round11.py"
    original = test_file.read_text(encoding="utf-8")
    anchor = (
        "        otel = importlib.import_module(\"app.core.otel\")\n"
        "\n"
        "        probes: list[str] = []\n"
    )
    injected = (
        "        otel = importlib.import_module(\"app.core.otel\")\n"
        "\n"
        "        # PROBE-ENVDEP: 故意断言环境状态（本机未装 otel）\n"
        "        assert otel._check_otel_available() is False, (\n"
        "            \"PROBE-ENVDEP: 依赖本机未装 opentelemetry 的环境断言\"\n"
        "        )\n"
        "\n"
        "        probes: list[str] = []\n"
    )
    assert original.count(anchor) == 1, f"反向验证锚点不唯一/不存在：{original.count(anchor)}"
    print("    [C] 注入 PROBE-ENVDEP 环境依赖断言…")
    test_file.write_text(original.replace(anchor, injected), encoding="utf-8")
    try:
        with tempfile.TemporaryDirectory() as td:
            make_ci_like_otel(pathlib.Path(td))
            rc_c, tail_c = run_gate(td, ".pytest_tmp_b31env_c")
        print(f"    rc={rc_c} :: {tail_c}")
        assert rc_c != 0, (
            "注入环境依赖断言后 CI 等价环境竟仍绿 ⇒ 该环境的探测能力不足，"
            "本次「B 环境全绿」的结论不可信"
        )
        print("    [C] OK：CI 等价环境能识别环境依赖断言（B 的结论因此可信）")
    finally:
        test_file.write_text(original, encoding="utf-8")

    # 还原后必须仍绿
    rc_d, tail_d = run_gate(None, ".pytest_tmp_b31env_d")
    print(f"\n[D] 还原后复跑：rc={rc_d} :: {tail_d}")
    assert rc_d == 0, f"还原不完整（{tail_d}）"

    print("=" * 72)
    print("整批闸门在两种环境下均绿，且环境探针本身有效 ⇒ 无残留环境依赖断言")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())