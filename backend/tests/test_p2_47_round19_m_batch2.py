"""ROUND_19 / M 批 2：统计口径 + 配置生效 + 事件时序 六条修复的守护测试。

对应审查报告 `outputs/CODE_REVIEW_2026-10-20.md` §二：
- M11 干预完成率可超过 100%（分子分母不同源）
- M12 预警设置三项：threshold_level 被硬编码下限架空；quiet_hours_* /
  notify_channels 能存能读能回显但无人消费
- M14 ``warning.created`` 事件在事务提交前发布
- M15 管理统计把已匿名化用户计入总数与高风险数
- M16 GDPR 可携权导出漏掉核心个人数据
- M10 ``end_date`` 当日数据被整体排除

写法约定（沿用本仓纪律）
------------------------
- 判据钉**交付形态下的不变量**，不钉偶发状态：完成率恒 ∈ [0,100]、
  事件只在提交后发出、匿名化后人数同步下降、导出清单 ⊇ 匿名化清单。
- M12 是产品行为变更：每条配置都钉"改前行为 / 改后行为"（见各 docstring），
  未接线的两项钉的是**显式不生效声明**，而不是"悄悄继续不生效"。
- M14 用**事件计数**断言（``event_bus.events_published`` 增量），
  不只用"handler 被调用过"——后者无法区分"提交前发"与"提交后发"。
"""

from __future__ import annotations

import ast
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

import pytest
from sqlalchemy import select

from app.core.event_bus import event_bus
from app.models.assessment import (
    DataDraft,
    PhysiologicalRecord,
    StructuredAssessment,
    TextEntry,
)
from app.models.counselor import ConsultationRecord
from app.models.intervention import (
    InterventionPlan,
    InterventionTask,
    TaskExecution,
)
from app.models.risk import RiskAssessment, WarningNotification, WarningSetting
from app.models.user import User

BACKEND = Path(__file__).resolve().parents[1]

# ── M11：干预完成率 ────────────────────────────────────────────────


