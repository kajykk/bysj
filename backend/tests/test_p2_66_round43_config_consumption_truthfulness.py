"""ROUND_43 配置消费真实性闸门.

开工实测（2026-10-25）：`Settings` 119 个字段中 3 项在 `backend/app/` 零消费：

- `route_feature_coverage_threshold`（默认 0.80）—— `_route_structured` 硬编码 0.80；
- `route_lite_min_text_length`（默认 20）—— 路由层与 `predict_lite` 各硬编码 20；
- `registry_auto_rollback_window_seconds`（默认 3600）—— 回退判定累计计数，
  窗口语义从未实现，docstring 却写「窗口内」。

本轮裁定：前两项接线（默认值不变、行为不变）；第三项保留为**显式预留**，
修正注释/docstring，不擅自实现窗口语义（那会改变回退行为）。

本闸门同时钉一枚全仓棘轮：`Settings` 每个字段都必须在 `backend/app/` 有读取点，
唯一豁免是上面的预留项；新增零消费字段、或豁免项过期（开始被消费）都会红。
"""

from __future__ import annotations

import ast
import asyncio
import inspect
import pathlib

import pytest

BACKEND = pathlib.Path(__file__).resolve().parents[1]
APP = BACKEND / "app"

CONFIG_REL = "app/core/config.py"
INFERENCE_REL = "app/core/model_engine/inference.py"
PREDICT_REL = "app/core/model_engine/predict.py"
SHADOW_REL = "app/services/shadow_comparison_service.py"

# 唯一允许零消费的字段（显式裁定，不是漏做）
ALLOWLIST = {
    "registry_auto_rollback_window_seconds": (
        "显式预留：窗口语义未实现，回退判定为进程内累计计数"
    ),
}


def _read(rel: str) -> str:
    return (BACKEND / rel).read_text(encoding="utf-8")


def _settings_fields() -> list[str]:
    tree = ast.parse(_read(CONFIG_REL))
    cls = next(
        n
        for n in tree.body
        if isinstance(n, ast.ClassDef) and n.name == "Settings"
    )
    return [
        s.target.id
        for s in cls.body
        if isinstance(s, ast.AnnAssign) and isinstance(s.target, ast.Name)
    ]


def _consumers() -> dict[str, list[str]]:
    """backend/app 下所有 `X.<field>` 形式的读取点（按字段名索引）。

    只按属性名匹配，宁宽松勿漏：同名属性出现在其它对象上会造成假「已消费」，
    棘轮因此偏保守；要发现「零消费」这一侧仍然有效（ROUND_42 的 otel_enabled
    与本案三项都是这样测出来的）。
    """
    found: dict[str, list[str]] = {}
    for p in APP.rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        rel = p.relative_to(BACKEND).as_posix()
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except SyntaxError:
            continue
        for n in ast.walk(tree):
            if isinstance(n, ast.Attribute):
                found.setdefault(n.attr, []).append(f"{rel}:{n.lineno}")
            elif (
                isinstance(n, ast.Call)
                and isinstance(n.func, ast.Name)
                and n.func.id == "getattr"
                and len(n.args) >= 2
                and isinstance(n.args[1], ast.Constant)
                and isinstance(n.args[1].value, str)
            ):
                found.setdefault(n.args[1].value, []).append(
                    f"{rel}:{n.lineno}"
                )
    return found


def _func(tree: ast.AST, name: str) -> ast.FunctionDef | ast.AsyncFunctionDef:
    return next(
        n
        for n in ast.walk(tree)
        if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef)) and n.name == name
    )


def _attrs(node: ast.AST) -> list[str]:
    return [
        n.attr for n in ast.walk(node) if isinstance(n, ast.Attribute)
    ]


def _compares_var_to_constant(
    node: ast.AST, var: str, constant: float | int
) -> list[str]:
    hits: list[str] = []
    for n in ast.walk(node):
        if not isinstance(n, ast.Compare):
            continue
        left = n.left
        if not (isinstance(left, ast.Name) and left.id == var):
            continue
        for comp in n.comparators:
            if isinstance(comp, ast.Constant) and comp.value == constant:
                hits.append(ast.unparse(n))
    return hits


