"""GDPR 合规服务 (v1.27 P1 任务 #11).

实现用户的"数据可携权"(导出) 与 "被遗忘权"(删除).

设计原则:
- 软删除优先: 用户的 PII 字段被脱敏而非物理删除，以保留审计链
- 匿名化: 用户名/邮箱/手机号/紧急联系人等替换为占位符
- 关键业务数据保留: 风险评估/预警/危机事件保留(用于法律合规与系统安全)
- 完整审计: 每次 GDPR 操作写入 OperationLog
- 二次确认: 删除操作要求用户重新输入密码

安全注意:
- 导出数据不能明文存储 (临时文件, 下载后 24h 自动清理)
- 删除操作需管理员复核 (大操作, 防误删)
"""

from __future__ import annotations

import json
import logging
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pii_crypto import (
    ENCRYPTED_PREFIX,
    decrypt_field,
    mask_pii,
)
from app.core.security import verify_password
from app.models.admin import OperationLog
from app.models.assessment import (
    DataDraft,
    PhysiologicalRecord,
    StructuredAssessment,
    TextEntry,
)
from app.models.counselor import ConsultationRecord
from app.models.intervention import InterventionPlan, InterventionTask, TaskExecution
from app.models.review import CrisisEvent
from app.models.risk import RiskAssessment, WarningNotification
from app.models.user import EmergencyContact, User, UserCounselorBinding, UserProfile

logger = logging.getLogger(__name__)

# 匿名化占位符
ANON_USERNAME_PREFIX = "anon_"
ANON_EMAIL_DOMAIN = "@deleted.local"
ANON_PHONE = "00000000000"
ANON_NAME = "[已删除]"
# C-Svc-8 修复：自由文本字段匿名化占位符（NOT NULL 字段必须用占位符，不能置 None）
ANON_TEXT = "[ANONYMIZED]"

# 关键保留期 (天) - 用于合规审计的最低保留
LEGAL_RETENTION_DAYS = 365 * 3  # 3年 (符合医疗数据一般要求)