class TestM11CompletionRate:
    """M11：完成率 = 至少完成过一次的任务数 / 任务总数，恒 ∈ [0, 100]。"""

    async def _make_plan(self, db_session, user_id: int) -> InterventionPlan:
        plan = InterventionPlan(
            user_id=user_id,
            plan_name="完成率口径计划",
            risk_level=3,
            status="active",
            start_date=date.today() - timedelta(days=7),
            end_date=date.today() + timedelta(days=7),
        )
        db_session.add(plan)
        await db_session.flush()
        return plan

    async def test_single_daily_task_three_checkins_is_100_not_300(
        self, db_session, seeded_user_id
    ) -> None:
        """改前：daily 任务连续打卡 3 天 ⇒ 300%；改后：100%。

        TaskExecution 唯一键是 (task_id, user_id, scheduled_date)，
        同一任务多天打卡天然产生多条记录 —— 旧口径把它们全算进分子。
        """
        from app.services.intervention_service import InterventionService

        plan = await self._make_plan(db_session, seeded_user_id)
        task = InterventionTask(
            plan_id=plan.id,
            task_name="每日呼吸训练",
            task_type="meditation",
            schedule="daily",
        )
        db_session.add(task)
        await db_session.flush()
        for offset in range(3):
            db_session.add(
                TaskExecution(
                    task_id=task.id,
                    user_id=seeded_user_id,
                    scheduled_date=date.today() - timedelta(days=offset),
                    status="completed",
                )
            )
        await db_session.commit()

        service = InterventionService(db_session)
        history = await service.get_history(seeded_user_id, 1, 20)
        item = next(i for i in history["items"] if i["plan_id"] == plan.id)
        assert item["completion_rate"] == 100.0, (
            f"1 个任务 3 次打卡应为 100%，实际 {item['completion_rate']} —— "
            "分子仍在数执行记录条数（M11 复发）"
        )

    async def test_two_tasks_one_completed_twice_is_50(
        self, db_session, seeded_user_id
    ) -> None:
        """分子按**任务**去重：任务 A 完成两次 + 任务 B 未完成 ⇒ 50%，不是 100%。"""
        from app.services.intervention_service import InterventionService

        plan = await self._make_plan(db_session, seeded_user_id)
        task_a = InterventionTask(
            plan_id=plan.id, task_name="A", task_type="meditation", schedule="daily"
        )
        task_b = InterventionTask(
            plan_id=plan.id, task_name="B", task_type="exercise", schedule="daily"
        )
        db_session.add_all([task_a, task_b])
        await db_session.flush()
        for offset in range(2):
            db_session.add(
                TaskExecution(
                    task_id=task_a.id,
                    user_id=seeded_user_id,
                    scheduled_date=date.today() - timedelta(days=offset),
                    status="completed",
                )
            )
        db_session.add(
            TaskExecution(
                task_id=task_b.id,
                user_id=seeded_user_id,
                scheduled_date=date.today(),
                status="pending",
            )
        )
        await db_session.commit()

        service = InterventionService(db_session)
        history = await service.get_history(seeded_user_id, 1, 20)
        item = next(i for i in history["items"] if i["plan_id"] == plan.id)
        assert item["completion_rate"] == 50.0

    async def test_stats_and_history_agree(self, db_session, seeded_user_id) -> None:
        """get_stats 的 SQL 聚合与 get_history 的逐条计算必须同数（P1-15 口径承诺）。"""
        from app.services.intervention_service import InterventionService

        plan = await self._make_plan(db_session, seeded_user_id)
        task_a = InterventionTask(
            plan_id=plan.id, task_name="A", task_type="meditation", schedule="daily"
        )
        task_b = InterventionTask(
            plan_id=plan.id, task_name="B", task_type="exercise", schedule="daily"
        )
        db_session.add_all([task_a, task_b])
        await db_session.flush()
        db_session.add(
            TaskExecution(
                task_id=task_a.id,
                user_id=seeded_user_id,
                scheduled_date=date.today(),
                status="completed",
            )
        )
        db_session.add(
            TaskExecution(
                task_id=task_a.id,
                user_id=seeded_user_id,
                scheduled_date=date.today() - timedelta(days=1),
                status="completed",
            )
        )
        await db_session.commit()

        service = InterventionService(db_session)
        history = await service.get_history(seeded_user_id, 1, 20)
        stats = await service.get_stats(seeded_user_id)
        item = next(i for i in history["items"] if i["plan_id"] == plan.id)
        assert item["completion_rate"] == 50.0
        assert stats["avg_completion"] == 50.0, (
            f"SQL 聚合 {stats['avg_completion']} 与逐条计算 {item['completion_rate']} "
            "不一致 —— 两处口径又漂了"
        )

    async def test_plan_without_tasks_is_zero(self, db_session, seeded_user_id) -> None:
        from app.services.intervention_service import InterventionService

        plan = await self._make_plan(db_session, seeded_user_id)
        await db_session.commit()

        service = InterventionService(db_session)
        history = await service.get_history(seeded_user_id, 1, 20)
        item = next(i for i in history["items"] if i["plan_id"] == plan.id)
        assert item["completion_rate"] == 0.0

    def test_out_of_range_is_clamped_and_counted(self) -> None:
        """纵深防御：越界读数被钳制并记静默降级（不静默放过 300%）。"""
        from app.core.metrics import silent_degradation_total
        from app.services.intervention_service import (
            COMPLETION_RATE_LOCATION,
            InterventionService,
        )

        before = sum(
            value
            for labels, value in silent_degradation_total.collect()
            if labels.get("location") == COMPLETION_RATE_LOCATION
        )
        assert InterventionService._completion_rate_percent(150, 100) == 100.0
        after = sum(
            value
            for labels, value in silent_degradation_total.collect()
            if labels.get("location") == COMPLETION_RATE_LOCATION
        )
        assert after == before + 1, "越界完成率没有记静默降级"
        assert InterventionService._completion_rate_percent(0, 0) == 0.0


# ── M12：预警设置三项 ──────────────────────────────────────────────


