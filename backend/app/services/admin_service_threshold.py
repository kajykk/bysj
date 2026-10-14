from __future__ import annotations

from typing import TYPE_CHECKING

from fastapi import Request
from sqlalchemy import select

from app.core.audit import record_audit
from app.models.admin import WarningThreshold

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
        *,
        # AUDIT-2026-10-13 (P1-21)：操作者角色必须由调用方如实传入。
        # 改前硬编码 ``operator_role="admin"``，而本端点的鉴权依赖
        # ``require_platform_admin()`` 同时放行 admin 与 super_admin ——
        # 于是 super_admin 的高危操作（改预警阈值）在审计日志里被记成
        # "admin"，事后无法区分「谁做的」。关键字参数且无默认值：漏传直接
        # TypeError，不给「忘记传」留静默兜底。
        admin_role: str,
        # P2-33 第六批：审计上下文由调用方穿入（API 端点传 request + 操作者租户）。
        # ip_address 仅在 request 缺失时生效（保留历史"调用方显式传 ip"路径不丢审计）。
        request: Request | None = None,
        tenant_id: int | None = None,
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
        await record_audit(
            self.db,
            actor_id=admin_id,
            actor_role=admin_role,
            action="upsert_warning_threshold",
            target_type="warning_threshold",
            target_id=row.id,
            detail={"level": row.level, "request_id": request_id or "-"},
            request=request,
            tenant_id=tenant_id,
            ip_address=ip_address,
        )
        await self.db.commit()
        await self.db.refresh(row)
        return row.id
