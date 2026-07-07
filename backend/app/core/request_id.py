from __future__ import annotations

import re
from uuid import uuid4

from fastapi import Request

REQUEST_ID_HEADER = "x-request-id"

# M-Core-10 修复：校验客户端传入的 x-request-id 格式，防止 CRLF 注入
# 仅允许字母、数字、连字符，长度 8-128
_REQUEST_ID_PATTERN = re.compile(r"^[a-zA-Z0-9-]{8,128}$")


def get_or_create_request_id(request: Request) -> str:
    request_id = request.headers.get(REQUEST_ID_HEADER)
    if request_id:
        request_id = request_id.strip()
        # 格式不匹配则忽略并生成新的，避免 CRLF 注入
        if request_id and _REQUEST_ID_PATTERN.match(request_id):
            return request_id
    return str(uuid4())
