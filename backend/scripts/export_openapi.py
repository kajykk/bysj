"""Export FastAPI OpenAPI schema for contract testing.

Usage:
    python scripts/export_openapi.py

Output:
    backend/tests/contract/openapi.json
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

# Add backend to path
backend_dir = Path(__file__).parent.parent
sys.path.insert(0, str(backend_dir))

from app.main import app


def export_openapi_schema(output_path: Path | None = None) -> Path:
    """Export FastAPI OpenAPI schema to JSON file.

    Args:
        output_path: Output file path. Defaults to tests/contract/openapi.json

    Returns:
        Path to the exported file
    """
    if output_path is None:
        output_path = backend_dir / "tests" / "contract" / "openapi.json"

    # Ensure directory exists
    output_path.parent.mkdir(parents=True, exist_ok=True)

    # Get OpenAPI schema from FastAPI app
    openapi_schema = app.openapi()

    # Write with pretty formatting
    output_path.write_text(
        json.dumps(openapi_schema, indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    print(f"✅ OpenAPI schema exported to: {output_path}")
    print(f"   Title: {openapi_schema.get('info', {}).get('title', 'N/A')}")
    print(f"   Version: {openapi_schema.get('info', {}).get('version', 'N/A')}")
    print(f"   Paths: {len(openapi_schema.get('paths', {}))}")
    print(f"   Components: {len(openapi_schema.get('components', {}).get('schemas', {}))}")

    return output_path


if __name__ == "__main__":
    export_openapi_schema()
