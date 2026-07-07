"""T-303: GDPRService 集成测试.

使用真实 db_session 测试 GDPRService, 覆盖:
- export_user_data: 完整数据导出 (含关系数据)
- fetch_user_account / fetch_profile: 流式导出基础方法
- iter_*: 流式迭代器 (emergency_contacts / counselor_bindings / risk_assessments /
  warnings / crisis_events / intervention_plans / intervention_tasks / operation_logs)
- anonymize_user: 完整匿名化流程 (密码验证 / 字段脱敏 / 关系清理 / OperationLog)
- _safe_decrypt / _profile_to_dict 等辅助函数
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from unittest.mock import MagicMock

import pytest
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.pii_crypto import compute_blind_index, encrypt_field
from app.core.security import get_password_hash, verify_password
from app.models.admin import OperationLog
from app.models.assessment import StructuredAssessment
from app.models.auth import RefreshTokenSession
from app.models.counselor import ConsultationRecord
from app.models.intervention import InterventionPlan, InterventionTask
from app.models.risk import RiskAssessment, WarningNotification
from app.models.user import (
    EmergencyContact,
    User,
    UserCounselorBinding,
    UserProfile,
)
from app.services.gdpr_service import (
    ANON_EMAIL_DOMAIN,
    ANON_NAME,
    ANON_PHONE,
    ANON_TEXT,
    ANON_USERNAME_PREFIX,
    GDPRService,
    _binding_to_dict,
    _contact_to_dict,
    _crisis_to_dict,
    _log_to_dict,
    _plan_to_dict,
    _profile_to_dict,
    _risk_to_dict,
    _safe_decrypt,
    _task_to_dict,
    _warning_to_dict,
)


@pytest.fixture
def gdpr_service(db_session: AsyncSession) -> GDPRService:
    return GDPRService(db_session)


@pytest.fixture
async def gdpr_user(db_session: AsyncSession) -> User:
    """创建一个完整的 GDPR 测试用户, 含 profile / contacts / bindings / risk / warnings."""
    # 使用真实密码哈希, 以便后续密码验证
    password_hash = get_password_hash("TestPwd-2024-Secure!")
    user = User(
        id=100,
        username="gdpr_user",
        email="gdpr@test.com",
        email_hash=compute_blind_index("gdpr@test.com", "email"),
        password_hash=password_hash,
        role="user",
        status="active",
    )
    db_session.add(user)

    profile = UserProfile(user_id=100, nickname="GDPR测试用户", gender="male", age=25)
    db_session.add(profile)

    contact = EmergencyContact(
        user_id=100, name="紧急联系人", phone="13900139000", relationship="父亲"
    )
    db_session.add(contact)

    binding = UserCounselorBinding(
        user_id=100, counselor_id=2, bind_code="GDPR001", status="active"
    )
    db_session.add(binding)

    risk = RiskAssessment(
        user_id=100,
        risk_score=70,
        risk_level=3,
        structured_score=70,
        models_used=["m"],
        risk_factors=[{"feature": "stress", "importance": 0.8}],
        assessment_type="structured",
    )
    db_session.add(risk)

    warning = WarningNotification(
        user_id=100,
        counselor_id=2,
        current_level=3,
        previous_level=2,
        trigger_reason="风险等级上升",
    )
    db_session.add(warning)

    plan = InterventionPlan(
        user_id=100,
        plan_name="GDPR测试计划",
        risk_level=3,
        status="active",
        start_date=datetime.now(UTC).replace(tzinfo=None).date(),
        end_date=(datetime.now(UTC).replace(tzinfo=None) + timedelta(days=28)).date(),
    )
    db_session.add(plan)
    await db_session.flush()
    task = InterventionTask(
        plan_id=plan.id,
        task_name="呼吸训练",
        task_type="meditation",
        description="每日 10 分钟",
        schedule="daily",
        duration_minutes=10,
        sort_order=0,
    )
    db_session.add(task)

    # OperationLog
    op_log = OperationLog(
        operator_id=100,
        operator_role="user",
        action_type="profile.update",
        target_type="user",
        target_id=100,
    )
    db_session.add(op_log)

    await db_session.commit()
    return user


class TestExportUserData:
    """export_user_data 完整数据导出测试."""

    @pytest.mark.asyncio
    async def test_export_raises_for_missing_user(self, gdpr_service: GDPRService):
        """TC-COV-GDPR-001: 不存在的用户抛 ValueError."""
        with pytest.raises(ValueError, match="用户不存在"):
            await gdpr_service.export_user_data(99999)

    @pytest.mark.asyncio
    async def test_export_returns_full_structure(
        self, gdpr_service: GDPRService, gdpr_user: User
    ):
        """TC-COV-GDPR-002: 导出应包含完整数据结构."""
        result = await gdpr_service.export_user_data(100)

        # 验证所有顶层字段
        assert "export_metadata" in result
        assert "account" in result
        assert "profile" in result
        assert "emergency_contacts" in result
        assert "counselor_bindings" in result
        assert "risk_assessments" in result
        assert "warnings" in result
        assert "crisis_events" in result
        assert "intervention_plans" in result
        assert "intervention_tasks" in result
        assert "operation_logs" in result
        assert "summary" in result

        # 验证 metadata
        assert result["export_metadata"]["user_id"] == 100
        assert "Article 15 (Access)" in result["export_metadata"]["gdpr_articles"]
        assert "Article 20 (Portability)" in result["export_metadata"]["gdpr_articles"]

        # 验证 account 字段
        assert result["account"]["username"] == "gdpr_user"
        assert result["account"]["email"] == "gdpr@test.com"
        assert result["account"]["role"] == "user"

        # 验证 profile
        assert result["profile"]["nickname"] == "GDPR测试用户"

        # 验证关系数据
        assert len(result["emergency_contacts"]) == 1
        assert result["emergency_contacts"][0]["name"] == "紧急联系人"
        assert len(result["counselor_bindings"]) == 1
        assert result["counselor_bindings"][0]["counselor_id"] == 2
        assert len(result["risk_assessments"]) == 1
        assert result["risk_assessments"][0]["risk_level"] == 3
        assert len(result["warnings"]) == 1
        assert len(result["intervention_plans"]) == 1
        assert len(result["intervention_tasks"]) == 1
        assert len(result["operation_logs"]) == 1

        # 验证 summary
        assert result["summary"]["risk_assessments_count"] == 1
        assert result["summary"]["warnings_count"] == 1
        assert result["summary"]["operation_logs_count"] == 1


class TestFetchUserAccount:
    """fetch_user_account 测试."""

    @pytest.mark.asyncio
    async def test_fetch_user_account_success(
        self, gdpr_service: GDPRService, gdpr_user: User
    ):
        """TC-COV-GDPR-003: 拉取账户基础信息."""
        result = await gdpr_service.fetch_user_account(100)
        assert result["username"] == "gdpr_user"
        assert result["email"] == "gdpr@test.com"
        assert result["role"] == "user"
        assert result["status"] == "active"

    @pytest.mark.asyncio
    async def test_fetch_user_account_not_found(self, gdpr_service: GDPRService):
        """TC-COV-GDPR-004: 用户不存在抛 ValueError."""
        with pytest.raises(ValueError, match="用户不存在"):
            await gdpr_service.fetch_user_account(99999)


class TestFetchProfile:
    """fetch_profile 测试."""

    @pytest.mark.asyncio
    async def test_fetch_profile_success(
        self, gdpr_service: GDPRService, gdpr_user: User
    ):
        """TC-COV-GDPR-005: 拉取用户档案."""
        result = await gdpr_service.fetch_profile(100)
        assert result is not None
        assert result["nickname"] == "GDPR测试用户"
        assert result["gender"] == "male"
        assert result["age"] == 25

    @pytest.mark.asyncio
    async def test_fetch_profile_not_found(
        self, gdpr_service: GDPRService, gdpr_user: User
    ):
        """TC-COV-GDPR-006: 无档案时返回 None."""
        # 删除 profile
        from sqlalchemy import select

        stmt = select(UserProfile).where(UserProfile.user_id == 100)
        profile = (await gdpr_service.db.execute(stmt)).scalar_one_or_none()
        if profile:
            await gdpr_service.db.delete(profile)
            await gdpr_service.db.commit()

        result = await gdpr_service.fetch_profile(100)
        assert result is None


class TestIterEmergencyContacts:
    """iter_emergency_contacts 流式测试."""

    @pytest.mark.asyncio
    async def test_iter_emergency_contacts(
        self, gdpr_service: GDPRService, gdpr_user: User
    ):
        """TC-COV-GDPR-007: 流式输出紧急联系人."""
        import json

        results = []
        async for item in gdpr_service.iter_emergency_contacts(100, batch_size=10):
            results.append(json.loads(item))

        assert len(results) == 1
        assert results[0]["name"] == "紧急联系人"
        assert results[0]["phone"] == "13900139000"
        assert results[0]["relationship"] == "父亲"

    @pytest.mark.asyncio
    async def test_iter_emergency_contacts_empty(
        self, gdpr_service: GDPRService, gdpr_user: User
    ):
        """TC-COV-GDPR-008: 无联系人时返回空."""
        results = []
        async for item in gdpr_service.iter_emergency_contacts(99999, batch_size=10):
            results.append(item)
        assert results == []


class TestIterCounselorBindings:
    """iter_counselor_bindings 流式测试."""

    @pytest.mark.asyncio
    async def test_iter_counselor_bindings(
        self, gdpr_service: GDPRService, gdpr_user: User
    ):
        """TC-COV-GDPR-009: 流式输出咨询师绑定."""
        import json

        results = []
        async for item in gdpr_service.iter_counselor_bindings(100, batch_size=10):
            results.append(json.loads(item))

        assert len(results) == 1
        assert results[0]["counselor_id"] == 2
        assert results[0]["status"] == "active"


class TestIterRiskAssessments:
    """iter_risk_assessments 流式测试."""

    @pytest.mark.asyncio
    async def test_iter_risk_assessments(
        self, gdpr_service: GDPRService, gdpr_user: User
    ):
        """TC-COV-GDPR-010: 流式输出风险评估."""
        import json

        results = []
        async for item in gdpr_service.iter_risk_assessments(100, batch_size=10):
            results.append(json.loads(item))

        assert len(results) == 1
        assert results[0]["risk_level"] == 3
        assert results[0]["risk_score"] == 70


class TestIterWarnings:
    """iter_warnings 流式测试."""

    @pytest.mark.asyncio
    async def test_iter_warnings(self, gdpr_service: GDPRService, gdpr_user: User):
        """TC-COV-GDPR-011: 流式输出预警记录."""
        import json

        results = []
        async for item in gdpr_service.iter_warnings(100, batch_size=10):
            results.append(json.loads(item))

        assert len(results) == 1
        assert results[0]["level"] == 3
        assert results[0]["previous_level"] == 2


class TestIterInterventionPlans:
    """iter_intervention_plans 流式测试."""

    @pytest.mark.asyncio
    async def test_iter_intervention_plans(
        self, gdpr_service: GDPRService, gdpr_user: User
    ):
        """TC-COV-GDPR-012: 流式输出干预计划."""
        import json

        results = []
        async for item in gdpr_service.iter_intervention_plans(100, batch_size=10):
            results.append(json.loads(item))

        assert len(results) == 1
        assert results[0]["status"] == "active"
        assert results[0]["risk_level"] == 3


class TestIterInterventionTasks:
    """iter_intervention_tasks 流式测试."""

    @pytest.mark.asyncio
    async def test_iter_intervention_tasks(
        self, gdpr_service: GDPRService, gdpr_user: User
    ):
        """TC-COV-GDPR-013: 流式输出干预任务 (基于 plans 关联)."""
        import json

        results = []
        async for item in gdpr_service.iter_intervention_tasks(100, batch_size=10):
            results.append(json.loads(item))

        assert len(results) == 1
        assert results[0]["task_name"] == "呼吸训练"
        assert results[0]["task_type"] == "meditation"

    @pytest.mark.asyncio
    async def test_iter_intervention_tasks_no_plans(
        self, gdpr_service: GDPRService, gdpr_user: User
    ):
        """TC-COV-GDPR-014: 无 plan 时直接返回 (不查询 task)."""
        results = []
        async for item in gdpr_service.iter_intervention_tasks(99999, batch_size=10):
            results.append(item)
        assert results == []


class TestIterOperationLogs:
    """iter_operation_logs 流式测试."""

    @pytest.mark.asyncio
    async def test_iter_operation_logs(
        self, gdpr_service: GDPRService, gdpr_user: User
    ):
        """TC-COV-GDPR-015: 流式输出操作日志."""
        import json

        results = []
        async for item in gdpr_service.iter_operation_logs(100, batch_size=10):
            results.append(json.loads(item))

        assert len(results) == 1
        assert results[0]["action"] == "profile.update"


class TestAnonymizeUser:
    """anonymize_user 完整匿名化流程测试."""

    @pytest.mark.asyncio
    async def test_anonymize_missing_user_raises(self, gdpr_service: GDPRService):
        """TC-COV-GDPR-016: 不存在的用户抛 ValueError."""
        with pytest.raises(ValueError, match="用户不存在"):
            await gdpr_service.anonymize_user(99999, password_confirm="any")

    @pytest.mark.asyncio
    async def test_anonymize_already_deleted_raises(
        self, gdpr_service: GDPRService, gdpr_user: User
    ):
        """TC-COV-GDPR-017: 已删除用户重复删除抛 ValueError."""
        gdpr_user.status = "deleted"
        await gdpr_service.db.commit()

        with pytest.raises(ValueError, match="已被删除"):
            await gdpr_service.anonymize_user(100, password_confirm="any")

    @pytest.mark.asyncio
    async def test_anonymize_wrong_password_raises(
        self, gdpr_service: GDPRService, gdpr_user: User
    ):
        """TC-COV-GDPR-018: 错误密码抛 ValueError."""
        with pytest.raises(ValueError, match="密码错误"):
            await gdpr_service.anonymize_user(100, password_confirm="wrong_password")

    @pytest.mark.asyncio
    async def test_anonymize_success_basic(
        self, gdpr_service: GDPRService, gdpr_user: User
    ):
        """TC-COV-GDPR-019: 正确密码完成匿名化, 字段被替换."""
        result = await gdpr_service.anonymize_user(
            100, password_confirm="TestPwd-2024-Secure!"
        )

        # 验证返回结构
        assert result["user_id"] == 100
        assert "anonymized_at" in result
        assert "original_email_masked" in result
        assert result["legal_records_retained"] is True

        # 验证 user 字段已被脱敏
        await gdpr_service.db.refresh(gdpr_user)
        assert gdpr_user.status == "deleted"
        assert gdpr_user.username.startswith(ANON_USERNAME_PREFIX)
        assert gdpr_user.email.endswith(ANON_EMAIL_DOMAIN)
        assert gdpr_user.phone is None
        assert gdpr_user.avatar_url is None

        # 验证 password_hash 被替换 (新随机密码)
        assert not verify_password("TestPwd-2024-Secure!", gdpr_user.password_hash)

    @pytest.mark.asyncio
    async def test_anonymize_writes_audit_log(
        self, gdpr_service: GDPRService, gdpr_user: User
    ):
        """TC-COV-GDPR-020: 匿名化写入 OperationLog 用于合规审计."""
        await gdpr_service.anonymize_user(100, password_confirm="TestPwd-2024-Secure!")

        # 查询新增的 gdpr.account.deleted 日志
        from sqlalchemy import select

        stmt = select(OperationLog).where(
            OperationLog.operator_id == 100,
            OperationLog.action_type == "gdpr.account.deleted",
        )
        log = (await gdpr_service.db.execute(stmt)).scalar_one_or_none()
        assert log is not None
        assert log.target_type == "user"
        assert log.target_id == 100
        # detail 是 JSON 字符串, 含 pii_text_anonymized
        import json

        detail = json.loads(log.detail)
        assert "anonymized_at" in detail
        assert "keep_legal_records" in detail
        assert "pii_text_anonymized" in detail

    @pytest.mark.asyncio
    async def test_anonymize_anonymizes_emergency_contacts(
        self, gdpr_service: GDPRService, gdpr_user: User
    ):
        """TC-COV-GDPR-021: 紧急联系人字段被脱敏."""
        await gdpr_service.anonymize_user(100, password_confirm="TestPwd-2024-Secure!")

        from sqlalchemy import select

        stmt = select(EmergencyContact).where(EmergencyContact.user_id == 100)
        contacts = (await gdpr_service.db.execute(stmt)).scalars().all()
        assert len(contacts) == 1
        assert contacts[0].name == ANON_NAME
        assert contacts[0].phone == ANON_PHONE
        assert contacts[0].relationship == ANON_NAME

    @pytest.mark.asyncio
    async def test_anonymize_deactivates_bindings(
        self, gdpr_service: GDPRService, gdpr_user: User
    ):
        """TC-COV-GDPR-022: 活跃的咨询师绑定被设为 inactive."""
        await gdpr_service.anonymize_user(100, password_confirm="TestPwd-2024-Secure!")

        from sqlalchemy import select

        from app.core.states import BindingStatus

        stmt = select(UserCounselorBinding).where(UserCounselorBinding.user_id == 100)
        bindings = (await gdpr_service.db.execute(stmt)).scalars().all()
        assert len(bindings) == 1
        assert bindings[0].status == BindingStatus.INACTIVE
        assert bindings[0].unbound_at is not None

    @pytest.mark.asyncio
    async def test_anonymize_anonymizes_warnings(
        self, gdpr_service: GDPRService, gdpr_user: User
    ):
        """TC-COV-GDPR-023: WarningNotification.trigger_reason 被脱敏."""
        await gdpr_service.anonymize_user(100, password_confirm="TestPwd-2024-Secure!")

        from sqlalchemy import select

        stmt = select(WarningNotification).where(WarningNotification.user_id == 100)
        warnings = (await gdpr_service.db.execute(stmt)).scalars().all()
        assert len(warnings) == 1
        assert warnings[0].trigger_reason == ANON_TEXT

    @pytest.mark.asyncio
    async def test_anonymize_anonymizes_intervention_task_description(
        self, gdpr_service: GDPRService, gdpr_user: User
    ):
        """TC-COV-GDPR-024: InterventionTask.description 被脱敏 (C-Svc-8 修复)."""
        await gdpr_service.anonymize_user(100, password_confirm="TestPwd-2024-Secure!")

        from sqlalchemy import select

        stmt = (
            select(InterventionTask)
            .join(InterventionPlan, InterventionTask.plan_id == InterventionPlan.id)
            .where(InterventionPlan.user_id == 100)
        )
        tasks = (await gdpr_service.db.execute(stmt)).scalars().all()
        assert len(tasks) == 1
        assert tasks[0].description == ANON_TEXT

    @pytest.mark.asyncio
    async def test_anonymize_anonymizes_profile(
        self, gdpr_service: GDPRService, gdpr_user: User
    ):
        """TC-COV-GDPR-025: UserProfile.nickname 被脱敏 (保留 gender/age 用于统计)."""
        await gdpr_service.anonymize_user(100, password_confirm="TestPwd-2024-Secure!")

        from sqlalchemy import select

        stmt = select(UserProfile).where(UserProfile.user_id == 100)
        profile = (await gdpr_service.db.execute(stmt)).scalar_one_or_none()
        assert profile is not None
        assert profile.nickname == ANON_NAME
        # gender/age 保留用于统计
        assert profile.gender == "male"
        assert profile.age == 25

    @pytest.mark.asyncio
    async def test_anonymize_revokes_refresh_tokens(
        self, gdpr_service: GDPRService, gdpr_user: User
    ):
        """TC-COV-GDPR-026: 撤销所有未过期的 refresh token sessions."""
        from datetime import datetime, timedelta

        # 先创建一条 session
        gdpr_service.db.add(
            RefreshTokenSession(
                user_id=100,
                jti="test_jti_1",
                expires_at=datetime.now(UTC).replace(tzinfo=None) + timedelta(days=7),
            )
        )
        await gdpr_service.db.commit()

        await gdpr_service.anonymize_user(100, password_confirm="TestPwd-2024-Secure!")

        from sqlalchemy import select

        stmt = select(RefreshTokenSession).where(RefreshTokenSession.user_id == 100)
        sessions = (await gdpr_service.db.execute(stmt)).scalars().all()
        assert len(sessions) == 1
        assert sessions[0].revoked_at is not None

    @pytest.mark.asyncio
    async def test_anonymize_keep_legal_records_default(
        self, gdpr_service: GDPRService, gdpr_user: User
    ):
        """TC-COV-GDPR-027: 默认保留风险评估记录 (合规审计)."""
        await gdpr_service.anonymize_user(100, password_confirm="TestPwd-2024-Secure!")

        # 风险评估应保留
        from sqlalchemy import select

        stmt = select(RiskAssessment).where(RiskAssessment.user_id == 100)
        risks = (await gdpr_service.db.execute(stmt)).scalars().all()
        assert len(risks) == 1
        assert risks[0].risk_score == 70

    @pytest.mark.asyncio
    async def test_anonymize_delete_legal_records_when_requested(
        self, gdpr_service: GDPRService, gdpr_user: User
    ):
        """TC-COV-GDPR-028: keep_legal_records=False 时删除风险评估."""
        result = await gdpr_service.anonymize_user(
            100,
            password_confirm="TestPwd-2024-Secure!",
            keep_legal_records=False,
        )

        # 风险评估应被删除
        from sqlalchemy import select

        stmt = select(RiskAssessment).where(RiskAssessment.user_id == 100)
        risks = (await gdpr_service.db.execute(stmt)).scalars().all()
        assert len(risks) == 0
        assert result["risk_assessments_deleted"] == 1
        assert result["legal_records_retained"] is False

    @pytest.mark.asyncio
    async def test_anonymize_email_hash_updated(
        self, gdpr_service: GDPRService, gdpr_user: User
    ):
        """TC-COV-GDPR-029: email_hash 盲索引与新匿名 email 一致 (P1-E 修复)."""
        await gdpr_service.anonymize_user(100, password_confirm="TestPwd-2024-Secure!")

        await gdpr_service.db.refresh(gdpr_user)
        # 新 email_hash 应等于新匿名 email 的盲索引
        expected_hash = compute_blind_index(gdpr_user.email, "email")
        assert gdpr_user.email_hash == expected_hash

    @pytest.mark.asyncio
    async def test_anonymize_anonymizes_consultation_records(
        self, gdpr_service: GDPRService, gdpr_user: User, db_session: AsyncSession
    ):
        """TC-COV-GDPR-030: ConsultationRecord 自由文本字段被脱敏 (C-Svc-8 修复)."""
        # 先添加一条咨询记录
        db_session.add(
            ConsultationRecord(
                user_id=100,
                counselor_id=2,
                main_topics="讨论焦虑情绪",
                client_status="中度焦虑",
                interventions="认知行为疗法",
                next_plan="下次继续",
                notes="患者配合度良好",
            )
        )
        await db_session.commit()

        await gdpr_service.anonymize_user(100, password_confirm="TestPwd-2024-Secure!")

        from sqlalchemy import select

        stmt = select(ConsultationRecord).where(ConsultationRecord.user_id == 100)
        records = (await gdpr_service.db.execute(stmt)).scalars().all()
        assert len(records) == 1
        rec = records[0]
        assert rec.main_topics == ANON_TEXT
        assert rec.client_status == ANON_TEXT
        assert rec.interventions == ANON_TEXT
        assert rec.next_plan == ANON_TEXT
        assert rec.notes == ANON_TEXT

    @pytest.mark.asyncio
    async def test_anonymize_anonymizes_structured_assessment(
        self, gdpr_service: GDPRService, gdpr_user: User, db_session: AsyncSession
    ):
        """TC-COV-GDPR-031: StructuredAssessment.data_payload 被清空 (C-Svc-8 修复)."""
        db_session.add(
            StructuredAssessment(
                user_id=100,
                assessment_type="comprehensive",
                score=45.0,
                severity="moderate",
                data_payload={"age": 25, "stress_level": 5, "sleep_duration": 5},
            )
        )
        await db_session.commit()

        await gdpr_service.anonymize_user(100, password_confirm="TestPwd-2024-Secure!")

        from sqlalchemy import select

        stmt = select(StructuredAssessment).where(StructuredAssessment.user_id == 100)
        records = (await gdpr_service.db.execute(stmt)).scalars().all()
        assert len(records) == 1
        assert records[0].data_payload == {}


class TestHelperFunctions:
    """辅助函数测试."""

    def test_safe_decrypt_with_encrypted_value(self):
        """TC-COV-GDPR-032: 加密值正确解密."""
        original = "test@example.com"
        encrypted = encrypt_field(original, "email")
        assert _safe_decrypt(encrypted, "email") == original

    def test_safe_decrypt_with_plaintext(self):
        """TC-COV-GDPR-033: 明文值直接返回."""
        assert _safe_decrypt("plaintext", "email") == "plaintext"

    def test_safe_decrypt_with_none(self):
        """TC-COV-GDPR-034: None 透传."""
        assert _safe_decrypt(None, "email") is None

    def test_safe_decrypt_with_empty(self):
        """TC-COV-GDPR-035: 空字符串透传."""
        assert _safe_decrypt("", "email") == ""

    def test_safe_decrypt_with_invalid_ciphertext(self):
        """TC-COV-GDPR-036: 解密失败返回 mask."""
        # 伪造的密文 (格式正确但内容无效)
        invalid = "enc:v1:invalidbase64=="
        result = _safe_decrypt(invalid, "email")
        assert result == "[DECRYPT_FAILED]"

    def test_profile_to_dict(self):
        """TC-COV-GDPR-037: _profile_to_dict 序列化."""
        p = MagicMock()
        p.nickname = "test"
        p.gender = "male"
        p.age = 25
        p.language = "zh"
        p.theme = "light"
        p.reminder_freq = "daily"

        result = _profile_to_dict(p)
        assert result["nickname"] == "test"
        assert result["gender"] == "male"
        assert result["age"] == 25
        assert result["language"] == "zh"

    def test_contact_to_dict(self):
        """TC-COV-GDPR-038: _contact_to_dict 序列化."""
        c = MagicMock()
        c.name = "father"
        c.relationship = "父亲"
        c.phone = "13900139000"

        result = _contact_to_dict(c)
        assert result["name"] == "father"
        assert result["relationship"] == "父亲"
        assert result["phone"] == "13900139000"

    def test_binding_to_dict(self):
        """TC-COV-GDPR-039: _binding_to_dict 序列化 (使用 bound_at 而非 created_at)."""
        from datetime import datetime

        b = MagicMock()
        b.counselor_id = 5
        b.status = "active"
        b.bound_at = datetime(2024, 1, 1)

        result = _binding_to_dict(b)
        assert result["counselor_id"] == 5
        assert result["status"] == "active"
        assert "created_at" in result  # 字段名映射
        assert "2024-01-01" in result["created_at"]

    def test_risk_to_dict(self):
        """TC-COV-GDPR-040: _risk_to_dict 序列化."""
        from datetime import datetime

        r = MagicMock()
        r.id = 1
        r.assessment_type = "structured"
        r.risk_level = 3
        r.risk_score = 70.0
        r.created_at = datetime(2024, 1, 1)

        result = _risk_to_dict(r)
        assert result["id"] == 1
        assert result["assessment_type"] == "structured"
        assert result["risk_level"] == 3
        assert result["risk_score"] == 70.0

    def test_warning_to_dict(self):
        """TC-COV-GDPR-041: _warning_to_dict 序列化."""
        from datetime import datetime

        w = MagicMock()
        w.id = 1
        w.current_level = 3
        w.previous_level = 2
        w.trigger_reason = "test"
        w.is_handled = False
        w.is_read = True
        w.handle_action = None
        w.created_at = datetime(2024, 1, 1)

        result = _warning_to_dict(w)
        assert result["id"] == 1
        assert result["level"] == 3
        assert result["previous_level"] == 2
        assert result["message"] == "test"
        assert result["status"] == "read"  # is_read=True, is_handled=False → read
        assert result["is_read"] is True
        assert result["is_handled"] is False

    def test_warning_to_dict_handled(self):
        """TC-COV-GDPR-042: _warning_to_dict 已处理状态."""
        w = MagicMock()
        w.is_handled = True
        w.is_read = True

        result = _warning_to_dict(w)
        assert result["status"] == "handled"

    def test_warning_to_dict_pending(self):
        """TC-COV-GDPR-043: _warning_to_dict pending 状态."""
        w = MagicMock()
        w.is_handled = False
        w.is_read = False

        result = _warning_to_dict(w)
        assert result["status"] == "pending"

    def test_crisis_to_dict(self):
        """TC-COV-GDPR-044: _crisis_to_dict 序列化."""
        from datetime import datetime

        c = MagicMock()
        c.id = 1
        c.trigger_source = "text_inference"
        c.crisis_score = 0.85
        c.created_at = datetime(2024, 1, 1)

        result = _crisis_to_dict(c)
        assert result["id"] == 1
        assert result["trigger_source"] == "text_inference"
        assert result["crisis_score"] == 0.85

    def test_plan_to_dict(self):
        """TC-COV-GDPR-045: _plan_to_dict 序列化."""
        from datetime import datetime

        p = MagicMock()
        p.id = 1
        p.status = "active"
        p.risk_level = 3
        p.created_at = datetime(2024, 1, 1)

        result = _plan_to_dict(p)
        assert result["id"] == 1
        assert result["status"] == "active"
        assert result["risk_level"] == 3

    def test_task_to_dict(self):
        """TC-COV-GDPR-046: _task_to_dict 序列化."""
        from datetime import datetime

        t = MagicMock()
        t.id = 1
        t.plan_id = 5
        t.task_name = "呼吸训练"
        t.task_type = "meditation"
        t.description = "每日 10 分钟"
        t.schedule = "daily"
        t.duration_minutes = 10
        t.sort_order = 0
        t.created_at = datetime(2024, 1, 1)

        result = _task_to_dict(t)
        assert result["id"] == 1
        assert result["plan_id"] == 5
        assert result["task_name"] == "呼吸训练"
        assert result["duration_minutes"] == 10

    def test_log_to_dict(self):
        """TC-COV-GDPR-047: _log_to_dict 序列化."""
        from datetime import datetime

        o = MagicMock()
        o.action_type = "user.login"
        o.target_type = "user"
        o.target_id = 100
        o.created_at = datetime(2024, 1, 1)

        result = _log_to_dict(o)
        assert result["action"] == "user.login"
        assert result["resource_type"] == "user"
        assert result["resource_id"] == 100

    def test_log_to_dict_with_none_created_at(self):
        """TC-COV-GDPR-048: _log_to_dict 处理 created_at=None."""
        o = MagicMock()
        o.action_type = "test"
        o.target_type = "user"
        o.target_id = 1
        o.created_at = None

        result = _log_to_dict(o)
        assert result["created_at"] is None

    def test_constants(self):
        """TC-COV-GDPR-049: 验证匿名化常量."""
        assert ANON_USERNAME_PREFIX == "anon_"
        assert ANON_EMAIL_DOMAIN == "@deleted.local"
        assert ANON_PHONE == "00000000000"
        assert ANON_NAME == "[已删除]"
        assert ANON_TEXT == "[ANONYMIZED]"
