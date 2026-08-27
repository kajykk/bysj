"""T5-B3/B4 契约测试：R-A 19 个端点必须声明具体 response_model。

验证 OpenAPI 中各路径的 200 响应均引用 ``ApiResponse[...]`` 泛型包裹的具体
数据 Schema（此前 data 为裸 dict 或裸泛型，OpenAPI 无法导航）。范式同
``test_analytics_response_contract.py``（T5-B2）。
"""

from __future__ import annotations

import pytest

# (路径, 方法) 集合：R-A 已补齐 response_model 的端点
TYPED_ENDPOINTS = [
    ("/api/v1/user/content/", "get"),
    ("/api/v1/user/content/favorites/list", "get"),
    ("/api/v1/user/content/recommendations", "get"),
    ("/api/v1/user/content/recent-views", "get"),
    ("/api/v1/user/content/meditation/log", "post"),
    ("/api/v1/user/content/{content_id}", "get"),
    ("/api/v1/user/content/{content_id}/favorite", "post"),
    ("/api/v1/content-governance/{content_id}/review", "post"),
    ("/api/v1/content-governance/{content_id}/takedown", "post"),
    ("/api/v1/content-governance/{content_id}/restore", "post"),
    ("/api/v1/content-governance/pending", "get"),
    ("/api/v1/content-governance/history/{content_id}", "get"),
    ("/api/v1/ops-dashboard/overview", "get"),
    ("/api/v1/ops-dashboard/review-metrics", "get"),
    ("/api/v1/user/gdpr/delete", "post"),
    ("/api/v1/admin/gdpr/delete/{user_id}", "post"),
    ("/api/v1/user/upload", "post"),
    ("/api/v1/user/upload/batch", "post"),
]


@pytest.fixture(scope="module")
def openapi_schema():
    from app.main import app

    return app.openapi()


def _ok_data_ref(schema: dict, path: str, method: str) -> str:
    """提取指定路径 200 响应中 ApiResponse.data 的 $ref 名称."""
    responses = schema["paths"][path][method]["responses"]
    ok_resp = responses.get("200") or responses.get("201")
    assert ok_resp is not None, f"{method} {path} 缺少 200 响应声明"
    resp_schema = (
        ok_resp.get("content", {}).get("application/json", {}).get("schema", {})
    )
    ref = resp_schema.get("$ref")
    assert ref, f"{method} {path} 200 响应未引用命名 Schema"
    wrapper = schema["components"]["schemas"][ref.split("/")[-1]]
    data_prop = wrapper["properties"]["data"]
    if "$ref" in data_prop:
        return data_prop["$ref"].split("/")[-1]
    for variant in data_prop.get("anyOf", []):
        if "$ref" in variant:
            return variant["$ref"].split("/")[-1]
    raise AssertionError(f"{method} {path} 的 data 属性未引用命名 Schema")


class TestRaResponseModelContracts:
    @pytest.mark.parametrize(
        "path,method",
        TYPED_ENDPOINTS,
        ids=[f"{m.upper()} {p}" for p, m in TYPED_ENDPOINTS],
    )
    def test_endpoint_data_is_navigable(self, openapi_schema, path, method):
        """每个端点 200 响应的 data 字段必须引用具体命名 Schema."""
        data_name = _ok_data_ref(openapi_schema, path, method)
        assert data_name, f"{method} {path} 未声明具体 data 类型"

    def test_metrics_query_declares_typed_response(self, openapi_schema):
        """metrics/query 直接返回 PrometheusQueryResponse（非 ok 信封）. """
        responses = openapi_schema["paths"]["/api/v1/query"]["get"]["responses"]
        resp_schema = responses["200"]["content"]["application/json"]["schema"]
        assert resp_schema["$ref"].endswith("PrometheusQueryResponse")

    def test_pending_list_has_paginated_shape(self, openapi_schema):
        data_name = _ok_data_ref(openapi_schema, "/api/v1/content-governance/pending", "get")
        props = openapi_schema["components"]["schemas"][data_name]["properties"]
        assert {"items", "total", "page", "page_size", "review_cycle_days"} <= set(props)

    def test_recommendations_preserves_explain_field(self, openapi_schema):
        """recommendations 必须保留顶层 explain（契约回归护栏）. """
        data_name = _ok_data_ref(
            openapi_schema, "/api/v1/user/content/recommendations", "get"
        )
        props = openapi_schema["components"]["schemas"][data_name]["properties"]
        assert "explain" in props, "recommendations 响应缺失 explain 字段"
        explain = props["explain"]
        assert "$ref" in explain or any(
            "$ref" in v for v in explain.get("anyOf", [])
        )