class TestM12ThresholdLevelEffective:
    """M12-1：threshold_level 真正参与预警判定。

    改前：`should_warn = risk_level >= 2` 硬编码，threshold_level 只能把阈值
    调高（二次比较）不能调低 —— seed 里 threshold_level=1 的用户是死配置。
    改后：阈值唯一来自用户设置（无设置回落 2），1 级即可预警、3 级可压掉 2 级。
    """

    async def _assess(self, db_session, user_id: int, level: int) -> RiskAssessment:
        risk = RiskAssessment(
            user_id=user_id,
            risk_score=level * 20,
            risk_level=level,
            models_used=["m"],
            risk_factors=[],
            assessment_type="text",
        )
        db_session.add(risk)
        await db_session.flush()
        return risk

    async def _trigger(self, db_session, risk: RiskAssessment):
        from app.services.risk_service import RiskService

        service = RiskService(db_session)
        return await service.trigger_warning_for_risk(risk)

    async def test_threshold_1_warns_at_level_1(
        self, db_session, seeded_user_id
    ) -> None:
        db_session.add(WarningSetting(user_id=seeded_user_id, threshold_level=1))
        await db_session.commit()

        risk = await self._assess(db_session, seeded_user_id, 1)
        warning = await self._trigger(db_session, risk)
        assert warning is not None, (
            "threshold_level=1 的用户在 1 级风险时应收到预警 —— "
            "硬编码 >= 2 复发（M12 主症状）"
        )

    async def test_threshold_3_suppresses_level_2(
        self, db_session, seeded_user_id
    ) -> None:
        db_session.add(WarningSetting(user_id=seeded_user_id, threshold_level=3))
        await db_session.commit()

        risk = await self._assess(db_session, seeded_user_id, 2)
        assert await self._trigger(db_session, risk) is None

    async def test_default_threshold_is_2(self, db_session, seeded_user_id) -> None:
        risk = await self._assess(db_session, seeded_user_id, 1)
        assert await self._trigger(db_session, risk) is None
        risk2 = await self._assess(db_session, seeded_user_id, 2)
        assert await self._trigger(db_session, risk2) is not None

    async def test_threshold_clamp_matches_schema_bounds(
        self, db_session, seeded_user_id
    ) -> None:
        """钳制区间与 schema/CheckConstraint（0..10）对齐，不再静默压到 4。

        改前设 10 会被存成 4（"永不预警"被偷偷改成"4 级就预警"）；
        改后 10 就是 10 —— 阈值高于风险等级上限即等价于不预警，意图不被篡改。
        """
        from app.services.warning_service import WarningService

        service = WarningService(db_session)
        await service.update_setting(seeded_user_id, {"threshold_level": 10})
        setting = await service.get_setting(seeded_user_id)
        assert setting.threshold_level == 10

        await service.update_setting(seeded_user_id, {"threshold_level": -5})
        setting = await service.get_setting(seeded_user_id)
        assert setting.threshold_level == 0


class TestM12NotEffectiveDeclared:
    """M12-2/3：quiet_hours_* 与 notify_channels 必须**显式声明不生效**。

    这两项目前没有任何分发链路读取（全仓只有写入与回显）。接线属于产品决策
    （免打扰一条危机预警该"推迟"还是"照发"涉及临床安全），本轮选③：
    保留字段但把状态说清楚 —— API 声明 + 日志告警 + 审计 detail 三处一致。
    """

    def test_get_response_declares_effectiveness(
        self, client, seeded_user_id, auth_headers
    ) -> None:
        res = client.get(
            "/api/v1/user/warning-settings", headers=auth_headers
        )
        assert res.status_code == 200
        body = res.json()["data"]
        assert body["effective"]["threshold_level"] is True
        assert body["effective"]["quiet_hours"] is False
        assert body["effective"]["notify_channels"] is False
        notice = body["not_effective_notice"]
        assert "quiet_hours_start" in notice and "notify_channels" in notice

    def test_update_warns_and_audits_not_effective(
        self, client, seeded_user_id, auth_headers, db_session, caplog
    ) -> None:
        res = client.put(
            "/api/v1/user/warning-settings",
            headers=auth_headers,
            json={
                "quiet_hours_start": "22:00:00",
                "quiet_hours_end": "07:00:00",
                "notify_channels": {"in_app": True},
            },
        )
        assert res.status_code == 200

        assert any(
            "warning_setting.not_effective" in record.message
            for record in caplog.records
        ), "设置了不生效字段却没有告警日志"

        async def _audit_detail():
            from app.models.admin import OperationLog

            row = (
                (
                    await db_session.execute(
                        select(OperationLog)
                        .where(
                            OperationLog.action_type == "update_warning_setting"
                        )
                        .order_by(OperationLog.id.desc())
                    )
                )
                .scalars()
                .first()
            )
            return row.detail if row else None

        detail_raw = self._run(_audit_detail())
        assert detail_raw is not None
        detail = (
            json.loads(detail_raw) if isinstance(detail_raw, str) else detail_raw
        )
        assert sorted(detail["not_effective"]) == [
            "notify_channels",
            "quiet_hours_end",
            "quiet_hours_start",
        ], "审计 detail 没有记录哪些字段不生效"

    def test_not_effective_registry_excludes_threshold_level(self) -> None:
        """登记表不得把已生效的 threshold_level 也算进去（否则声明失真）。"""
        from app.services.warning_service import _NOT_EFFECTIVE_KEYS

        assert "threshold_level" not in _NOT_EFFECTIVE_KEYS
        assert _NOT_EFFECTIVE_KEYS == {
            "quiet_hours_start",
            "quiet_hours_end",
            "notify_channels",
        }

    @staticmethod
    def _run(coro):
        from tests.conftest import run  # noqa: PLC0415 - 复用会话级事件循环助手

        return run(coro)


