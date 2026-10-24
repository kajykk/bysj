"""ROUND_39：启动自检真实性闸门（可选组件不得谎报 ok）。

背景（P2_13 §一之二十八 第二十七批记录的独立待办）：
`init_sentry` 在「未配置 DSN」与「SDK 不可导入」两条降级路径上正常 return，
`record_step_sync` 一律把正常返回记为 `ok` ⇒ `/health/startup` 的
`components.init_sentry.status` 无法区分「Sentry 已初始化」与「压根没启用」。

ROUND_39 修法：
- `startup_status` 新增 `SKIPPED` 哨兵：步骤正常返回哨兵 ⇒ 记 `skipped`；
- `init_sentry` 返回 bool（True 已初始化 / False 跳过）；
- `main._init_sentry` 把 False 映射为 `SKIPPED`，lifespan 仍以 `fatal=False`
  登记（truthful 化不得变成阻断启动）。

三档自检（缺一条就不算闸门）：
- `TestSentinelMechanism`：同步/异步包装器把哨兵记 `<skipped>`，普通返回仍 `ok`；
- `TestSentryContract`：无 DSN / SDK 缺失 → False，成功 → True；
- `TestMainWiring`：运行时驱动**真实** `main._init_sentry`（不是测试内复刻），
  结构化钉住模块级定义与 `fatal=False` 登记，并验证端点序列化。
"""
from __future__ import annotations

import ast
import pathlib
import sys
import types
from unittest.mock import MagicMock

import pytest

import app.core.startup_status as ss_module
from app.core.sentry import init_sentry
from app.core.startup_status import (
    SKIPPED,
    SkippedStep,
    StartupStatus,
    record_step_async,
    record_step_sync,
)

BACKEND = pathlib.Path(__file__).resolve().parents[1]
MAIN_REL = BACKEND / "app" / "main.py"


@pytest.fixture
def fresh_status(monkeypatch):
    """替换全局单例，避免与会话级 lifespan 的既有记录互相污染。"""
    fresh = StartupStatus()
    monkeypatch.setattr(ss_module, "startup_status", fresh)
    return fresh


def _install_mock_sdk(monkeypatch) -> MagicMock:
    sdk = types.ModuleType("sentry_sdk")
    sdk.init = MagicMock()
    fastapi_mod = types.ModuleType("sentry_sdk.integrations.fastapi")
    fastapi_mod.FastApiIntegration = MagicMock()
    sqlalchemy_mod = types.ModuleType("sentry_sdk.integrations.sqlalchemy")
    sqlalchemy_mod.SqlalchemyIntegration = MagicMock()
    integrations = types.ModuleType("sentry_sdk.integrations")
    integrations.FastApiIntegration = fastapi_mod.FastApiIntegration
    integrations.SqlalchemyIntegration = sqlalchemy_mod.SqlalchemyIntegration
    monkeypatch.setitem(sys.modules, "sentry_sdk", sdk)
    monkeypatch.setitem(sys.modules, "sentry_sdk.integrations", integrations)
    monkeypatch.setitem(sys.modules, "sentry_sdk.integrations.fastapi", fastapi_mod)
    monkeypatch.setitem(
        sys.modules, "sentry_sdk.integrations.sqlalchemy", sqlalchemy_mod
    )
    return sdk


def _main_ast() -> tuple[str, ast.Module]:
    src = MAIN_REL.read_text(encoding="utf-8")
    return src, ast.parse(src)


class TestSentinelMechanism:
    """SKIPPED 哨兵必须能改变状态，且不得误伤普通返回。"""

    def test_sync_sentinel_records_skipped(self, fresh_status):
        def _step():
            return SKIPPED

        out = record_step_sync("init_sentry", _step, fatal=False)
        assert out is SKIPPED
        rec = fresh_status.components["init_sentry"]
        assert rec.status == "skipped"
        assert rec.error_type == ""
        assert fresh_status.failed_components == []

    def test_sync_normal_return_records_ok(self, fresh_status):
        out = record_step_sync("init_sentry", lambda: 42, fatal=False)
        assert out == 42
        assert fresh_status.components["init_sentry"].status == "ok"

    async def test_async_sentinel_records_skipped(self, fresh_status):
        async def _step():
            return SKIPPED

        out = await record_step_async("init_otel", _step(), fatal=False)
        assert out is SKIPPED
        assert fresh_status.components["init_otel"].status == "skipped"

    async def test_async_normal_return_records_ok(self, fresh_status):
        async def _step():
            return "done"

        out = await record_step_async("init_otel", _step(), fatal=False)
        assert out == "done"
        assert fresh_status.components["init_otel"].status == "ok"

    def test_skipped_is_not_failed(self, fresh_status):
        record_step_sync("init_sentry", lambda: SKIPPED, fatal=False)
        assert fresh_status.failed_components == []
        assert fresh_status.components["init_sentry"].status != "failed"

    def test_sentinel_type_is_public(self):
        assert isinstance(SKIPPED, SkippedStep)
        assert repr(SKIPPED) == "SKIPPED"


