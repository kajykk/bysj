from __future__ import annotations

import os
from datetime import date
from typing import Any

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import AsyncSessionLocal
from app.core.security import get_password_hash
from app.core.pii_crypto import compute_blind_index
from app.models import (
    EducationContent,
    InterventionPlan,
    InterventionTask,
    InterventionTemplate,
    PhysiologicalRecord,
    RiskAssessment,
    StructuredAssessment,
    User,
    UserCounselorBinding,
    UserProfile,
    WarningNotification,
    WarningSetting,
)

# 从环境变量读取种子数据密码，默认值仅用于开发环境
# 修复：生产环境必须显式配置密码，防止弱口令后门
_SEED_ADMIN_PASSWORD = os.getenv("SEED_ADMIN_PASSWORD", "Admin@123")
_SEED_COUNSELOR_PASSWORD = os.getenv("SEED_COUNSELOR_PASSWORD", "Counselor@123")
_SEED_USER_PASSWORD = os.getenv("SEED_USER_PASSWORD", "User@12345")
_E2E_ADMIN_PASSWORD = os.getenv("E2E_ADMIN_PASSWORD", "E2E@Admin123")
_E2E_COUNSELOR_PASSWORD = os.getenv("E2E_COUNSELOR_PASSWORD", "E2E@Counselor123")
_E2E_USER_PASSWORD = os.getenv("E2E_USER_PASSWORD", "E2E@User123")


def _validate_seed_passwords_for_production() -> None:
    """生产环境强制要求种子密码通过环境变量配置，防止弱口令后门。"""
    from app.core.config import settings
    if settings.app_env.lower() != "production":
        return
    missing = [
        name for name, val in [
            ("SEED_ADMIN_PASSWORD", os.getenv("SEED_ADMIN_PASSWORD")),
            ("SEED_COUNSELOR_PASSWORD", os.getenv("SEED_COUNSELOR_PASSWORD")),
            ("SEED_USER_PASSWORD", os.getenv("SEED_USER_PASSWORD")),
        ] if not val
    ]
    if missing:
        raise RuntimeError(
            f"生产环境必须通过环境变量配置种子密码，缺失: {missing}。"
            f"请在 .env 或部署环境中设置这些变量。"
        )

_COUNSELOR_SEED_DATA: list[dict[str, str]] = [
    {"username": "dr_wang", "email": "wang@clinic.com"},
    {"username": "dr_li", "email": "li@clinic.com"},
    {"username": "dr_chen", "email": "chen@clinic.com"},
    {"username": "dr_zhao", "email": "zhao@clinic.com"},
]