# ── M14：事件提交后发布 ────────────────────────────────────────────


class TestM14EventAfterCommit:
    """M14：``warning.created`` 只在事务提交后发布。

    判据是**事件计数**：提交前 ``events_published`` 不变、提交后 +1、
    回滚后不变。只断言"handler 收到过"无法区分提交前/后发布。

    为什么自带内存库：``tests/conftest.py`` 的 ``db_session`` fixture 把
    ``session.commit`` 换成了 ``flush``（外层事务在 teardown 统一回滚），
    ``after_commit`` 在该 session 上永远不会触发。要验证**真实提交语义**，
    必须用一条自己掌控生命周期的 session + engine。
    """

    @pytest.fixture
    def counting_bus(self):
        """统计已发布事件数（不订阅 handler，避免消费循环时序干扰判据）。"""
        before = event_bus.events_published
        yield
        assert event_bus.events_published >= before  # 单调不减

    @staticmethod
    async def _make_session():
        """独立内存库 + 建表 + 一个用户，返回 (engine, session)。"""
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

        from app.core.pii_crypto import compute_blind_index
        from app.models import Base

        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        session = AsyncSession(engine)
        session.add(
            User(
                id=1,
                username="m14_user",
                email="m14@test.com",
                email_hash=compute_blind_index("m14@test.com", "email"),
                password_hash="x",
                role="user",
                status="active",
            )
        )
        await session.commit()
        return engine, session

    async def _warn(self, session) -> None:
        from app.services.risk_service import RiskService

        risk = RiskAssessment(
            user_id=1,
            risk_score=60,
            risk_level=3,
            models_used=["m"],
            risk_factors=[],
            assessment_type="text",
        )
        session.add(risk)
        await session.flush()
        service = RiskService(session)
        warning = await service.trigger_warning_for_risk(risk)
        assert warning is not None, "前置条件失败：3 级风险应触发预警"
        return warning

    async def test_event_published_only_after_commit(self, counting_bus) -> None:
        engine, session = await self._make_session()
        try:
            before = event_bus.events_published
            await self._warn(session)
            assert event_bus.events_published == before, (
                "事件在 commit 之前就发出去了 —— 订阅方回查会读到空行（M14 复发）"
            )
            await session.commit()
            assert event_bus.events_published == before + 1, "commit 之后事件没有发出"
        finally:
            await session.close()
            await engine.dispose()

    async def test_event_not_published_on_rollback(self, counting_bus) -> None:
        engine, session = await self._make_session()
        try:
            before = event_bus.events_published
            await self._warn(session)
            await session.rollback()
            assert event_bus.events_published == before, (
                "事务回滚了事件却照发 —— '事件已发、数据不存在'（M14 复发）"
            )
        finally:
            await session.close()
            await engine.dispose()

    async def test_no_warning_row_after_rollback(self, counting_bus) -> None:
        """配套验证：回滚后库里确实没有那条预警（事件不是"发了但数据在"）。"""
        engine, session = await self._make_session()
        try:
            await self._warn(session)
            await session.rollback()
            rows = (
                (await session.execute(select(WarningNotification))).scalars().all()
            )
            assert rows == []
        finally:
            await session.close()
            await engine.dispose()


