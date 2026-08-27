"""T5-B2 契约测试：/analytics 端点必须声明具体 response_model。

验证 OpenAPI 中四个 analytics 路径的 200 响应均引用 ``ApiResponse[...]``
泛型包裹的具体数据 Schema，且 data 字段包含预期键（此前 data 为裸 dict，
OpenAPI 无法导航）。这是 T5 各批次的可复制范式。
"""

from __future__ import annotations

import pytest


@pytest.fixture(scope="module")
def openapi_schema():
    from app.main import app

    return app.openapi()


def _ok_data_ref(schema: dict, path: str, method: str) -> str | None:
    """提取指定路径 200 响应中 ApiResponse.data 的 $ref 名称。

    ``ApiResponse.data: T | None`` 在 OpenAPI 中生成为
    ``anyOf: [{$ref}, {type: null}]``，此处解包取具体模型引用。
    """
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


class TestAnalyticsResponseContracts:
    def test_submit_events_declares_typed_response(self, openapi_schema):
        data_name = _ok_data_ref(openapi_schema, "/api/v1/analytics/events", "post")
        props = openapi_schema["components"]["schemas"][data_name]["properties"]
        assert set(props) == {"stored", "retention_days"}

    def test_get_consent_declares_typed_response(self, openapi_schema):
        data_name = _ok_data_ref(openapi_schema, "/api/v1/analytics/consent", "get")
        props = openapi_schema["components"]["schemas"][data_name]["properties"]
        assert set(props) == {"consented", "retention_days", "event_types"}

    def test_update_consent_declares_typed_response(self, openapi_schema):
        data_name = _ok_data_ref(openapi_schema, "/api/v1/analytics/consent", "put")
        props = openapi_schema["components"]["schemas"][data_name]["properties"]
        assert set(props) == {"consented", "changed"}

    def test_query_events_declares_typed_response(self, openapi_schema):
        data_name = _ok_data_ref(openapi_schema, "/api/v1/analytics/events", "get")
        data_schema = openapi_schema["components"]["schemas"][data_name]
        assert set(data_schema["properties"]) == {"events", "total"}
        # events 为带 $ref 的数组项（AnalyticsEventRecord），而非裸 object
        item = data_schema["properties"]["events"]["items"]
        assert "$ref" in item, "events.items 应引用 AnalyticsEventRecord"
        record_props = openapi_schema["components"]["schemas"][
            item["$ref"].split("/")[-1]
        ]["properties"]
        assert {
            "user_id",
            "event_type",
            "timestamp",
            "metadata",
            "client_ip",
            "received_at",
            "retention_expires_at",
        } == set(record_props)