_USER_SEED_DATA: list[dict[str, Any]] = [
    {
        "username": "user_none",
        "email": "user_none@test.com",
        "nickname": "无风险用户",
        "threshold_level": 2,
        "assessment_score": 2,
        "assessment_severity": "none",
        "stress_level": 0,
        "sleep_duration": 8,
        "risk_score": 8,
        "risk_level": 0,
        "models_used": ["Logistic_Regression_quick"],
        "risk_factors": [],
        "counselor_username": "dr_wang",
        "bind_code": "A10001",
        "physiological_record": {
            "source": "manual",
            "sleep_hours": 8.0,
            "sleep_quality": 8,
            "exercise_minutes": 40,
            "heart_rate": 68,
            "systolic_bp": 116,
            "diastolic_bp": 74,
            "steps": 8200,
            "data_payload": {"screen_time": 1.0, "caffeine_intake": 0},
        },
    },
    {
        "username": "user_low",
        "email": "user_low@test.com",
        "nickname": "低风险用户",
        "threshold_level": 2,
        "assessment_score": 6,
        "assessment_severity": "mild",
        "stress_level": 1,
        "sleep_duration": 7,
        "risk_score": 24,
        "risk_level": 1,
        "models_used": ["Logistic_Regression_quick"],
        "risk_factors": ["近期轻微情绪波动"],
        "counselor_username": "dr_wang",
        "bind_code": "A10002",
    },
    {
        "username": "user_mild",
        "email": "user_mild@test.com",
        "nickname": "轻度风险用户",
        "threshold_level": 2,
        "assessment_score": 9,
        "assessment_severity": "mild",
        "stress_level": 2,
        "sleep_duration": 6,
        "risk_score": 41,
        "risk_level": 2,
        "models_used": ["Logistic_Regression_quick"],
        "risk_factors": ["睡眠质量下降", "学习压力偏高"],
        "counselor_username": "dr_li",
        "bind_code": "A10003",
    },
    {
        "username": "user_moderate",
        "email": "user_moderate@test.com",
        "nickname": "中度风险用户",
        "threshold_level": 2,
        "assessment_score": 14,
        "assessment_severity": "moderate",
        "stress_level": 3,
        "sleep_duration": 6,
        "risk_score": 62,
        "risk_level": 3,
        "models_used": ["Logistic_Regression_quick"],
        "risk_factors": ["持续焦虑", "睡眠不足"],
        "counselor_username": "dr_li",
        "bind_code": "A10004",
        "warning": {
            "previous_level": 2,
            "current_level": 3,
            "trigger_reason": "风险等级上升，需要咨询师持续关注",
        },
        "plan": {
            "plan_name": "中风险情绪稳定计划",
            "risk_level": 3,
            "status": "active",
            "tasks": [
                {
                    "task_name": "10分钟呼吸训练",
                    "task_type": "meditation",
                    "description": "每日进行呼吸放松训练",
                    "schedule": "daily",
                    "duration_minutes": 10,
                },
                {
                    "task_name": "轻度运动",
                    "task_type": "exercise",
                    "description": "快走或慢跑20分钟",
                    "schedule": "daily",
                    "duration_minutes": 20,
                },
            ],
        },
    },
    {
        "username": "user_high",
        "email": "user_high@test.com",
        "nickname": "高风险用户",
        "threshold_level": 2,
        "assessment_score": 20,
        "assessment_severity": "severe",
        "stress_level": 5,
        "sleep_duration": 4,
        "risk_score": 86,
        "risk_level": 4,
        "models_used": ["Logistic_Regression_quick"],
        "risk_factors": ["持续失眠", "明显情绪低落", "社交退缩"],
        "counselor_username": "dr_chen",
        "bind_code": "A10005",
        "warning": {
            "previous_level": 3,
            "current_level": 4,
            "trigger_reason": "高风险预警，请尽快联系咨询师",
        },
        "plan": {
            "plan_name": "高风险支持性干预计划",
            "risk_level": 4,
            "status": "active",
            "tasks": [
                {
                    "task_name": "紧急联系咨询师",
                    "task_type": "education",
                    "description": "与咨询师完成一次沟通",
                    "schedule": "one_time",
                    "duration_minutes": 30,
                },
                {
                    "task_name": "睡眠作息重建",
                    "task_type": "sleep",
                    "description": "固定时间入睡并记录睡眠",
                    "schedule": "daily",
                    "duration_minutes": 15,
                },
            ],
        },
    },
    {
        "username": "user_critical",
        "email": "user_critical@test.com",
        "nickname": "危急风险用户",
        "threshold_level": 1,
        "assessment_score": 24,
        "assessment_severity": "severe",
        "stress_level": 5,
        "sleep_duration": 3,
        "risk_score": 96,
        "risk_level": 4,
        "models_used": ["Logistic_Regression_quick", "FusionPriorityV1"],
        "risk_factors": ["持续极端压力", "严重睡眠障碍", "需要立即人工干预"],
        "counselor_username": "dr_zhao",
        "bind_code": "A10006",
        "warning": {
            "previous_level": 3,
            "current_level": 4,
            "trigger_reason": "危急预警，请立即安排人工干预和紧急回访",
        },
        "plan": {
            "plan_name": "高风险支持性干预计划",
            "risk_level": 4,
            "status": "active",
            "tasks": [
                {
                    "task_name": "紧急联系咨询师",
                    "task_type": "education",
                    "description": "立即与咨询师建立联系并完成风险复核",
                    "schedule": "one_time",
                    "duration_minutes": 30,
                },
                {
                    "task_name": "建立每日情绪观察",
                    "task_type": "checkin",
                    "description": "每日早晚各记录一次情绪和睡眠情况",
                    "schedule": "daily",
                    "duration_minutes": 10,
                },
            ],
        },
    },
    {
        "username": "user_low_academic",
        "email": "user_low_academic@test.com",
        "nickname": "学业压力初期用户",
        "threshold_level": 2,
        "assessment_score": 5,
        "assessment_severity": "mild",
        "stress_level": 1,
        "sleep_duration": 7,
        "risk_score": 18,
        "risk_level": 1,
        "models_used": ["Logistic_Regression_quick"],
        "risk_factors": ["期末备考压力", "轻度注意力分散"],
        "counselor_username": "dr_wang",
        "bind_code": "A10007",
        "physiological_record": {
            "source": "manual",
            "sleep_hours": 7.0,
            "sleep_quality": 6,
            "exercise_minutes": 30,
            "heart_rate": 72,
            "systolic_bp": 118,
            "diastolic_bp": 76,
            "steps": 6000,
            "data_payload": {"screen_time": 3.5, "caffeine_intake": 1},
        },
    },
    {
        "username": "user_mild_social",
        "email": "user_mild_social@test.com",
        "nickname": "社交回避型用户",
        "threshold_level": 2,
        "assessment_score": 8,
        "assessment_severity": "mild",
        "stress_level": 2,
        "sleep_duration": 6,
        "risk_score": 35,
        "risk_level": 2,
        "models_used": ["Logistic_Regression_quick"],
        "risk_factors": ["社交回避倾向", "小组合作焦虑"],
        "counselor_username": "dr_li",
        "bind_code": "A10008",
        "physiological_record": {
            "source": "manual",
            "sleep_hours": 6.0,
            "sleep_quality": 5,
            "exercise_minutes": 15,
            "heart_rate": 76,
            "systolic_bp": 120,
            "diastolic_bp": 78,
            "steps": 3500,
            "data_payload": {"screen_time": 5.0, "social_media_hours": 4.0},
        },
    },
    {
        "username": "user_borderline_moderate",
        "email": "user_borderline@test.com",
        "nickname": "边界风险用户",
        "threshold_level": 2,
        "assessment_score": 10,
        "assessment_severity": "moderate",
        "stress_level": 3,
        "sleep_duration": 5,
        "risk_score": 48,
        "risk_level": 2,
        "models_used": ["Logistic_Regression_quick"],
        "risk_factors": ["持续学业压力", "睡眠质量持续下降", "情绪波动频繁"],
        "counselor_username": "dr_chen",
        "bind_code": "A10009",
        "warning": {
            "previous_level": 1,
            "current_level": 2,
            "trigger_reason": "风险等级由低转轻度，睡眠和情绪指标持续恶化，需加强关注",
        },
    },
    {
        "username": "user_moderate_insomnia",
        "email": "user_insomnia@test.com",
        "nickname": "失眠型中度风险用户",
        "threshold_level": 2,
        "assessment_score": 15,
        "assessment_severity": "moderate",
        "stress_level": 3,
        "sleep_duration": 4,
        "risk_score": 58,
        "risk_level": 3,
        "models_used": ["Logistic_Regression_quick"],
        "risk_factors": ["慢性失眠", "昼夜节律紊乱", "日间功能受损"],
        "counselor_username": "dr_zhao",
        "bind_code": "A10010",
        "warning": {
            "previous_level": 2,
            "current_level": 3,
            "trigger_reason": "睡眠障碍加重，从轻度升级为中度风险",
        },
        "plan": {
            "plan_name": "中风险情绪稳定计划",
            "risk_level": 3,
            "status": "active",
            "tasks": [
                {
                    "task_name": "睡眠限制疗法入门",
                    "task_type": "sleep",
                    "description": "固定起床时间，记录睡眠日志",
                    "schedule": "daily",
                    "duration_minutes": 15,
                },
                {
                    "task_name": "睡前放松练习",
                    "task_type": "meditation",
                    "description": "睡前30分钟进行渐进式肌肉放松",
                    "schedule": "daily",
                    "duration_minutes": 20,
                },
            ],
        },
    },
    {
        "username": "user_moderate_anxiety",
        "email": "user_anxiety@test.com",
        "nickname": "焦虑型中度偏高用户",
        "threshold_level": 2,
        "assessment_score": 18,
        "assessment_severity": "moderate",
        "stress_level": 4,
        "sleep_duration": 5,
        "risk_score": 72,
        "risk_level": 3,
        "models_used": ["Logistic_Regression_quick"],
        "risk_factors": ["广泛性焦虑", "惊恐发作前兆", "回避行为增加"],
        "counselor_username": "dr_wang",
        "bind_code": "A10011",
        "warning": {
            "previous_level": 2,
            "current_level": 3,
            "trigger_reason": "焦虑症状明显加重，接近高风险阈值，需立即评估干预方案",
        },
        "plan": {
            "plan_name": "中风险情绪稳定计划",
            "risk_level": 3,
            "status": "active",
            "tasks": [
                {
                    "task_name": "认知重构练习",
                    "task_type": "education",
                    "description": "识别并记录自动负性思维，练习替代性思考",
                    "schedule": "daily",
                    "duration_minutes": 15,
                },
                {
                    "task_name": "呼吸放松训练",
                    "task_type": "meditation",
                    "description": "腹式呼吸练习，每日两次",
                    "schedule": "daily",
                    "duration_minutes": 10,
                },
                {
                    "task_name": "行为激活",
                    "task_type": "exercise",
                    "description": "每日完成至少一项愉悦或成就感活动",
                    "schedule": "daily",
                    "duration_minutes": 20,
                },
            ],
        },
    },
    {
        "username": "user_high_selfharm",
        "email": "user_selfharm@test.com",
        "nickname": "自伤风险用户",
        "threshold_level": 1,
        "assessment_score": 23,
        "assessment_severity": "severe",
        "stress_level": 5,
        "sleep_duration": 3,
        "risk_score": 90,
        "risk_level": 4,
        "models_used": ["Logistic_Regression_quick", "FusionPriorityV1"],
        "risk_factors": ["自伤意念", "重度抑郁症状", "社会支持严重缺乏", "绝望感"],
        "counselor_username": "dr_chen",
        "bind_code": "A10012",
        "warning": {
            "previous_level": 3,
            "current_level": 4,
            "trigger_reason": "出现自伤意念，风险评估升级为高风险，请立即启动危机干预流程",
        },
        "plan": {
            "plan_name": "高风险支持性干预计划",
            "risk_level": 4,
            "status": "active",
            "tasks": [
                {
                    "task_name": "安全计划制定",
                    "task_type": "education",
                    "description": "与咨询师共同制定个性化安全计划，明确危机应对步骤",
                    "schedule": "one_time",
                    "duration_minutes": 45,
                },
                {
                    "task_name": "每日安全确认",
                    "task_type": "checkin",
                    "description": "每日与咨询师完成一次安全状态确认",
                    "schedule": "daily",
                    "duration_minutes": 10,
                },
                {
                    "task_name": "社会支持网络重建",
                    "task_type": "education",
                    "description": "识别并联系至少一位可信任的支持者",
                    "schedule": "one_time",
                    "duration_minutes": 30,
                },
            ],
        },
    },
    {
        "username": "user_recovering",
        "email": "user_recovering@test.com",
        "nickname": "恢复中用户",
        "threshold_level": 2,
        "assessment_score": 3,
        "assessment_severity": "mild",
        "stress_level": 1,
        "sleep_duration": 7,
        "risk_score": 14,
        "risk_level": 1,
        "models_used": ["Logistic_Regression_quick"],
        "risk_factors": [],
        "counselor_username": "dr_li",
        "bind_code": "A10013",
        "physiological_record": {
            "source": "manual",
            "sleep_hours": 7.0,
            "sleep_quality": 7,
            "exercise_minutes": 45,
            "heart_rate": 70,
            "systolic_bp": 114,
            "diastolic_bp": 72,
            "steps": 7500,
            "data_payload": {"screen_time": 2.0, "meditation_minutes": 15},
        },
    },
]


