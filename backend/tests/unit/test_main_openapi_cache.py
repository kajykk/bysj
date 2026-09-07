"""N3 修订：/openapi.json 序列化缓存契约测试。

背景：``app.main`` 将 FastAPI 默认 openapi 路由替换为「预序列化字节直出」，
消除每次请求 O(schema) 的 JSON 编码开销（load test 基线 p50=128ms / QPS137）。

本测试固化以下契约：
1. 路由替换后 ``/openapi.json`` 仍可访问，返回合法 JSON（含 openapi 版本与 paths）
2. 热路径命中缓存——两次请求返回相同字节，且缓存仅序列化一次
3. ``_invalidate_openapi_cache()`` 后，下一次请求触发缓存重建
4. 缓存内容与 ``app.openapi()`` 字典语义一致（字段集合不缺失）

边界：本应用路由表为 import 期静态注册（无运行期动态挂载点），缓存在此
前提下恒正确；若未来引入动态路由，必须在挂载后调用
``_invalidate_openapi_cache()``（见 main.py 边界说明）。
"""

from __future__ import annotations

import json

import pytest


@pytest.mark.usefixtures("client")
class TestOpenApiJsonCache:
    """main.py OpenAPI 缓存路由契约。"""

    def test_openapi_json_route_serves_valid_schema(self, client) -> None:
        from app.main import app

        resp = client.get(app.openapi_url or "/openapi.json")
        assert resp.status_code == 200
        assert resp.headers["content-type"].startswith("application/json")
        payload = resp.json()
        assert "openapi" in payload
        assert "paths" in payload
        # 191 端点的巨型 schema 不应为空
        assert len(payload["paths"]) > 0

    def test_cache_hit_returns_identical_bytes(self, client) -> None:
        from app.main import _get_openapi_json, _invalidate_openapi_cache, app

        _invalidate_openapi_cache()
        first = client.get(app.openapi_url or "/openapi.json")
        assert first.status_code == 200
        cached = _get_openapi_json()
        # 缓存已建立
        assert cached is not None
        # 热路径返回与缓存完全相同的字节
        second = client.get(app.openapi_url or "/openapi.json")
        assert second.content == cached
        # 缓存未被重建（同一 bytes 对象，证明第二次请求未重新序列化）
        assert _get_openapi_json() is cached

    def test_invalidate_rebuilds_on_next_request(self, client) -> None:
        from app.main import (
            _get_openapi_json,
            _invalidate_openapi_cache,
            app,
        )

        # 预热缓存
        client.get(app.openapi_url or "/openapi.json")
        assert _get_openapi_json() is not None

        # 失效后缓存清空
        _invalidate_openapi_cache()
        import app.main as main_module

        assert main_module._openapi_json_cache is None

        # 下一次请求触发重建，内容与失效前语义一致
        rebuilt = client.get(app.openapi_url or "/openapi.json")
        assert rebuilt.status_code == 200
        assert main_module._openapi_json_cache is not None
        assert json.loads(rebuilt.content) == json.loads(_get_openapi_json())

    def test_cached_schema_matches_app_openapi_dict(self, client) -> None:
        from app.main import _get_openapi_json, app

        cached_payload = json.loads(_get_openapi_json())
        schema = app.openapi()
        # 字段集合一致：缓存直出与字典序列化不缺失任何顶层字段
        assert set(cached_payload.keys()) == set(schema.keys())
        assert set(cached_payload["paths"].keys()) == set(schema["paths"].keys())
