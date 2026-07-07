from __future__ import annotations

import logging
import secrets
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

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
from app.core.states import BindingStatus
from app.models.admin import OperationLog
from app.models.counselor import ClientGroup, ClientGroupMember, ConsultationRecord
from app.models.risk import RiskAssessment, WarningNotification
from app.models.user import User, UserCounselorBinding

logger = logging.getLogger(__name__)


class CounselorService:
    def __init__(self, db: AsyncSession) -> None:
        self.db = db

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

    async def list_my_users(
        self,
        counselor_id: int,
        page: int,
        page_size: int,
        risk_level: int | None = None,
    ) -> dict:
        offset = (page - 1) * page_size
        base_conditions = [
            UserCounselorBinding.counselor_id == counselor_id,
            UserCounselorBinding.status == BindingStatus.ACTIVE,
        ]

        # 按风险等级过滤：筛选最新风险评估匹配指定等级的用户
        if risk_level is not None:
            latest_risk_subq = (
                select(
                    RiskAssessment.user_id,
                    func.max(RiskAssessment.created_at).label("max_created_at"),
                )
                .group_by(RiskAssessment.user_id)
                .subquery()
            )
            matching_user_ids = (
                select(RiskAssessment.user_id)
                .join(
                    latest_risk_subq,
                    (RiskAssessment.user_id == latest_risk_subq.c.user_id)
                    & (RiskAssessment.created_at == latest_risk_subq.c.max_created_at),
                )
                .where(RiskAssessment.risk_level == risk_level)
                .scalar_subquery()
            )
            base_conditions.append(User.id.in_(matching_user_ids))

        stmt = (
            select(User)
            .join(UserCounselorBinding, UserCounselorBinding.user_id == User.id)
            .where(*base_conditions)
            .order_by(User.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        rows = (await self.db.execute(stmt)).scalars().all()

        count_stmt = (
            select(func.count(User.id))
            .join(UserCounselorBinding, UserCounselorBinding.user_id == User.id)
            .where(*base_conditions)
        )
        total = (await self.db.execute(count_stmt)).scalar_one()

        user_ids = [u.id for u in rows]
        risk_map: dict[int, RiskAssessment] = {}
        if user_ids:
            latest_risk_subq = (
                select(
                    RiskAssessment.user_id,
                    func.max(RiskAssessment.created_at).label("max_created_at"),
                )
                .where(RiskAssessment.user_id.in_(user_ids))
                .group_by(RiskAssessment.user_id)
                .subquery()
            )
            risk_stmt = select(RiskAssessment).join(
                latest_risk_subq,
                (RiskAssessment.user_id == latest_risk_subq.c.user_id)
                & (RiskAssessment.created_at == latest_risk_subq.c.max_created_at),
            )
            risk_rows = (await self.db.execute(risk_stmt)).scalars().all()
            risk_map = {r.user_id: r for r in risk_rows}

        items = [
            {
                "id": u.id,
                "username": u.username,
                "status": u.status,
                "latest_risk_level": (
                    risk_map[u.id].risk_level if u.id in risk_map else None
                ),
                "latest_risk_score": (
                    risk_map[u.id].risk_score if u.id in risk_map else None
                ),
                "latest_risk_label": (
                    normalize_risk_level(risk_map[u.id].risk_level)
                    if u.id in risk_map
                    else "none"
                ),
                "risk_level": risk_map[u.id].risk_level if u.id in risk_map else 0,
                "risk_score": risk_map[u.id].risk_score if u.id in risk_map else None,
            }
            for u in rows
        ]

        return {"items": items, "total": total, "page": page, "page_size": page_size}

    async def create_consultation_record(
        self, counselor_id: int, user_id: int, payload: dict
    ) -> int:
        binding_stmt = select(UserCounselorBinding).where(
            UserCounselorBinding.counselor_id == counselor_id,
            UserCounselorBinding.user_id == user_id,
            UserCounselorBinding.status == BindingStatus.ACTIVE,
        )
        binding = (await self.db.execute(binding_stmt)).scalar_one_or_none()
        if binding is None:
            raise ValueError("当前用户未绑定到该咨询师")

        warning_id = payload.get("warning_id")
        if warning_id is not None:
            warning = await self.db.get(WarningNotification, warning_id)
            if (
                warning is None
                or warning.user_id != user_id
                or warning.counselor_id != counselor_id
            ):
                raise ValueError("预警不存在或不属于当前咨询师用户关系")

        record = ConsultationRecord(
            counselor_id=counselor_id,
            user_id=user_id,
            warning_id=warning_id,
            main_topics=payload.get("main_topics"),
            client_status=payload.get("client_status"),
            interventions=payload.get("interventions"),
            next_plan=payload.get("next_plan"),
            notes=payload.get("notes"),
        )
        self.db.add(record)
        await self.db.flush()
        self.db.add(
            OperationLog(
                operator_id=counselor_id,
                operator_role="counselor",
                action_type="create_consultation_record",
                target_type="consultation_record",
                target_id=record.id,
                detail=f"user_id={user_id};warning_id={warning_id or '-'}",
            )
        )
        await self.db.commit()
        await self.db.refresh(record)
        return record.id

    async def update_consultation_record(
        self, counselor_id: int, user_id: int, record_id: int, payload: dict
    ) -> bool:
        record = await self.db.get(ConsultationRecord, record_id)
        if (
            record is None
            or record.counselor_id != counselor_id
            or record.user_id != user_id
        ):
            return False
        if "warning_id" in payload and payload.get("warning_id") != record.warning_id:
            warning_id = payload.get("warning_id")
            if warning_id is not None:
                warning = await self.db.get(WarningNotification, warning_id)
                if (
                    warning is None
                    or warning.user_id != record.user_id
                    or warning.counselor_id != counselor_id
                ):
                    raise ValueError("预警不存在或不属于当前咨询师用户关系")
            record.warning_id = warning_id
        for field in (
            "main_topics",
            "client_status",
            "interventions",
            "next_plan",
            "notes",
        ):
            if field in payload:
                setattr(record, field, payload[field])
        self.db.add(
            OperationLog(
                operator_id=counselor_id,
                operator_role="counselor",
                action_type="update_consultation_record",
                target_type="consultation_record",
                target_id=record.id,
                detail=f"user_id={record.user_id}",
            )
        )
        await self.db.commit()
        return True

    async def get_user_detail(self, counselor_id: int, user_id: int) -> dict | None:
        binding_stmt = select(UserCounselorBinding).where(
            UserCounselorBinding.counselor_id == counselor_id,
            UserCounselorBinding.user_id == user_id,
            UserCounselorBinding.status == BindingStatus.ACTIVE,
        )
        binding = (await self.db.execute(binding_stmt)).scalar_one_or_none()
        if not binding:
            return None
        user = await self.db.get(User, user_id)
        if not user:
            return None
        latest_risk_stmt = (
            select(RiskAssessment)
            .where(RiskAssessment.user_id == user_id)
            .order_by(RiskAssessment.created_at.desc())
            .limit(1)
        )
        latest_risk = (await self.db.execute(latest_risk_stmt)).scalar_one_or_none()
        return {
            "id": user.id,
            "username": user.username,
            "nickname": getattr(user, "nickname", None),
            # 修复：咨询师不需要用户 email（PII 越权暴露），仅管理员可获取
            "status": user.status,
            "latest_risk_level": latest_risk.risk_level if latest_risk else None,
            "latest_risk_score": latest_risk.risk_score if latest_risk else None,
            "latest_risk_label": (
                normalize_risk_level(latest_risk.risk_level) if latest_risk else "none"
            ),
            "risk_level": latest_risk.risk_level if latest_risk else 0,
            "risk_score": latest_risk.risk_score if latest_risk else None,
        }

    async def list_consultation_records(
        self, counselor_id: int, user_id: int, page: int, page_size: int
    ) -> dict:
        offset = (page - 1) * page_size
        stmt = (
            select(ConsultationRecord)
            .where(
                ConsultationRecord.counselor_id == counselor_id,
                ConsultationRecord.user_id == user_id,
            )
            .order_by(ConsultationRecord.created_at.desc())
            .offset(offset)
            .limit(page_size)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        count_stmt = (
            select(func.count())
            .select_from(ConsultationRecord)
            .where(
                ConsultationRecord.counselor_id == counselor_id,
                ConsultationRecord.user_id == user_id,
            )
        )
        total = (await self.db.execute(count_stmt)).scalar_one()

        warning_ids = [r.warning_id for r in rows if r.warning_id is not None]
        warning_map: dict[int, WarningNotification] = {}
        if warning_ids:
            warning_rows = (
                (
                    await self.db.execute(
                        select(WarningNotification).where(
                            WarningNotification.id.in_(warning_ids)
                        )
                    )
                )
                .scalars()
                .all()
            )
            warning_map = {w.id: w for w in warning_rows}

        return {
            "items": [
                {
                    "id": r.id,
                    "warning_id": r.warning_id,
                    "warning_status": (
                        resolve_warning_status(
                            warning_map[r.warning_id].is_handled,
                            warning_map[r.warning_id].handle_action,
                        )
                        if r.warning_id in warning_map
                        else None
                    ),
                    "warning_risk_level": (
                        normalize_risk_level(warning_map[r.warning_id].current_level)
                        if r.warning_id in warning_map
                        else None
                    ),
                    "main_topics": r.main_topics,
                    "client_status": r.client_status,
                    "interventions": r.interventions,
                    "next_plan": r.next_plan,
                    "notes": r.notes,
                    "created_at": r.created_at.isoformat(),
                }
                for r in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def create_group(
        self,
        counselor_id: int,
        group_name: str,
        description: str | None,
        color_tag: str,
    ) -> int:
        group = ClientGroup(
            counselor_id=counselor_id,
            group_name=group_name,
            description=description,
            color_tag=color_tag,
        )
        self.db.add(group)
        await self.db.flush()
        self.db.add(
            OperationLog(
                operator_id=counselor_id,
                operator_role="counselor",
                action_type="create_client_group",
                target_type="client_group",
                target_id=group.id,
                detail=f"group_name={group_name}",
            )
        )
        await self.db.commit()
        await self.db.refresh(group)
        return group.id

    async def list_groups(self, counselor_id: int, page: int, page_size: int) -> dict:
        offset = (page - 1) * page_size
        stmt = (
            select(ClientGroup)
            .where(ClientGroup.counselor_id == counselor_id)
            .order_by(ClientGroup.id.desc())
            .offset(offset)
            .limit(page_size)
        )
        rows = (await self.db.execute(stmt)).scalars().all()
        total = (
            await self.db.execute(
                select(func.count())
                .select_from(ClientGroup)
                .where(ClientGroup.counselor_id == counselor_id)
            )
        ).scalar_one()

        # M13 修复：用一次聚合查询替代循环内逐条 COUNT，消除 N+1
        group_ids = [g.id for g in rows]
        count_map: dict[int, int] = {}
        if group_ids:
            count_rows = (
                await self.db.execute(
                    select(ClientGroupMember.group_id, func.count())
                    .where(ClientGroupMember.group_id.in_(group_ids))
                    .group_by(ClientGroupMember.group_id)
                )
            ).all()
            count_map = {row[0]: int(row[1]) for row in count_rows}

        return {
            "items": [
                {
                    "id": g.id,
                    "group_name": g.group_name,
                    "description": g.description,
                    "color_tag": g.color_tag,
                    "user_count": count_map.get(g.id, 0),
                }
                for g in rows
            ],
            "total": total,
            "page": page,
            "page_size": page_size,
        }

    async def add_group_member(
        self, counselor_id: int, group_id: int, user_id: int
    ) -> bool:
        group = await self.db.get(ClientGroup, group_id)
        if group is None or group.counselor_id != counselor_id:
            return False

        # M9 修复（IDOR）：校验被添加的用户是否与该咨询师有活跃绑定关系
        # 防止咨询师将任意用户 ID 添加到自己的分组
        binding_stmt = select(UserCounselorBinding).where(
            UserCounselorBinding.counselor_id == counselor_id,
            UserCounselorBinding.user_id == user_id,
            UserCounselorBinding.status == BindingStatus.ACTIVE,
        )
        binding = (await self.db.execute(binding_stmt)).scalar_one_or_none()
        if binding is None:
            # 用户未与该咨询师建立绑定关系，拒绝添加
            return False

        existing_stmt = select(ClientGroupMember).where(
            ClientGroupMember.group_id == group_id,
            ClientGroupMember.user_id == user_id,
        )
        existing = (await self.db.execute(existing_stmt)).scalar_one_or_none()
        if existing is not None:
            return True

        self.db.add(ClientGroupMember(group_id=group_id, user_id=user_id))
        try:
            await self.db.flush()
        except IntegrityError:
            await self.db.rollback()
            return True

        self.db.add(
            OperationLog(
                operator_id=counselor_id,
                operator_role="counselor",
                action_type="add_group_member",
                target_type="client_group_member",
                target_id=None,
                detail=f"group_id={group_id},user_id={user_id};status=added",
            )
        )
        await self.db.commit()
        return True

    async def _generate_unique_bind_code(self) -> str:
        code = self._generate_bind_code()
        for _ in range(20):
            dup_stmt = select(UserCounselorBinding).where(
                UserCounselorBinding.bind_code == code
            )
            if not (await self.db.execute(dup_stmt)).scalar_one_or_none():
                return code
            code = self._generate_bind_code()
        raise ValueError("绑定码生成失败，请稍后重试")

    async def get_or_create_bind_code(self, counselor_id: int) -> str:
        stmt = (
            select(UserCounselorBinding)
            .where(
                UserCounselorBinding.counselor_id == counselor_id,
                UserCounselorBinding.user_id == counselor_id,
                UserCounselorBinding.status == BindingStatus.PLACEHOLDER,
            )
            .order_by(UserCounselorBinding.id.desc())
        )
        existing = (await self.db.execute(stmt)).scalars().first()
        if existing and existing.bind_code:
            return existing.bind_code

        code = await self._generate_unique_bind_code()

        if not existing:
            binding = UserCounselorBinding(
                counselor_id=counselor_id,
                user_id=counselor_id,
                bind_code=code,
                status=BindingStatus.PLACEHOLDER,
            )
            if hasattr(binding, "bound_at"):
                binding.bound_at = None
            if hasattr(binding, "unbound_at"):
                binding.unbound_at = None
            self.db.add(binding)
            self.db.add(
                OperationLog(
                    operator_id=counselor_id,
                    operator_role="counselor",
                    action_type="create_bind_code",
                    target_type="user_counselor_binding",
                    target_id=None,
                    detail=f"status=placeholder;bind_code={code}",
                )
            )
        else:
            existing.bind_code = code
            if existing.status not in {BindingStatus.ACTIVE, BindingStatus.PLACEHOLDER}:
                existing.status = BindingStatus.PLACEHOLDER
            self.db.add(
                OperationLog(
                    operator_id=counselor_id,
                    operator_role="counselor",
                    action_type="refresh_bind_code",
                    target_type="user_counselor_binding",
                    target_id=existing.id,
                    detail=f"status={existing.status};bind_code={code}",
                )
            )
        await self.db.commit()
        return code

    async def refresh_bind_code(self, counselor_id: int) -> str:
        """M7 修复：真正刷新绑定码 - 作废当前 bind_code 并生成新码.

        与 get_or_create_bind_code 的区别:
        - get_or_create: 幂等，若已有 bind_code 则直接返回
        - refresh: 强制作废当前 bind_code，生成新码并持久化
        """
        stmt = (
            select(UserCounselorBinding)
            .where(
                UserCounselorBinding.counselor_id == counselor_id,
                UserCounselorBinding.user_id == counselor_id,
                UserCounselorBinding.status == BindingStatus.PLACEHOLDER,
            )
            .order_by(UserCounselorBinding.id.desc())
        )
        existing = (await self.db.execute(stmt)).scalars().first()

        # 生成新码（_generate_unique_bind_code 会确保唯一性）
        new_code = await self._generate_unique_bind_code()

        if existing is None:
            # 无占位绑定，创建新的
            binding = UserCounselorBinding(
                counselor_id=counselor_id,
                user_id=counselor_id,
                bind_code=new_code,
                status=BindingStatus.PLACEHOLDER,
            )
            if hasattr(binding, "bound_at"):
                binding.bound_at = None
            if hasattr(binding, "unbound_at"):
                binding.unbound_at = None
            self.db.add(binding)
            self.db.add(
                OperationLog(
                    operator_id=counselor_id,
                    operator_role="counselor",
                    action_type="create_bind_code",
                    target_type="user_counselor_binding",
                    target_id=None,
                    detail=f"status=placeholder;bind_code={new_code};trigger=refresh",
                )
            )
        else:
            # 作废旧码：将旧 bind_code 标记为失效（设为 None 防止重复使用）
            old_code = existing.bind_code
            existing.bind_code = new_code
            if existing.status not in {BindingStatus.ACTIVE, BindingStatus.PLACEHOLDER}:
                existing.status = BindingStatus.PLACEHOLDER
            self.db.add(
                OperationLog(
                    operator_id=counselor_id,
                    operator_role="counselor",
                    action_type="refresh_bind_code",
                    target_type="user_counselor_binding",
                    target_id=existing.id,
                    detail=f"old_bind_code={old_code};new_bind_code={new_code};status={existing.status}",
                )
            )
        await self.db.commit()
        return new_code

    @staticmethod
    def _generate_bind_code() -> str:
        # L-Svc-2 修复：原 token_urlsafe(6)[:8] 仅约 48 bits 熵，抗穷举强度不足。
        # 增加输入字节数与输出长度至 bind_code CHECK 约束上限（10 字符），提升熵。
        return secrets.token_urlsafe(10)[:10].upper()

    async def bind_by_code(self, user_id: int, bind_code: str) -> dict:
        # C-Svc-3 修复：bind_code SELECT 加 with_for_update()，避免 TOCTOU 竞态。
        # 原实现仅锁定 user 行，未锁定 binding 行；当 bind_code 被并发使用时
        # （如同一咨询师给多个用户发放相同绑定码、或绑定码泄露后被并发消费），
        # 两个事务都能通过 binding.status IN (ACTIVE, PLACEHOLDER) 校验，
        # 都进入更新分支，造成绑定码被重复消费、placeholder 被多次激活等问题。
        # 加 FOR UPDATE 后，并发请求会串行化在 binding 行锁上；先获取锁的事务
        # 提交后，后获取锁的事务会读到最新 status，WHERE 子句中
        # status IN (ACTIVE, PLACEHOLDER) 不再匹配（已变为 INACTIVE），
        # scalar_one_or_none() 返回 None，触发“绑定码无效或已过期”错误。
        stmt = (
            select(UserCounselorBinding)
            .where(
                UserCounselorBinding.bind_code == bind_code,
                UserCounselorBinding.status.in_(
                    [BindingStatus.ACTIVE, BindingStatus.PLACEHOLDER]
                ),
            )
            .with_for_update()
        )
        binding = (await self.db.execute(stmt)).scalar_one_or_none()
        if binding is None:
            raise ValueError("绑定码无效或已过期")
        counselor_id = binding.counselor_id

        # H-01 修复：锁定用户行防止并发绑定（TOCTOU 竞态）
        user_lock = select(User).where(User.id == user_id).with_for_update()
        await self.db.execute(user_lock)

        active_stmt = (
            select(UserCounselorBinding)
            .where(
                UserCounselorBinding.user_id == user_id,
                UserCounselorBinding.status == BindingStatus.ACTIVE,
                UserCounselorBinding.counselor_id != user_id,
            )
            .order_by(UserCounselorBinding.bound_at.desc())
            .limit(1)
        )
        active_binding = (await self.db.execute(active_stmt)).scalars().first()
        if active_binding:
            if active_binding.counselor_id == counselor_id:
                raise ValueError("您已绑定该咨询师，无需重复绑定")
            raise ValueError("您已绑定其他咨询师，请先解绑后再绑定新咨询师")

        counselor = await self.db.get(User, counselor_id)
        if (
            not counselor
            or counselor.role != "counselor"
            or counselor.status != "active"
        ):
            raise ValueError("绑定的咨询师不存在或已停用")

        previous_status = binding.status
        if binding.status == BindingStatus.PLACEHOLDER:
            # M21 修复：修改 placeholder 的 user_id 可能违反 UniqueConstraint("user_id", "counselor_id")。
            # 先查询是否存在该 (user_id, counselor_id) 的历史 binding，若有则激活它而非修改 placeholder。
            existing_stmt = select(UserCounselorBinding).where(
                UserCounselorBinding.user_id == user_id,
                UserCounselorBinding.counselor_id == counselor_id,
            )
            existing_binding = (
                await self.db.execute(existing_stmt)
            ).scalar_one_or_none()
            if existing_binding is not None and existing_binding.id != binding.id:
                # 已存在历史 binding，激活它并将 placeholder 标记为已使用
                existing_binding.status = BindingStatus.ACTIVE
                existing_binding.bound_at = datetime.now(UTC).replace(tzinfo=None)
                if hasattr(existing_binding, "unbound_at"):
                    existing_binding.unbound_at = None
                # C-02 修复：bind_code 为 NOT NULL 且有 CHECK 约束(4-10 字符)，不能设为 None
                binding.bind_code = self._generate_bind_code()
                binding.status = BindingStatus.INACTIVE
                await self.db.flush()
                new_binding = existing_binding
            else:
                binding.user_id = user_id
                binding.status = BindingStatus.ACTIVE
                binding.bound_at = datetime.now(UTC).replace(tzinfo=None)
                if hasattr(binding, "unbound_at"):
                    binding.unbound_at = None
                await self.db.flush()
                new_binding = binding
        else:
            # 原 binding 已是 ACTIVE 状态：生成新占位码防止重复使用
            # C-02 修复：bind_code 为 NOT NULL 且有 CHECK 约束，不能设为 None
            binding.bind_code = self._generate_bind_code()
            new_binding = UserCounselorBinding(
                user_id=user_id,
                counselor_id=counselor_id,
                bind_code=self._generate_bind_code(),  # ACTIVE 绑定也需满足 NOT NULL 约束
                status=BindingStatus.ACTIVE,
            )
            self.db.add(new_binding)
            await self.db.flush()

        self.db.add(
            OperationLog(
                operator_id=user_id,
                operator_role="user",
                action_type="bind_counselor",
                target_type="user_counselor_binding",
                target_id=new_binding.id,
                detail=f"counselor_id={counselor_id};bind_code={bind_code};from_status={previous_status};to_status=active",
            )
        )
        await self.db.commit()
        await self.db.refresh(new_binding)

        counselor_profile_stmt = select(User).where(User.id == counselor_id)
        counselor_user = (
            await self.db.execute(counselor_profile_stmt)
        ).scalar_one_or_none()

        return {
            "binding_id": new_binding.id,
            "counselor_id": counselor_id,
            "counselor_name": (
                counselor_user.username if counselor_user else f"咨询师#{counselor_id}"
            ),
            "status": (
                new_binding.status.value
                if hasattr(new_binding.status, "value")
                else new_binding.status
            ),
            "bind_code_status": (
                new_binding.status.value
                if hasattr(new_binding.status, "value")
                else new_binding.status
            ),
            "bound_at": new_binding.bound_at.isoformat(),
        }

    async def get_user_binding(self, user_id: int) -> dict | None:
        stmt = (
            select(UserCounselorBinding)
            .where(
                UserCounselorBinding.user_id == user_id,
                UserCounselorBinding.status == BindingStatus.ACTIVE,
                UserCounselorBinding.counselor_id != user_id,
            )
            .order_by(UserCounselorBinding.bound_at.desc())
            .limit(1)
        )
        binding = (await self.db.execute(stmt)).scalars().first()
        if not binding:
            return None

        counselor = await self.db.get(User, binding.counselor_id)
        status_value = (
            binding.status.value if hasattr(binding.status, "value") else binding.status
        )
        return {
            "binding_id": binding.id,
            "counselor_id": binding.counselor_id,
            "counselor_name": (
                counselor.username if counselor else f"咨询师#{binding.counselor_id}"
            ),
            "bound_at": binding.bound_at.isoformat() if binding.bound_at else None,
            "status": status_value,
            "bind_code_status": status_value,
        }

    async def unbind(self, user_id: int) -> bool:
        stmt = (
            select(UserCounselorBinding)
            .where(
                UserCounselorBinding.user_id == user_id,
                UserCounselorBinding.status == BindingStatus.ACTIVE,
                UserCounselorBinding.counselor_id != user_id,
            )
            .order_by(UserCounselorBinding.bound_at.desc())
            .limit(1)
        )
        binding = (await self.db.execute(stmt)).scalars().first()
        if not binding:
            return False

        binding.status = BindingStatus.INACTIVE
        binding.unbound_at = datetime.now(UTC).replace(tzinfo=None)
        self.db.add(
            OperationLog(
                operator_id=user_id,
                operator_role="user",
                action_type="unbind_counselor",
                target_type="user_counselor_binding",
                target_id=binding.id,
                detail=f"counselor_id={binding.counselor_id};to_status=inactive",
            )
        )
        await self.db.commit()
        return True
