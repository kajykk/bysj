"""第三十批（第二十九批 CI 红的事故复盘）运行时证据.

事故: 第二十九批E2 断言 `_check_otel_available() is False` 依赖**本机venv 环境**,
本机 venv 恰好没装 opentelemetry-api 而 CI 装了(经 fastapi 传递) ⇒ CI 红。
本脚本建立**CI 等价环境**(顶层 opentelemetry 包可导入 / sdk+exporter 缺失),
逐条重算 7 条 handler 的可达性, 替换「依赖未交付 ⇒ 全部不可达」的错误判据。

用法: .venv/Scripts/python.exe tests/tools/probe_p2_35_batch30_runtime.py
"""

from __future__ import annotations

import pathlib
import sys
import tempfile


def _make_fake_otel(root: pathlib.Path) -> None:
    """构造「顶层 opentelemetry 可导入、sdk/exporter/instrumentation 全缺」的环境.

    这正是 requirements.lock 交付形态下 CI 的样子:
    opentelemetry-api==1.45.0 (via fastapi) 提供 opentelemetry/ 顶层包与trace,
    但 lock 无 opentelemetry-sdk / -exporter-otlp / -instrumentation-*。
    """
    pkg = root / "opentelemetry"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("", encoding="utf-8")
    # api 包提供的最小 trace 门面
    (pkg / "trace.py").write_text(
        "def set_tracer_provider(p):\n    pass\n\n\n"
        "def get_tracer_provider():\n    class _P:\n"
        "        def shutdown(self):\n            pass\n    return _P()\n",
        encoding="utf-8",
    )