class TestDefaultsUnchanged:
    """接线不得改变既有默认行为。"""

    def test_threshold_defaults(self):
        from app.core.config import Settings

        fields = Settings.model_fields
        assert fields["route_feature_coverage_threshold"].default == 0.80
        assert fields["route_lite_min_text_length"].default == 20
        assert fields["registry_auto_rollback_window_seconds"].default == 3600


class TestThresholdWiringStructure:
    def test_predict_lite_reads_setting_without_literal(self):
        fn = _func(ast.parse(_read(PREDICT_REL)), "predict_lite")
        assert "route_lite_min_text_length" in _attrs(fn), (
            "predict_lite 不再读取 settings.route_lite_min_text_length"
        )
        assert not _compares_var_to_constant(fn, "length", 20), (
            "predict_lite 的长度比较又硬编码了 20 —— 配置重新变成死配置"
        )

    def test_router_reads_both_settings_without_literals(self):
        fn = _func(ast.parse(_read(INFERENCE_REL)), "_route_structured")
        attrs = _attrs(fn)
        assert "route_feature_coverage_threshold" in attrs, (
            "_route_structured 不再读取 settings.route_feature_coverage_threshold"
        )
        assert "route_lite_min_text_length" in attrs, (
            "_route_structured 不再读取 settings.route_lite_min_text_length"
        )
        assert not _compares_var_to_constant(fn, "f_coverage", 0.8), (
            "覆盖率比较又硬编码了 0.80 —— 配置重新变成死配置"
        )
        assert not _compares_var_to_constant(fn, "length", 20), (
            "路由层的文本长度比较又硬编码了 20"
        )

    def test_config_declares_each_field_once(self):
        src = _read(CONFIG_REL)
        assert src.count("route_feature_coverage_threshold: float = 0.80") == 1
        assert src.count("route_lite_min_text_length: int = 20") == 1
        assert src.count("registry_auto_rollback_window_seconds: int = 3600") == 1


class TestRoutingRuntime:
    """运行时实证：改配置值，路由/降级结论随之改变。"""

    @pytest.fixture
    def engine(self):
        from app.core.model_engine import ModelEngine

        return ModelEngine()

    @staticmethod
    def _raw() -> dict:
        # 2/14 覆盖率 (0.1429)，gad7 + 30 字文本
        return {
            "age": 22,
            "gender": 1,
            "gad7_score": 10,
            "audio_transcript": "x" * 30,
        }

    def test_coverage_threshold_controls_structured_vs_lite(self, engine, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "route_feature_coverage_threshold", 0.99)
        info, routed = engine._route_structured(self._raw())
        assert routed == "lite", (
            f"阈值调到 0.99 后 0.1429 覆盖率不应走 structured：{info}"
        )

        monkeypatch.setattr(settings, "route_feature_coverage_threshold", 0.05)
        info, routed = engine._route_structured(self._raw())
        assert routed is None, (
            f"阈值调到 0.05 后 0.1429 覆盖率应走 structured：{info}"
        )
        assert info["routing_reason"] == "feature_coverage_sufficient"

    def test_lite_min_length_controls_router(self, engine, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "route_lite_min_text_length", 100)
        info, routed = engine._route_structured(self._raw())
        assert routed == "anxiety_only", (
            f"门槛调到 100 后 30 字文本不应路由到 lite：{info}"
        )

        monkeypatch.setattr(settings, "route_lite_min_text_length", 5)
        info, routed = engine._route_structured(self._raw())
        assert routed == "lite", (
            f"门槛调到 5 后 30 字文本应路由到 lite：{info}"
        )

    def test_lite_min_length_controls_predict_lite(self, engine, monkeypatch):
        from app.core.config import settings

        monkeypatch.setattr(settings, "route_lite_min_text_length", 100)
        short_result = asyncio.run(engine.predict_lite(10.0, "x" * 30))
        assert short_result["model_used"] == "anxiety_only_heuristic"
        assert short_result["fallback_reason"] == "anxiety_only_heuristic", (
            "高门槛应走长度不足分支（未覆盖 fallback_reason）"
        )

        monkeypatch.setattr(settings, "route_lite_min_text_length", 5)

        async def _boom(*_args, **_kwargs):
            raise RuntimeError("model unavailable in gate")

        monkeypatch.setattr(engine, "_load_model_async", _boom)
        passed_result = asyncio.run(engine.predict_lite(10.0, "x" * 30))
        assert passed_result["fallback_reason"].startswith("lite_model_unavailable"), (
            "低门槛下 30 字文本应通过长度检查并进入模型装配分支；"
            f"实际 fallback_reason={passed_result.get('fallback_reason')!r}"
        )