class GDPRService:
    """GDPR 数据导出与删除服务."""

    def __init__(self, db: AsyncSession) -> None:
        self.db = db

    # ── 数据导出 (Article 20 - Data Portability) ──────────────────────

    async def export_user_data(self, user_id: int) -> dict[str, Any]:
        """导出用户的所有个人数据 (机器可读 JSON).

        保留此方法用于小数据量场景或单测。生产环境优先使用流式方法（fetch_user_account + iter_*）。

        Returns:
            包含所有用户相关表的数据字典
        """
        user = await self.db.get(User, user_id)
        if not user:
            raise ValueError("用户不存在")

        # 1. 基础信息
        profile = (
            await self.db.execute(
                select(UserProfile).where(UserProfile.user_id == user_id)
            )
        ).scalar_one_or_none()

        # 2. 紧急联系人
        contacts = (
            (
                await self.db.execute(
                    select(EmergencyContact).where(EmergencyContact.user_id == user_id)
                )
            )
            .scalars()
            .all()
        )

        # 3. 咨询师绑定
        bindings = (
            (
                await self.db.execute(
                    select(UserCounselorBinding).where(
                        UserCounselorBinding.user_id == user_id
                    )
                )
            )
            .scalars()
            .all()
        )

        # 4. 风险评估
        risk_assessments = (
            (
                await self.db.execute(
                    select(RiskAssessment).where(RiskAssessment.user_id == user_id)
                )
            )
            .scalars()
            .all()
        )

        # 5. 预警记录
        warnings = (
            (
                await self.db.execute(
                    select(WarningNotification).where(
                        WarningNotification.user_id == user_id
                    )
                )
            )
            .scalars()
            .all()
        )

        # 6. 危机事件
        crisis_events = (
            (
                await self.db.execute(
                    select(CrisisEvent).where(CrisisEvent.user_id == user_id)
                )
            )
            .scalars()
            .all()
        )

        # 7. 干预计划
        plans = (
            (
                await self.db.execute(
                    select(InterventionPlan).where(InterventionPlan.user_id == user_id)
                )
            )
            .scalars()
            .all()
        )

        plan_ids = [p.id for p in plans]
        tasks: list[Any] = []
        if plan_ids:
            tasks = (
                (
                    await self.db.execute(
                        select(InterventionTask).where(
                            InterventionTask.plan_id.in_(plan_ids)
                        )
                    )
                )
                .scalars()
                .all()
            )

        # 8. 操作日志 (该用户的)
        op_logs = (
            (
                await self.db.execute(
                    select(OperationLog).where(OperationLog.operator_id == user_id)
                )
            )
            .scalars()
            .all()
        )

        return {
            "export_metadata": {
                "export_id": str(uuid.uuid4()),
                "exported_at": datetime.now(timezone.utc).isoformat(),
                "user_id": user_id,
                "gdpr_articles": ["Article 15 (Access)", "Article 20 (Portability)"],
                "format_version": "1.0",
            },
            "account": {
                "username": _safe_decrypt(user.username, "username"),
                "email": _safe_decrypt(user.email, "email"),
                "phone": _safe_decrypt(user.phone, "phone"),
                "role": user.role,
                "status": user.status,
                "created_at": user.created_at.isoformat() if user.created_at else None,
                "last_login_at": (
                    user.last_login_at.isoformat() if user.last_login_at else None
                ),
            },
            "profile": _profile_to_dict(profile) if profile else None,
            "emergency_contacts": [_contact_to_dict(c) for c in contacts],
            "counselor_bindings": [_binding_to_dict(b) for b in bindings],
            "risk_assessments": [_risk_to_dict(r) for r in risk_assessments],
            "warnings": [_warning_to_dict(w) for w in warnings],
            "crisis_events": [_crisis_to_dict(c) for c in crisis_events],
            "intervention_plans": [_plan_to_dict(p) for p in plans],
            "intervention_tasks": [_task_to_dict(t) for t in tasks],
            "operation_logs": [_log_to_dict(o) for o in op_logs],
            "summary": {
                "risk_assessments_count": len(risk_assessments),
                "warnings_count": len(warnings),
                "crisis_events_count": len(crisis_events),
                "intervention_plans_count": len(plans),
                "operation_logs_count": len(op_logs),
            },
        }

    # ── M-4 修复：流式导出方法 ──────────────────────────────────────────
    # M-Svc-4 TODO：以下 iter_* 方法均使用 OFFSET 分页，深翻页时性能下降
    # （OFFSET N 需扫描 N+batch_size 行）。后续应改为 keyset pagination：
    # 基于 (created_at, id) 游标，where (created_at, id) > (last_created_at, last_id)
    # 配合 order_by(created_at.asc(), id.asc()) 实现稳定且高性能的分页。
    # 当前保留 OFFSET 方案，因单用户数据量通常有限（GDPR 导出为低频操作）。

    async def fetch_user_account(self, user_id: int) -> dict[str, Any]:
        """拉取用户账户基础信息（小数据，一次性获取）.

        Raises:
            ValueError: 用户不存在
        """
        user = await self.db.get(User, user_id)
        if not user:
            raise ValueError("用户不存在")
        return {
            "username": _safe_decrypt(user.username, "username"),
            "email": _safe_decrypt(user.email, "email"),
            "phone": _safe_decrypt(user.phone, "phone"),
            "role": user.role,
            "status": user.status,
            "created_at": user.created_at.isoformat() if user.created_at else None,
            "last_login_at": (
                user.last_login_at.isoformat() if user.last_login_at else None
            ),
        }

    async def fetch_profile(self, user_id: int) -> dict[str, Any] | None:
        """拉取用户档案（单条）。"""
        profile = (
            await self.db.execute(
                select(UserProfile).where(UserProfile.user_id == user_id)
            )
        ).scalar_one_or_none()
        return _profile_to_dict(profile) if profile else None

    async def iter_emergency_contacts(self, user_id: int, batch_size: int = 200):
        """流式输出紧急联系人。"""
        offset = 0
        while True:
            rows = (
                (
                    await self.db.execute(
                        select(EmergencyContact)
                        .where(EmergencyContact.user_id == user_id)
                        .offset(offset)
                        .limit(batch_size)
                    )
                )
                .scalars()
                .all()
            )
            if not rows:
                break
            for c in rows:
                yield json.dumps(_contact_to_dict(c), ensure_ascii=False, default=str)
            offset += batch_size

    async def iter_counselor_bindings(self, user_id: int, batch_size: int = 200):
        """流式输出咨询师绑定。"""
        offset = 0
        while True:
            rows = (
                (
                    await self.db.execute(
                        select(UserCounselorBinding)
                        .where(UserCounselorBinding.user_id == user_id)
                        .offset(offset)
                        .limit(batch_size)
                    )
                )
                .scalars()
                .all()
            )
            if not rows:
                break
            for b in rows:
                yield json.dumps(_binding_to_dict(b), ensure_ascii=False, default=str)
            offset += batch_size

    async def iter_risk_assessments(self, user_id: int, batch_size: int = 200):
        """流式输出风险评估。"""
        offset = 0
        while True:
            rows = (
                (
                    await self.db.execute(
                        select(RiskAssessment)
                        .where(RiskAssessment.user_id == user_id)
                        .offset(offset)
                        .limit(batch_size)
                    )
                )
                .scalars()
                .all()
            )
            if not rows:
                break
            for r in rows:
                yield json.dumps(_risk_to_dict(r), ensure_ascii=False, default=str)
            offset += batch_size

    async def iter_warnings(self, user_id: int, batch_size: int = 200):
        """流式输出预警记录。"""
        offset = 0
        while True:
            rows = (
                (
                    await self.db.execute(
                        select(WarningNotification)
                        .where(WarningNotification.user_id == user_id)
                        .offset(offset)
                        .limit(batch_size)
                    )
                )
                .scalars()
                .all()
            )
            if not rows:
                break
            for w in rows:
                yield json.dumps(_warning_to_dict(w), ensure_ascii=False, default=str)
            offset += batch_size

    async def iter_crisis_events(self, user_id: int, batch_size: int = 200):
        """流式输出危机事件。"""
        offset = 0
        while True:
            rows = (
                (
                    await self.db.execute(
                        select(CrisisEvent)
                        .where(CrisisEvent.user_id == user_id)
                        .offset(offset)
                        .limit(batch_size)
                    )
                )
                .scalars()
                .all()
            )
            if not rows:
                break
            for c in rows:
                yield json.dumps(_crisis_to_dict(c), ensure_ascii=False, default=str)
            offset += batch_size

    async def iter_intervention_plans(self, user_id: int, batch_size: int = 200):
        """流式输出干预计划。"""
        offset = 0
        while True:
            rows = (
                (
                    await self.db.execute(
                        select(InterventionPlan)
                        .where(InterventionPlan.user_id == user_id)
                        .offset(offset)
                        .limit(batch_size)
                    )
                )
                .scalars()
                .all()
            )
            if not rows:
                break
            for p in rows:
                yield json.dumps(_plan_to_dict(p), ensure_ascii=False, default=str)
            offset += batch_size

    async def iter_intervention_tasks(self, user_id: int, batch_size: int = 200):
        """流式输出干预任务（基于该用户的 plans 关联）。"""
        # 先获取该用户的所有 plan_ids（小集合）
        plan_ids_result = (
            (
                await self.db.execute(
                    select(InterventionPlan.id).where(
                        InterventionPlan.user_id == user_id
                    )
                )
            )
            .scalars()
            .all()
        )
        if not plan_ids_result:
            return
        offset = 0
        while True:
            rows = (
                (
                    await self.db.execute(
                        select(InterventionTask)
                        .where(InterventionTask.plan_id.in_(plan_ids_result))
                        .offset(offset)
                        .limit(batch_size)
                    )
                )
                .scalars()
                .all()
            )
            if not rows:
                break
            for t in rows:
                yield json.dumps(_task_to_dict(t), ensure_ascii=False, default=str)
            offset += batch_size

    async def iter_operation_logs(self, user_id: int, batch_size: int = 200):
        """流式输出操作日志（大数据量，重点分批）。"""
        offset = 0
        while True:
            rows = (
                (
                    await self.db.execute(
                        select(OperationLog)
                        .where(OperationLog.operator_id == user_id)
                        .offset(offset)
                        .limit(batch_size)
                    )
                )
                .scalars()
                .all()
            )
            if not rows:
                break
            for o in rows:
                yield json.dumps(_log_to_dict(o), ensure_ascii=False, default=str)
            offset += batch_size

    # ── 被遗忘权 (Article 17 - Right to Erasure) ─────────────────────

    async def anonymize_user(
        self,
        user_id: int,
        *,
        password_confirm: str | None = None,
        keep_legal_records: bool = True,
    ) -> dict[str, Any]:
        """匿名化用户数据 (软删除).

        流程:
        1. 验证密码（防止 CSRF/误操作）；若 password_confirm=None 表示管理员越权操作，跳过密码校验
        2. 匿名化 User 核心字段 (username/email/phone)
        3. 软删除 UserProfile (设置 status='deleted' 但保留行)
        4. 匿名化 EmergencyContact
        5. 软删除关联关系 (UserCounselorBinding)
        6. 保留风险评估/危机事件 (用于合规审计)
        7. User.status = 'deleted' (无法登录)
        8. 撤销所有 refresh token session
        9. 写 OperationLog 记录本次删除

        Args:
            user_id: 目标用户 ID
            password_confirm: 用户当前密码（用于二次确认）；None 表示管理员越权路径（ISS-074）
            keep_legal_records: 是否保留合规审计数据（默认 True）

        Returns:
            摘要信息 (删除时间, 受影响行数)
        """
        user = await self.db.get(User, user_id)
        if not user:
            raise ValueError("用户不存在")
        if user.status == "deleted":
            raise ValueError("用户已被删除")

        # 1. 密码验证（管理员越权路径跳过）
        if password_confirm is not None:
            if not verify_password(password_confirm, user.password_hash):
                raise ValueError("密码错误，无法执行删除操作")

        original_email = _safe_decrypt(user.email, "email")
        anonymized_at = datetime.now(timezone.utc).replace(tzinfo=None)

        # 2. 匿名化 User
        anon_id = ANON_USERNAME_PREFIX + str(user_id) + "_" + uuid.uuid4().hex[:8]
        user.username = anon_id
        anon_email = anon_id + ANON_EMAIL_DOMAIN
        user.email = anon_email
        # PII 加密：同步更新 email_hash 盲索引
        from app.core.pii_crypto import compute_blind_index

        user.email_hash = compute_blind_index(anon_email, "email")
        user.phone = None
        # L-修复：使用随机密码生成有效 bcrypt 哈希，避免伪造格式导致 verify_password 抛异常
        from app.core.security import get_password_hash

        user.password_hash = get_password_hash(secrets.token_urlsafe(32))
        user.status = "deleted"
        user.avatar_url = None
        # 保留 created_at / last_login_at 以满足合规要求

        # 3. 匿名化 UserProfile
        profile = (
            await self.db.execute(
                select(UserProfile).where(UserProfile.user_id == user_id)
            )
        ).scalar_one_or_none()
        if profile:
            profile.nickname = ANON_NAME
            # 保留 gender/age/setting 字段用于统计

        # 4. 匿名化 EmergencyContact
        contacts = (
            (
                await self.db.execute(
                    select(EmergencyContact).where(EmergencyContact.user_id == user_id)
                )
            )
            .scalars()
            .all()
        )
        for contact in contacts:
            contact.name = ANON_NAME
            contact.phone = ANON_PHONE
            contact.relationship = ANON_NAME

        # C-Svc-8 修复：补充遗漏的 PII 表匿名化。
        # 原实现仅处理 User/UserProfile/EmergencyContact/UserCounselorBinding/
        # RefreshTokenSession/RiskAssessment，遗漏了 ConsultationRecord、
        # InterventionTask.description、TaskExecution.feedback_note、
        # CrisisEvent 自由文本、WarningNotification 自由文本、TextEntry.content、
        # DataDraft/StructuredAssessment/PhysiologicalRecord 的 data_payload 等，
        # 严重违反 GDPR Article 17。以下按表逐个匿名化自由文本字段，
        # 保留行用于合规审计；JSON 容器清空为 {} 避免泄露结构化 PII。
        pii_text_counts: dict[str, int] = {}

        # 4b. ConsultationRecord（咨询记录：notes/main_topics/client_status/interventions/next_plan）
        consultation_records = (
            (
                await self.db.execute(
                    select(ConsultationRecord).where(
                        ConsultationRecord.user_id == user_id
                    )
                )
            )
            .scalars()
            .all()
        )
        for rec in consultation_records:
            rec.main_topics = ANON_TEXT
            rec.client_status = ANON_TEXT
            rec.interventions = ANON_TEXT
            rec.next_plan = ANON_TEXT
            rec.notes = ANON_TEXT
        pii_text_counts["consultation_records"] = len(consultation_records)

        # 4c. InterventionTask.description（通过 user_id 关联 plan_id）
        task_desc_result = (
            (
                await self.db.execute(
                    select(InterventionTask)
                    .join(
                        InterventionPlan,
                        InterventionTask.plan_id == InterventionPlan.id,
                    )
                    .where(InterventionPlan.user_id == user_id)
                )
            )
            .scalars()
            .all()
        )
        for task in task_desc_result:
            if task.description is not None:
                task.description = ANON_TEXT
        pii_text_counts["intervention_tasks"] = len(task_desc_result)

        # 4d. TaskExecution.feedback_note
        task_executions = (
            (
                await self.db.execute(
                    select(TaskExecution).where(TaskExecution.user_id == user_id)
                )
            )
            .scalars()
            .all()
        )
        for exe in task_executions:
            if exe.feedback_note is not None:
                exe.feedback_note = ANON_TEXT
        pii_text_counts["task_executions"] = len(task_executions)

        # 4e. CrisisEvent（危机事件：crisis_keywords/input_summary/handled_action）
        crisis_events = (
            (
                await self.db.execute(
                    select(CrisisEvent).where(CrisisEvent.user_id == user_id)
                )
            )
            .scalars()
            .all()
        )
        for ev in crisis_events:
            # crisis_keywords 默认 "[]"，统一替换为 ANON_TEXT
            ev.crisis_keywords = ANON_TEXT
            if ev.input_summary is not None:
                ev.input_summary = ANON_TEXT
            if ev.handled_action is not None:
                ev.handled_action = ANON_TEXT
        pii_text_counts["crisis_events"] = len(crisis_events)

        # 4f. WarningNotification（trigger_reason NOT NULL，handle_note 可空）
        warnings = (
            (
                await self.db.execute(
                    select(WarningNotification).where(
                        WarningNotification.user_id == user_id
                    )
                )
            )
            .scalars()
            .all()
        )
        for w in warnings:
            # trigger_reason 为 NOT NULL，必须用占位符
            w.trigger_reason = ANON_TEXT
            if w.handle_note is not None:
                w.handle_note = ANON_TEXT
        pii_text_counts["warnings"] = len(warnings)

        # 4g. TextEntry（content NOT NULL，是 PII 密度最高的字段）
        text_entries = (
            (
                await self.db.execute(
                    select(TextEntry).where(TextEntry.user_id == user_id)
                )
            )
            .scalars()
            .all()
        )
        for te in text_entries:
            # content 为 NOT NULL，必须用占位符
            te.content = ANON_TEXT
            # emotion_tags JSON 清空
            te.emotion_tags = []
        pii_text_counts["text_entries"] = len(text_entries)

        # 4h. DataDraft / StructuredAssessment / PhysiologicalRecord 的 data_payload JSON
        data_drafts = (
            (
                await self.db.execute(
                    select(DataDraft).where(DataDraft.user_id == user_id)
                )
            )
            .scalars()
            .all()
        )
        for dd in data_drafts:
            dd.data_payload = {}
        pii_text_counts["data_drafts"] = len(data_drafts)

        structured_assessments = (
            (
                await self.db.execute(
                    select(StructuredAssessment).where(
                        StructuredAssessment.user_id == user_id
                    )
                )
            )
            .scalars()
            .all()
        )
        for sa in structured_assessments:
            sa.data_payload = {}
        pii_text_counts["structured_assessments"] = len(structured_assessments)

        physiological_records = (
            (
                await self.db.execute(
                    select(PhysiologicalRecord).where(
                        PhysiologicalRecord.user_id == user_id
                    )
                )
            )
            .scalars()
            .all()
        )
        # PhysiologicalRecord 的数值字段（sleep_hours 等）不构成直接 PII，
        # 仅清空 data_payload JSON 容器
        for pr in physiological_records:
            pr.data_payload = {}
        pii_text_counts["physiological_records"] = len(physiological_records)

        # 5. 软删除关联关系 (UserCounselorBinding) - M16 修复：补充遗漏的绑定关系处理
        from app.core.states import BindingStatus

        bindings = (
            (
                await self.db.execute(
                    select(UserCounselorBinding).where(
                        UserCounselorBinding.user_id == user_id,
                        UserCounselorBinding.status == BindingStatus.ACTIVE,
                    )
                )
            )
            .scalars()
            .all()
        )
        for binding in bindings:
            binding.status = BindingStatus.INACTIVE
            binding.unbound_at = anonymized_at

        # 6. 撤销所有 refresh token sessions
        from datetime import datetime as dt

        from app.models.auth import RefreshTokenSession

        sessions = (
            (
                await self.db.execute(
                    select(RefreshTokenSession).where(
                        RefreshTokenSession.user_id == user_id,
                        RefreshTokenSession.revoked_at.is_(None),
                    )
                )
            )
            .scalars()
            .all()
        )
        for s in sessions:
            s.revoked_at = dt.now(timezone.utc).replace(tzinfo=None)

        # 6b. 根据 keep_legal_records 决定是否删除风险评估记录
        risk_assessments_deleted = 0
        if not keep_legal_records:
            risk_assessments = (
                (
                    await self.db.execute(
                        select(RiskAssessment).where(RiskAssessment.user_id == user_id)
                    )
                )
                .scalars()
                .all()
            )
            for ra in risk_assessments:
                await self.db.delete(ra)
            risk_assessments_deleted = len(risk_assessments)

        # 6. 写 OperationLog (合规审计 - 必须保留)
        audit_log = OperationLog(
            operator_id=user_id,
            operator_role=user.role,
            action_type="gdpr.account.deleted",
            target_type="user",
            target_id=user_id,
            detail=json.dumps(
                {
                    "anonymized_at": anonymized_at.isoformat(),
                    "original_email_masked": mask_pii(original_email, keep_last=0),
                    "keep_legal_records": keep_legal_records,
                    "contacts_anonymized": len(contacts),
                    "sessions_revoked": len(sessions),
                    "risk_assessments_deleted": risk_assessments_deleted,
                    # C-Svc-8 修复：记录各 PII 表匿名化行数，便于合规审计追溯
                    "pii_text_anonymized": pii_text_counts,
                }
            ),
        )
        self.db.add(audit_log)

        await self.db.commit()

        return {
            "user_id": user_id,
            "anonymized_at": anonymized_at.isoformat(),
            "original_email_masked": mask_pii(original_email, keep_last=0),
            "contacts_anonymized": len(contacts),
            "sessions_revoked": len(sessions),
            "risk_assessments_deleted": risk_assessments_deleted,
            # C-Svc-8 修复：返回各 PII 表匿名化行数
            "pii_text_anonymized": pii_text_counts,
            "legal_records_retained": keep_legal_records,
            "warning": "账户已匿名化，无法恢复。PII 已被永久替换。",
        }


