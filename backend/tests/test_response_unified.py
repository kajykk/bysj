"""STAB-P1-001 测试: 统一响应体结构为 {code, message, data, error}.

验证所有响应路径 (成功/错误/限流/异常) 都返回统一的 4 字段结构,
前端可用同一套解析逻辑处理, 无需区分成功/错误分支.

覆盖路径:
1. ok() 辅助函数 - 成功响应
2. fail() 辅助函数 - 错误响应
3. AppException handler - 业务异常
4. HTTPException handler - HTTP 异常
5. RequestValidationError handler - 参数校验异常
6. generic Exception handler - 未知异常
7. RateLimitExceeded handler - 限流响应
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from slowapi.errors import RateLimitExceeded
from starlette.testclient import TestClient

from app.core.exceptions import AppException, install_exception_handlers
from app.core.rate_limit import rate_limit_exceeded_handler
from app.core.response import fail, ok

# ─────────────────────────────────────────────────────────────────────────────
# 1. ok() / fail() 辅助函数测试
# ─────────────────────────────────────────────────────────────────────────────


class TestOkFunction:
    """测试 ok() 辅助函数返回统一结构."""

    def test_ok_has_four_fields(self):
        """ok() 应返回 4 个字段: code, message, data, error."""
        result = ok({"key": "value"})
        assert set(result.keys()) == {"code", "message", "data", "error"}

    def test_ok_error_is_none(self):
        """ok() 的 error 字段应为 None."""
        result = ok({"key": "value"})
        assert result["error"] is None

    def test_ok_default_code_is_200(self):
        """ok() 默认 code=200."""
        assert ok("data")["code"] == 200

    def test_ok_default_message_is_success(self):
        """ok() 默认 message='success'."""
        assert ok("data")["message"] == "success"

    def test_ok_preserves_data(self):
        """ok() 应保留传入的 data."""
        assert ok({"a": 1})["data"] == {"a": 1}

    def test_ok_custom_code_and_message(self):
        """ok() 应支持自定义 code 和 message."""
        result = ok("data", message="created", code=201)
        assert result["code"] == 201
        assert result["message"] == "created"

    def test_ok_none_data(self):
        """ok(None) 应返回 data=None."""
        assert ok(None)["data"] is None


class TestFailFunction:
    """测试 fail() 辅助函数返回统一结构."""

    def test_fail_has_four_fields(self):
        """fail() 应返回 4 个字段: code, message, data, error."""
        result = fail("error msg")
        assert set(result.keys()) == {"code", "message", "data", "error"}

    def test_fail_data_is_none(self):
        """fail() 的 data 字段应为 None."""
        assert fail("error")["data"] is None

    def test_fail_default_code_is_500(self):
        """fail() 默认 code=500."""
        assert fail("error")["code"] == 500

    def test_fail_message_preserved(self):
        """fail() 应保留传入的 message."""
        assert fail("custom error")["message"] == "custom error"

    def test_fail_default_error_is_dict_with_message(self):
        """fail() 未指定 error 时, error 应为 {'message': message}."""
        result = fail("custom error")
        assert result["error"] == {"message": "custom error"}

    def test_fail_custom_error_dict(self):
        """fail() 应支持自定义 error dict."""
        custom_error = {"code": "VALIDATION_ERROR", "fields": ["name"]}
        result = fail("invalid", code=422, error=custom_error)
        assert result["error"] == custom_error
        assert result["code"] == 422

    def test_fail_custom_error_string(self):
        """fail() 应支持 error 为字符串."""
        result = fail("error", error="simple string")
        assert result["error"] == "simple string"


# ─────────────────────────────────────────────────────────────────────────────
# 2. AppException handler 测试
# ─────────────────────────────────────────────────────────────────────────────


def _build_test_app() -> FastAPI:
    """构建带异常处理器的测试 app."""
    app = FastAPI()
    install_exception_handlers(app)

    @app.get("/app-error")
    def app_error():
        raise AppException("TEST_ERROR", "test message", status_code=400, layer="TEST")

    @app.get("/http-error")
    def http_error():
        raise HTTPException(status_code=404, detail="not found")

    @app.get("/generic-error")
    def generic_error():
        raise ValueError("unexpected")

    # STAB-P1-001: 用真实请求参数校验失败触发 RequestValidationError
    @app.get("/validation-error")
    def validation_error(required_param: str):
        return {"param": required_param}

    return app


class TestAppExceptionHandlerUnified:
    """验证 AppException handler 返回统一 4 字段结构."""

    def test_app_exception_has_four_fields(self):
        """AppException 响应应包含 code, message, data, error 4 字段."""
        client = TestClient(_build_test_app())
        response = client.get("/app-error")
        assert response.status_code == 400
        data = response.json()
        assert set(data.keys()) == {"code", "message", "data", "error"}

    def test_app_exception_code_is_status_code(self):
        """AppException 顶层 code 应等于 HTTP 状态码."""
        client = TestClient(_build_test_app())
        data = client.get("/app-error").json()
        assert data["code"] == 400

    def test_app_exception_data_is_none(self):
        """AppException 顶层 data 应为 None."""
        client = TestClient(_build_test_app())
        data = client.get("/app-error").json()
        assert data["data"] is None

    def test_app_exception_message_preserved(self):
        """AppException 顶层 message 应等于异常 message."""
        client = TestClient(_build_test_app())
        data = client.get("/app-error").json()
        assert data["message"] == "test message"

    def test_app_exception_error_is_dict(self):
        """AppException error 字段应为 dict 且包含 code/message."""
        client = TestClient(_build_test_app())
        data = client.get("/app-error").json()
        assert isinstance(data["error"], dict)
        assert data["error"]["code"] == "TEST_ERROR"
        assert data["error"]["message"] == "test message"
        assert data["error"]["status_code"] == 400
        assert data["error"]["layer"] == "TEST"


class TestHttpExceptionHandlerUnified:
    """验证 HTTPException handler 返回统一 4 字段结构."""

    def test_http_exception_has_four_fields(self):
        """HTTPException 响应应包含 4 字段."""
        client = TestClient(_build_test_app())
        response = client.get("/http-error")
        assert response.status_code == 404
        data = response.json()
        assert set(data.keys()) == {"code", "message", "data", "error"}

    def test_http_exception_code_is_status_code(self):
        """HTTPException 顶层 code 应等于 HTTP 状态码."""
        client = TestClient(_build_test_app())
        data = client.get("/http-error").json()
        assert data["code"] == 404

    def test_http_exception_data_is_none(self):
        """HTTPException 顶层 data 应为 None."""
        client = TestClient(_build_test_app())
        data = client.get("/http-error").json()
        assert data["data"] is None

    def test_http_exception_error_code_is_http_prefix(self):
        """HTTPException error.code 应为 'HTTP_<status>'."""
        client = TestClient(_build_test_app())
        data = client.get("/http-error").json()
        assert data["error"]["code"] == "HTTP_404"
        assert data["error"]["message"] == "not found"


class TestGenericExceptionHandlerUnified:
    """验证 generic Exception handler 返回统一 4 字段结构."""

    def test_generic_exception_has_four_fields(self):
        """未知异常响应应包含 4 字段."""
        client = TestClient(_build_test_app(), raise_server_exceptions=False)
        response = client.get("/generic-error")
        assert response.status_code == 500
        data = response.json()
        assert set(data.keys()) == {"code", "message", "data", "error"}

    def test_generic_exception_code_is_500(self):
        """未知异常顶层 code 应为 500."""
        client = TestClient(_build_test_app(), raise_server_exceptions=False)
        data = client.get("/generic-error").json()
        assert data["code"] == 500

    def test_generic_exception_data_is_none(self):
        """未知异常顶层 data 应为 None."""
        client = TestClient(_build_test_app(), raise_server_exceptions=False)
        data = client.get("/generic-error").json()
        assert data["data"] is None

    def test_generic_exception_error_is_internal_error(self):
        """未知异常 error.code 应为 'INTERNAL_ERROR'."""
        client = TestClient(_build_test_app(), raise_server_exceptions=False)
        data = client.get("/generic-error").json()
        assert data["error"]["code"] == "INTERNAL_ERROR"


class TestValidationExceptionHandlerUnified:
    """验证 RequestValidationError handler 返回统一 4 字段结构."""

    def test_validation_exception_has_four_fields(self):
        """参数校验异常响应应包含 4 字段."""
        client = TestClient(_build_test_app())
        response = client.get("/validation-error")
        assert response.status_code == 422
        data = response.json()
        assert set(data.keys()) == {"code", "message", "data", "error"}

    def test_validation_exception_code_is_422(self):
        """参数校验异常顶层 code 应为 422."""
        client = TestClient(_build_test_app())
        data = client.get("/validation-error").json()
        assert data["code"] == 422

    def test_validation_exception_data_is_none(self):
        """参数校验异常顶层 data 应为 None."""
        client = TestClient(_build_test_app())
        data = client.get("/validation-error").json()
        assert data["data"] is None

    def test_validation_exception_error_code(self):
        """参数校验异常 error.code 应为 'VALIDATION_ERROR'."""
        client = TestClient(_build_test_app())
        data = client.get("/validation-error").json()
        assert data["error"]["code"] == "VALIDATION_ERROR"


# ─────────────────────────────────────────────────────────────────────────────
# 3. RateLimitExceeded handler 测试
# ─────────────────────────────────────────────────────────────────────────────


class TestRateLimitHandlerUnified:
    """验证 RateLimitExceeded handler 返回统一 4 字段结构."""

    def _make_exc(self):
        """构造一个 RateLimitExceeded 异常 (用 Mock 避免 Limit 复杂构造)."""
        from unittest.mock import MagicMock

        exc = MagicMock(spec=RateLimitExceeded)
        return exc

    def test_rate_limit_response_has_four_fields(self):
        """限流响应应包含 4 字段."""
        import json
        from unittest.mock import MagicMock

        from fastapi import Request

        exc = self._make_exc()
        request = MagicMock(spec=Request)

        response = rate_limit_exceeded_handler(request, exc)
        data = json.loads(response.body)
        assert set(data.keys()) == {"code", "message", "data", "error"}

    def test_rate_limit_response_code_is_429(self):
        """限流响应顶层 code 应为 429."""
        import json
        from unittest.mock import MagicMock

        from fastapi import Request

        exc = self._make_exc()
        request = MagicMock(spec=Request)
        response = rate_limit_exceeded_handler(request, exc)
        data = json.loads(response.body)
        assert data["code"] == 429

    def test_rate_limit_response_data_is_none(self):
        """限流响应顶层 data 应为 None."""
        import json
        from unittest.mock import MagicMock

        from fastapi import Request

        exc = self._make_exc()
        request = MagicMock(spec=Request)
        response = rate_limit_exceeded_handler(request, exc)
        data = json.loads(response.body)
        assert data["data"] is None

    def test_rate_limit_response_error_code(self):
        """限流响应 error.code 应为 'RATE_LIMIT_EXCEEDED'."""
        import json
        from unittest.mock import MagicMock

        from fastapi import Request

        exc = self._make_exc()
        request = MagicMock(spec=Request)
        response = rate_limit_exceeded_handler(request, exc)
        data = json.loads(response.body)
        assert data["error"]["code"] == "RATE_LIMIT_EXCEEDED"

    def test_rate_limit_status_code_is_429(self):
        """限流响应 HTTP 状态码应为 429."""
        from unittest.mock import MagicMock

        from fastapi import Request

        exc = self._make_exc()
        request = MagicMock(spec=Request)
        response = rate_limit_exceeded_handler(request, exc)
        assert response.status_code == 429


# ─────────────────────────────────────────────────────────────────────────────
# 4. 结构一致性测试 (成功 vs 错误响应 keys 对齐)
# ─────────────────────────────────────────────────────────────────────────────


class TestStructureConsistency:
    """验证成功响应与错误响应的 keys 完全对齐."""

    def test_ok_and_fail_have_same_keys(self):
        """ok() 和 fail() 应返回相同的 keys 集合."""
        success = ok({"data": "value"})
        error = fail("error msg")
        assert set(success.keys()) == set(error.keys())

    def test_ok_and_app_exception_have_same_keys(self):
        """ok() 与 AppException 响应应有相同的顶层 keys."""
        client = TestClient(_build_test_app())
        success_keys = set(ok("data").keys())
        error_keys = set(client.get("/app-error").json().keys())
        assert success_keys == error_keys

    def test_ok_and_http_exception_have_same_keys(self):
        """ok() 与 HTTPException 响应有相同的顶层 keys."""
        client = TestClient(_build_test_app())
        success_keys = set(ok("data").keys())
        error_keys = set(client.get("/http-error").json().keys())
        assert success_keys == error_keys

    def test_ok_and_generic_exception_have_same_keys(self):
        """ok() 与未知异常响应有相同的顶层 keys."""
        client = TestClient(_build_test_app(), raise_server_exceptions=False)
        success_keys = set(ok("data").keys())
        error_keys = set(client.get("/generic-error").json().keys())
        assert success_keys == error_keys

    def test_ok_and_rate_limit_have_same_keys(self):
        """ok() 与限流响应有相同的顶层 keys."""
        import json
        from unittest.mock import MagicMock

        from fastapi import Request

        success_keys = set(ok("data").keys())
        exc = MagicMock(spec=RateLimitExceeded)
        request = MagicMock(spec=Request)
        response = rate_limit_exceeded_handler(request, exc)
        error_keys = set(json.loads(response.body).keys())
        assert success_keys == error_keys
