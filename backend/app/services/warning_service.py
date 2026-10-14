from __future__ import annotations

import logging
from datetime import UTC, datetime, time

from fastapi import Request
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.audit import record_audit
from app.core.contracts import (
    ACTION_TYPE_WARNING_READ,
    ACTION_TYPE_WARNING_READ_ALL,
    NOTIFY_CHANNELS,
    RISK_LEVEL_DISPLAY_ZH,
    normalize_risk_level,
    resolve_warning_status,
    USER_ROLE_USER,
)
from app.models.risk import WarningNotification, WarningSetting

logger = logging.getLogger(__name__)

# MAINT-P1-003: 通知渠道白名单统一引用 contracts.NOTIFY_CHANNELS (Single Source of Truth)
# 保留 _ALLOWED_NOTIFY_CHANNELS 别名向后兼容 (test_contracts_aggregation 护栏测试仍可校验)
_ALLOWED_NOTIFY_CHANNELS: frozenset[str] = NOTIFY_CHANNELS


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
        count_stmt = (
            select(func.count())
            .select_from(WarningNotification)
            .where(WarningNotification.user_id == user_id)
        )

        if is_read is not None:
            stmt = stmt.where(WarningNotification.is_read == is_read)
            count_stmt = count_stmt.where(WarningNotification.is_read == is_read)

        # M6 修复：risk_level 过滤下推到 SQL，避免 total 与 items 不一致
        if risk_level is not None:
            stmt = stmt.where(WarningNotification.current_level == risk_level)
            count_stmt = count_stmt.where(
                WarningNotification.current_level == risk_level
            )

        stmt = (
            stmt.order_by(WarningNotification.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        total = (await self.db.execute(count_stmt)).scalar_one()

        items = [
            {
                "id": row.id,
                "risk_level": normalize_risk_level(row.current_level),
                "risk_level_label": normalize_risk_level(row.current_level),
                # I18N-03 修复：标题等级改用中文展示标签，避免“风险等级high预警”式英嵌中文案
                "title": f"风险等级{RISK_LEVEL_DISPLAY_ZH.get(normalize_risk_level(row.current_level), normalize_risk_level(row.current_level))}预警",
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

    async def get_stats(self, user_id: int) -> dict:
        """预警统计（P1-15 / F-03 修复）。

        原前端 ``page_size:200`` 拉全量预警到浏览器 filter：数据超 200 条时
        分子（分级/已处理/未读）只覆盖前 200 条，而分母用服务端 total ——
        「高危 46 / 共 260」式的统计结果是错的。改为 SQL 层条件聚合。

        口径与 ``list_warnings`` 的响应字段一一对应：
        - 分级按 ``current_level`` 原始数值（3/2/1），与前端
          ``normalizeWarningRiskLevel`` 把标签映射回数值后比较一致；
          ``current_level`` 为 0/4 或越界值（normalize 出 'none'/'critical'/
          'unknown'）不计入三档，与前端相同；
        - 已处理 = ``is_handled``（handle/ignore/escalate 均置 True，
          与前端 ``isWarningHandled`` 的 status 集合一致）；
        - 未读 = ``is_read`` 为 False。
        """
        stmt = (
            select(
                func.count().label("total"),
                func.count()
                .filter(WarningNotification.current_level == 3)
                .label("high_risk"),
                func.count()
                .filter(WarningNotification.current_level == 2)
                .label("medium_risk"),
                func.count()
                .filter(WarningNotification.current_level == 1)
                .label("low_risk"),
                func.count()
                .filter(WarningNotification.is_handled.is_(True))
                .label("handled"),
                func.count()
                .filter(WarningNotification.is_read.is_(False))
                .label("unread"),
            )
            .select_from(WarningNotification)
            .where(WarningNotification.user_id == user_id)
        )
        row = (await self.db.execute(stmt)).one()
        return {
            "total": int(row.total or 0),
            "high_risk": int(row.high_risk or 0),
            "medium_risk": int(row.medium_risk or 0),
            "low_risk": int(row.low_risk or 0),
            "handled": int(row.handled or 0),
            "unread": int(row.unread or 0),
        }

    async def mark_read(
        self,
        user_id: int,
        warning_id: int,
        *,
        request: Request | None = None,
        tenant_id: int | None = None,
    ) -> bool:
        """P2-33 第五批：审计上下文由调用方穿入（API 端点传 request/tenant，
        任务与旧测试不传则记 None/平台默认）。"""
        stmt = select(WarningNotification).where(
            WarningNotification.id == warning_id,
            WarningNotification.user_id == user_id,
        )
        warning = (await self.db.execute(stmt)).scalar_one_or_none()
        if warning is None:
            return False

        if not warning.is_read:
            warning.is_read = True
            warning.read_at = datetime.now(UTC).replace(tzinfo=None)
            await record_audit(
                self.db,
                actor_id=user_id,
                actor_role=USER_ROLE_USER,
                action=ACTION_TYPE_WARNING_READ,
                target_type="warning_notification",
                target_id=warning.id,
                detail={"warning_id": warning.id},
                request=request,
                tenant_id=tenant_id,
            )
            await self.db.commit()
        return True

    async def mark_all_read(
        self,
        user_id: int,
        *,
        request: Request | None = None,
        tenant_id: int | None = None,
    ) -> int:
        stmt = (
            update(WarningNotification)
            .where(
                WarningNotification.user_id == user_id,
                WarningNotification.is_read.is_(False),
            )
            .values(is_read=True, read_at=datetime.now(UTC).replace(tzinfo=None))
        )
        result = await self.db.execute(stmt)
        changed = result.rowcount or 0
        if changed > 0:
            await record_audit(
                self.db,
                actor_id=user_id,
                actor_role=USER_ROLE_USER,
                action=ACTION_TYPE_WARNING_READ_ALL,
                target_type="warning_notification",
                target_id=None,
                detail={"count": changed},
                request=request,
                tenant_id=tenant_id,
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
            # M-Svc-9 修复：校验 hour/minute/second 范围，避免非法值导致 time() 抛模糊异常
            if not 0 <= h <= 23:
                raise ValueError(f"hour 必须在 0-23 范围内，当前值: {h}")
            if not 0 <= m <= 59:
                raise ValueError(f"minute 必须在 0-59 范围内，当前值: {m}")
            if not 0 <= s <= 59:
                raise ValueError(f"second 必须在 0-59 范围内，当前值: {s}")
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

    async def update_setting(
        self,
        user_id: int,
        payload: dict,
        *,
        request: Request | None = None,
        tenant_id: int | None = None,
    ) -> WarningSetting:
        setting = await self.get_setting(user_id)
        changed_keys: list[str] = []
        if "notify_channels" in payload and payload["notify_channels"] is not None:
            # M-Svc-10 修复：校验 notify_channels 类型和元素，防御性校验
            # （service 层可能被非 schema 路径调用，需独立校验）
            channels = payload["notify_channels"]
            if isinstance(channels, list):
                # 列表形式：校验每个元素是允许的通道名，并转换为 dict 形式（启用）
                invalid = [ch for ch in channels if ch not in _ALLOWED_NOTIFY_CHANNELS]
                if invalid:
                    raise ValueError(
                        f"无效的 notify_channel: {', '.join(invalid)}，"
                        f"允许值: {', '.join(sorted(_ALLOWED_NOTIFY_CHANNELS))}"
                    )
                channels = {ch: True for ch in channels}
            elif isinstance(channels, dict):
                extra = set(channels.keys()) - _ALLOWED_NOTIFY_CHANNELS
                if extra:
                    raise ValueError(
                        f"无效的 notify_channel: {', '.join(sorted(extra))}，"
                        f"允许值: {', '.join(sorted(_ALLOWED_NOTIFY_CHANNELS))}"
                    )
                for ch, enabled in channels.items():
                    if not isinstance(enabled, bool):
                        raise ValueError(
                            f"notify_channel.{ch} 的值必须是 bool，当前: {type(enabled).__name__}"
                        )
            else:
                raise ValueError(
                    f"notify_channels 必须是 dict 或 list，当前类型: {type(channels).__name__}"
                )
            setting.notify_channels = channels
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
                await record_audit(
                    self.db,
                    actor_id=user_id,
                    actor_role=USER_ROLE_USER,
                    action="update_warning_setting",
                    target_type="warning_setting",
                    target_id=setting.id,
                    detail={"changed": changed_keys},
                    request=request,
                    tenant_id=tenant_id,
                )
                # P1-D5 修复：原代码在 try/except 外调用 commit()，导致：
                # 1. 若 add() 抛异常（Python 层），except 捕获后仍执行 commit()，
                #    会提交 setting 更新但丢失审计日志，破坏审计完整性。
                # 2. 若 commit() 本身因审计日志约束失败而抛异常，未被捕获，
                #    调用方无法区分是 setting 更新失败还是审计失败。
                # 改为：commit() 放入 try 块内，任何失败都 rollback 并向上抛出，
                # 保证 setting 更新与审计日志的原子性（符合审计 fail-safe 原则）。
                await self.db.commit()
            except Exception:
                await self.db.rollback()
                logger.exception(
                    "Failed to update warning setting and audit log for user %s; "
                    "transaction rolled back to maintain audit integrity",
                    user_id,
                )
                raise
        else:
            await self.db.commit()
        await self.db.refresh(setting)
        return setting