# ── M15：统计排除匿名化用户 ────────────────────────────────────────


class TestM15StatsExcludeAnonymized:
    """M15：匿名化后 total_users / total_counselors / 高风险数同步下降。

    匿名化只置 ``User.status='deleted'`` 不删行（见
    ``gdpr_service_anonymize._step_anonymize_user_core``），本测试直接置该状态
    复现其**后置条件**，锁住统计口径对它的响应。
    """

    async def _stats(self, db_session) -> dict:
        from app.services.admin_service import AdminService

        return await AdminService(db_session).get_stats()

    async def test_anonymized_user_drops_out_of_totals(
        self, db_session, seeded_user_id
    ) -> None:
        from app.core.pii_crypto import compute_blind_index

        # 第二个普通用户 + 一条高风险评估
        db_session.add(
            User(
                id=90,
                username="u90",
                email="u90@test.com",
                email_hash=compute_blind_index("u90@test.com", "email"),
                password_hash="x",
                role="user",
                status="active",
            )
        )
        db_session.add(
            RiskAssessment(
                user_id=90,
                risk_score=90,
                risk_level=4,
                models_used=["m"],
                risk_factors=[],
                assessment_type="text",
            )
        )
        await db_session.commit()

        before = await self._stats(db_session)
        assert before["high_risk_users"] >= 1
        users_before = before["total_users"]

        # 匿名化后置条件：status -> deleted（行仍在）
        user = (await db_session.execute(select(User).where(User.id == 90))).scalar_one()
        user.status = "deleted"
        await db_session.commit()

        after = await self._stats(db_session)
        assert after["total_users"] == users_before - 1, (
            "匿名化后总用户数没下降 —— 仪表盘人数只增不减（M15 复发）"
        )
        assert after["high_risk_users"] == before["high_risk_users"] - 1, (
            "高风险数仍包含已行使被遗忘权的主体（M15 复发）"
        )

    async def test_anonymized_counselor_drops_out_of_counselors(
        self, db_session, seeded_user_id
    ) -> None:
        from app.core.pii_crypto import compute_blind_index

        db_session.add(
            User(
                id=91,
                username="c91",
                email="c91@test.com",
                email_hash=compute_blind_index("c91@test.com", "email"),
                password_hash="x",
                role="counselor",
                status="active",
            )
        )
        await db_session.commit()

        before = await self._stats(db_session)
        user = (await db_session.execute(select(User).where(User.id == 91))).scalar_one()
        user.status = "deleted"
        await db_session.commit()

        after = await self._stats(db_session)
        assert after["total_counselors"] == before["total_counselors"] - 1


# ── M16：GDPR 导出覆盖面对齐匿名化 ─────────────────────────────────

# 对照表：持有用户个人数据的模型 → 导出 section 键。
# 两个方向都被 tests/test_export_coverage_matches_anonymization 锁死：
#   1. 匿名化流程触及的每个模型都必须出现在本表（不能擦了却不给导出）；
#   2. 本表的每个 section 键都必须出现在 export_user_data 的结果里。
MODEL_TO_SECTION: dict[str, str] = {
    "User": "account",
    "UserProfile": "profile",
    "EmergencyContact": "emergency_contacts",
    "UserCounselorBinding": "counselor_bindings",
    "RiskAssessment": "risk_assessments",
    "WarningNotification": "warnings",
    "CrisisEvent": "crisis_events",
    "InterventionPlan": "intervention_plans",
    "InterventionTask": "intervention_tasks",
    "OperationLog": "operation_logs",
    # M16 修复（ROUND_19）新增的 6 项 —— 原导出清单正好漏掉这些
    "StructuredAssessment": "structured_assessments",
    "TextEntry": "text_entries",
    "PhysiologicalRecord": "physiological_records",
    "ConsultationRecord": "consultation_records",
    "TaskExecution": "task_executions",
    "DataDraft": "data_drafts",
}


