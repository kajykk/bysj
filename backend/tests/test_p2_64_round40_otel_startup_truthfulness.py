"""ROUND_40：OTel 启动自检真实性闸门（Sentry 同型缺陷收口）。

背景（P2_13 第二十九批记录的独立待办信号）：
`main.py` 的 `_init_otel` 调用 `init_otel(...)` 但丢弃返回值，且 `init_otel`
的 bool 同时表示「未启用」与「初始化失败」⇒ `/health/startup` 一律记 `ok`，
无法区分「追踪已就绪」「SDK 没装/没配 endpoint」「装配失败」。

ROUND_40 修法：
- `app/core/otel.py`：`init_otel` 返回三态 `OtelInit.OK / SKIPPED / FAILED`；
  SKIPPED 只给两条前置未启用路径（顶层依赖不可导入、endpoint 未配置），
  装配异常 → FAILED；
- `app/main.py`：`_init_otel` 提到模块级；OK → None，SKIPPED → `SKIPPED`
  哨兵，FAILED → 抛 `OTelInitError`，由 `record_step_sync(fatal=False)`
  记 `failed`（不阻断启动）。

三档自检：
- `TestOtelContract`：驱动真实 `init_otel`，逐条覆盖三态；
- `TestMainWiring`：驱动真实 `main._init_otel`，验证映射、非致命与端点序列化；
- `TestBoundaryInterlock`：`otel_enabled` 的唯一消费位置（ROUND_42 由
  「死配置零消费」改判为「真开关单点消费」，互锁语义反转、强度不变）。
"""
from __future__ import annotations

import ast
import pathlib
import sys
import types
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

import app.core.startup_status as ss_module
from app.core.otel import OtelInit, init_otel
from app.core.startup_status import (
    SKIPPED,
    SkippedStep,
    StartupStatus,
    record_step_sync,
)

BACKEND = pathlib.Path(__file__).resolve().parents[1]
MAIN_REL = BACKEND / "app" / "main.py"
BATCH29_REL = BACKEND / "tests" / "test_p2_11_round11.py"


@pytest.fixture
def fresh_status(monkeypatch):
    """替换全局单例，避免与会话级 lifespan 的既有记录互相污染。"""
    fresh = StartupStatus()
    monkeypatch.setattr(ss_module, "startup_status", fresh)
    return fresh


@pytest.fixture
def fresh_otel(monkeypatch):
    import app.core.otel as otel

    monkeypatch.setattr(otel, "_otel_initialized", False)
    monkeypatch.setattr(otel, "_instrument_fastapi", lambda: None)
    monkeypatch.setattr(otel, "_instrument_sqlalchemy", lambda: None)
    monkeypatch.setattr(otel, "_instrument_redis", lambda: None)
    return otel


def _main_mod():
    return __import__("app.main", fromlist=["_init_otel", "OTelInitError"])


def _install_fake_sdk(monkeypatch, *, tracer_provider=None) -> types.ModuleType:
    """安装最小 opentelemetry 模块树；tracer_provider 可换成抛错类。"""

    def module(name: str) -> types.ModuleType:
        mod = types.ModuleType(name)
        monkeypatch.setitem(sys.modules, name, mod)
        return mod

    pkg = module("opentelemetry")
    trace = module("opentelemetry.trace")
    trace.set_tracer_provider = MagicMock(name="set_tracer_provider")
    pkg.trace = trace

    exporter = module("opentelemetry.exporter")
    otlp = module("opentelemetry.exporter.otlp")
    proto = module("opentelemetry.exporter.otlp.proto")
    grpc = module("opentelemetry.exporter.otlp.proto.grpc")
    trace_exporter = module("opentelemetry.exporter.otlp.proto.grpc.trace_exporter")
    trace_exporter.OTLPSpanExporter = MagicMock(name="OTLPSpanExporter")
    exporter.otlp = otlp
    otlp.proto = proto
    proto.grpc = grpc
    grpc.trace_exporter = trace_exporter
    pkg.exporter = exporter

    sdk = module("opentelemetry.sdk")
    resources = module("opentelemetry.sdk.resources")
    resources.Resource = MagicMock(name="Resource")
    resources.Resource.create.return_value = MagicMock(name="resource")
    sdk.resources = resources

    sdk_trace = module("opentelemetry.sdk.trace")
    if tracer_provider is None:
        tp = MagicMock(name="TracerProvider")
        tp.return_value.add_span_processor = MagicMock(name="add_span_processor")
        sdk_trace.TracerProvider = tp
    else:
        sdk_trace.TracerProvider = tracer_provider
    sdk.trace = sdk_trace

    sdk_trace_export = module("opentelemetry.sdk.trace.export")
    sdk_trace_export.BatchSpanProcessor = MagicMock(name="BatchSpanProcessor")
    sdk_trace.export = sdk_trace_export
    pkg.sdk = sdk
    return pkg


