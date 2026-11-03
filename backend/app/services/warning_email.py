"""来访者风险预警邮件：只投递给该来访者当前绑定的咨询师本人。

与系统级告警邮件（``ALERT_EMAIL_RECIPIENTS``，面向运维/值班）相互独立：
- 系统告警：AlertManager → OperationLog → CompositeNotifier；
- 来访者预警：WarningNotification → 绑定咨询师在个人设置中填写的 ``users.email``。

触发路径有两条，均**在预警落库之后**执行：
- 实时评估：``warning.created`` 事件（``schedule_after_commit`` 在事务提交后发布）；
- 每日扫描：``tasks.scheduler._notify_warning`` 在按页 commit 之后调用。

任何失败只记录日志、返回 False，不向调用方抛异常——预警已入库，
邮件是附加通知通道，不得反过来影响主流程。
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.contracts import (
    USER_ROLE_COUNSELOR,
    USER_STATUS_ACTIVE,
    USER_STATUS_DELETED,
)
from app.core.event_bus import event_bus
from app.core.states import BindingStatus
from app.models.user import User, UserCounselorBinding
from app.services.email_service import EmailService

logger = logging.getLogger(__name__)

_REGISTERED = False


@dataclass(frozen=True)
class _Recipient:
    email: str
    client_name: str
    client_user_id: int


def _is_deliverable_email(email: str) -> bool:
    """拒绝空值/控制字符/明显非法地址，避免把用户输入写进邮件头。"""
    if not email or len(email) > 254:
        return False
    if any(ch.isspace() or ord(ch) < 32 or ord(ch) == 127 for ch in email):
        return False
    local, sep, domain = email.partition("@")
    return bool(sep and local and domain and "." in domain and "@" not in domain)


async def _resolve_recipient(
    db: AsyncSession,
    *,
    user_id: int,
    counselor_id: int,
) -> _Recipient | None:
    client = await db.get(User, user_id)
    counselor = await db.get(User, counselor_id)

    if counselor_id == user_id:
        logger.warning(
            "warning_email.skip_self_binding user_id=%s counselor_id=%s",
            user_id,
            counselor_id,
        )
        return None
    if client is None or counselor is None:
        logger.warning(
            "warning_email.skip_missing_user user_id=%s counselor_id=%s",
            user_id,
            counselor_id,
        )
        return None
    if client.status == USER_STATUS_DELETED:
        logger.warning(
            "warning_email.skip_deleted_client user_id=%s counselor_id=%s",
            user_id,
            counselor_id,
        )
        return None
    if counselor.role != USER_ROLE_COUNSELOR:
        logger.warning(
            "warning_email.skip_counselor_role user_id=%s counselor_id=%s role=%s",
            user_id,
            counselor_id,
            counselor.role,
        )
        return None
    if counselor.status != USER_STATUS_ACTIVE:
        logger.warning(
            "warning_email.skip_inactive_counselor user_id=%s counselor_id=%s status=%s",
            user_id,
            counselor_id,
            counselor.status,
        )
        return None
    if counselor.tenant_id != client.tenant_id:
        logger.warning(
            "warning_email.skip_tenant_mismatch user_id=%s counselor_id=%s "
            "client_tenant=%s counselor_tenant=%s",
            user_id,
            counselor_id,
            client.tenant_id,
            counselor.tenant_id,
        )
        return None

    email = counselor.email or ""
    if not _is_deliverable_email(email):
        logger.warning(
            "warning_email.skip_invalid_email user_id=%s counselor_id=%s",
            user_id,
            counselor_id,
        )
        return None

    binding_stmt = (
        select(UserCounselorBinding.id)
        .where(
            UserCounselorBinding.user_id == user_id,
            UserCounselorBinding.counselor_id == counselor_id,
            UserCounselorBinding.status == BindingStatus.ACTIVE,
        )
        .limit(1)
    )
    if (await db.execute(binding_stmt)).first() is None:
        logger.warning(
            "warning_email.skip_inactive_binding user_id=%s counselor_id=%s",
            user_id,
            counselor_id,
        )
        return None

    return _Recipient(
        email=email,
        client_name=client.username,
        client_user_id=client.id,
    )


async def _deliver(recipient: _Recipient, *, warning_id: int, risk_level: int, trigger_reason: str) -> bool:
    try:
        sent = await EmailService().send_warning_alert_email(
            email=recipient.email,
            client_name=recipient.client_name,
            client_user_id=recipient.client_user_id,
            risk_level=risk_level,
            trigger_reason=trigger_reason,
            warning_id=warning_id,
        )
    except Exception:
        logger.exception(
            "warning_email.delivery_failed warning_id=%s client_user_id=%s",
            warning_id,
            recipient.client_user_id,
        )
        return False
    return sent


async def send_warning_email(
    *,
    warning_id: int,
    user_id: int,
    counselor_id: int | None,
    risk_level: int,
    trigger_reason: str,
    db: AsyncSession | None = None,
) -> bool:
    """把一条预警投递到绑定咨询师的邮箱，返回是否已交给 SMTP。

    ``db`` 为空时自行开一个短生命周期 session（查完收件人即关闭，
    避免 SMTP 握手期间占用连接）；调用方已有 session 时可传入复用。
    """
    if counselor_id is None:
        logger.debug(
            "warning_email.skip_no_counselor warning_id=%s user_id=%s",
            warning_id,
            user_id,
        )
        return False

    try:
        if db is not None:
            recipient = await _resolve_recipient(
                db, user_id=user_id, counselor_id=counselor_id
            )
        else:
            from app.core.database import AsyncSessionLocal

            async with AsyncSessionLocal() as session:
                recipient = await _resolve_recipient(
                    session, user_id=user_id, counselor_id=counselor_id
                )
    except Exception:
        logger.exception(
            "warning_email.resolve_failed warning_id=%s user_id=%s counselor_id=%s",
            warning_id,
            user_id,
            counselor_id,
        )
        return False

    if recipient is None:
        return False

    sent = await _deliver(
        recipient,
        warning_id=warning_id,
        risk_level=risk_level,
        trigger_reason=trigger_reason,
    )
    if sent:
        logger.info(
            "warning_email.sent warning_id=%s user_id=%s counselor_id=%s",
            warning_id,
            user_id,
            counselor_id,
        )
    return sent


async def _on_warning_created(data: dict) -> None:
    warning_id = data.get("warning_id")
    user_id = data.get("user_id")
    risk_level = data.get("current_level")
    if warning_id is None or user_id is None or risk_level is None:
        logger.warning(
            "warning_email.invalid_event keys=%s", sorted(data.keys())
        )
        return
    try:
        await send_warning_email(
            warning_id=int(warning_id),
            user_id=int(user_id),
            counselor_id=data.get("counselor_id"),
            risk_level=int(risk_level),
            trigger_reason=str(data.get("trigger_reason") or ""),
        )
    except Exception:
        # send_warning_email 自身已兜底；这里防的是事件数据形状异常
        logger.exception(
            "warning_email.event_handler_failed warning_id=%s", warning_id
        )


def register_warning_email_handler() -> None:
    """订阅 ``warning.created``。重复调用只注册一次。"""
    global _REGISTERED
    if _REGISTERED:
        return
    event_bus.subscribe("warning.created", _on_warning_created)
    _REGISTERED = True
    logger.info("warning_email handler registered for warning.created")