def main() -> None:
    import importlib
    import logging

    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2]))
    otel = importlib.import_module("app.core.otel")

    # ---------- E1: 依赖门在 CI 等价环境下是「开」的, 不是我上批断言的关----------
    saved_path = list(sys.path)
    saved_modules = {k: v for k, v in sys.modules.items() if k.split(".")[0] == "opentelemetry"}
    for k in saved_modules:
        del sys.modules[k]

    with tempfile.TemporaryDirectory() as td:
        _make_fake_otel(pathlib.Path(td))
        sys.path.insert(0, td)
        try:
            available = otel._check_otel_available()
            print(f"[E1] CI 等价环境下 _check_otel_available() = {available}")
            assert available is True, (
                "顶层 opentelemetry 包应可导入 —— 说明依赖门在 CI 里是开的，"
                "第二十九批 P4 判据（依赖未交付 ⇒ 全部不可达）不成立"
            )

            # ---------- E2: 真正的阻断点是 otlp_endpoint 默认空串 ----------
            otel._otel_initialized = False
            no_endpoint = otel.init_otel("b30_probe", otlp_endpoint="")
            print(f"[E2a] otlp_endpoint='' 时 init_otel 返回 {no_endpoint}")
            assert no_endpoint is otel.OtelInit.SKIPPED, (
                "空 endpoint 应返回 SKIPPED（ROUND_40 三态）"
            )
            assert otel._otel_initialized is False, "空endpoint 不得置 _otel_initialized"

            # ---------- E3: 配了 endpoint 后 L133 外层 except 真实可达 ----------
            otel._otel_initialized = False
            records: list[logging.LogRecord] = []

            class _Cap(logging.Handler):
                def __init__(self) -> None:
                    super().__init__()
                    self.records: list[logging.LogRecord] = []

                def emit(self, record: logging.LogRecord) -> None:
                    self.records.append(record)

            handler = _Cap()
            otel.logger.addHandler(handler)
            otel.logger.setLevel(logging.DEBUG)
            try:
                # 顶层的 trace 在此时已可导入; sdk/exporter 缺失 ⇒ L133 命中
                with_endpoint = otel.init_otel(
                    "b30_probe", otlp_endpoint="http://collector:4317"
                )
            finally:
                otel.logger.removeHandler(handler)

            print(f"[E3] 配了 endpoint 时 init_otel 返回 {with_endpoint}")
            warns = [r for r in handler.records if r.levelno >= logging.WARNING]
            msgs = [r.getMessage() for r in warns]
            print(f"[E3] warning 条数={len(warns)}")
            for m in msgs:
                print(f"       - {m[:96]}")
            assert with_endpoint is otel.OtelInit.FAILED, (
                "sdk 缺失时 init_otel 应返回 FAILED（配置了但初始化失败）"
            )
            assert any("initialization failed" in m for m in msgs), (
                f"L133 外层 except 未被触发 ⇒ 该 handler 在交付形态下并不可达，"
                f"P4 可成立；实际记录={msgs}"
            )
            assert otel._otel_initialized is False, "失败后不得置 _otel_initialized"

            # ---------- E4: 三个 _instrument_* handler 仍不可达 ----------
            # 它们只在 init 成功(需 sdk+exporter)之后才被调用 ⇒ 由 L133 失败
            # 之前的正常路径保护，交付形态下不可达。
            src = otel.__file__ and pathlib.Path(otel.__file__).read_text(encoding="utf-8")
            assert src, "读不到 otel.py 源码"
            init_body = src[src.index("def init_otel(") : src.index("def _instrument_fastapi(")]
            for name in ("_instrument_fastapi", "_instrument_sqlalchemy", "_instrument_redis"):
                assert name in init_body, f"{name} 不在 init_otel 体内"
            idx_calls = [init_body.index(f"    {n}()") for n in
                         ("_instrument_fastapi", "_instrument_sqlalchemy", "_instrument_redis")]
            idx_success = init_body.index("        _otel_initialized = True")
            assert all(i > idx_success for i in idx_calls), (
                "三处 _instrument_* 调用出现在 _otel_initialized=True 之前 ⇒ "
                "失败路径也会触发，P 型不成立"
            )
            print("[E4] 三处 _instrument_* 调用行号均大于 `_otel_initialized = True` 行号"
                  f" ({min(idx_calls)} > {idx_success}) ⇒ 仅成功路径可达")

            # ---------- E5: instrument_app / shutdown_otel 受 _otel_initialized 闸门保护 ----------
            cap2 = _Cap()
            otel.logger.addHandler(cap2)
            otel.logger.setLevel(logging.DEBUG)
            try:
                otel._otel_initialized = False
                otel.instrument_app(object())
                otel.shutdown_otel()
                gated = len(cap2.records)
                print(f"[E5a] _otel_initialized=False：instrument_app+shutdown_otel "
                      f"产生日志 {gated} 条（应0，闸门直接return）")
                assert gated == 0, "未初始化时这两个函数不应产生任何日志"

                # 反证: 置True 后 L203/L205/L228 才可达
                otel._otel_initialized = True
                base = len(cap2.records)
                otel.instrument_app(object())  # instrumentation.fastapi 缺失 ⇒ ImportError 分支
                otel.shutdown_otel()
                unblocked = len(cap2.records) - base
                print(f"[E5b] _otel_initialized=True：产生日志 {unblocked} 条"
                      f"（反证 L203/L205/L228 仅在此后可达）")
                assert unblocked > 0, (
                    "置 True 后仍无日志 ⇒ 反证不成立，L205/L228 的可达性判据需重估"
                )
            finally:
                otel.logger.removeHandler(cap2)
                otel._otel_initialized = False
        finally:
            sys.path[:] = saved_path
            for k in list(sys.modules):
                if k.split(".")[0] == "opentelemetry":
                    del sys.modules[k]
            sys.modules.update(saved_modules)

    print("\n[E结论] 第二十九批 P4 判据错位：")
    print("  - 依赖门(_check_otel_available)在 CI 交付形态下**是开的**")
    print("    (opentelemetry-api==1.45.0 经 fastapi 传递引入顶层包)")
    print("  - 真正的默认阻断是 `otlp_endpoint` 默认空串 ⇒ init_otel 走 L77 提前 return")
    print("  - 一旦运维显式配置 endpoint，L133 外层 except **真实可达**"
          "(sdk/exporter 缺失 ⇒ ImportError 被 except Exception 捕获)")
    print("  ⇒ 7 条不是「全部不可达」：L133 可达(V 型：return False + warning)，")
    print("    L151/166/180/203/205/228 六条由 _otel_initialized 闸门保护而不可达(P 型)")


if __name__ == "__main__":
    main()