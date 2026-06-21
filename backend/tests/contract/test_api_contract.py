"""API Contract Tests using schemathesis.

Validates all API endpoints conform to OpenAPI specification.
Run after updating API routes: python scripts/export_openapi.py
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest
import schemathesis
from hypothesis import settings

pytestmark = pytest.mark.contract

# Load OpenAPI schema from exported file
OPENAPI_PATH = Path(__file__).parent / "openapi.json"

if not OPENAPI_PATH.exists():
    pytest.skip(f"OpenAPI schema not found at {OPENAPI_PATH}. Run: python scripts/export_openapi.py", allow_module_level=True)

# schemathesis 4.x API - load from WSGI/ASGI app for in-process testing
from app.main import app
schema = schemathesis.openapi.from_asgi("/openapi.json", app)

# Filtered schemas for specific endpoints
predict_tabular_schema = schema.include(path="/api/v1/model/predict/tabular")
predict_text_schema = schema.include(path="/api/v1/model/predict/text")
health_schema = schema.include(path="/health")


@schema.parametrize()
@settings(max_examples=10, deadline=None)
def test_api_contract(case):
    """Validate all API endpoints conform to OpenAPI spec.

    This test automatically generates requests for all endpoints defined
    in the OpenAPI schema and validates responses.
    """
    response = case.call()
    case.validate_response(response)


@predict_tabular_schema.parametrize()
@settings(max_examples=10, deadline=None)
def test_predict_tabular_contract(case):
    """Specific contract test for tabular prediction endpoint."""
    response = case.call()
    case.validate_response(response)

    # Additional validation for prediction response structure
    if response.status_code == 200:
        data = response.json()
        assert "risk_score" in data or "error" in data


@predict_text_schema.parametrize()
@settings(max_examples=10, deadline=None)
def test_predict_text_contract(case):
    """Specific contract test for text prediction endpoint."""
    response = case.call()
    case.validate_response(response)

    if response.status_code == 200:
        data = response.json()
        assert "risk_score" in data or "error" in data


@health_schema.parametrize()
@settings(max_examples=5, deadline=None)
def test_health_endpoint_contract(case):
    """Contract test for health check endpoint."""
    response = case.call()
    case.validate_response(response)

    if response.status_code == 200:
        data = response.json()
        assert "status" in data