class TestM16GdprExportCoverage:
    """M16：可携权导出不得漏掉会被匿名化擦掉的个人数据。"""

    async def test_export_contains_previously_missing_sections(
        self, db_session, seeded_user_id
    ) -> None:
        from app.services.gdpr_service import GDPRService

        user_id = seeded_user_id
        db_session.add(
            StructuredAssessment(
                user_id=user_id,
                assessment_type="phq9",
                score=12,
                severity="moderate",
                data_payload={"q1": 2, "q9": 1},
            )
        )
        db_session.add(
            TextEntry(
                user_id=user_id,
                entry_type="diary",
                content="今天很难过",
                emotion_tags=["sad"],
            )
        )
        db_session.add(
            PhysiologicalRecord(
                user_id=user_id, source="manual", sleep_hours=6.5, heart_rate=72
            )
        )
        db_session.add(
            ConsultationRecord(
                user_id=user_id, main_topics="睡眠问题", notes="第 3 次咨询"
            )
        )
        plan = InterventionPlan(
            user_id=user_id,
            plan_name="导出覆盖计划",
            risk_level=3,
            status="active",
            start_date=date.today(),
        )
        db_session.add(plan)
        await db_session.flush()
        task = InterventionTask(
            plan_id=plan.id, task_name="T", task_type="meditation", schedule="daily"
        )
        db_session.add(task)
        await db_session.flush()
        db_session.add(
            TaskExecution(
                task_id=task.id,
                user_id=user_id,
                scheduled_date=date.today(),
                status="completed",
                feedback_note="感觉有帮助",
            )
        )
        db_session.add(
            DataDraft(user_id=user_id, draft_type="phq9", data_payload={"q1": 3})
        )
        await db_session.commit()

        data = await GDPRService(db_session).export_user_data(user_id)

        assert data["structured_assessments"][0]["data_payload"] == {"q1": 2, "q9": 1}
        assert data["text_entries"][0]["content"] == "今天很难过"
        assert data["physiological_records"][0]["heart_rate"] == 72
        assert data["consultation_records"][0]["notes"] == "第 3 次咨询"
        assert data["task_executions"][0]["feedback_note"] == "感觉有帮助"
        assert data["data_drafts"][0]["data_payload"] == {"q1": 3}
        # summary 与数组同步（不能"数组里有、摘要里没有"）
        assert data["summary"]["text_entries_count"] == 1
        assert data["summary"]["structured_assessments_count"] == 1

    async def test_export_coverage_matches_anonymization(
        self, db_session, seeded_user_id
    ) -> None:
        """对照表闸门：匿名化触及的模型 ⊆ 导出清单，且每条都真的在导出里。"""
        from app.services.gdpr_service import GDPRService

        # 1) 从匿名化模块抽出它实际导入的模型名（AST，不靠文本 grep）。
        # 不能拿全部 ast.Name 与 MODEL_TO_SECTION 取交集——交集里的名字按定义
        # 都在表中，断言恒空（ROUND_00 审计 B2）。有效判据是：匿名化模块从
        # app.models 导入的每个模型都必须登记在对照表里。
        anon_src = (
            BACKEND / "app" / "services" / "gdpr_service_anonymize.py"
        ).read_text(encoding="utf-8")
        tree = ast.parse(anon_src)
        touched = {
            node.id
            for node in ast.walk(tree)
            if isinstance(node, ast.Name)
        }
        imported_models = {
            alias.name
            for node in ast.walk(tree)
            if isinstance(node, ast.ImportFrom)
            and node.module
            and node.module.startswith("app.models")
            for alias in node.names
        }
        assert imported_models, "未能从匿名化模块解析出任何 app.models 导入（AST 结构变了？）"
        # RefreshTokenSession 只存 jti / 过期 / 吊销时间，不含 PII；匿名化撤销它是
        # 安全动作（登出所有会话），不是擦除个人数据 ⇒ 明确豁免可携权导出。
        security_only = {"RefreshTokenSession"}
        assert security_only <= imported_models, "豁免项必须真的被匿名化模块导入（防陈旧豁免）"
        missing = sorted(imported_models - set(MODEL_TO_SECTION) - security_only)
        assert not missing, f"匿名化模块引用但未登记的模型: {missing}"

        # 反向：登记表里声称"匿名化会擦"的模型，匿名化模块必须真的提到。
        # OperationLog 例外：匿名化**写**它（合规审计）而不是擦它，
        # 但用户本人的操作日志仍属于可携权数据，故在导出清单里。
        audit_only = {"OperationLog"}
        unbacked = sorted(
            name
            for name in MODEL_TO_SECTION
            if name not in touched and name not in audit_only | {"User", "UserProfile"}
        )
        assert not unbacked, (
            f"对照表声称这些模型被匿名化，但匿名化模块没引用它们: {unbacked}"
        )

        # 2) 每个 section 键都真实出现在导出结果中
        data = await GDPRService(db_session).export_user_data(seeded_user_id)
        for model, section in MODEL_TO_SECTION.items():
            assert section in data, f"导出缺少 {model} 对应的 section: {section}"

    def test_streaming_sections_match_oneshot_export(self) -> None:
        """流式导出（gdpr.py 的 sections 清单）与一次性导出必须同清单。"""
        gdpr_api = (BACKEND / "app" / "api" / "v1" / "gdpr.py").read_text(
            encoding="utf-8"
        )
        export_mod = (BACKEND / "app" / "services" / "gdpr_service_export.py")
        tree = ast.parse(export_mod.read_text(encoding="utf-8"))
        iterators = {
            node.name
            for node in ast.walk(tree)
            if isinstance(node, ast.AsyncFunctionDef) and node.name.startswith("iter_")
        }
        assert iterators, "没找到流式迭代器"

        registered = {
            line.split('"')[1]
            for line in gdpr_api.splitlines()
            if 'service.iter_' in line
        }
        missing = sorted(iterators - {f"iter_{name}" for name in registered})
        assert not missing, f"有迭代器但没接进流式导出: {missing}"

        # 一次性导出的每个列表 section 都必须有对应迭代器
        for section in MODEL_TO_SECTION.values():
            if section in {"account", "profile"}:
                continue
            assert f"iter_{section}" in iterators, (
                f"section {section} 没有对应流式迭代器"
            )


