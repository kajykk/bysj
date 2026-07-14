from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import func, select

from app.models.admin import ModelFeedback, OperationLog, SystemConfig

if TYPE_CHECKING:
    pass


class ConfigMixin:
    """系统配置与模型反馈管理相关方法 Mixin。

    包含:
    - 系统配置的列表查询与 upsert (含 ISS-078 配置 key 白名单校验、H-03 竞态修复)
    - 模型反馈 (ModelFeedback) 的分页查询

    依赖主类 AdminService 提供 `self.db` 以及主模块的 `_ALLOWED_CONFIG_KEYS` 常量
    (通过延迟导入规避循环导入)。
    """

    async def list_feedbacks(self, page: int, page_size: int) -> dict:
        offset = (page - 1) * page_size
        stmt = (
            select(ModelFeedback)
            .order_by(ModelFeedback.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        total = (
            await self.db.execute(select(func.count()).select_from(ModelFeedback))
        ).scalar_one()
        return {
            "items": [
                {
                    "id": r.id,
                    "counselor_id": r.counselor_id,
                    "user_id": r.user_id,
                    "assessment_id": r.assessment_id,
                    "agreed": r.agreed,
                    "reason": r.reason,
                    "created_at": r.created_at.isoformat(),
                }
                for r in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def list_configs(self) -> list[dict]:
        rows = (
            (
                await self.db.execute(
                    select(SystemConfig).order_by(SystemConfig.config_key.asc())
                )
            )
            .scalars()
            .all()
        )
        return [
            {
                "id": r.id,
                "config_key": r.config_key,
                "config_value": r.config_value,
                "description": r.description,
                "updated_by": r.updated_by,
            }
            for r in rows
        ]

    async def upsert_config(self, admin_id: int, payload: dict) -> int:
        # ISS-078: 配置 key 白名单校验，防止任意 key 写入
        # 延迟导入主模块的 _ALLOWED_CONFIG_KEYS 常量，规避循环导入
        from app.services.admin_service import _ALLOWED_CONFIG_KEYS

        key = payload["config_key"]
        if key not in _ALLOWED_CONFIG_KEYS:
            raise ValueError(f"不支持的配置键: {key}（仅允许白名单内的配置项）")
        row = (
            await self.db.execute(
                select(SystemConfig).where(SystemConfig.config_key == key)
            )
        ).scalar_one_or_none()
        from sqlalchemy.exc import IntegrityError as SAIntegrityError

        try:
            if row is None:
                row = SystemConfig(
                    config_key=payload["config_key"],
                    config_value=payload["config_value"],
                    description=payload.get("description"),
                    updated_by=admin_id,
                )
                self.db.add(row)
            else:
                row.config_value = payload["config_value"]
                row.description = payload.get("description")
                row.updated_by = admin_id

            await self.db.flush()
        except SAIntegrityError:
            # H-03 修复：并发 upsert 竞态，回滚后重试为 update
            await self.db.rollback()
            row = (
                await self.db.execute(
                    select(SystemConfig).where(
                        SystemConfig.config_key == payload["config_key"]
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                raise
            row.config_value = payload["config_value"]
            row.description = payload.get("description")
            row.updated_by = admin_id
            await self.db.flush()
        self.db.add(
            OperationLog(
                operator_id=admin_id,
                operator_role="admin",
                action_type="upsert_system_config",
                target_type="system_config",
                target_id=row.id,
                detail=f"config_key={row.config_key}",
            )
        )
        await self.db.commit()
        await self.db.refresh(row)
        return row.id
