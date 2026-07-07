"""Tests for exception handlers."""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from starlette.testclient import TestClient

from app.core.exceptions import (
    AppException,
    ModelException,
    ServiceException,
    ValidationException,
    install_exception_handlers,
)

app = FastAPI()
install_exception_handlers(app)


@app.get("/app-error")
def app_error():
    raise AppException("TEST_ERROR", "test message", status_code=400, layer="TEST")


@app.get("/model-error")
def model_error():
    raise ModelException("MODEL_FAIL", "model failed")


@app.get("/validation-error")
def validation_error():
    raise ValidationException("INVALID", "invalid input")


@app.get("/service-error")
def service_error():
    raise ServiceException("SERVICE_FAIL", "service failed")


@app.get("/http-error")
def http_error():
    raise HTTPException(status_code=404, detail="not found")


@app.get("/generic-error")
def generic_error():
    raise ValueError("unexpected")


client = TestClient(app)


class TestExceptions:
    """Test exception classes and handlers."""

    def test_app_exception_to_dict(self):
        """TC-COV-EXC-001: AppException to_dict."""
        exc = AppException("TEST", "msg", status_code=400, layer="L")
        d = exc.to_dict()
        assert d["error"]["code"] == "TEST"
        assert d["error"]["message"] == "msg"
        assert d["error"]["status_code"] == 400
        assert d["error"]["layer"] == "L"

    def test_app_exception_defaults(self):
        """TC-COV-EXC-002: AppException defaults."""
        exc = AppException("TEST", "msg")
        assert exc.status_code == 500
        assert exc.details == {}
        assert exc.layer is None
        assert exc.fallback_to is None
        assert exc.timestamp is not None
        assert exc.request_id is not None

    def test_model_exception(self):
        """TC-COV-EXC-003: ModelException."""
        exc = ModelException("MF", "model error")
        assert exc.code == "MF"
        assert exc.layer == "MODEL"
        assert exc.status_code == 500

    def test_validation_exception(self):
        """TC-COV-EXC-004: ValidationException."""
        exc = ValidationException("VE", "validation error")
        assert exc.code == "VE"
        assert exc.layer == "VALIDATION"
        assert exc.status_code == 422

    def test_service_exception(self):
        """TC-COV-EXC-005: ServiceException."""
        exc = ServiceException("SE", "service error")
        assert exc.code == "SE"
        assert exc.layer == "SERVICE"
        assert exc.status_code == 500

    def test_app_exception_handler(self):
        """TC-COV-EXC-006: AppException handler returns JSON."""
        response = client.get("/app-error")
        assert response.status_code == 400
        data = response.json()
        assert data["error"]["code"] == "TEST_ERROR"
        assert data["error"]["message"] == "test message"

    def test_model_exception_handler(self):
        """TC-COV-EXC-007: ModelException handler returns JSON."""
        response = client.get("/model-error")
        assert response.status_code == 500
        data = response.json()
        assert data["error"]["code"] == "MODEL_FAIL"

    def test_validation_exception_handler(self):
        """TC-COV-EXC-008: ValidationException handler returns JSON."""
        response = client.get("/validation-error")
        assert response.status_code == 422
        data = response.json()
        assert data["error"]["code"] == "INVALID"

    def test_service_exception_handler(self):
        """TC-COV-EXC-009: ServiceException handler returns JSON."""
        response = client.get("/service-error")
        assert response.status_code == 500
        data = response.json()
        assert data["error"]["code"] == "SERVICE_FAIL"

    def test_http_exception_handler(self):
        """TC-COV-EXC-010: HTTPException handler returns JSON."""
        response = client.get("/http-error")
        assert response.status_code == 404
        data = response.json()
        assert data["error"]["code"] == "HTTP_404"
        assert data["error"]["message"] == "not found"

    def test_generic_exception_handler(self):
        """TC-COV-EXC-011: Generic exception handler returns JSON."""
        # Create a fresh app with exception handlers but no Starlette error middleware
        from fastapi import FastAPI
        from starlette.testclient import TestClient

        from app.core.exceptions import install_exception_handlers

        test_app = FastAPI()
        install_exception_handlers(test_app)

        @test_app.get("/error")
        def error():
            raise ValueError("unexpected")

        test_client = TestClient(test_app, raise_server_exceptions=False)
        response = test_client.get("/error")
        assert response.status_code == 500
        data = response.json()
        assert data["error"]["code"] == "INTERNAL_ERROR"
