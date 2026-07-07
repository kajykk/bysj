"""Extended tests for app/core/exceptions module."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.testclient import TestClient

from app.core.exceptions import (
    AppException,
    ModelException,
    ServiceException,
    ValidationException,
    install_exception_handlers,
)


class TestAppException:
    """Test AppException base class."""

    def test_app_exception_creation(self):
        """TC-COV-017: AppException stores all attributes."""
        exc = AppException(
            code="TEST_ERROR",
            message="Test message",
            status_code=400,
            details={"key": "value"},
            layer="TEST",
            fallback_to="DEFAULT",
        )
        assert exc.code == "TEST_ERROR"
        assert exc.message == "Test message"
        assert exc.status_code == 400
        assert exc.details == {"key": "value"}
        assert exc.layer == "TEST"
        assert exc.fallback_to == "DEFAULT"
        assert exc.timestamp is not None
        assert exc.request_id is not None

    def test_app_exception_to_dict(self):
        """TC-COV-018: AppException.to_dict returns structured dict."""
        exc = AppException(code="TEST", message="Test")
        result = exc.to_dict()
        assert "error" in result
        assert result["error"]["code"] == "TEST"
        assert result["error"]["message"] == "Test"
        assert "timestamp" in result["error"]
        assert "request_id" in result["error"]

    def test_app_exception_default_details(self):
        """TC-COV-019: AppException defaults details to empty dict."""
        exc = AppException(code="TEST", message="Test")
        assert exc.details == {}


class TestModelException:
    """Test ModelException."""

    def test_model_exception_defaults(self):
        """TC-COV-020: ModelException defaults layer to MODEL."""
        exc = ModelException(code="MODEL_FAIL", message="Model failed")
        assert exc.layer == "MODEL"
        assert exc.status_code == 500

    def test_model_exception_custom_status(self):
        """TC-COV-021: ModelException accepts custom status_code."""
        exc = ModelException(code="MODEL_FAIL", message="Model failed", status_code=503)
        assert exc.status_code == 503


class TestValidationException:
    """Test ValidationException."""

    def test_validation_exception_defaults(self):
        """TC-COV-022: ValidationException defaults layer to VALIDATION."""
        exc = ValidationException(code="INVALID", message="Invalid input")
        assert exc.layer == "VALIDATION"
        assert exc.status_code == 422


class TestServiceException:
    """Test ServiceException."""

    def test_service_exception_defaults(self):
        """TC-COV-023: ServiceException defaults layer to SERVICE."""
        exc = ServiceException(code="SERVICE_FAIL", message="Service failed")
        assert exc.layer == "SERVICE"
        assert exc.status_code == 500


class TestExceptionHandlers:
    """Test installed exception handlers."""

    def test_app_exception_handler(self):
        """TC-COV-024: AppException returns JSONResponse."""
        app = FastAPI()
        install_exception_handlers(app)

        @app.get("/test")
        def _raise():
            raise AppException(code="TEST", message="Test error", status_code=418)

        client = TestClient(app)
        resp = client.get("/test")
        assert resp.status_code == 418
        assert resp.json()["error"]["code"] == "TEST"

    def test_http_exception_handler(self):
        """TC-COV-025: HTTPException returns JSONResponse."""
        app = FastAPI()
        install_exception_handlers(app)

        @app.get("/test")
        def _raise():
            raise HTTPException(status_code=404, detail="Not found")

        client = TestClient(app)
        resp = client.get("/test")
        assert resp.status_code == 404
        assert resp.json()["error"]["code"] == "HTTP_404"

    def test_validation_error_handler(self):
        """TC-COV-026: RequestValidationError returns 422."""
        app = FastAPI()
        install_exception_handlers(app)

        @app.get("/test")
        def _test(param: int):
            return param

        client = TestClient(app)
        resp = client.get("/test?param=not_int")
        assert resp.status_code == 422
        assert resp.json()["error"]["code"] == "VALIDATION_ERROR"

    def test_generic_exception_handler(self):
        """TC-COV-027: Unhandled exceptions return 500."""
        from fastapi import FastAPI
        from fastapi.testclient import TestClient

        from app.core.exceptions import install_exception_handlers

        app = FastAPI()
        install_exception_handlers(app)

        @app.get("/test")
        def _raise():
            raise RuntimeError("Unexpected")

        # v1.31: 添加 raise_server_exceptions=False 使 handler 接管
        client = TestClient(app, raise_server_exceptions=False)
        resp = client.get("/test")
        assert resp.status_code == 500
        assert resp.json()["error"]["code"] == "INTERNAL_ERROR"