# ── 辅助函数 ─────────────────────────────────────────────────────────


def _safe_decrypt(value: str | None, field: str) -> str | None:
    """安全解密 (失败返回 mask)."""
    if not value:
        return value
    if value.startswith(ENCRYPTED_PREFIX):
        try:
            return decrypt_field(value, field)
        except ValueError:
            return "[DECRYPT_FAILED]"
    return value


def _profile_to_dict(p: UserProfile) -> dict:
    return {
        "nickname": p.nickname,
        "gender": p.gender,
        "age": p.age,
        "language": p.language,
        "theme": p.theme,
        "reminder_freq": p.reminder_freq,
    }


def _contact_to_dict(c: EmergencyContact) -> dict:
    return {
        "name": c.name,
        "relationship": c.relationship,
        "phone": c.phone,
    }


def _binding_to_dict(b: UserCounselorBinding) -> dict:
    return {
        "counselor_id": b.counselor_id,
        "status": b.status,
        # UserCounselorBinding 实际使用 bound_at 而非 created_at (v1.27 模型修正)
        "created_at": b.bound_at.isoformat() if b.bound_at else None,
    }


def _risk_to_dict(r: RiskAssessment) -> dict:
    return {
        "id": r.id,
        "assessment_type": r.assessment_type,
        "risk_level": r.risk_level,
        "risk_score": r.risk_score,
        "created_at": r.created_at.isoformat() if r.created_at else None,
    }


