from __future__ import annotations

import logging
from datetime import UTC, datetime

from sqlalchemy import func, select

from app.core.contracts import (
    ACTION_TYPE_WARNING_ESCALATE,
    ACTION_TYPE_WARNING_HANDLE,
    ACTION_TYPE_WARNING_IGNORE,
    WARNING_ACTION_ESCALATE,
    WARNING_ACTION_HANDLE,
    WARNING_ACTION_IGNORE,
    normalize_risk_level,
    resolve_warning_status,
)
from app.models.admin import OperationLog
from app.models.risk import WarningNotification

logger = logging.getLogger(__name__)


class WarningMixin:
    """风险告警处理相关方法 Mixin。

    包含:
    - `list_warnings`: 列出当前咨询师的告警通知 (支持 only_unhandled 过滤)
    - `handle_warning`: 处理告警 (HANDLE/IGNORE)，含 H-Svc-13 幂等性修复
    - `escalate_warning`: 升级告警 (ISS-058)，记录升级原因并写入审计日志

    依赖主类 CounselorService 提供 `self.db`。
    """

    async def list_warnings(
        self, counselor_id: int, page: int, page_size: int, only_unhandled: bool
    ) -> dict:
        offset = (page - 1) * page_size
        stmt = select(WarningNotification).where(
            WarningNotification.counselor_id == counselor_id
        )
        count_stmt = (
            select(func.count())
            .select_from(WarningNotification)
            .where(WarningNotification.counselor_id == counselor_id)
        )
        if only_unhandled:
            stmt = stmt.where(WarningNotification.is_handled.is_(False))
            count_stmt = count_stmt.where(WarningNotification.is_handled.is_(False))

        stmt = (
            stmt.order_by(WarningNotification.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        total = (await self.db.execute(count_stmt)).scalar_one()

        return {
            "items": [
                {
                    "id": r.id,
                    "user_id": r.user_id,
                    "risk_assessment_id": r.risk_assessment_id,
                    "title": f"用户#{r.user_id}风险预警",
                    "content": r.trigger_reason,
                    "risk_level": normalize_risk_level(r.current_level),
                    "status": resolve_warning_status(r.is_handled, r.handle_action),
                    "handled_at": r.handled_at.isoformat() if r.handled_at else None,
                    "handled_by": (
                        f"counselor#{r.counselor_id}" if r.is_handled else None
                    ),
                    "handled_note": r.handle_note,
                    "created_at": r.created_at.isoformat(),
                }
                for r in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def handle_warning(
        self,
        counselor_id: int,
        warning_id: int,
        action: str,
        note: str | None,
        ip_address: str | None = None,
        request_id: str | None = None,
    ) -> bool:
        warning = await self.db.get(WarningNotification, warning_id)
        if warning is None or warning.counselor_id != counselor_id:
            return False
        if warning.is_handled:
            # H-Svc-13 修复：已处理但 action 不一致时返回 False，避免幂等性破坏
            # （如已 IGNORE 后再调 HANDLE 仍返回 True 但 DB 仍是 IGNORE）
            if warning.handle_action != action:
                logger.warning(
                    "handle_warning idempotency violated: warning_id=%s existing_action=%s requested_action=%s",
                    warning_id,
                    warning.handle_action,
                    action,
                )
                return False
            return True

        if action not in {WARNING_ACTION_HANDLE, WARNING_ACTION_IGNORE}:
            return False

        warning.is_handled = True
        warning.handled_at = datetime.now(UTC).replace(tzinfo=None)
        warning.handle_action = action
        warning.handle_note = note
        action_type = (
            ACTION_TYPE_WARNING_IGNORE
            if action == WARNING_ACTION_IGNORE
            else ACTION_TYPE_WARNING_HANDLE
        )
        self.db.add(
            OperationLog(
                operator_id=counselor_id,
                operator_role="counselor",
                action_type=action_type,
                target_type="warning_notification",
                target_id=warning.id,
                detail=f"action={action};request_id={request_id or '-'}",
                ip_address=ip_address,
            )
        )
        await self.db.commit()
        return True

    async def escalate_warning(
        self,
        counselor_id: int,
        warning_id: int,
        reason: str,
        ip_address: str | None = None,
        request_id: str | None = None,
    ) -> bool:
        # ISS-058: 升级预警 - 更新状态为 escalated，记录升级原因到 handled_note，写入审计日志
        warning = await self.db.get(WarningNotification, warning_id)
        if warning is None or warning.counselor_id != counselor_id:
            return False
        warning.is_handled = True
        warning.handled_at = datetime.now(UTC).replace(tzinfo=None)
        warning.handle_action = WARNING_ACTION_ESCALATE
        warning.handle_note = reason
        self.db.add(
            OperationLog(
                operator_id=counselor_id,
                operator_role="counselor",
                action_type=ACTION_TYPE_WARNING_ESCALATE,
                target_type="warning_notification",
                target_id=warning.id,
                detail=f"action=escalated;reason={reason};request_id={request_id or '-'}",
                ip_address=ip_address,
            )
        )
        await self.db.commit()
        return True
