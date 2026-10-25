"""ROUND_42：OTel 配置面真实性闸门（声明即有效，或显式改判）。

背景（P2_13 第二十九批独立待办 E1）：
`app/core/config.py` 的 STAB-P2-009 配置块里，`otel_enabled` 与
`otel_resource_attributes` 全仓零消费 —— 运维改环境变量毫无效果，
属于本项目已定性的缺陷类「配置项存在 ≠ 被消费 ⇒ 误导运维」。

ROUND_42 修法：
- `app/core/otel.py`：`init_otel` 新增 `enabled`（默认 True，保持库级直调
  既有行为）与 `resource_attributes` 形参；判定顺序 enabled → 已初始化
  幂等 → 依赖门 → endpoint 空；`enabled=False` 打印独立文案并返回 SKIPPED。
  资源属性按 "k=v,k2=v2" 解析，畸形项跳过 + debug，不打断装配。
- `app/main.py`：`_init_otel` 透传 `enabled=settings.otel_enabled` 与
  `resource_attributes=settings.otel_resource_attributes`。
- `backend/.env.example`：五个有消费的 OTel 项按 SENTRY_* 写法登记，
  并注明「需另装 SDK/exporter」与默认关闭。

行为变更：只配 endpoint、不开 `OTEL_ENABLED` 的部署由「追踪开启」变为
「追踪关闭」（见 CHANGELOG）。

四档：
- `TestConfigDefaults`：默认值实测；
- `TestSwitchContract`：开关优先级 / 三态 / 不置初始化标记；
- `TestResourceAttributes`：解析、畸形跳过、注入 `Resource.create`；
- `TestMainHealthAndRegistry`：main 透传、`/health/startup` 三态贯通、
  `.env.example` 登记、全仓消费点 AST 反向钉。
"""
from __future__ import annotations

import ast
import inspect
import logging
import pathlib
import sys
import types
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

import app.core.startup_status as ss_module
from app.core.otel import OtelInit, init_otel
from app.core.startup_status import (
    SKIPPED,
    StartupStatus,
    record_step_sync,
)

BACKEND = pathlib.Path(__file__).resolve().parents[1]
MAIN_REL = BACKEND / "app" / "main.py"
OTEL_REL = BACKEND / "app" / "core" / "otel.py"
CFG_REL = BACKEND / "app" / "core" / "config.py"
ENV_EXAMPLE_REL = BACKEND / ".env.example"


@pytest.fixture
def fresh_status(monkeypatch):
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


def _settings_stub(**overrides) -> SimpleNamespace:
    values = dict(
        otel_service_name="mindcare-backend",
        app_version="test",
        otlp_endpoint="http://collector.invalid:4317",
        otlp_protocol="grpc",
        sentry_environment="test",
        otel_enabled=False,
        otel_resource_attributes="",
    )
    values.update(overrides)
    return SimpleNamespace(**values)


def _install_fake_sdk(monkeypatch, *, tracer_provider=None) -> SimpleNamespace:
    """装最小 opentelemetry 模块树；返回可断言的模块引用。"""

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
    sdk.trace.export = sdk_trace_export
    pkg.sdk = sdk
    return SimpleNamespace(pkg=pkg, trace=trace, resources=resources, sdk=sdk)


class TestConfigDefaults:
    """默认值必须与 .env.example 登记的默认一致。"""

    def test_defaults_are_off_and_empty(self):
        from app.core.config import Settings

        s = Settings()
        assert s.otel_enabled is False, "otel_enabled 默认值不再是 False"
        assert s.otlp_endpoint == "", "otlp_endpoint 默认值不再是空串"
        assert s.otlp_protocol == "grpc"
        assert s.otel_service_name == "mindcare-backend"
        assert s.otel_resource_attributes == ""


