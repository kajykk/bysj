"""P2-35 第三十批变异验证（第二十九批 CI 红事故复盘批，4 条变异）。

背景：第二十九批 E2断言写成 `_check_otel_available() is False` —— 那是
**本机 venv 的环境状态**而非交付形态（`opentelemetry-api==1.45.0` 经
fastapi 传递进入 lock ⇒ CI 环境该门是开的）⇒ CI 1 failed / 6901 passed。
第三十批把判据从「环境」换成「交付形态 + 结构顺序」，本脚本验证新判据
真能翻转（不是换了个同样假绿的写法）。

M1 把三处 `_instrument_*` 调用之一提到 `_otel_initialized = True` **之前**
   → `test_instrument_calls_only_on_success_path` 必须红
   （否则失败路径也会触发它，L151/L166/L180 的 P 型不成立）
M2 删掉 `instrument_app` 的 `if not _otel_initialized: return` 闸门
   → `test_instrument_app_and_shutdown_gated_by_initialized_flag` 必须红
M3 把 `_check_otel_available` 改成同时 import sdk（收紧依赖门）
   → `test_otel_dependency_not_delivered` 必须红
   （「依赖门只查顶层包」这条前提被推翻）
M4 在 `init_otel` 的 L77 提前 return **之前**插一个 `from opentelemetry.sdk
   import trace`（让 sdk 缺失不再阻断 endpoint 检查之外的东西）
   → E2「空 endpoint 返回 False」必须红

纪律：锚点先读实际落盘文本；`mutate()` 用 try/finally 保证**无论 RED 还是
假绿都还原**；日志落盘（须 git add -f）。
"""

from __future__ import annotations

import pathlib
import subprocess

BACKEND = pathlib.Path(__file__).resolve().parents[2]
REPO = BACKEND.parent
PY = BACKEND / ".venv" / "Scripts" / "python.exe"
OTEL = BACKEND / "app" / "core" / "otel.py"

TARGETS = [
    "tests/test_p2_11_round11.py::TestP235Round13Batch29Declined",
]

PYTEST_BASE = [
    "-m", "pytest",
    "-o", "addopts=--strict-markers --import-mode=importlib",
    "-p", "no:cacheprovider", "-q", "--basetemp=.pytest_tmp_b30mut",
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
    assert rc2 == 0, f"{label}: 还原态闸门仍红（returncode={rc2}）—— 还原不完整！"
    print(f"  [{label}] GREEN-OK（还原后 returncode=0）")


def main() -> int:
    print("=" * 72)
    print("P2-35 第三十批变异验证（第二十九批 CI 红事故复盘）")
    print("=" * 72)

    print("  [baseline] 变异前闸门应为绿…")
    assert run_gate() == 0, "基线不绿—— 不许在红态下做变异验证"
    print("  [baseline] GREEN-OK")

    # M1：把 _instrument_fastapi() 提到 _otel_initialized = True 之前
    m1_old = (
        "        _otel_initialized = True\n"
        "        logger.info(\n"
        "            \"STAB-P2-009: OpenTelemetry initialized, service=%s, endpoint=%s, protocol=%s\",\n"
        "            service_name,\n"
        "            otlp_endpoint,\n"
        "            otlp_protocol,\n"
        "        )\n"
        "\n"
        "        # 自动 instrumentation\n"
        "        _instrument_fastapi()\n"
    )
    m1_new = (
        "        # 自动 instrumentation（MUTATION: 提到成功标记之前）\n"
        "        _instrument_fastapi()\n"
        "\n"
        "        _otel_initialized = True\n"
        "        logger.info(\n"
        "            \"STAB-P2-009: OpenTelemetry initialized, service=%s, endpoint=%s, protocol=%s\",\n"
        "            service_name,\n"
        "            otlp_endpoint,\n"
        "            otlp_protocol,\n"
        "        )\n"
    )
    mutate("M1 把 _instrument_fastapi 提到成功标记之前", OTEL, m1_old, m1_new)

    # M2：删掉 instrument_app 的 _otel_initialized 闸门
    m2_old = (
        "    if not _otel_initialized:\n"
        "        return\n"
        "\n"
        "    try:\n"
        "        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor\n"
    )
    m2_new = (
        "    # MUTATION: 闸门被删\n"
        "\n"
        "    try:\n"
        "        from opentelemetry.instrumentation.fastapi import FastAPIInstrumentor\n"
    )
    mutate("M2 删 instrument_app 的 _otel_initialized 闸门", OTEL, m2_old, m2_new)

    # M3：把依赖门从「只查顶层包」收紧为「同时查 sdk」
    m3_old = (
        "    try:\n"
        "        import opentelemetry  # noqa: F401\n"
        "\n"
        "        return True\n"
        "    except ImportError:\n"
        "        return False\n"
    )
    m3_new = (
        "    try:\n"
        "        import opentelemetry  # noqa: F401\n"
        "        from opentelemetry.sdk.trace import TracerProvider  # MUTATION: 收紧\n"
        "\n"
        "        return True\n"
        "    except ImportError:\n"
        "        return False\n"
    )
    mutate("M3 把依赖门收紧为同时查 sdk", OTEL, m3_old, m3_new)

    # M4：让空 endpoint 也能走到 L133（提前 return 被绕过）
    m4_old = (
        "    if not otlp_endpoint:\n"
        "        logger.info(\n"
        "            \"STAB-P2-009: OTLP endpoint not configured, \"\n"
        "            \"distributed tracing disabled\"\n"
        "        )\n"
        "        return False\n"
    )
    m4_new = (
        "    otlp_endpoint = otlp_endpoint or \"http://mutated.invalid:4317\"  # MUTATION\n"
    )
    mutate("M4 绕过空 endpoint 的提前 return", OTEL, m4_old, m4_new)

    print("=" * 72)
    print("四条变异全部 RED-OK / GREEN-OK")
    print("=" * 72)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())