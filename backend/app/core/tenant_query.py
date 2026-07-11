"""Phase 5 租户级查询隔离工具.

按 ADR-001 决策：
- 所有租户敏感表的查询必须包含 WHERE tenant_id = :current_tenant_id
- 提供 tenant_scoped_query(model, tenant_id) 工具函数
- 自动化越权测试验证跨租户访问被阻断

设计原则:
1. 单一入口 — 所有租户敏感查询必须通过本模块构造，避免散落 tenant_id 过滤
2. 防呆设计 — 未提供 tenant_id 时抛错而非静默放行
3. 可观测 — 记录跨租户访问尝试
4. 可测试 — 提供 assert_tenant_isolated 辅助测试函数

使用示例:
    from app.core.tenant_query import tenant_scoped_query

    stmt = tenant_scoped_query(User, tenant_id=1).where(User.role == "admin")
    users = (await db.execute(stmt)).scalars().all()

    # 单条查询
    stmt = tenant_scoped_query(User, tenant_id=1).where(User.id == user_id)
    user = (await db.execute(stmt)).scalar_one_or_none()

    # 带 join 的查询
    stmt = (
        tenant_scoped_query(User, tenant_id=1)
        .join(UserProfile, UserProfile.user_id == User.id)
    )
"""

from __future__ import annotations

import logging
from typing import TypeVar

from fastapi import HTTPException, status
from sqlalchemy import Select, select
from sqlalchemy.orm import DeclarativeBase

from app.core.contracts import DEFAULT_TENANT_ID

logger = logging.getLogger(__name__)

ModelT = TypeVar("ModelT", bound=DeclarativeBase)


class TenantColumnMissingError(RuntimeError):
    """模型缺少 tenant_id 列时抛出."""


def _get_tenant_id_column(model: type[DeclarativeBase]):
    """安全获取模型的 tenant_id 列.

    Raises:
        TenantColumnMissingError: 模型未定义 tenant_id 属性
    """
    col = getattr(model, "tenant_id", None)
    if col is None:
        raise TenantColumnMissingError(
            f"模型 {model.__name__} 未定义 tenant_id 列，无法应用租户隔离。"
            " 若该表确实无需租户隔离，请显式使用 select() 而非 tenant_scoped_query()。"
        )
    return col


def tenant_scoped_query(
    model: type[ModelT],
    tenant_id: int,
    *,
    assert_tenant_column: bool = True,
) -> Select:
    """构造带租户隔离过滤的 select 语句.

    Args:
        model: SQLAlchemy 模型类（必须含 tenant_id 列）
        tenant_id: 当前租户 ID
        assert_tenant_column: 是否校验模型含 tenant_id 列（默认 True）

    Returns:
        Select 语句，已附加 WHERE tenant_id = :tenant_id

    Raises:
        TenantColumnMissingError: 模型缺少 tenant_id 列且 assert_tenant_column=True
        ValueError: tenant_id 为 None 或非正整数

    Examples:
        >>> stmt = tenant_scoped_query(User, tenant_id=1).where(User.role == "admin")
        >>> users = (await db.execute(stmt)).scalars().all()
    """
    if tenant_id is None:
        raise ValueError("tenant_id 不能为 None，必须显式提供")
    if not isinstance(tenant_id, int) or tenant_id < 1:
        raise ValueError(f"tenant_id 必须为正整数，收到: {tenant_id!r}")

    if assert_tenant_column:
        col = _get_tenant_id_column(model)
    else:
        col = getattr(model, "tenant_id", None)
        if col is None:
            # 静默回退到普通 select（用于可选租户隔离的表）
            return select(model)

    return select(model).where(col == tenant_id)


def tenant_scoped_filter(
    model: type[DeclarativeBase],
    tenant_id: int,
    *,
    assert_tenant_column: bool = True,
):
    """构造租户隔离过滤条件（用于组合到已有查询）.

    与 tenant_scoped_query 区别：返回过滤条件而非完整 select，
    适用于 join/subquery 等复杂场景。

    Examples:
        >>> from sqlalchemy import and_
        >>> cond = tenant_scoped_filter(User, tenant_id=1)
        >>> stmt = select(User).where(and_(cond, User.role == "admin"))
    """
    if tenant_id is None:
        raise ValueError("tenant_id 不能为 None，必须显式提供")
    if not isinstance(tenant_id, int) or tenant_id < 1:
        raise ValueError(f"tenant_id 必须为正整数，收到: {tenant_id!r}")

    if assert_tenant_column:
        col = _get_tenant_id_column(model)
    else:
        col = getattr(model, "tenant_id", None)
        if col is None:
            return None  # 无租户列，返回 None 表示无需过滤

    return col == tenant_id


async def get_tenant_scoped_or_404(
    db,
    model: type[ModelT],
    obj_id: int,
    tenant_id: int,
    *,
    id_field: str = "id",
) -> ModelT:
    """获取租户隔离的单条记录，不存在或跨租户时抛 404.

    适用于"通过 ID 查询单条资源"的场景，避免跨租户访问。

    Args:
        db: AsyncSession
        model: 模型类
        obj_id: 资源 ID
        tenant_id: 当前租户 ID
        id_field: 主键字段名（默认 "id"）

    Returns:
        模型实例

    Raises:
        HTTPException(404): 记录不存在或跨租户
    """
    from sqlalchemy import select as _select

    col = _get_tenant_id_column(model)
    id_col = getattr(model, id_field)

    stmt = _select(model).where(id_col == obj_id, col == tenant_id)
    obj = (await db.execute(stmt)).scalar_one_or_none()

    if obj is None:
        logger.warning(
            "Tenant-scoped get failed: model=%s id=%s tenant_id=%s",
            model.__name__, obj_id, tenant_id,
        )
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"{model.__name__} 不存在或无权访问",
        )
    return obj


def assert_tenant_isolated(model: type[DeclarativeBase]) -> bool:
    """断言模型已具备 tenant_id 列（用于测试和启动期校验）.

    Returns:
        True: 模型含 tenant_id 列

    Raises:
        TenantColumnMissingError: 模型缺少 tenant_id 列
    """
    _get_tenant_id_column(model)
    return True


def normalize_tenant_id(tenant_id: int | None) -> int:
    """规范化 tenant_id：None 视为默认租户.

    主要用于兼容历史数据（tenant_id 可能为 NULL）。
    新代码应直接使用 tenant_scoped_query 并显式提供 tenant_id。
    """
    if tenant_id is None:
        return DEFAULT_TENANT_ID
    if not isinstance(tenant_id, int) or tenant_id < 1:
        raise ValueError(f"无效的 tenant_id: {tenant_id!r}")
    return tenant_id
