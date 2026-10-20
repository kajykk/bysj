from __future__ import annotations

import logging
from datetime import UTC, datetime

from fastapi import Request
from sqlalchemy import func, select

from app.core.audit import record_audit
from app.core.contracts import (
    ACTION_TYPE_WARNING_ESCALATE,
    ACTION_TYPE_WARNING_HANDLE,
    ACTION_TYPE_WARNING_IGNORE,
    USER_ROLE_COUNSELOR,
    WARNING_ACTION_ESCALATE,
    WARNING_ACTION_HANDLE,
    WARNING_ACTION_IGNORE,
    normalize_risk_level,
    resolve_warning_status,
)
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

        # ROUND_23 修复：created_at 不是唯一键——同一秒内产生的多条告警
        # created_at 相同，单键排序下顺序由 DB 决定（SQLite/PG 都不保证），
        # 配 LIMIT/OFFSET 会让同一条告警在相邻两页**重复出现或被整页跳过**。
        # 加 id 降序作确定性的 tie-break（与 gdpr_service_export 的
        # "LIMIT/OFFSET 必须有确定性 ORDER BY" 同一纪律）。
        stmt = (
            stmt.order_by(
                WarningNotification.created_at.desc(),
                WarningNotification.id.desc(),
            )
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
                    # M-FIX-006: 补充 is_read 字段. 用户端 WarningService 已返回该字段,
                    # 咨询师端缺失导致前端 WarningsTable/DetailDrawer 的已读/未读标签恒为"未读".
                    "is_read": r.is_read,
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

    async def get_warning_stats(self, counselor_id: int) -> dict:
        """咨询师预警统计（P1-15 / F-03 修复）。

        原前端 ``page_size:200`` 拉全量到浏览器 filter：数据超 200 条时
        分子截断、分母不截断，统计结果是错的。改为 SQL 层条件聚合。

        口径与 ``list_warnings``（不带 ``only_unhandled`` 的全量视图）一致：
        - 已处理/未处理 = ``is_handled`` 布尔本身（前端 ``isHandled`` 即
          ``isWarningHandled``，对 handle/ignore/escalate 三种处置均为 True）；
        - 分级按 ``current_level`` 原始数值（3/2/1），0/4 与越界值不计入
          三档（与前端 normalizeWarningRiskLevel 映射后比较的行为一致）。
        """
        stmt = (
            select(
                func.count().label("total"),
                func.count()
                .filter(WarningNotification.is_handled.is_(False))
                .label("unhandled"),
                func.count()
                .filter(WarningNotification.is_handled.is_(True))
                .label("handled"),
                func.count()
                .filter(WarningNotification.current_level == 3)
                .label("high_risk"),
                func.count()
                .filter(WarningNotification.current_level == 2)
                .label("medium_risk"),
                func.count()
                .filter(WarningNotification.current_level == 1)
                .label("low_risk"),
            )
            .select_from(WarningNotification)
            .where(WarningNotification.counselor_id == counselor_id)
        )
        row = (await self.db.execute(stmt)).one()
        return {
            "total": int(row.total or 0),
            "unhandled": int(row.unhandled or 0),
            "handled": int(row.handled or 0),
            "high_risk": int(row.high_risk or 0),
            "medium_risk": int(row.medium_risk or 0),
            "low_risk": int(row.low_risk or 0),
        }

    async def handle_warning(
        self,
        counselor_id: int,
        warning_id: int,
        action: str,
        note: str | None,
        ip_address: str | None = None,
        request_id: str | None = None,
        *,
        # P2-33 第六批：审计上下文由调用方穿入（API 端点传 request + 操作者租户；
        # 任务/旧测试不传则记 None/平台默认）。
        request: Request | None = None,
        tenant_id: int | None = None,
    ) -> bool:
        """处理预警（HANDLE/IGNORE）。

        `ip_address` 仅在 `request` 缺失时生效（record_audit 一律从 request 取 ip），
        保留它是为了让"服务层直接调用且调用方已有 ip"的历史路径不丢审计信息。
        """
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
        await record_audit(
            self.db,
            actor_id=counselor_id,
            actor_role=USER_ROLE_COUNSELOR,
            action=action_type,
            target_type="warning_notification",
            target_id=warning.id,
            detail={"action": action, "request_id": request_id or "-"},
            request=request,
            tenant_id=tenant_id,
            ip_address=ip_address,
        )
        await self.db.commit()
        return True

    async def get_warning_for_counselor(
        self, counselor_id: int, warning_id: int
    ) -> dict | None:
        """查询属于咨询师的单条告警 (含 status 字段).

        ISS-070 修复: 路由层在 handle_warning 返回失败时用于区分
        "真正不存在/未归属"与"已处理但 action 不一致"两类语义, 避免
        已处理的预警被误报为 404。
        """
        warning = await self.db.get(WarningNotification, warning_id)
        if warning is None or warning.counselor_id != counselor_id:
            return None
        return {
            "id": warning.id,
            "user_id": warning.user_id,
            "risk_assessment_id": warning.risk_assessment_id,
            "title": f"用户#{warning.user_id}风险预警",
            "content": warning.trigger_reason,
            "risk_level": normalize_risk_level(warning.current_level),
            "status": resolve_warning_status(warning.is_handled, warning.handle_action),
            "is_read": warning.is_read,
            "handled_at": (
                warning.handled_at.isoformat() if warning.handled_at else None
            ),
            "handled_by": f"counselor#{warning.counselor_id}"
            if warning.is_handled
            else None,
            "handled_note": warning.handle_note,
            "created_at": warning.created_at.isoformat(),
        }

    async def escalate_warning(
        self,
        counselor_id: int,
        warning_id: int,
        reason: str,
        ip_address: str | None = None,
        request_id: str | None = None,
        *,
        # P2-33 第六批：同上，审计上下文由调用方穿入。
        request: Request | None = None,
        tenant_id: int | None = None,
    ) -> bool:
        # ISS-058: 升级预警 - 更新状态为 escalated，记录升级原因到 handled_note，写入审计日志
        #
        # M9 修复（ROUND_18）：补齐行锁 + 幂等 + 状态前置，与同 mixin 的
        # handle_warning 对齐。原实现仅做"取行 + 校验归属 + 无条件改写"：
        # 一条已 ignored（咨询师判断无需干预）的预警可被再次升级，
        # handle_action 被改写、原 handle_note 被覆盖，且每次调用都写一条审计。
        result = await self.db.execute(
            select(WarningNotification)
            .where(WarningNotification.id == warning_id)
            .with_for_update()
        )
        warning = result.scalar_one_or_none()
        if warning is None or warning.counselor_id != counselor_id:
            return False

        if warning.is_handled:
            if warning.handle_action == WARNING_ACTION_ESCALATE:
                # 重复升级幂等：状态与审计在首次调用已落地，这里仅回 True。
                # 不追加第二条审计，也不覆盖首次升级原因（事故复盘以首次为准）。
                logger.info(
                    "escalate_warning idempotent replay: warning_id=%s counselor_id=%s",
                    warning_id,
                    counselor_id,
                )
                return True
            # ignored / handled 之后不允许再升级（防"已判定无需干预"被悄悄改写）
            logger.warning(
                "escalate_warning rejected: warning_id=%s already handled with action=%s",
                warning_id,
                warning.handle_action,
            )
            return False

        warning.is_handled = True
        warning.handled_at = datetime.now(UTC).replace(tzinfo=None)
        warning.handle_action = WARNING_ACTION_ESCALATE
        warning.handle_note = reason
        await record_audit(
            self.db,
            actor_id=counselor_id,
            actor_role=USER_ROLE_COUNSELOR,
            action=ACTION_TYPE_WARNING_ESCALATE,
            target_type="warning_notification",
            target_id=warning.id,
            detail={
                "action": "escalated",
                "reason": reason,
                "request_id": request_id or "-",
            },
            request=request,
            tenant_id=tenant_id,
            ip_address=ip_address,
        )
        await self.db.commit()
        return True