class TestSwitchContract:
    """开关语义：关闭是一票否决，且三条跳过路径都不得置初始化标记。"""

    def test_disabled_short_circuits_before_dependency_probe(
        self, fresh_otel, monkeypatch, caplog
    ):
        monkeypatch.setattr(
            fresh_otel,
            "_check_otel_available",
            lambda: (_ for _ in ()).throw(
                AssertionError("enabled=False 时不应探测依赖")
            ),
        )
        with caplog.at_level(logging.INFO, logger="app.core.otel"):
            state = init_otel(
                service_name="test",
                otlp_endpoint="http://collector.invalid:4317",
                enabled=False,
            )
        assert state is OtelInit.SKIPPED
        assert fresh_otel._otel_initialized is False
        msgs = [r.getMessage() for r in caplog.records]
        assert any(
            "OpenTelemetry disabled by configuration" in m
            and "otel_enabled=False" in m
            for m in msgs
        ), f"关闭路径缺少独立文案：{msgs}"
        assert not any("packages not installed" in m for m in msgs), (
            "关闭路径误报依赖缺失 —— 两条跳过原因被混为一谈"
        )

    def test_disabled_with_sdk_installed_does_not_assemble(
        self, fresh_otel, monkeypatch
    ):
        sdk = _install_fake_sdk(monkeypatch)
        monkeypatch.setattr(fresh_otel, "_check_otel_available", lambda: True)
        state = init_otel(
            service_name="test",
            otlp_endpoint="http://collector.invalid:4317",
            enabled=False,
        )
        assert state is OtelInit.SKIPPED
        assert sdk.resources.Resource.create.call_count == 0, (
            "enabled=False 仍构建了 Resource —— 开关没有挡住装配"
        )
        assert not sdk.trace.set_tracer_provider.called, (
            "enabled=False 仍设置了全局 TracerProvider"
        )
        assert fresh_otel._otel_initialized is False

    def test_enabled_default_keeps_library_behavior(self):
        sig = inspect.signature(init_otel)
        assert sig.parameters["enabled"].default is True, (
            "enabled 默认值必须为 True（库级直调既有行为）"
        )
        assert sig.parameters["resource_attributes"].default == ""

    def test_enabled_with_empty_endpoint_skipped(self, fresh_otel, monkeypatch):
        monkeypatch.setattr(fresh_otel, "_check_otel_available", lambda: True)
        state = init_otel(
            service_name="test", otlp_endpoint="", enabled=True
        )
        assert state is OtelInit.SKIPPED
        assert fresh_otel._otel_initialized is False

    def test_enabled_with_sdk_ok(self, fresh_otel, monkeypatch):
        sdk = _install_fake_sdk(monkeypatch)
        state = init_otel(
            service_name="test",
            otlp_endpoint="http://collector.invalid:4317",
            enabled=True,
        )
        assert state is OtelInit.OK
        assert fresh_otel._otel_initialized is True
        assert sdk.trace.set_tracer_provider.called

    def test_assembly_failure_returns_failed(self, fresh_otel, monkeypatch):
        class _BoomProvider:
            def __init__(self, *args, **kwargs) -> None:
                raise RuntimeError("provider boom")

        _install_fake_sdk(monkeypatch, tracer_provider=_BoomProvider)
        state = init_otel(
            service_name="test",
            otlp_endpoint="http://collector.invalid:4317",
            enabled=True,
        )
        assert state is OtelInit.FAILED
        assert fresh_otel._otel_initialized is False, "失败路径不得置初始化标记"


class TestResourceAttributes:
    """`otel_resource_attributes` 的解析与注入。"""

    def test_parse_normal_and_malformed_items(self, fresh_otel, caplog):
        with caplog.at_level(logging.DEBUG, logger="app.core.otel"):
            parsed = fresh_otel._parse_resource_attributes(
                "team=core, env = prod ,broken,=no-key,,team_id="
            )
        assert parsed == {"team": "core", "env": "prod", "team_id": ""}, parsed
        debug_msgs = [
            r.getMessage() for r in caplog.records if r.levelno == logging.DEBUG
        ]
        assert any("broken" in m for m in debug_msgs), (
            f"缺 '=' 的畸形项未留痕：{debug_msgs}"
        )
        assert any("=no-key" in m for m in debug_msgs), (
            f"空 key 的畸形项未留痕：{debug_msgs}"
        )

    def test_resource_create_receives_configured_attrs(
        self, fresh_otel, monkeypatch
    ):
        sdk = _install_fake_sdk(monkeypatch)
        state = init_otel(
            service_name="svc",
            service_version="1.2.3",
            otlp_endpoint="http://collector.invalid:4317",
            environment="test",
            enabled=True,
            resource_attributes="team=core,env=prod",
        )
        assert state is OtelInit.OK
        attrs = sdk.resources.Resource.create.call_args.args[0]
        assert attrs["team"] == "core", f"配置的资源属性未进入 Resource.create：{attrs}"
        assert attrs["env"] == "prod"
        assert attrs["service.name"] == "svc"
        assert attrs["service.version"] == "1.2.3"
        assert attrs["deployment.environment"] == "test"

    def test_malformed_only_does_not_break_assembly(self, fresh_otel, monkeypatch):
        _install_fake_sdk(monkeypatch)
        state = init_otel(
            service_name="svc",
            otlp_endpoint="http://collector.invalid:4317",
            enabled=True,
            resource_attributes="broken,=x",
        )
        assert state is OtelInit.OK, (
            "畸形资源属性把整条装配打成 FAILED —— 解析问题被升级成故障"
        )
        assert fresh_otel._otel_initialized is True