class TestOtelContract:
    """init_otel 的返回值契约：三态必须可分，不得继续用 False 混表失败。"""

    def test_empty_endpoint_skipped(self, fresh_otel, monkeypatch):
        monkeypatch.setattr(fresh_otel, "_check_otel_available", lambda: True)
        state = init_otel(service_name="test", otlp_endpoint="")
        assert state is OtelInit.SKIPPED
        assert fresh_otel._otel_initialized is False

    def test_dependency_unavailable_skipped(self, fresh_otel, monkeypatch):
        monkeypatch.setattr(fresh_otel, "_check_otel_available", lambda: False)
        state = init_otel(
            service_name="test", otlp_endpoint="http://collector.invalid:4317"
        )
        assert state is OtelInit.SKIPPED
        assert fresh_otel._otel_initialized is False

    def test_assembly_failure_returns_failed(self, fresh_otel, monkeypatch):
        class _BoomProvider:
            def __init__(self, *args, **kwargs) -> None:
                raise RuntimeError("provider boom")

        _install_fake_sdk(monkeypatch, tracer_provider=_BoomProvider)
        state = init_otel(
            service_name="test", otlp_endpoint="http://collector.invalid:4317"
        )
        assert state is OtelInit.FAILED
        assert fresh_otel._otel_initialized is False, "失败路径不得置初始化标记"

    def test_success_returns_ok(self, fresh_otel, monkeypatch):
        pkg = _install_fake_sdk(monkeypatch)
        state = init_otel(
            service_name="test", otlp_endpoint="http://collector.invalid:4317"
        )
        assert state is OtelInit.OK
        assert fresh_otel._otel_initialized is True
        assert pkg.trace.set_tracer_provider.called

    def test_already_initialized_is_ok_and_idempotent(self, fresh_otel, monkeypatch):
        monkeypatch.setattr(
            fresh_otel,
            "_check_otel_available",
            lambda: (_ for _ in ()).throw(AssertionError("幂等路径不应再探测依赖")),
        )
        monkeypatch.setattr(fresh_otel, "_otel_initialized", True)
        state = init_otel(
            service_name="test", otlp_endpoint="http://collector.invalid:4317"
        )
        assert state is OtelInit.OK

    def test_three_states_are_distinct(self):
        assert len({OtelInit.OK, OtelInit.SKIPPED, OtelInit.FAILED}) == 3


