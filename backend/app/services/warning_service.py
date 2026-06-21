from __future__ import annotations

import logging
from datetime import UTC, datetime, time

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.contracts import (
    ACTION_TYPE_WARNING_READ,
    ACTION_TYPE_WARNING_READ_ALL,
    normalize_risk_level,
    resolve_warning_status,
)
from app.models.admin import OperationLog
from app.models.risk import WarningNotification, WarningSetting

logger = logging.getLogger(__name__)


class WarningService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    async def list_warnings(
        self,
        user_id: int,
        page: int,
        page_size: int,
        is_read: bool | None,
        risk_level: int | None = None,
    ) -> dict:
        offset = (page - 1) * page_size
        stmt = select(WarningNotification).where(WarningNotification.user_id == user_id)
        count_stmt = select(func.count()).select_from(WarningNotification).where(WarningNotification.user_id == user_id)

        if is_read is not None:
            stmt = stmt.where(WarningNotification.is_read == is_read)
            count_stmt = count_stmt.where(WarningNotification.is_read == is_read)

        # M6 修复：risk_level 过滤下推到 SQL，避免 total 与 items 不一致
        if risk_level is not None:
            stmt = stmt.where(WarningNotification.current_level == risk_level)
            count_stmt = count_stmt.where(WarningNotification.current_level == risk_level)

        stmt = stmt.order_by(WarningNotification.created_at.desc()).offset(offset).limit(page_size)
        rows = (await self.db.execute(stmt)).scalars().all()
        total = (await self.db.execute(count_stmt)).scalar_one()

        items = [
            {
                "id": row.id,
                "risk_level": normalize_risk_level(row.current_level),
                "risk_level_label": normalize_risk_level(row.current_level),
                "title": f"风险等级{normalize_risk_level(row.current_level)}预警",
                "content": row.trigger_reason,
                "is_read": row.is_read,
                "status": resolve_warning_status(row.is_handled, row.handle_action),
                "created_at": row.created_at.isoformat() if row.created_at else None,
                "handled_at": row.handled_at.isoformat() if row.handled_at else None,
                "handled_by": row.counselor_id,
                "handled_note": row.handle_note,
                "physiological_score": None,
                "fusion_detail": None,
            }
            for row in rows
        ]
        return {
            "items": items,
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def mark_read(self, user_id: int, warning_id: int) -> bool:
        stmt = select(WarningNotification).where(
            WarningNotification.id == warning_id,
            WarningNotification.user_id == user_id,
        )
        warning = (await self.db.execute(stmt)).scalar_one_or_none()
        if warning is None:
            return False

        if not warning.is_read:
            warning.is_read = True
            warning.read_at = datetime.now(UTC)
            self.db.add(
                OperationLog(
                    operator_id=user_id,
                    operator_role="user",
                    action_type=ACTION_TYPE_WARNING_READ,
                    target_type="warning_notification",
                    target_id=warning.id,
                    detail=f"warning_id={warning.id}",
                )
            )
            await self.db.commit()
        return True

    async def mark_all_read(self, user_id: int) -> int:
        stmt = (
            update(WarningNotification)
            .where(WarningNotification.user_id == user_id, WarningNotification.is_read.is_(False))
            .values(is_read=True, read_at=datetime.now(UTC))
        )
        result = await self.db.execute(stmt)
        changed = result.rowcount or 0
        if changed > 0:
            self.db.add(
                OperationLog(
                    operator_id=user_id,
                    operator_role="user",
                    action_type=ACTION_TYPE_WARNING_READ_ALL,
                    target_type="warning_notification",
                    target_id=None,
                    detail=f"count={changed}",
                )
            )
            await self.db.commit()
        return changed

    @staticmethod
    def _parse_time_value(value) -> time:
        if isinstance(value, time):
            return value
        if isinstance(value, str):
            parts = value.split(":")
            h = int(parts[0]) if parts and parts[0].isdigit() else 0
            m = int(parts[1]) if len(parts) > 1 and parts[1].isdigit() else 0
            s = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
            return time(h, m, s)
        return time(0, 0, 0)

    async def mark_read_all(self, user_id: int) -> int:
        """Alias for mark_all_read (used by older tests)."""
        return await self.mark_all_read(user_id)

    async def get_setting(self, user_id: int) -> WarningSetting:
        stmt = select(WarningSetting).where(WarningSetting.user_id == user_id)
        setting = (await self.db.execute(stmt)).scalar_one_or_none()
        if setting is None:
            setting = WarningSetting(user_id=user_id)
            self.db.add(setting)
            await self.db.flush()
        return setting

    async def update_setting(self, user_id: int, payload: dict) -> WarningSetting:
        setting = await self.get_setting(user_id)
        changed_keys: list[str] = []
        if "notify_channels" in payload and payload["notify_channels"] is not None:
            setting.notify_channels = payload["notify_channels"]
            changed_keys.append("notify_channels")
        if "threshold_level" in payload and payload["threshold_level"] is not None:
            threshold = int(payload["threshold_level"])
            if threshold < 0:
                threshold = 0
            if threshold > 4:
                threshold = 4
            setting.threshold_level = threshold
            changed_keys.append("threshold_level")
        if "quiet_hours_start" in payload and payload["quiet_hours_start"] is not None:
            value = payload["quiet_hours_start"]
            setting.quiet_hours_start = self._parse_time_value(value)
            changed_keys.append("quiet_hours_start")
        if "quiet_hours_end" in payload and payload["quiet_hours_end"] is not None:
            value = payload["quiet_hours_end"]
            setting.quiet_hours_end = self._parse_time_value(value)
            changed_keys.append("quiet_hours_end")

        if changed_keys:
            try:
                self.db.add(
                    OperationLog(
                        operator_id=user_id,
                        operator_role="user",
                        action_type="update_warning_setting",
                        target_type="warning_setting",
                        target_id=setting.id,
                        detail=f"changed={','.join(changed_keys)}",
                    )
                )
            except Exception:
                # P1-E 修复：审计日志写入失败必须记录完整堆栈，便于发现审计系统异常
                logger.exception("Failed to add operation log for update_warning_setting")
        await self.db.commit()
        await self.db.refresh(setting)
        return setting