class TestMainHealthAndRegistry:
    """交付路径：main 透传、启动状态三态、登记面与消费点反向钉。"""

    def test_main_forwards_switch_and_attrs(self):
        tree = ast.parse(MAIN_REL.read_text(encoding="utf-8"))
        fn = next(
            n
            for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name == "_init_otel"
        )
        call = next(
            n
            for n in ast.walk(fn)
            if isinstance(n, ast.Call)
            and isinstance(n.func, ast.Name)
            and n.func.id == "init_otel"
        )
        kwargs = {kw.arg: ast.unparse(kw.value) for kw in call.keywords}
        assert kwargs.get("enabled") == "settings.otel_enabled", (
            f"main 未透传开关：{kwargs}"
        )
        assert (
            kwargs.get("resource_attributes")
            == "settings.otel_resource_attributes"
        ), f"main 未透传资源属性：{kwargs}"

    def test_disabled_records_skipped_not_failed(
        self, fresh_status, fresh_otel, monkeypatch
    ):
        main_mod = _main_mod()
        monkeypatch.setattr(
            main_mod, "settings", _settings_stub(otel_enabled=False)
        )
        assert main_mod._init_otel() is SKIPPED
        record_step_sync("init_otel", main_mod._init_otel, fatal=False)
        rec = fresh_status.components["init_otel"]
        assert rec.status == "skipped", rec.status
        assert fresh_status.failed_components == []

    def test_enabled_but_unconfigured_records_skipped(
        self, fresh_status, fresh_otel, monkeypatch
    ):
        main_mod = _main_mod()
        monkeypatch.setattr(
            main_mod,
            "settings",
            _settings_stub(otel_enabled=True, otlp_endpoint=""),
        )
        assert main_mod._init_otel() is SKIPPED
        record_step_sync("init_otel", main_mod._init_otel, fatal=False)
        assert fresh_status.components["init_otel"].status == "skipped"
        assert fresh_status.failed_components == []

    async def test_startup_payload_marks_disabled_as_skipped(
        self, fresh_status, fresh_otel, monkeypatch
    ):
        main_mod = _main_mod()
        monkeypatch.setattr(main_mod.app.state, "started", True, raising=False)
        monkeypatch.setattr(
            main_mod, "settings", _settings_stub(otel_enabled=False)
        )
        record_step_sync("init_otel", main_mod._init_otel, fatal=False)
        payload = await main_mod.startup_check()
        assert payload["components"]["init_otel"]["status"] == "skipped"
        assert "init_otel" not in payload["failed_components"], (
            "未启用被误报成启动失败"
        )
        assert payload["status"] == "ok"

    def test_env_example_registers_otel_keys(self):
        text = ENV_EXAMPLE_REL.read_text(encoding="utf-8")
        for key in (
            "OTEL_ENABLED=false",
            "OTLP_ENDPOINT",
            "OTLP_PROTOCOL",
            "OTEL_SERVICE_NAME",
            "OTEL_RESOURCE_ATTRIBUTES",
        ):
            assert key in text, f".env.example 缺少 OTel 登记项：{key}"
        assert "OTEL_ENABLED 是真开关" in text, (
            ".env.example 未声明开关语义（行为变更需对运维可见）"
        )
        assert "pip install opentelemetry-sdk opentelemetry-exporter-otlp" in text, (
            ".env.example 缺少「需另装 SDK/exporter」提示"
        )

    def test_config_consumers_are_exactly_main_and_otel(self):
        cfg = CFG_REL.read_text(encoding="utf-8")
        assert "otel_enabled: bool = False" in cfg
        assert "otel_resource_attributes: str = \"\"" in cfg

        targets = {"otel_enabled", "otel_resource_attributes"}
        hits: dict[str, list[str]] = {name: [] for name in targets}
        for p in (BACKEND / "app").rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            try:
                tree = ast.parse(p.read_text(encoding="utf-8"))
            except Exception:
                continue
            for n in ast.walk(tree):
                if isinstance(n, ast.Attribute) and n.attr in targets:
                    rel = p.relative_to(BACKEND).as_posix()
                    hits[n.attr].append(f"{rel}:{n.lineno}")
        for name, locs in hits.items():
            assert len(locs) == 1 and locs[0].startswith("app/main.py:"), (
                f"{name} 的消费点应恰好是 main.py 一处，实际 {locs}"
            )

        otel_tree = ast.parse(OTEL_REL.read_text(encoding="utf-8"))
        fn = next(
            n
            for n in otel_tree.body
            if isinstance(n, ast.FunctionDef) and n.name == "init_otel"
        )
        params = [a.arg for a in fn.args.args]
        assert "enabled" in params and "resource_attributes" in params, params
        loads = {
            n.id
            for n in ast.walk(fn)
            if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)
        }
        assert {"enabled", "resource_attributes"} <= loads, (
            "init_otel 声明了形参却不读取 —— 又一处「声明 ≠ 消费」"
        )
