"""Phase 5 租户上下文中间件与依赖测试.

覆盖：
- tenant_context_middleware: 请求头解析、子域名解析、默认回退
- get_current_tenant: 从 tenant_id/code 解析、缓存、暂停租户
- get_current_tenant_id: 轻量级 ID 获取
- get_request_tenant_id: 从 request.state 直接读取
- enforce_tenant_match: 匹配/不匹配
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi import HTTPException

from app.core.contracts import DEFAULT_TENANT_ID, TENANT_STATUS_SUSPENDED
from app.core.tenant_context import (
    TENANT_HEADER,
    TENANT_STATE_KEY,
    enforce_tenant_match,
    get_current_tenant,
    get_current_tenant_id,
    get_request_tenant_id,
    tenant_context_middleware,
)
from app.models.tenant import Tenant


def _make_request(
    headers: dict[str, str] | None = None,
    host: str = "localhost",
    method: str = "GET",
    path: str = "/",
):
    """构造 mock Request 对象."""
    headers = headers or {}
    # 确保 host header 存在
    if not any(k.lower() == "host" for k in headers):
        headers = {**headers, "host": host}

    request = MagicMock()
    # headers 使用 MagicMock 模拟 starlette Headers 对象
    request.headers = MagicMock()
    request.headers.get = lambda key, default="": headers.get(key, headers.get(key.lower(), headers.get(key.upper(), default)))

    request.method = method
    request.url = MagicMock()
    request.url.path = path
    # request.state 使用简单对象，允许设置任意属性
    request.state = MagicMock(spec=[])
    return request


def _make_tenant(
    id: int = 1,
    code: str = "default",
    status: str = "active",
    name: str = "默认租户",
) -> Tenant:
    return Tenant(id=id, name=name, code=code, status=status)


# =========================================================================
# 中间件测试
# =========================================================================


class TestTenantContextMiddleware:
    """Test tenant_context_middleware."""

    @pytest.mark.asyncio
    async def test_header_numeric_id(self):
        """TC-P5-022: X-Tenant-ID 数字 ID 直接解析."""
        request = _make_request(headers={TENANT_HEADER: "42"})

        async def call_next(req):
            return MagicMock()

        await tenant_context_middleware(request, call_next)
        assert request.state.tenant_id == 42
        assert getattr(request.state, "tenant_code", None) is None

    @pytest.mark.asyncio
    async def test_header_code_string(self):
        """TC-P5-023: X-Tenant-ID 字符串 code 解析."""
        request = _make_request(headers={TENANT_HEADER: "xx_univ"})

        async def call_next(req):
            return MagicMock()

        await tenant_context_middleware(request, call_next)
        assert request.state.tenant_id is None
        assert request.state.tenant_code == "xx_univ"

    @pytest.mark.asyncio
    async def test_header_with_whitespace(self):
        """TC-P5-024: X-Tenant-ID 含空格应 trim."""
        request = _make_request(headers={TENANT_HEADER: "  42  "})

        async def call_next(req):
            return MagicMock()

        await tenant_context_middleware(request, call_next)
        assert request.state.tenant_id == 42

    @pytest.mark.asyncio
    async def test_subdomain_parsing(self):
        """TC-P5-025: 子域名解析租户 code."""
        request = _make_request(host="xx_univ.dws.example.com")

        async def call_next(req):
            return MagicMock()

        await tenant_context_middleware(request, call_next)
        assert request.state.tenant_code == "xx_univ"
        assert request.state.tenant_id is None

    @pytest.mark.asyncio
    async def test_www_subdomain_ignored(self):
        """TC-P5-026: www 子域名不作为租户解析."""
        request = _make_request(host="www.dws.example.com")

        async def call_next(req):
            return MagicMock()

        await tenant_context_middleware(request, call_next)
        # 应回退到默认租户
        assert request.state.tenant_id == DEFAULT_TENANT_ID

    @pytest.mark.asyncio
    async def test_localhost_uses_default(self):
        """TC-P5-027: localhost 使用默认租户."""
        request = _make_request(host="localhost:8000")

        async def call_next(req):
            return MagicMock()

        await tenant_context_middleware(request, call_next)
        assert request.state.tenant_id == DEFAULT_TENANT_ID

    @pytest.mark.asyncio
    async def test_no_header_no_subdomain_uses_default(self):
        """TC-P5-028: 无请求头无子域名使用默认租户."""
        request = _make_request(host="dws.example.com")

        async def call_next(req):
            return MagicMock()

        await tenant_context_middleware(request, call_next)
        assert request.state.tenant_id == DEFAULT_TENANT_ID

    @pytest.mark.asyncio
    async def test_header_takes_priority_over_subdomain(self):
        """TC-P5-029: 请求头优先级高于子域名."""
        request = _make_request(
            headers={TENANT_HEADER: "99"},
            host="xx_univ.dws.example.com",
        )

        async def call_next(req):
            return MagicMock()

        await tenant_context_middleware(request, call_next)
        assert request.state.tenant_id == 99
        assert getattr(request.state, "tenant_code", None) is None


# =========================================================================
# 依赖测试
# =========================================================================


class TestGetCurrentTenant:
    """Test get_current_tenant."""

    @pytest.mark.asyncio
    async def test_resolve_by_tenant_id(self, db_session):
        """TC-P5-030: 通过 tenant_id 解析租户."""
        tenant = Tenant(id=30, name="租户30", code="t30", status="active")
        db_session.add(tenant)
        await db_session.flush()

        request = _make_request()
        request.state.tenant_id = 30
        request.state.tenant_code = None

        result = await get_current_tenant(request=request, db=db_session)
        assert result.id == 30
        assert result.code == "t30"

    @pytest.mark.asyncio
    async def test_resolve_by_tenant_code(self, db_session):
        """TC-P5-031: 通过 tenant_code 解析租户."""
        tenant = Tenant(id=31, name="租户31", code="t31_code", status="active")
        db_session.add(tenant)
        await db_session.flush()

        request = _make_request()
        request.state.tenant_id = None
        request.state.tenant_code = "t31_code"

        result = await get_current_tenant(request=request, db=db_session)
        assert result.id == 31
        assert result.code == "t31_code"

    @pytest.mark.asyncio
    async def test_resolve_default_tenant_when_none(self, db_session):
        """TC-P5-032: 无 tenant_id 和 code 时解析默认租户."""
        default_tenant = Tenant(
            id=DEFAULT_TENANT_ID, name="默认租户", code="default", status="active"
        )
        db_session.add(default_tenant)
        await db_session.flush()

        request = _make_request()
        request.state.tenant_id = None
        request.state.tenant_code = None

        result = await get_current_tenant(request=request, db=db_session)
        assert result.id == DEFAULT_TENANT_ID

    @pytest.mark.asyncio
    async def test_nonexistent_tenant_returns_404(self, db_session):
        """TC-P5-033: 不存在的租户返回 404."""
        request = _make_request()
        request.state.tenant_id = 99999
        request.state.tenant_code = None

        with pytest.raises(HTTPException) as exc_info:
            await get_current_tenant(request=request, db=db_session)
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_suspended_tenant_returns_403(self, db_session):
        """TC-P5-034: 已暂停租户返回 403."""
        tenant = Tenant(
            id=34, name="暂停租户", code="suspended", status=TENANT_STATUS_SUSPENDED
        )
        db_session.add(tenant)
        await db_session.flush()

        request = _make_request()
        request.state.tenant_id = 34
        request.state.tenant_code = None

        with pytest.raises(HTTPException) as exc_info:
            await get_current_tenant(request=request, db=db_session)
        assert exc_info.value.status_code == 403

    @pytest.mark.asyncio
    async def test_cached_tenant_not_re_queried(self, db_session):
        """TC-P5-035: 同请求内缓存租户对象，不重复查库."""
        tenant = Tenant(id=35, name="缓存租户", code="cached", status="active")
        db_session.add(tenant)
        await db_session.flush()

        request = _make_request()
        request.state.tenant_id = 35
        request.state.tenant_code = None

        # 第一次查询
        result1 = await get_current_tenant(request=request, db=db_session)
        assert result1.id == 35

        # 用 mock 替换 db.execute 验证第二次不查库
        original_execute = db_session.execute
        call_count = 0

        async def _counting_execute(*args, **kwargs):
            nonlocal call_count
            call_count += 1
            return await original_execute(*args, **kwargs)

        db_session.execute = _counting_execute

        try:
            # 第二次查询应命中缓存，不触发 db.execute
            result2 = await get_current_tenant(request=request, db=db_session)
            assert result2.id == 35
            assert call_count == 0, "第二次查询应命中缓存，不应调用 db.execute"
        finally:
            db_session.execute = original_execute


class TestGetCurrentTenantId:
    """Test get_current_tenant_id."""

    @pytest.mark.asyncio
    async def test_returns_int_id(self, db_session):
        """TC-P5-036: 返回 int 类型的 tenant_id."""
        tenant = Tenant(id=36, name="租户36", code="t36", status="active")
        db_session.add(tenant)
        await db_session.flush()

        request = _make_request()
        request.state.tenant_id = 36
        request.state.tenant_code = None

        result = await get_current_tenant_id(request=request, db=db_session)
        assert isinstance(result, int)
        assert result == 36


class TestGetRequestTenantId:
    """Test get_request_tenant_id."""

    def test_returns_set_tenant_id(self):
        """TC-P5-037: 返回 request.state 上已设置的 tenant_id."""
        request = _make_request()
        request.state.tenant_id = 77
        assert get_request_tenant_id(request) == 77

    def test_returns_default_when_not_set(self):
        """TC-P5-038: 未设置时返回默认租户 ID."""
        request = _make_request()
        # 不设置 tenant_id
        assert get_request_tenant_id(request) == DEFAULT_TENANT_ID

    def test_returns_default_when_none(self):
        """TC-P5-039: tenant_id=None 时返回默认."""
        request = _make_request()
        request.state.tenant_id = None
        assert get_request_tenant_id(request) == DEFAULT_TENANT_ID


class TestEnforceTenantMatch:
    """Test enforce_tenant_match."""

    def test_matching_tenant_passes(self):
        """TC-P5-040: 租户匹配时不抛错."""
        enforce_tenant_match(resource_tenant_id=10, request_tenant_id=10)

    def test_mismatched_tenant_raises_403(self):
        """TC-P5-041: 租户不匹配时抛 403."""
        with pytest.raises(HTTPException) as exc_info:
            enforce_tenant_match(resource_tenant_id=10, request_tenant_id=20)
        assert exc_info.value.status_code == 403
        assert "跨租户" in exc_info.value.detail

    def test_none_resource_tenant_uses_default(self):
        """TC-P5-042: 资源 tenant_id=None 视为默认租户."""
        # 默认租户匹配
        enforce_tenant_match(
            resource_tenant_id=None,
            request_tenant_id=DEFAULT_TENANT_ID,
        )
        # 默认租户与非默认租户不匹配
        with pytest.raises(HTTPException):
            enforce_tenant_match(
                resource_tenant_id=None,
                request_tenant_id=99,
            )
