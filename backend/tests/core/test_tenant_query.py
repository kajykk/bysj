"""Phase 5 租户级查询隔离工具测试.

覆盖：
- tenant_scoped_query: 基本功能、无效 tenant_id、缺少 tenant_id 列
- tenant_scoped_filter: 基本功能、组合查询
- get_tenant_scoped_or_404: 找到、未找到、跨租户
- assert_tenant_isolated: 模型有/无 tenant_id 列
- normalize_tenant_id: None/有效/无效
"""

from __future__ import annotations

import pytest

from app.core.contracts import DEFAULT_TENANT_ID
from app.core.tenant_query import (
    TenantColumnMissingError,
    assert_tenant_isolated,
    get_tenant_scoped_or_404,
    normalize_tenant_id,
    tenant_scoped_filter,
    tenant_scoped_query,
)
from app.models.admin import EducationContent, OperationLog
from app.models.tenant import Tenant
from app.models.user import User


# =========================================================================
# 纯单元测试（无 DB）
# =========================================================================


class TestTenantScopedQuery:
    """Test tenant_scoped_query."""

    def test_basic_query_has_tenant_filter(self):
        """TC-P5-001: 基本查询应包含 tenant_id 过滤条件."""
        stmt = tenant_scoped_query(User, tenant_id=1)
        # 编译 SQL 检查 WHERE 子句
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "tenant_id" in compiled
        assert "1" in compiled

    def test_invalid_tenant_id_none_raises(self):
        """TC-P5-002: tenant_id=None 应抛 ValueError."""
        with pytest.raises(ValueError, match="不能为 None"):
            tenant_scoped_query(User, tenant_id=None)

    def test_invalid_tenant_id_zero_raises(self):
        """TC-P5-003: tenant_id=0 应抛 ValueError."""
        with pytest.raises(ValueError, match="正整数"):
            tenant_scoped_query(User, tenant_id=0)

    def test_invalid_tenant_id_negative_raises(self):
        """TC-P5-004: tenant_id=-1 应抛 ValueError."""
        with pytest.raises(ValueError, match="正整数"):
            tenant_scoped_query(User, tenant_id=-1)

    def test_invalid_tenant_id_string_raises(self):
        """TC-P5-005: tenant_id 字符串应抛 ValueError."""
        with pytest.raises(ValueError, match="正整数"):
            tenant_scoped_query(User, tenant_id="1")  # type: ignore[arg-type]

    def test_model_without_tenant_id_raises(self):
        """TC-P5-006: 模型缺少 tenant_id 列应抛 TenantColumnMissingError."""
        # EducationContent 没有 tenant_id 列
        with pytest.raises(TenantColumnMissingError, match="EducationContent"):
            tenant_scoped_query(EducationContent, tenant_id=1)

    def test_model_without_tenant_id_silent_fallback(self):
        """TC-P5-007: assert_tenant_column=False 时不抛错，回退到普通 select."""
        stmt = tenant_scoped_query(
            EducationContent, tenant_id=1, assert_tenant_column=False
        )
        # 应该是一个普通的 select，不带 tenant_id 过滤
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "tenant_id" not in compiled

    def test_operation_log_has_tenant_filter(self):
        """TC-P5-008: OperationLog 查询应包含 tenant_id 过滤."""
        stmt = tenant_scoped_query(OperationLog, tenant_id=2)
        compiled = str(stmt.compile(compile_kwargs={"literal_binds": True}))
        assert "tenant_id" in compiled
        assert "2" in compiled


class TestTenantScopedFilter:
    """Test tenant_scoped_filter."""

    def test_basic_filter(self):
        """TC-P5-009: 基本过滤条件."""
        cond = tenant_scoped_filter(User, tenant_id=1)
        assert cond is not None
        compiled = str(cond.compile(compile_kwargs={"literal_binds": True}))
        assert "tenant_id" in compiled

    def test_invalid_tenant_id_raises(self):
        """TC-P5-010: 无效 tenant_id 抛 ValueError."""
        with pytest.raises(ValueError):
            tenant_scoped_filter(User, tenant_id=None)

    def test_model_without_tenant_id_returns_none(self):
        """TC-P5-011: 模型无 tenant_id 列且 assert=False 时返回 None."""
        cond = tenant_scoped_filter(
            EducationContent, tenant_id=1, assert_tenant_column=False
        )
        assert cond is None

    def test_model_without_tenant_id_raises(self):
        """TC-P5-012: 模型无 tenant_id 列且 assert=True 时抛错."""
        with pytest.raises(TenantColumnMissingError):
            tenant_scoped_filter(EducationContent, tenant_id=1)