class TestSentryContract:
    """init_sentry 的返回值契约：只有真正初始化成功才是 True。"""

    def test_without_dsn_returns_false(self, monkeypatch):
        monkeypatch.delenv("SENTRY_DSN", raising=False)
        assert init_sentry(dsn=None) is False

    def test_sdk_unavailable_returns_false(self, monkeypatch):
        monkeypatch.setitem(sys.modules, "sentry_sdk", None)
        assert init_sentry(dsn="https://key@sentry.io/123") is False

    def test_success_returns_true(self, monkeypatch):
        mock_sdk = _install_mock_sdk(monkeypatch)
        assert init_sentry(dsn="https://key@sentry.io/123") is True
        assert mock_sdk.init.called


class TestMainWiring:
    """main.py 必须把 False 映射为 SKIPPED，且不得阻断启动。"""

    def test_init_sentry_is_module_level(self):
        _src, tree = _main_ast()
        module_funcs = [
            n.name
            for n in tree.body
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        assert "_init_sentry" in module_funcs, (
            "main._init_sentry 应为模块级函数（lifespan 内嵌套则无法独立见证）"
        )

    def test_init_sentry_maps_false_to_sentinel(self):
        _src, tree = _main_ast()
        fn = next(
            n
            for n in tree.body
            if isinstance(n, ast.FunctionDef) and n.name == "_init_sentry"
        )
        returns = [n for n in ast.walk(fn) if isinstance(n, ast.Return)]
        assert any("SKIPPED" in ast.unparse(r) for r in returns), (
            "_init_sentry 未把未初始化路径映射为 SKIPPED —— "
            "/health/startup 会重新谎报 ok"
        )

    def test_lifespan_registers_non_fatal(self):
        _src, tree = _main_ast()
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
                and node.args[0].value == "init_sentry"
            ):
                continue
            fatal = next(
                (kw.value for kw in node.keywords if kw.arg == "fatal"), None
            )
            assert isinstance(fatal, ast.Constant) and fatal.value is False, (
                "init_sentry 登记必须保持 fatal=False（监控降级不得阻断启动）"
            )
            found = True
        assert found, "lifespan 中缺少 init_sentry 的 record_step_sync 登记"

    def test_runtime_false_path_records_skipped(self, fresh_status, monkeypatch):
        main_mod = __import__("app.main", fromlist=["_init_sentry"])
        monkeypatch.setattr(main_mod, "init_sentry", lambda **kwargs: False)

        assert main_mod._init_sentry() is SKIPPED
        record_step_sync("init_sentry", main_mod._init_sentry, fatal=False)
        rec = fresh_status.components["init_sentry"]
        assert rec.status == "skipped"
        assert fresh_status.failed_components == []

    def test_runtime_true_path_records_ok(self, fresh_status, monkeypatch):
        main_mod = __import__("app.main", fromlist=["_init_sentry"])
        monkeypatch.setattr(main_mod, "init_sentry", lambda **kwargs: True)

        assert main_mod._init_sentry() is None
        record_step_sync("init_sentry", main_mod._init_sentry, fatal=False)
        assert fresh_status.components["init_sentry"].status == "ok"

    async def test_startup_endpoint_exposes_skipped(self, fresh_status, monkeypatch):
        main_mod = __import__("app.main", fromlist=["startup_check"])
        monkeypatch.setattr(main_mod.app.state, "started", True, raising=False)
        fresh_status.record("init_sentry", "skipped")

        payload = await main_mod.startup_check()
        assert payload["components"]["init_sentry"]["status"] == "skipped"
        assert "init_sentry" not in payload["failed_components"]
