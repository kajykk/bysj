from __future__ import annotations

from uuid import uuid4

from fastapi import Request

REQUEST_ID_HEADER = "x-request-id"


def get_or_create_request_id(request: Request) -> str:
    request_id = request.headers.get(REQUEST_ID_HEADER)
    if request_id and request_id.strip():
        return request_id.strip()
    return str(uuid4())
