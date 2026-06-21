"""Tests for CSP Report API endpoint."""

from __future__ import annotations

import json

import pytest
from fastapi.testclient import TestClient


class TestCSPReport:
    """Test suite for /csp-report endpoint."""

    def test_csp_report_success(self, client: TestClient) -> None:
        """TC-SEC-001: Valid CSP report returns 204."""
        payload = {
            "csp-report": {
                "document-uri": "http://localhost:5173/",
                "referrer": "",
                "violated-directive": "script-src-elem",
                "effective-directive": "script-src-elem",
                "original-policy": "default-src 'self'; script-src 'self';",
                "blocked-uri": "inline",
                "source-file": "http://localhost:5173/",
                "line-number": 10,
                "column-number": 5,
            }
        }
        resp = client.post(
            "/api/v1/csp-report",
            json=payload,
            headers={"Content-Type": "application/csp-report"},
        )
        assert resp.status_code == 204

    def test_csp_report_application_json(self, client: TestClient) -> None:
        """TC-SEC-002: Valid CSP report with application/json returns 204."""
        payload = {
            "csp-report": {
                "document-uri": "http://localhost:5173/login",
                "violated-directive": "style-src-elem",
                "blocked-uri": "inline",
            }
        }
        resp = client.post(
            "/api/v1/csp-report",
            json=payload,
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 204

    def test_csp_report_reports_json(self, client: TestClient) -> None:
        """TC-SEC-003: Valid CSP report with application/reports+json returns 204."""
        payload = {
            "csp-report": {
                "document-uri": "http://localhost:5173/dashboard",
                "violated-directive": "img-src",
                "blocked-uri": "http://evil.com/img.png",
            }
        }
        resp = client.post(
            "/api/v1/csp-report",
            json=payload,
            headers={"Content-Type": "application/reports+json"},
        )
        assert resp.status_code == 204

    def test_csp_report_reporting_api_format(self, client: TestClient) -> None:
        """TC-SEC-004: Reporting API format (type + body) returns 204."""
        payload = {
            "type": "csp-violation",
            "age": 0,
            "url": "http://localhost:5173/",
            "user_agent": "Mozilla/5.0",
            "body": {
                "document-uri": "http://localhost:5173/",
                "violated-directive": "script-src",
                "blocked-uri": "http://evil.com/script.js",
            },
        }
        resp = client.post(
            "/api/v1/csp-report",
            json=payload,
            headers={"Content-Type": "application/reports+json"},
        )
        assert resp.status_code == 204

    def test_csp_report_camel_case_keys(self, client: TestClient) -> None:
        """TC-SEC-005: CamelCase keys (cspReport, blockedURI) returns 204."""
        payload = {
            "cspReport": {
                "documentURI": "http://localhost:5173/",
                "violatedDirective": "script-src",
                "blockedURI": "inline",
            }
        }
        resp = client.post("/api/v1/csp-report", json=payload)
        assert resp.status_code == 204

    def test_csp_report_empty_body(self, client: TestClient) -> None:
        """TC-SEC-006: Empty body returns 204."""
        resp = client.post("/api/v1/csp-report", data="")
        assert resp.status_code == 204

    def test_csp_report_empty_json(self, client: TestClient) -> None:
        """TC-SEC-007: Empty JSON object returns 204."""
        resp = client.post("/api/v1/csp-report", json={})
        assert resp.status_code == 204

    def test_csp_report_no_report_body(self, client: TestClient) -> None:
        """TC-SEC-008: JSON without csp-report key returns 204."""
        payload = {"other-field": "value"}
        resp = client.post("/api/v1/csp-report", json=payload)
        assert resp.status_code == 204

    def test_csp_report_invalid_json(self, client: TestClient) -> None:
        """TC-SEC-009: Invalid JSON returns 400."""
        resp = client.post(
            "/api/v1/csp-report",
            data="not-json",
            headers={"Content-Type": "application/json"},
        )
        assert resp.status_code == 400

    def test_csp_report_payload_too_large(self, client: TestClient) -> None:
        """TC-SEC-010: Payload > 64KB returns 413."""
        large_payload = {
            "csp-report": {
                "document-uri": "http://localhost:5173/",
                "violated-directive": "script-src",
                "blocked-uri": "x" * (65 * 1024),
            }
        }
        resp = client.post("/api/v1/csp-report", json=large_payload)
        assert resp.status_code == 413

    def test_csp_report_content_length_too_large(self, client: TestClient) -> None:
        """TC-SEC-011: Content-Length header > 64KB returns 413."""
        resp = client.post(
            "/api/v1/csp-report",
            json={"csp-report": {}},
            headers={"Content-Length": str(65 * 1024)},
        )
        assert resp.status_code == 413

    def test_csp_report_missing_fields(self, client: TestClient) -> None:
        """TC-SEC-012: Missing optional fields still returns 204."""
        payload = {
            "csp-report": {
                "document-uri": "http://localhost:5173/",
            }
        }
        resp = client.post("/api/v1/csp-report", json=payload)
        assert resp.status_code == 204

    def test_csp_report_all_optional_fields(self, client: TestClient) -> None:
        """TC-SEC-013: All CSP Level 3 fields accepted."""
        payload = {
            "csp-report": {
                "blocked-url": "http://evil.com/script.js",
                "blockedURI": "http://evil.com/script.js",
                "document-url": "http://localhost:5173/",
                "documentURI": "http://localhost:5173/",
                "effective-directive": "script-src-elem",
                "original-policy": "default-src 'self';",
                "referrer": "http://localhost:5173/login",
                "script-sample": "alert(1)",
                "status-code": 200,
                "violated-directive": "script-src",
                "source-file": "http://localhost:5173/app.js",
                "line-number": 42,
                "column-number": 10,
                "disposition": "enforce",
            }
        }
        resp = client.post("/api/v1/csp-report", json=payload)
        assert resp.status_code == 204