class TestWindowReserved:
    """registry_auto_rollback_window_seconds：显式预留，不是漏接线。"""

    def test_config_comment_marks_reserved(self):
        src = _read(CONFIG_REL)
        idx = src.index("registry_auto_rollback_window_seconds: int = 3600")
        window = src[max(0, idx - 260) : idx]
        assert "预留项" in window, "配置注释未标注「预留项」"
        assert "尚未实现" in window, "配置注释未声明窗口语义尚未实现"

    def test_docstring_no_longer_claims_window(self):
        from app.services.shadow_comparison_service import ShadowComparisonService

        src = inspect.getsource(ShadowComparisonService.should_auto_rollback)
        assert "累计" in src, "回退判定 docstring 未说明是累计计数"
        assert "窗口内推理样本" not in src, (
            "docstring 仍在宣称「窗口内推理样本」，与实现不符"
        )

    def test_comment_no_longer_claims_sliding_window(self):
        src = _read(SHADOW_REL)
        assert "窗口滑动在检查时计算" not in src, (
            "健康统计注释仍宣称滑动窗口，与累计实现不符"
        )

    def test_window_has_zero_consumers(self):
        assert "registry_auto_rollback_window_seconds" not in _consumers(), (
            "预留项开始被消费 —— 要么删掉豁免并补行为闸门，要么撤回消费"
        )


class TestConfigConsumptionRatchet:
    def test_zero_consumed_fields_exactly_allowlist(self):
        fields = set(_settings_fields())
        consumed = _consumers()
        zero = sorted(fields - set(consumed))
        assert zero == sorted(ALLOWLIST), (
            "Settings 零消费字段与豁免清单不一致："
            f"实际 {zero}，豁免 {sorted(ALLOWLIST)}。"
            "新增配置项必须同时接线，或显式登记为预留并写明理由。"
        )

    def test_allowlist_entries_exist_and_are_still_zero_consumed(self):
        fields = set(_settings_fields())
        consumed = _consumers()
        for name in ALLOWLIST:
            assert name in fields, f"豁免项 {name} 已不存在（过期豁免）"
            assert name not in consumed, (
                f"豁免项 {name} 已被消费 —— 请从 ALLOWLIST 移除并补行为闸门"
            )

    def test_scanner_sees_known_consumers(self):
        """扫描器自证：已知消费点必须可见，避免「恒空集合」式静默失效。"""
        consumed = _consumers()
        assert consumed.get("otel_enabled"), "扫描器漏掉 ROUND_42 的 otel_enabled"
        assert consumed.get("route_feature_coverage_threshold"), (
            "扫描器漏掉 route_feature_coverage_threshold"
        )
        lite_reads = consumed.get("route_lite_min_text_length") or []
        files = {c.rsplit(":", 1)[0] for c in lite_reads}
        assert {INFERENCE_REL, PREDICT_REL} <= files, (
            f"route_lite_min_text_length 的读取点应覆盖路由与预测两处：{sorted(files)}"
        )

    def test_allowlist_not_broadened_for_convenience(self):
        assert list(ALLOWLIST) == ["registry_auto_rollback_window_seconds"], (
            "ALLOWLIST 只允许这一项预留；其它字段一律必须接线"
        )


class TestEnvExampleRegistration:
    def test_routing_keys_registered(self):
        src = (BACKEND / ".env.example").read_text(encoding="utf-8")
        assert "ROUTE_FEATURE_COVERAGE_THRESHOLD=0.80" in src, (
            ".env.example 未登记 ROUTE_FEATURE_COVERAGE_THRESHOLD"
        )
        assert "ROUTE_LITE_MIN_TEXT_LENGTH=20" in src, (
            ".env.example 未登记 ROUTE_LITE_MIN_TEXT_LENGTH"
        )