async def seed_database() -> None:
    # 修复：生产环境强制验证种子密码已通过环境变量配置
    _validate_seed_passwords_for_production()
    async with AsyncSessionLocal() as db:
        await _seed_users(db)
        await _seed_templates(db)
        await _seed_contents(db)
        await _seed_assessments_and_warnings(db)


async def _seed_users(db: AsyncSession) -> None:
    desired_users = [
        {
            "username": "admin",
            "email": "admin@system.com",
            "role": "admin",
            "password_hash": get_password_hash(_E2E_ADMIN_PASSWORD),
        },
        *[
            {
                "username": item["username"],
                "email": item["email"],
                "role": "counselor",
                "password_hash": get_password_hash(_E2E_COUNSELOR_PASSWORD),
            }
            for item in _COUNSELOR_SEED_DATA
        ],
        *[
            {
                "username": item["username"],
                "email": item["email"],
                "role": "user",
                "password_hash": get_password_hash(_E2E_USER_PASSWORD),
            }
            for item in _USER_SEED_DATA
        ],
    ]

    existing_users = (await db.execute(select(User))).scalars().all()
    user_map = {user.username: user for user in existing_users}

    for item in desired_users:
        if item["username"] in user_map:
            continue
        user = User(
            username=item["username"],
            email=item["email"],
            email_hash=compute_blind_index(item["email"], "email"),
            role=item["role"],
            status="active",
            password_hash=item["password_hash"],
        )
        db.add(user)
        user_map[user.username] = user

    await db.flush()

    profile_user_ids = set((await db.execute(select(UserProfile.user_id))).scalars().all())
    warning_setting_user_ids = set((await db.execute(select(WarningSetting.user_id))).scalars().all())
    binding_pairs = set((await db.execute(select(UserCounselorBinding.user_id, UserCounselorBinding.counselor_id))).all())

    for user in user_map.values():
        if user.id not in profile_user_ids:
            nickname = user.username
            if user.role == "user":
                user_seed = next((item for item in _USER_SEED_DATA if item["username"] == user.username), None)
                nickname = user_seed.get("nickname", user.username) if user_seed else user.username
            db.add(UserProfile(user_id=user.id, nickname=nickname))

    for user_seed in _USER_SEED_DATA:
        user = user_map[user_seed["username"]]
        counselor = user_map[user_seed["counselor_username"]]
        if user.id not in warning_setting_user_ids:
            db.add(WarningSetting(user_id=user.id, threshold_level=user_seed.get("threshold_level", 2)))
        if (user.id, counselor.id) not in binding_pairs:
            db.add(
                UserCounselorBinding(
                    user_id=user.id,
                    counselor_id=counselor.id,
                    bind_code=user_seed["bind_code"],
                    status="active",
                )
            )

    await db.commit()


