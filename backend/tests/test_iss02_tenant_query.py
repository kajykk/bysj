"""ISS-02 覆盖率提升：app/core/tenant_query.py 聚焦测试.

多租户隔离安全关键模块（0% 覆盖）。用轻量 SQLAlchemy Column 桩 + Mock session 隔离，
无需真实数据库。
"""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest
from sqlalchemy import Column, Integer, select

from app.core.tenant_query import (
    DEFAULT_TENANT_ID,
    TenantColumnMissingError,
    assert_tenant_isolated,
    get_tenant_scoped_or_404,
    normalize_tenant_id,
    tenant_scoped_filter,
    tenant_scoped_query,
)


# 用应用真实的 DeclarativeBase 构造最小映射类，select() 可正常构造（无需数据库）
from app.models.base import Base  # noqa: E402


class _Model(Base):
    __tablename__ = "_tq_test_model"
    id = Column(Integer, primary_key=True)
    tenant_id = Column(Integer)


class _ModelNoTenant(Base):
    __tablename__ = "_tq_test_model_no_tenant"
    id = Column(Integer, primary_key=True)


def test_scoped_query_contains_tenant_filter():
    stmt = tenant_scoped_query(_Model, tenant_id=7)
    sql = str(stmt)
    assert "tenant_id" in sql


def test_scoped_query_invalid_tenant_id():
    with pytest.raises(ValueError):
        tenant_scoped_query(_Model, tenant_id=None)
    with pytest.raises(ValueError):
        tenant_scoped_query(_Model, tenant_id=0)
    with pytest.raises(ValueError):
        tenant_scoped_query(_Model, tenant_id="x")  # type: ignore[arg-type]


def test_scoped_query_missing_column_raises():
    with pytest.raises(TenantColumnMissingError):
        tenant_scoped_query(_ModelNoTenant, tenant_id=1)


def test_scoped_query_assert_false_falls_back_to_select():
    # 无 tenant 列且 assert=False → 返回普通 select(不抛错)
    stmt = tenant_scoped_query(_ModelNoTenant, tenant_id=1, assert_tenant_column=False)
    assert isinstance(stmt, type(select(_ModelNoTenant)))


def test_scoped_filter_returns_condition():
    cond = tenant_scoped_filter(_Model, tenant_id=3)
    assert cond is not None
    assert "tenant_id" in str(cond)


def test_scoped_filter_invalid_tenant_id():
    with pytest.raises(ValueError):
        tenant_scoped_filter(_Model, tenant_id=-1)


def test_scoped_filter_missing_column_assert_false_returns_none():
    assert tenant_scoped_filter(_ModelNoTenant, tenant_id=1, assert_tenant_column=False) is None


async def test_get_scoped_or_404_returns_obj():
    obj = _Model()
    db = MagicMock()
    db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=obj))
    )
    result = await get_tenant_scoped_or_404(db, _Model, obj_id=5, tenant_id=1)
    assert result is obj


async def test_get_scoped_or_404_raises_404_when_missing():
    db = MagicMock()
    db.execute = AsyncMock(
        return_value=MagicMock(scalar_one_or_none=MagicMock(return_value=None))
    )
    from fastapi import HTTPException

    with pytest.raises(HTTPException) as ei:
        await get_tenant_scoped_or_404(db, _Model, obj_id=999, tenant_id=1)
    assert ei.value.status_code == 404


def test_assert_tenant_isolated_true():
    assert assert_tenant_isolated(_Model) is True


def test_assert_tenant_isolated_missing_raises():
    with pytest.raises(TenantColumnMissingError):
        assert_tenant_isolated(_ModelNoTenant)


def test_normalize_tenant_id():
    assert normalize_tenant_id(None) == DEFAULT_TENANT_ID
    assert normalize_tenant_id(5) == 5
    with pytest.raises(ValueError):
        normalize_tenant_id(-1)
