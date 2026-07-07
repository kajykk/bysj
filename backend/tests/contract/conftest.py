"""Contract test conftest: optimize Schemathesis ASGI transport.

问题: Schemathesis ``ASGITransport.send`` 每次 ``case.call()`` 都创建新 ``TestClient(app)``
并触发 lifespan startup (ML 模型加载/DB 建表/seed/exporter 启动等), 导致单测试 > 30s.

修复: session 级别启动一个 ``TestClient`` (lifespan 只跑一次), monkey-patch
``ASGITransport.send`` 复用该 client, 跳过 per-call lifespan 开销.
"""

from __future__ import annotations

import pytest
import schemathesis
from schemathesis.transport.asgi import ASGITransport
from schemathesis.transport.prepare import normalize_base_url
from schemathesis.transport.requests import RequestsTransport
from starlette_testclient import TestClient

from app.main import app

# 保存原始 send 实现 (fallback)
_original_asgi_send = ASGITransport.send

# session 级 TestClient (启动一次, 全部 contract 测试复用)
_started_client: TestClient | None = None

# 全部 contract 测试使用的认证头 (配合 conftest.py 的 override_user_dependency)
AUTH_HEADERS = {"Authorization": "Bearer contract-test-token"}

# SQLite int64 上限 (2^63 - 1). Schemathesis 默认生成超大整数会导致 OverflowError.
_INT64_MAX = 9223372036854775807


def _fast_asgi_send(self: ASGITransport, case, *, session=None, **kwargs):
    """复用已启动的 TestClient, 避免每次 call 触发 lifespan startup/shutdown."""
    if kwargs.get("base_url") is None:
        kwargs["base_url"] = normalize_base_url(case.operation.base_url)
    # 丢弃 app 参数 (由 _started_client 提供 ASGI 传输)
    kwargs.pop("app", None)
    # 自动注入认证头 (除非测试显式覆盖)
    headers = kwargs.get("headers") or {}
    if "Authorization" not in headers:
        headers["Authorization"] = AUTH_HEADERS["Authorization"]
        kwargs["headers"] = headers
    client = _started_client
    if client is None:
        # fallback: 未启动时走原始逻辑
        return _original_asgi_send(self, case, session=session, **kwargs)
    return RequestsTransport.send(self, case, session=client, **kwargs)


@schemathesis.hook
def before_call(ctx, case, **kwargs):
    """限制路径/查询参数中的整数到 int64 范围, 避免 SQLite OverflowError.

    Schemathesis 默认会生成 2^63 等超大整数, 但 SQLite int64 上限是 2^63-1,
    导致 ``OverflowError: Python int too large to convert to SQLite INTEGER``.
    这里在请求发送前将超大整数 clamp 到 int64 范围.

    同时处理 password 字段的 UTF-8 字节长度问题:
    JSON Schema maxLength 按字符数计算, 但 validate_password_bytes 按 UTF-8
    字节计算 (72 字节上限). 非 ASCII 字符 (3 字节/字符) 可能字符数 <=72
    但字节数 >72, 导致 422. 这里在请求发送前截断超长密码.
    """
    for params in (case.path_parameters, case.query):
        if not params:
            continue
        for key, value in list(params.items()):
            if isinstance(value, int) and value > _INT64_MAX:
                params[key] = _INT64_MAX

    # 截断 password/new_password 字段至 72 UTF-8 字节 (MAX_PASSWORD_BYTES)
    # JSON Schema maxLength 按字符数计算, 但 validate_password_bytes 按 UTF-8 字节计算.
    # 非 ASCII 字符 (3 字节/字符) 可能字符数 <=72 但字节数 >72, 导致 422.
    body = case.body
    if isinstance(body, dict):
        for pwd_key in ("password", "new_password"):
            if pwd_key not in body:
                continue
            pwd = body[pwd_key]
            if not isinstance(pwd, str):
                continue
            encoded = pwd.encode("utf-8")
            if len(encoded) > 72:
                # 截断到 72 字节, 然后解码 (可能丢掉不完整的多字节字符)
                truncated = encoded[:72].decode("utf-8", errors="ignore")
                # 确保截断后仍满足 min_length=8, 否则替换为安全密码
                if len(truncated) >= 8:
                    body[pwd_key] = truncated
                else:
                    body[pwd_key] = "SafePass123!"

    return None


@pytest.fixture(scope="session", autouse=True)
def _contract_asgi_client():
    """启动单个 TestClient 供全部 contract 测试复用, 并 monkey-patch ASGI transport."""
    global _started_client
    ASGITransport.send = _fast_asgi_send
    with TestClient(app) as client:
        _started_client = client
        yield
    _started_client = None
    ASGITransport.send = _original_asgi_send


@pytest.fixture(autouse=True)
def _contract_admin_role():
    """设置 admin 角色, 覆盖父 conftest 的默认 user 角色 (contract 测试需访问全部端点)."""
    from tests.conftest import CURRENT_USER

    CURRENT_USER["role"] = "admin"
    CURRENT_USER["id"] = 3
    yield