async def _seed_templates(db: AsyncSession) -> None:
    exists_template = (await db.execute(select(InterventionTemplate).limit(1))).scalar_one_or_none()
    if exists_template:
        return

    templates = [
        InterventionTemplate(
            template_name="中风险情绪稳定计划",
            applicable_levels=[2, 3],
            task_list=[
                {
                    "task_name": "10分钟呼吸训练",
                    "task_type": "meditation",
                    "description": "每日进行呼吸放松训练",
                    "schedule": "daily",
                    "duration_minutes": 10,
                },
                {
                    "task_name": "轻度运动",
                    "task_type": "exercise",
                    "description": "快走或慢跑20分钟",
                    "schedule": "daily",
                    "duration_minutes": 20,
                },
            ],
            estimated_weeks=4,
            status="active",
        ),
        InterventionTemplate(
            template_name="高风险支持性干预计划",
            applicable_levels=[4],
            task_list=[
                {
                    "task_name": "紧急联系咨询师",
                    "task_type": "education",
                    "description": "与咨询师完成一次沟通",
                    "schedule": "one_time",
                    "duration_minutes": 30,
                },
                {
                    "task_name": "睡眠作息重建",
                    "task_type": "sleep",
                    "description": "固定时间入睡并记录睡眠",
                    "schedule": "daily",
                    "duration_minutes": 15,
                },
            ],
            estimated_weeks=6,
            status="active",
        ),
    ]
    db.add_all(templates)
    await db.commit()


