"""GDPR 数据匿名化/删除 Mixin.

实现用户的"被遗忘权"(Article 17 - Right to Erasure).

包含:
- anonymize_user: 完整匿名化流程 (密码验证 / 字段脱敏 / 关系清理 / OperationLog)

设计原则:
- 软删除优先: 用户的 PII 字段被脱敏而非物理删除，以保留审计链
- 匿名化: 用户名/邮箱/手机号/紧急联系人等替换为占位符
- 关键业务数据保留: 风险评估/预警/危机事件保留(用于法律合规与系统安全)
- 完整审计: 每次 GDPR 操作写入 OperationLog
- 二次确认: 删除操作要求用户重新输入密码

依赖主类 GDPRService 提供 `self.db`，以及主模块 gdpr_service 提供的模块级工具:
- `ANON_USERNAME_PREFIX` / `ANON_EMAIL_DOMAIN` / `ANON_PHONE` / `ANON_NAME` /
  `ANON_TEXT`: 匿名化占位符常量
- `_safe_decrypt`: PII 安全解密辅助函数

这些模块级工具通过延迟导入 (方法内 import) 访问, 避免与主模块形成循环导入。
"""

from __future__ import annotations

import json
import secrets
import uuid
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select

from app.core.pii_crypto import mask_pii
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


class AnonymizeMixin:
    """GDPR 数据匿名化/删除相关方法 Mixin。

    包含 `anonymize_user` 方法, 实现 GDPR Article 17 被遗忘权。

    依赖主类 GDPRService 提供 `self.db`。
    """

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
        # 延迟导入模块级常量与辅助函数，避免与主模块 gdpr_service.py 形成循环导入
        from app.services.gdpr_service import (
            ANON_EMAIL_DOMAIN,
            ANON_NAME,
            ANON_PHONE,
            ANON_TEXT,
            ANON_USERNAME_PREFIX,
            _safe_decrypt,
        )

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
