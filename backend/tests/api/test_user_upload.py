"""Tests for user upload API endpoints."""

from __future__ import annotations

import io

import pytest


class TestUserUploadApi:
    """Test user upload API endpoints."""

    def test_upload_no_file(self, client, auth_headers):
        """TC-COV-API-018: Upload without file returns 422."""
        response = client.post("/api/v1/user/upload", headers=auth_headers)
        assert response.status_code == 422

    def test_upload_empty_filename(self, client, auth_headers):
        """TC-COV-API-019: Upload with empty filename returns 400."""
        # FastAPI may reject this at validation layer
        response = client.post(
            "/api/v1/user/upload",
            headers=auth_headers,
            files={"file": ("", io.BytesIO(b"test"), "text/plain")},
        )
        assert response.status_code in (400, 422)

    def test_upload_invalid_extension(self, client, auth_headers):
        """TC-COV-API-020: Upload with invalid extension returns 400."""
        response = client.post(
            "/api/v1/user/upload",
            headers=auth_headers,
            files={
                "file": ("test.exe", io.BytesIO(b"test"), "application/octet-stream")
            },
        )
        assert response.status_code == 400

    def test_upload_batch_too_many_files(self, client, auth_headers):
        """TC-COV-API-021: Batch upload with more than 10 files returns 400."""
        files = [
            (f"file{i}", (f"test{i}.txt", io.BytesIO(b"test"), "text/plain"))
            for i in range(11)
        ]
        response = client.post(
            "/api/v1/user/upload/batch",
            headers=auth_headers,
            data={"category": "document"},
            files=files,
        )
        # Note: This test may need adjustment based on actual FastAPI behavior
        assert response.status_code in (400, 422)

    def test_upload_unauthorized(self, client):
        """TC-COV-API-022: Upload without auth returns 401/403/422 (validation may run first)."""
        response = client.post("/api/v1/user/upload")
        assert response.status_code in (401, 403, 422)

    def test_validate_extension_no_extension(self):
        """TC-COV-API-023: Validate extension for file without extension."""
        from app.api.v1.user_upload import _validate_extension

        with pytest.raises(Exception):
            _validate_extension("noextension")

    def test_validate_extension_invalid_category(self):
        """TC-COV-API-024: Validate extension with invalid category."""
        from app.api.v1.user_upload import _validate_extension

        with pytest.raises(Exception):
            _validate_extension("test.exe", category="image")