async def _seed_contents(db: AsyncSession) -> None:
    exists_content = (await db.execute(select(EducationContent).limit(1))).scalar_one_or_none()
    if exists_content:
        return

    contents = [
        EducationContent(
            title="如何在压力下保持稳定情绪",
            content_type="article",
            category="emotion",
            content="<p>从呼吸、睡眠和社交支持三个方面入手...</p>",
            summary="学习几个可立即执行的稳定情绪方法。",
            duration_minutes=8,
            difficulty="easy",
            sort_order=1,
        ),
        EducationContent(
            title="10分钟正念呼吸练习",
            content_type="meditation",
            category="mindfulness",
            content="<p>闭上眼睛，跟随呼吸节奏...</p>",
            summary="适合睡前放松和焦虑缓解。",
            audio_url="/uploads/audio/mindfulness_10min.mp3",
            duration_minutes=10,
            difficulty="easy",
            sort_order=2,
        ),
        EducationContent(
            title="睡眠改善计划入门",
            content_type="sleep_guide",
            category="wellbeing",
            content="<p>建立固定作息，减少睡前刺激...</p>",
            summary="从作息、环境和习惯三方面改善睡眠。",
            duration_minutes=12,
            difficulty="easy",
            sort_order=3,
        ),
    ]
    db.add_all(contents)
    await db.commit()