class TestAssertTenantIsolated:
    """Test assert_tenant_isolated."""

    def test_model_with_tenant_id(self):
        """TC-P5-013: 含 tenant_id 列的模型返回 True."""
        assert assert_tenant_isolated(User) is True
        assert assert_tenant_isolated(OperationLog) is True

    def test_model_without_tenant_id_raises(self):
        """TC-P5-014: 不含 tenant_id 列的模型抛错."""
        with pytest.raises(TenantColumnMissingError):
            assert_tenant_isolated(EducationContent)


class TestNormalizeTenantId:
    """Test normalize_tenant_id."""

    def test_none_returns_default(self):
        """TC-P5-015: None 返回默认租户 ID."""
        assert normalize_tenant_id(None) == DEFAULT_TENANT_ID

    def test_valid_id_returns_unchanged(self):
        """TC-P5-016: 有效 ID 原样返回."""
        assert normalize_tenant_id(1) == 1
        assert normalize_tenant_id(42) == 42

    def test_invalid_id_raises(self):
        """TC-P5-017: 无效 ID 抛 ValueError."""
        with pytest.raises(ValueError):
            normalize_tenant_id(0)
        with pytest.raises(ValueError):
            normalize_tenant_id(-1)
        with pytest.raises(ValueError):
            normalize_tenant_id("1")  # type: ignore[arg-type]


# =========================================================================
# DB 相关测试
# =========================================================================


class TestGetTenantScopedOr404:
    """Test get_tenant_scoped_or_404."""

    @pytest.mark.asyncio
    async def test_get_existing_record_same_tenant(self, db_session):
        """TC-P5-018: 同租户查询应返回记录."""
        # 准备：创建租户和用户
        tenant = Tenant(id=10, name="测试租户A", code="tenant_a", status="active")
        db_session.add(tenant)
        await db_session.flush()

        user = User(
            id=100,
            username="tenant_a_user",
            email="a@tenant.com",
            email_hash="hash_a_001",
            password_hash="x",
            role="user",
            status="active",
            tenant_id=10,
        )
        db_session.add(user)
        await db_session.flush()

        # 执行：同租户查询
        result = await get_tenant_scoped_or_404(
            db_session, User, obj_id=100, tenant_id=10
        )
        assert result.id == 100
        assert result.tenant_id == 10

    @pytest.mark.asyncio
    async def test_cross_tenant_returns_404(self, db_session):
        """TC-P5-019: 跨租户查询应返回 404（不泄露存在性）."""
        from fastapi import HTTPException

        tenant_a = Tenant(id=11, name="租户A", code="ta", status="active")
        tenant_b = Tenant(id=22, name="租户B", code="tb", status="active")
        db_session.add_all([tenant_a, tenant_b])
        await db_session.flush()

        # 租户 A 的用户
        user = User(
            id=101,
            username="cross_tenant_user",
            email="cross@tenant.com",
            email_hash="hash_cross_001",
            password_hash="x",
            role="user",
            status="active",
            tenant_id=11,  # 属于租户 A
        )
        db_session.add(user)
        await db_session.flush()

        # 执行：租户 B 查询租户 A 的用户 → 404
        with pytest.raises(HTTPException) as exc_info:
            await get_tenant_scoped_or_404(
                db_session, User, obj_id=101, tenant_id=22
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_nonexistent_record_returns_404(self, db_session):
        """TC-P5-020: 不存在的记录返回 404."""
        from fastapi import HTTPException

        tenant = Tenant(id=12, name="租户C", code="tc", status="active")
        db_session.add(tenant)
        await db_session.flush()

        with pytest.raises(HTTPException) as exc_info:
            await get_tenant_scoped_or_404(
                db_session, User, obj_id=99999, tenant_id=12
            )
        assert exc_info.value.status_code == 404

    @pytest.mark.asyncio
    async def test_model_without_tenant_id_raises(self, db_session):
        """TC-P5-021: 模型无 tenant_id 列应抛 TenantColumnMissingError."""
        with pytest.raises(TenantColumnMissingError):
            await get_tenant_scoped_or_404(
                db_session, EducationContent, obj_id=1, tenant_id=1
            )
