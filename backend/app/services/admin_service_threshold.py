from __future__ import annotations

from typing import TYPE_CHECKING

from sqlalchemy import select

from app.models.admin import OperationLog, WarningThreshold

if TYPE_CHECKING:
    pass


class ThresholdMixin:
    """告警阈值管理相关方法 Mixin。

    包含告警阈值的列表查询与 upsert (创建/更新) 逻辑，
    并处理并发竞态 (H-03 修复)，在变更时写入 OperationLog 审计日志。

    依赖主类 AdminService 提供 `self.db`。
    """

    async def list_thresholds(self) -> list[dict]:
        rows = (
            (
                await self.db.execute(
                    select(WarningThreshold).order_by(WarningThreshold.level.asc())
                )
            )
            .scalars()
            .all()
        )
        return [
            {
                "id": r.id,
                "level": r.level,
                "level_name": r.level_name,
                "min_score": r.min_score,
                "max_score": r.max_score,
                "color": r.color,
                "action_required": r.action_required,
            }
            for r in rows
        ]

    async def upsert_threshold(
        self,
        admin_id: int,
        payload: dict,
        ip_address: str | None = None,
        request_id: str | None = None,
    ) -> int:
        row = (
            await self.db.execute(
                select(WarningThreshold).where(
                    WarningThreshold.level == payload["level"]
                )
            )
        ).scalar_one_or_none()
        from sqlalchemy.exc import IntegrityError as SAIntegrityError

        try:
            if row is None:
                # 使用显式字段构造而非 **payload 直接解包
                row = WarningThreshold(
                    level=payload["level"],
                    level_name=payload["level_name"],
                    min_score=payload["min_score"],
                    max_score=payload["max_score"],
                    color=payload["color"],
                    action_required=payload["action_required"],
                )
                self.db.add(row)
                await self.db.flush()
            else:
                for key in [
                    "level_name",
                    "min_score",
                    "max_score",
                    "color",
                    "action_required",
                ]:
                    if key in payload:
                        setattr(row, key, payload[key])
                await self.db.flush()
        except SAIntegrityError:
            # H-03 修复：并发 upsert 竞态，回滚后重试为 update
            await self.db.rollback()
            row = (
                await self.db.execute(
                    select(WarningThreshold).where(
                        WarningThreshold.level == payload["level"]
                    )
                )
            ).scalar_one_or_none()
            if row is None:
                raise
            for key in [
                "level_name",
                "min_score",
                "max_score",
                "color",
                "action_required",
            ]:
                if key in payload:
                    setattr(row, key, payload[key])
            await self.db.flush()
        self.db.add(
            OperationLog(
                operator_id=admin_id,
                operator_role="admin",
                action_type="upsert_warning_threshold",
                target_type="warning_threshold",
                target_id=row.id,
                detail=f"level={row.level};request_id={request_id or '-'}",
                ip_address=ip_address,
            )
        )
        await self.db.commit()
        await self.db.refresh(row)
        return row.id
