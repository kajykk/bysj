"""Tests for CSP report endpoint."""

from __future__ import annotations

import json

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.csp_report import router as csp_router


app = FastAPI()
app.include_router(csp_router)
client = TestClient(app)


class TestCSPReport:
    """Test CSP report endpoint."""

    def test_empty_body(self):
        """TC-COV-CSP-001: Empty body returns 204."""
        response = client.post("/api/v1/csp-report", data=b"")
        assert response.status_code == 204

    def test_empty_json(self):
        """TC-COV-CSP-002: Empty JSON returns 204."""
        response = client.post("/api/v1/csp-report", json={})
        assert response.status_code == 204

    def test_valid_csp_report(self):
        """TC-COV-CSP-003: Valid CSP report returns 204."""
        payload = {
            "csp-report": {
                "blocked-url": "https://evil.com/script.js",
                "document-url": "https://example.com/page",
                "effective-directive": "script-src",
                "source-file": "https://example.com/page",
                "line-number": 42,
            }
        }
        response = client.post("/api/v1/csp-report", json=payload)
        assert response.status_code == 204

    def test_csp_report_camelcase(self):
        """TC-COV-CSP-004: CamelCase CSP report returns 204."""
        payload = {
            "cspReport": {
                "blockedURI": "https://evil.com/script.js",
                "documentURI": "https://example.com/page",
            }
        }
        response = client.post("/api/v1/csp-report", json=payload)
        assert response.status_code == 204

    def test_reporting_api_format(self):
        """TC-COV-CSP-005: Reporting API format returns 204."""
        payload = {
            "type": "csp-violation",
            "body": {
                "blocked-url": "https://evil.com/script.js",
                "document-url": "https://example.com/page",
            }
        }
        response = client.post("/api/v1/csp-report", json=payload)
        assert response.status_code == 204

    def test_top_level_as_report(self):
        """TC-COV-CSP-006: Top-level fields as report body."""
        payload = {
            "blocked-url": "https://evil.com/script.js",
            "document-url": "https://example.com/page",
        }
        response = client.post("/api/v1/csp-report", json=payload)
        assert response.status_code == 204

    def test_invalid_json(self):
        """TC-COV-CSP-007: Invalid JSON returns 400."""
        response = client.post(
            "/api/v1/csp-report",
            data=b"not json",
            headers={"content-type": "application/json"},
        )
        assert response.status_code == 400

    def test_payload_too_large(self):
        """TC-COV-CSP-008: Payload too large returns 413."""
        large_payload = {"x": "a" * (64 * 1024 + 100)}
        response = client.post("/api/v1/csp-report", json=large_payload)
        assert response.status_code == 413

    def test_no_report_body(self):
        """TC-COV-CSP-009: No report body returns 204."""
        payload = {"other": "data"}
        response = client.post("/api/v1/csp-report", json=payload)
        assert response.status_code == 204