async def _seed_assessments_and_warnings(db: AsyncSession) -> None:
    users = (await db.execute(select(User).where(User.role == "user"))).scalars().all()
    user_map = {user.username: user for user in users}

    counselors = (await db.execute(select(User).where(User.role == "counselor"))).scalars().all()
    counselor_map = {counselor.username: counselor for counselor in counselors}

    risk_by_username: dict[str, RiskAssessment] = {}
    users_with_assessment = set((await db.execute(select(StructuredAssessment.user_id))).scalars().all())
    users_with_physiological_record = set((await db.execute(select(PhysiologicalRecord.user_id))).scalars().all())

    for user_seed in _USER_SEED_DATA:
        user = user_map.get(user_seed["username"])
        if not user:
            continue

        if user.id not in users_with_assessment:
            db.add(
                StructuredAssessment(
                    user_id=user.id,
                    assessment_type="comprehensive",
                    score=user_seed["assessment_score"],
                    severity=user_seed["assessment_severity"],
                    data_payload={
                        "stress_level": user_seed["stress_level"],
                        "sleep_duration": user_seed["sleep_duration"],
                    },
                )
            )
            risk = RiskAssessment(
                user_id=user.id,
                risk_score=user_seed["risk_score"],
                risk_level=user_seed["risk_level"],
                structured_score=user_seed["risk_score"],
                models_used=user_seed["models_used"],
                risk_factors=user_seed["risk_factors"],
                assessment_type="structured",
            )
            db.add(risk)
            risk_by_username[user.username] = risk

        physiological_record = user_seed.get("physiological_record")
        if physiological_record and user.id not in users_with_physiological_record:
            db.add(PhysiologicalRecord(user_id=user.id, **physiological_record))

    await db.flush()

    for user_seed in _USER_SEED_DATA:
        user = user_map.get(user_seed["username"])
        if not user or user_seed["username"] in risk_by_username:
            continue
        risk = (
            await db.execute(
                select(RiskAssessment)
                .where(RiskAssessment.user_id == user.id)
                .order_by(RiskAssessment.created_at.desc(), RiskAssessment.id.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        if risk:
            risk_by_username[user_seed["username"]] = risk

    users_with_warning = set((await db.execute(select(WarningNotification.user_id))).scalars().all())
    users_with_plan = set((await db.execute(select(InterventionPlan.user_id))).scalars().all())

    for user_seed in _USER_SEED_DATA:
        warning_seed = user_seed.get("warning")
        if not warning_seed:
            continue

        user = user_map.get(user_seed["username"])
        counselor = counselor_map.get(user_seed["counselor_username"])
        risk = risk_by_username.get(user_seed["username"])
        if not user or not counselor or not risk:
            continue

        if user.id not in users_with_warning:
            db.add(
                WarningNotification(
                    user_id=user.id,
                    risk_assessment_id=risk.id,
                    counselor_id=counselor.id,
                    previous_level=warning_seed["previous_level"],
                    current_level=warning_seed["current_level"],
                    trigger_reason=warning_seed["trigger_reason"],
                )
            )

        plan_seed = user_seed.get("plan")
        if not plan_seed or user.id in users_with_plan:
            continue

        plan = InterventionPlan(
            user_id=user.id,
            plan_name=plan_seed["plan_name"],
            risk_level=plan_seed["risk_level"],
            status=plan_seed["status"],
            start_date=date.today(),
            end_date=date.today(),
        )
        db.add(plan)
        await db.flush()

        db.add_all(
            InterventionTask(
                plan_id=plan.id,
                task_name=task_seed["task_name"],
                task_type=task_seed["task_type"],
                description=task_seed["description"],
                schedule=task_seed["schedule"],
                duration_minutes=task_seed["duration_minutes"],
                sort_order=sort_order,
            )
            for sort_order, task_seed in enumerate(plan_seed["tasks"])
        )

    await db.commit()


if __name__ == "__main__":
    import asyncio

    asyncio.run(seed_database())
