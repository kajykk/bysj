"""ROUND_34 / S-01：分析事件审计查询的租户隔离闸门。

缺陷背景：``_event_store`` 是汇聚所有租户的进程级全局列表，GET
``/analytics/events`` 原先只做裸角色判断（admin/super_admin）后
``records = list(_event_store)`` 整表拷出，写入侧也没有 ``tenant_id``
字段 ⇒ 租户 B 的 admin 能读到租户 A 的 user_id / metadata / client_ip。

替换层说明：本闸门直接调用**真实纯函数** ``_visible_events_for_tenant``
（不做 dependency_overrides / mock），并用 AST 断言钉住「写入侧真的带
tenant_id」「查询侧真的调用过滤函数」两处接线。翻转任一实现，断言真值
空间都会翻转：删掉过滤 → 混合输入用例红；删掉 tenant_id 写入 → AST 用例红。
"""

from __future__ import annotations

import ast
from pathlib import Path

from app.api.v1.analytics_events import _visible_events_for_tenant

_MODULE_PATH = (
    Path(__file__).resolve().parents[2] / "app" / "api" / "v1" / "analytics_events.py"
)


def _record(tenant_id: int, user_id: int, **extra: object) -> dict:
    record: dict = {
        "user_id": user_id,
        "tenant_id": tenant_id,
        "event_type": "assessment_start",
        "timestamp": 1_700_000_000_000,
        "metadata": {"page": "/dashboard", "risk_level": 2},
        "client_ip": "10.0.0.7",
        "received_at": "2026-11-06T00:00:00",
        "retention_expires_at": "2099-01-01T00:00:00",
    }
    record.update(extra)
    return record


class TestVisibleEventsForTenant:
    def test_mixed_tenants_only_returns_requested_tenant(self):
        """混合输入才能区分「返回全部」「返回空」「按租户过滤」三种实现。"""
        records = [
            _record(1, 11),
            _record(2, 22),
            _record(1, 12),
            _record(3, 33),
        ]
        result = _visible_events_for_tenant(records, 2)
        assert [r["user_id"] for r in result] == [22]

    def test_same_tenant_records_all_preserved(self):
        records = [_record(5, 51), _record(5, 52), _record(9, 91)]
        result = _visible_events_for_tenant(records, 5)
        assert [r["user_id"] for r in result] == [51, 52]

    def test_internal_fields_stripped_from_response(self):
        result = _visible_events_for_tenant([_record(1, 11)], 1)
        assert len(result) == 1
        assert "tenant_id" not in result[0]
        assert "client_ip" not in result[0]
        # 业务字段必须保留，避免「剥字段」被实现成「只留空壳」
        assert result[0]["user_id"] == 11
        assert result[0]["metadata"]["page"] == "/dashboard"
        assert result[0]["event_type"] == "assessment_start"

    def test_missing_tenant_id_is_rejected_fail_closed(self):
        record = _record(1, 11)
        del record["tenant_id"]
        assert _visible_events_for_tenant([record], 1) == []
        assert _visible_events_for_tenant([record], 999) == []

    def test_non_integer_tenant_id_is_rejected(self):
        record = _record(1, 11)
        record["tenant_id"] = "1"  # type: ignore[assignment]
        assert _visible_events_for_tenant([record], 1) == []

    def test_source_records_not_mutated(self):
        records = [_record(1, 11)]
        snapshot = {k: v for k, v in records[0].items()}
        _visible_events_for_tenant(records, 1)
        assert records[0] == snapshot


def _function_node(name: str) -> ast.AST:
    tree = ast.parse(_MODULE_PATH.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return node
    raise AssertionError(f"{name} 不存在于 analytics_events.py")


def test_submit_events_writes_tenant_id_in_record_literal():
    """AST：写入侧的 dict 字面量必须含 tenant_id 键（注释/docstring 不算命中）。"""
    node = _function_node("submit_events")
    keys = {
        key.value
        for sub in ast.walk(node)
        if isinstance(sub, ast.Dict)
        for key in sub.keys
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    }
    assert "tenant_id" in keys, "submit_events 写入事件时未附加 tenant_id"


def test_query_events_actually_calls_tenant_filter():
    """AST：查询端点必须调用过滤函数，不能只在注释里声明隔离。"""
    node = _function_node("query_events")
    called = {
        call.func.id
        for call in ast.walk(node)
        if isinstance(call, ast.Call) and isinstance(call.func, ast.Name)
    }
    assert "_visible_events_for_tenant" in called

    # 同一函数不得再把全局仓库直接整表拷出
    list_calls = [
        call
        for call in ast.walk(node)
        if isinstance(call, ast.Call)
        and isinstance(call.func, ast.Name)
        and call.func.id == "list"
        and any(
            isinstance(arg, ast.Name) and arg.id == "_event_store"
            for arg in call.args
        )
    ]
    assert not list_calls, "query_events 仍在直接 list(_event_store)（应使用过滤函数）"