def _warning_to_dict(w: WarningNotification) -> dict:
    return {
        "id": w.id,
        "level": w.current_level,
        "previous_level": w.previous_level,
        "message": w.trigger_reason,
        "status": "handled" if w.is_handled else ("read" if w.is_read else "pending"),
        "is_read": w.is_read,
        "is_handled": w.is_handled,
        "handle_action": w.handle_action,
        "created_at": w.created_at.isoformat() if w.created_at else None,
    }


def _crisis_to_dict(c: CrisisEvent) -> dict:
    return {
        "id": c.id,
        "trigger_source": c.trigger_source,
        "crisis_score": c.crisis_score,
        "created_at": c.created_at.isoformat() if c.created_at else None,
    }


def _plan_to_dict(p: InterventionPlan) -> dict:
    return {
        "id": p.id,
        "status": p.status,
        "risk_level": p.risk_level,
        "created_at": p.created_at.isoformat() if p.created_at else None,
    }


def _task_to_dict(t: InterventionTask) -> dict:
    return {
        "id": t.id,
        "plan_id": t.plan_id,
        "task_name": t.task_name,
        "task_type": t.task_type,
        "description": t.description,
        "schedule": t.schedule,
        "duration_minutes": t.duration_minutes,
        "sort_order": t.sort_order,
        "created_at": t.created_at.isoformat() if t.created_at else None,
    }


def _log_to_dict(o: OperationLog) -> dict:
    return {
        "action": o.action_type,
        "resource_type": o.target_type,
        "resource_id": o.target_id,
        "created_at": o.created_at.isoformat() if o.created_at else None,
    }
