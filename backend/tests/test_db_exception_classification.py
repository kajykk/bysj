"""STAB-P2-001: DB exception classification tests."""

from __future__ import annotations

from fastapi import FastAPI
from sqlalchemy.exc import IntegrityError, OperationalError
from starlette.testclient import TestClient

from app.core.exceptions import install_exception_handlers

app = FastAPI()
install_exception_handlers(app)


@app.get("/integrity-error")
def integrity_error():
    raise IntegrityError(
        "INSERT INTO users (email) VALUES ('dup@example.com')",
        params={},
        orig=Exception("UNIQUE constraint failed: users.email"),
    )


@app.get("/operational-error")
def operational_error():
    raise OperationalError(
        "SELECT 1",
        params={},
        orig=Exception("server closed the connection unexpectedly"),
    )


@app.get("/integrity-error-no-orig")
def integrity_error_no_orig():
    raise IntegrityError("INSERT", params={}, orig=None)


client = TestClient(app)


class TestIntegrityErrorHandler:
    """IntegrityError -> 409 Conflict."""

    def test_returns_409_status(self):
        resp = client.get("/integrity-error")
        assert resp.status_code == 409

    def test_response_has_unified_structure(self):
        resp = client.get("/integrity-error")
        body = resp.json()
        assert set(body.keys()) == {"code", "message", "data", "error"}

    def test_code_is_409(self):
        resp = client.get("/integrity-error")
        body = resp.json()
        assert body["code"] == 409

    def test_data_is_none(self):
        resp = client.get("/integrity-error")
        body = resp.json()
        assert body["data"] is None

    def test_error_code_is_integrity_error(self):
        resp = client.get("/integrity-error")
        body = resp.json()
        assert body["error"]["code"] == "INTEGRITY_ERROR"

    def test_error_status_code_is_409(self):
        resp = client.get("/integrity-error")
        body = resp.json()
        assert body["error"]["status_code"] == 409

    def test_error_has_timestamp(self):
        resp = client.get("/integrity-error")
        body = resp.json()
        assert "timestamp" in body["error"]

    def test_error_has_request_id(self):
        resp = client.get("/integrity-error")
        body = resp.json()
        assert "request_id" in body["error"]
        assert body["error"]["request_id"]

    def test_works_without_orig(self):
        resp = client.get("/integrity-error-no-orig")
        assert resp.status_code == 409
        body = resp.json()
        assert body["error"]["code"] == "INTEGRITY_ERROR"


class TestOperationalErrorHandler:
    """OperationalError -> 503 Service Unavailable."""

    def test_returns_503_status(self):
        resp = client.get("/operational-error")
        assert resp.status_code == 503

    def test_response_has_unified_structure(self):
        resp = client.get("/operational-error")
        body = resp.json()
        assert set(body.keys()) == {"code", "message", "data", "error"}

    def test_code_is_503(self):
        resp = client.get("/operational-error")
        body = resp.json()
        assert body["code"] == 503

    def test_data_is_none(self):
        resp = client.get("/operational-error")
        body = resp.json()
        assert body["data"] is None

    def test_error_code_is_db_operational_error(self):
        resp = client.get("/operational-error")
        body = resp.json()
        assert body["error"]["code"] == "DB_OPERATIONAL_ERROR"

    def test_error_status_code_is_503(self):
        resp = client.get("/operational-error")
        body = resp.json()
        assert body["error"]["status_code"] == 503

    def test_error_has_timestamp(self):
        resp = client.get("/operational-error")
        body = resp.json()
        assert "timestamp" in body["error"]

    def test_error_has_request_id(self):
        resp = client.get("/operational-error")
        body = resp.json()
        assert "request_id" in body["error"]
        assert body["error"]["request_id"]


class TestExceptionTypeRouting:
    """DB exceptions should be caught by classified handlers, not generic 500."""

    def test_integrity_error_not_500(self):
        resp = client.get("/integrity-error")
        assert resp.status_code != 500
        assert resp.status_code == 409

    def test_operational_error_not_500(self):
        resp = client.get("/operational-error")
        assert resp.status_code != 500
        assert resp.status_code == 503

    def test_integrity_error_message_is_user_friendly(self):
        resp = client.get("/integrity-error")
        body = resp.json()
        assert "冲突" in body["message"]
        assert "INSERT" not in body["message"]

    def test_operational_error_message_is_user_friendly(self):
        resp = client.get("/operational-error")
        body = resp.json()
        assert "数据库" in body["message"]
        assert "server closed" not in body["message"]


class TestExceptionStructureConsistency:
    """DB exception responses should match unified response format."""

    def test_integrity_error_keys_match_success_response(self):
        resp = client.get("/integrity-error")
        body = resp.json()
        assert set(body.keys()) == {"code", "message", "data", "error"}

    def test_operational_error_keys_match_success_response(self):
        resp = client.get("/operational-error")
        body = resp.json()
        assert set(body.keys()) == {"code", "message", "data", "error"}

    def test_integrity_error_error_subkeys(self):
        resp = client.get("/integrity-error")
        body = resp.json()
        error = body["error"]
        for key in ("code", "message", "status_code", "timestamp", "request_id"):
            assert key in error, f"missing {key} in error"

    def test_operational_error_error_subkeys(self):
        resp = client.get("/operational-error")
        body = resp.json()
        error = body["error"]
        for key in ("code", "message", "status_code", "timestamp", "request_id"):
            assert key in error, f"missing {key} in error"