class TestMainWiring:
    """main._init_otel 必须把三态如实映射，且失败不阻断启动。"""

    def test_init_otel_is_module_level(self):
        tree = ast.parse(MAIN_REL.read_text(encoding="utf-8"))
        module_funcs = {
            n.name
            for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        }
        assert "_init_otel" in module_funcs, (
            "main._init_otel 应为模块级函数（lifespan 内嵌套则无法独立见证）"
        )

    def test_init_otel_maps_skipped_and_raises_failed(self):
        tree = ast.parse(MAIN_REL.read_text(encoding="utf-8"))
        fn = next(
            n
            for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name == "_init_otel"
        )
        returns = [ast.unparse(r) for r in ast.walk(fn) if isinstance(r, ast.Return)]
        assert any("SKIPPED" in r for r in returns), (
            "_init_otel 未把 SKIPPED 映射为哨兵 —— /health/startup 会谎报 ok"
        )
        assert all("FAILED" not in r for r in returns), (
            "_init_otel 把 FAILED 当返回值 —— 失败必须抛 OTelInitError，不得伪装"
        )
        assert any(isinstance(n, ast.Raise) for n in ast.walk(fn)), (
            "_init_otel 未对 FAILED 抛异常 —— 失败信号会被包装器记成 ok/skipped"
        )

    def test_lifespan_registers_init_otel_non_fatal(self):
        tree = ast.parse(MAIN_REL.read_text(encoding="utf-8"))
        lifespan = next(
            n
            for n in tree.body
            if isinstance(n, ast.AsyncFunctionDef) and n.name == "lifespan"
        )
        found = False
        for node in ast.walk(lifespan):
            if not (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Name)
                and node.func.id == "record_step_sync"
                and node.args
                and isinstance(node.args[0], ast.Constant)
                and node.args[0].value == "init_otel"
            ):
                continue
            fatal = next(
                (kw.value for kw in node.keywords if kw.arg == "fatal"), None
            )
            assert isinstance(fatal, ast.Constant) and fatal.value is False, (
                "init_otel 登记必须保持 fatal=False（追踪降级不得阻断启动）"
            )
            found = True
        assert found, "lifespan 中缺少 init_otel 的 record_step_sync 登记"

    def test_runtime_failed_records_failed_without_raising(
        self, fresh_status, monkeypatch
    ):
        main_mod = _main_mod()
        monkeypatch.setattr(main_mod, "init_otel", lambda **kwargs: OtelInit.FAILED)

        with pytest.raises(main_mod.OTelInitError):
            main_mod._init_otel()
        assert (
            record_step_sync("init_otel", main_mod._init_otel, fatal=False) is None
        ), "fatal=False 的失败必须被包装器吞掉，不得阻断启动"
        rec = fresh_status.components["init_otel"]
        assert rec.status == "failed"
        assert rec.error_type == "OTelInitError"
        assert "init_otel" in fresh_status.failed_components

    def test_runtime_failed_is_not_masked_as_skipped(self, fresh_status, monkeypatch):
        main_mod = _main_mod()
        monkeypatch.setattr(main_mod, "init_otel", lambda **kwargs: OtelInit.FAILED)

        try:
            main_mod._init_otel()
        except main_mod.OTelInitError:
            pass
        else:
            raise AssertionError(
                "FAILED 被映射成非异常返回 —— 失败伪装成未启用，/health 无法区分"
            )
        record_step_sync("init_otel", main_mod._init_otel, fatal=False)
        assert fresh_status.components["init_otel"].status == "failed"
        assert "init_otel" in fresh_status.failed_components

    def test_runtime_skipped_records_skipped(self, fresh_status, monkeypatch):
        main_mod = _main_mod()
        monkeypatch.setattr(main_mod, "init_otel", lambda **kwargs: OtelInit.SKIPPED)

        assert main_mod._init_otel() is SKIPPED
        record_step_sync("init_otel", main_mod._init_otel, fatal=False)
        assert fresh_status.components["init_otel"].status == "skipped"
        assert fresh_status.failed_components == []

    def test_runtime_ok_records_ok(self, fresh_status, monkeypatch):
        main_mod = _main_mod()
        monkeypatch.setattr(main_mod, "init_otel", lambda **kwargs: OtelInit.OK)

        assert main_mod._init_otel() is None
        record_step_sync("init_otel", main_mod._init_otel, fatal=False)
        assert fresh_status.components["init_otel"].status == "ok"
        assert fresh_status.failed_components == []

    async def test_startup_endpoint_serializes_three_states(
        self, fresh_status, monkeypatch
    ):
        main_mod = _main_mod()
        monkeypatch.setattr(main_mod.app.state, "started", True, raising=False)
        fresh_status.record("init_otel", "failed")
        fresh_status.record("init_sentry", "skipped")
        fresh_status.record("init_db", "ok")

        payload = await main_mod.startup_check()
        assert payload["status"] == "ok"
        assert payload["components"]["init_otel"]["status"] == "failed"
        assert payload["components"]["init_sentry"]["status"] == "skipped"
        assert payload["components"]["init_db"]["status"] == "ok"
        assert payload["failed_components"] == ["init_otel"]

    async def test_ready_degrades_on_failed_but_not_skipped(
        self, fresh_status, monkeypatch
    ):
        main_mod = _main_mod()
        snapshot = SimpleNamespace(
            database=True, redis=True, celery_worker=True, models=True
        )
        monkeypatch.setattr(
            main_mod, "get_health_snapshot_nonblocking", AsyncMock(return_value=snapshot)
        )

        fresh_status.record("init_otel", "failed")
        payload = await main_mod.readiness_check()
        assert payload["status"] == "degraded"
        assert payload["startup_failed_components"] == ["init_otel"]

        fresh_status.reset()
        fresh_status.record("init_otel", "skipped")
        payload = await main_mod.readiness_check()
        assert payload["status"] == "ok", "skipped 是未启用，不是降级"


class TestBoundaryInterlock:
    """边界互锁：`otel_enabled` 的唯一消费位置（ROUND_42 反转）。

    ROUND_40 时 `otel_enabled` 是死配置，本类钉「零消费」；ROUND_42 接线后
    零消费断言必然红，改为等价的**反弱化**互锁：`backend/app` 下只有
    `main._init_otel` 的 `enabled=settings.otel_enabled` 一处读取，且
    p2_11 的第二十九批改判钉仍在位。任何额外消费点或删除唯一消费点都会红。
    """

    def test_otel_enabled_single_consumer_in_main(self):
        src = MAIN_REL.read_text(encoding="utf-8")
        assert src.count("settings.otel_enabled") == 1, (
            "main.py 的 otel_enabled 透传不是恰好一处"
        )

        tree = ast.parse(src)
        fn = next(
            n
            for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name == "_init_otel"
        )
        consumers = [
            n.lineno
            for n in ast.walk(fn)
            if isinstance(n, ast.Attribute) and n.attr == "otel_enabled"
        ]
        assert len(consumers) == 1, (
            f"_init_otel 的 otel_enabled 消费点应为恰好 1 处，实际 {consumers}"
        )

        elsewhere: list[str] = []
        for p in (BACKEND / "app").rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            try:
                other = ast.parse(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            for n in ast.walk(other):
                if isinstance(n, ast.Attribute) and n.attr == "otel_enabled":
                    elsewhere.append(
                        f"{p.relative_to(BACKEND).as_posix()}:{n.lineno}"
                    )
        assert elsewhere == [f"app/main.py:{consumers[0]}"], (
            f"otel_enabled 出现预期外消费点：{elsewhere}"
        )

        batch29 = BATCH29_REL.read_text(encoding="utf-8")
        assert "def test_otel_enabled_consumers_locked" in batch29, (
            "E1 反弱化钉消失 —— 本轮的边界互锁失去引用对象"
        )