# ── M10：end_date 当日数据 ────────────────────────────────────────


class TestM10EndDateInclusive:
    """M10：日期型 end_date 扩张到当天结束，当日数据不再被整体排除。"""

    def test_date_only_end_expands_to_end_of_day(self) -> None:
        from app.core.datetime_params import parse_range_params

        _, end = parse_range_params(None, "2026-10-20")
        assert end == datetime(2026, 10, 20, 23, 59, 59, 999999)

    def test_start_stays_at_midnight(self) -> None:
        from app.core.datetime_params import parse_range_params

        start, _ = parse_range_params("2026-10-01", None)
        assert start == datetime(2026, 10, 1, 0, 0)

    def test_datetime_value_not_expanded(self) -> None:
        """显式给了时刻就按字面值 —— 扩张会把 12:30 之后的记录也算进来。"""
        from app.core.datetime_params import parse_datetime_param

        assert parse_datetime_param("2026-10-20T12:30:00") == datetime(
            2026, 10, 20, 12, 30
        )

    def test_aware_datetime_normalized_to_naive_utc(self) -> None:
        from app.core.datetime_params import parse_datetime_param

        assert parse_datetime_param("2026-10-20T12:30:00Z") == datetime(
            2026, 10, 20, 12, 30
        )

    def test_invalid_value_raises_value_error(self) -> None:
        from app.core.datetime_params import parse_datetime_param

        with pytest.raises(ValueError, match="ISO8601"):
            parse_datetime_param("not-a-date")

    async def test_history_includes_today(
        self, db_session, seeded_user_id
    ) -> None:
        """端到端：end_date == 今天 ⇒ 今天创建的记录必须出现在结果里。"""
        from app.services.user_data_service import UserDataService

        db_session.add(
            TextEntry(
                user_id=seeded_user_id,
                entry_type="diary",
                content="今天的日记",
                emotion_tags=[],
            )
        )
        await db_session.commit()

        service = UserDataService(db_session)
        end_dt = datetime.combine(date.today(), datetime.max.time())
        result = await service.get_history(
            seeded_user_id, "text", 1, 20, None, end_dt
        )
        assert result["total"] >= 1, "end_date=今天时今天的记录被漏掉了（M10 复发）"
        assert any(i["data"]["content"] == "今天的日记" for i in result["items"])
