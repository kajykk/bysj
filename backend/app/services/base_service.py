"""MAINT-P2-004: 通用 CRUD 基类 (BaseService).

减少 API 层 CRUD 代码重复 (列表查询/单条查询/创建/更新/删除).
子类继承 BaseService 并指定 model 类型, 即可获得通用 CRUD 方法.

设计原则:
- 泛型支持: 用 TypeVar 绑定 Model 子类, 保持类型安全
- 可扩展: 子类可覆盖任意方法实现自定义逻辑
- 事务安全: 所有写操作使用 flush() (在 savepoint 内) 或 commit()
- 统一异常: NotFoundError / ValidationError / ConflictError
- 向后兼容: 不强制现有 service 继承 BaseService, 新代码可选使用

使用示例::

    class WarningService(BaseService[WarningNotification]):
        model = WarningNotification

        async def get_unhandled(self, user_id: int) -> list[WarningNotification]:
            stmt = select(self.model).where(
                self.model.user_id == user_id,
                self.model.is_handled.is_(False),
            )
            return (await self.db.execute(stmt)).scalars().all()

        # 继承的通用方法: get_by_id / list_paginated / create / update / delete
"""

from __future__ import annotations

import logging
from typing import Any, Generic, TypeVar

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.base import Base

logger = logging.getLogger(__name__)

T = TypeVar("T", bound=Base)


class NotFoundError(Exception):
    """记录不存在异常."""

    def __init__(self, model_name: str, record_id: Any) -> None:
        self.model_name = model_name
        self.record_id = record_id
        super().__init__(f"{model_name} with id={record_id} not found")


class BaseService(Generic[T]):
    """MAINT-P2-004: 通用 CRUD 服务基类.

    子类需设置:
        model: SQLAlchemy Model 类 (如 WarningNotification)

    提供方法:
        get_by_id(record_id) -> T | None
        get_by_id_or_404(record_id) -> T
        list_paginated(offset, limit, filters) -> tuple[list[T], int]
        create(data: dict) -> T
        update(record_id, data: dict) -> T
        delete(record_id) -> bool
    """

    model: type[T]

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def get_by_id(self, record_id: Any) -> T | None:
        """根据 ID 查询单条记录.

        Args:
            record_id: 记录主键 ID.

        Returns:
            记录对象, 不存在返回 None.
        """
        stmt = select(self.model).where(self.model.id == record_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def get_by_id_or_404(self, record_id: Any) -> T:
        """根据 ID 查询, 不存在抛 NotFoundError.

        Args:
            record_id: 记录主键 ID.

        Returns:
            记录对象.

        Raises:
            NotFoundError: 记录不存在.
        """
        record = await self.get_by_id(record_id)
        if record is None:
            raise NotFoundError(self.model.__name__, record_id)
        return record

    async def list_paginated(
        self,
        offset: int = 0,
        limit: int = 20,
        *,
        filters: list[Any] | None = None,
        order_by: Any = None,
    ) -> tuple[list[T], int]:
        """分页查询记录列表.

        Args:
            offset: 偏移量 (默认 0).
            limit: 每页数量 (默认 20).
            filters: SQLAlchemy where 条件列表 (可选).
            order_by: 排序条件 (可选, 默认按 id 降序).

        Returns:
            (records, total) 元组.
        """
        stmt = select(self.model)
        count_stmt = select(func.count()).select_from(self.model)

        if filters:
            for f in filters:
                stmt = stmt.where(f)
                count_stmt = count_stmt.where(f)

        if order_by is not None:
            stmt = stmt.order_by(order_by)
        else:
            stmt = stmt.order_by(self.model.id.desc())

        total_result = await self.db.execute(count_stmt)
        total = total_result.scalar() or 0

        stmt = stmt.offset(offset).limit(limit)
        result = await self.db.execute(stmt)
        records = list(result.scalars().all())

        return records, total

    async def create(self, data: dict[str, Any]) -> T:
        """创建记录.

        Args:
            data: 字段名到值的映射.

        Returns:
            创建的记录对象 (已 flush, id 可用).
        """
        record = self.model(**data)
        self.db.add(record)
        await self.db.flush()
        await self.db.refresh(record)
        logger.debug(
            "MAINT-P2-004: Created %s id=%s", self.model.__name__, record.id
        )
        return record

    async def update(self, record_id: Any, data: dict[str, Any]) -> T:
        """更新记录.

        Args:
            record_id: 记录主键 ID.
            data: 需要更新的字段名到值的映射.

        Returns:
            更新后的记录对象.

        Raises:
            NotFoundError: 记录不存在.
        """
        record = await self.get_by_id_or_404(record_id)
        for key, value in data.items():
            if hasattr(record, key):
                setattr(record, key, value)
        await self.db.flush()
        await self.db.refresh(record)
        logger.debug(
            "MAINT-P2-004: Updated %s id=%s", self.model.__name__, record_id
        )
        return record

    async def delete(self, record_id: Any) -> bool:
        """删除记录.

        Args:
            record_id: 记录主键 ID.

        Returns:
            True if deleted, False if not found.

        Raises:
            NotFoundError: 记录不存在 (如果需要严格模式).
        """
        record = await self.get_by_id(record_id)
        if record is None:
            return False
        await self.db.delete(record)
        await self.db.flush()
        logger.debug(
            "MAINT-P2-004: Deleted %s id=%s", self.model.__name__, record_id
        )
        return True
