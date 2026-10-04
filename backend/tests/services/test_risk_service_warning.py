"""WarningInterventionMixin (app/services/risk_service_warning.py) 核心逻辑单元测试.

覆盖目标模块中带明确修复标注的分支, 防止回归:

- H-Svc-7: previous.risk_level 为 None 时降级为 0, 不得抛 TypeError
- L-08: should_warn 复用; 等级上升/持平生成不同 trigger_reason
- C-2: warning 插入走 savepoint (begin_nested), 重复插入时回读已有记录
- M17: 风险升级时"先建新计划再取消旧计划"; 无模板时不得让用户失去干预
- H-Svc-8: 无活跃模板时返回 None 并记录告警, 不静默掩盖
- 模板任务校验 (_validate_and_normalize_template_tasks) 的全部非法输入分支

测试依赖 conftest 的 db_session (commit -> flush, 每用例回滚)。
"""

from __future__ import annotations

from datetime import datetime, timezone
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select
from sqlalchemy.exc import IntegrityError

from app.core.states import BindingStatus
from app.models.intervention import (
    InterventionPlan,
    InterventionTask,
    InterventionTemplate,
)
from app.models.risk import RiskAssessment, WarningNotification, WarningSetting
from app.models.user import UserCounselorBinding
from app.services.risk_service import RiskService

_normalize = RiskService._validate_and_normalize_template_tasks


def _make_risk(user_id: int, level: int, score: float | None = None) -> RiskAssessment:
    return RiskAssessment(
        user_id=user_id,
        risk_score=score if score is not None else level * 20,
        risk_level=level,
        structured_score=score if score is not None else level * 20,
        models_used=["unit-test"],
        risk_factors=[],
        assessment_type="structured",
        created_at=datetime.now(timezone.utc),
    )


def _make_template(
    name: str,
    levels: list[int],
    tasks: list[dict] | None = None,
    weeks: int = 4,
    status: str = "active",
) -> InterventionTemplate:
    return InterventionTemplate(
        template_name=name,
        applicable_levels=levels,
        task_list=tasks
        if tasks is not None
        else [{"task_name": "呼吸训练", "task_type": "meditation", "duration_minutes": 10}],
        estimated_weeks=weeks,
        status=status,
    )


def _result(scalar=None, first=None) -> MagicMock:
    """构造一个假的 SQLAlchemy Result: 支持 .scalar_one_or_none() 与 .scalars().first()。"""
    mock = MagicMock()
    mock.scalar_one_or_none.return_value = scalar
    mock.scalars.return_value.first.return_value = first
    return mock


def _make_plan(user_id: int, risk_level: int, name: str = "旧计划") -> InterventionPlan:
    today = datetime.now(timezone.utc).date()
    return InterventionPlan(
        user_id=user_id,
        plan_name=name,
        risk_level=risk_level,
        status="active",
        start_date=today,
        end_date=today,
    )


class TestValidateAndNormalizeTemplateTasks:
    """纯函数分支, 不涉及数据库。"""

    def test_non_list_raises(self):
        with pytest.raises(ValueError, match="任务列表格式错误"):
            _normalize({"task_name": "x"}, "模板A")

    def test_empty_list_raises(self):
        with pytest.raises(ValueError, match="任务列表不能为空"):
            _normalize([], "模板A")

    def test_non_dict_item_raises(self):
        with pytest.raises(ValueError, match="第 2 个任务格式错误"):
            _normalize([{"task_name": "a", "task_type": "b"}, "oops"], "模板A")

    def test_missing_task_name_raises(self):
        with pytest.raises(ValueError, match="第 1 个任务缺少必要字段"):
            _normalize([{"task_type": "meditation"}], "模板A")

    def test_blank_task_type_raises(self):
        # 纯空白字符串经 strip() 后为空, 同样视为缺失
        with pytest.raises(ValueError, match="第 1 个任务缺少必要字段"):
            _normalize([{"task_name": "呼吸", "task_type": "   "}], "模板A")

    def test_non_integer_duration_raises(self):
        with pytest.raises(ValueError, match="第 1 个任务时长非法"):
            _normalize(
                [{"task_name": "a", "task_type": "b", "duration_minutes": "abc"}],
                "模板A",
            )

    def test_non_positive_duration_raises(self):
        with pytest.raises(ValueError, match="任务时长必须大于0"):
            _normalize(
                [{"task_name": "a", "task_type": "b", "duration_minutes": 0}], "模板A"
            )

    def test_defaults_applied(self):
        assert _normalize([{"task_name": "a", "task_type": "b"}], "模板A") == [
            {
                "task_name": "a",
                "task_type": "b",
                "description": "",
                "schedule": "daily",
                "duration_minutes": 15,
            }
        ]

    def test_explicit_values_preserved_and_stripped(self):
        result = _normalize(
            [
                {
                    "task_name": "  正念呼吸  ",
                    "task_type": " meditation ",
                    "description": " 每日一次 ",
                    "schedule": " weekly ",
                    "duration_minutes": "20",  # 字符串数字应被 int() 接受
                }
            ],
            "模板A",
        )
        assert result[0] == {
            "task_name": "正念呼吸",
            "task_type": "meditation",
            "description": "每日一次",
            "schedule": "weekly",
            "duration_minutes": 20,
        }

    def test_blank_schedule_falls_back_to_daily(self):
        result = _normalize(
            [{"task_name": "a", "task_type": "b", "schedule": "  "}], "模板A"
        )
        assert result[0]["schedule"] == "daily"

    def test_multiple_tasks_keep_order(self):
        result = _normalize(
            [
                {"task_name": "t1", "task_type": "a"},
                {"task_name": "t2", "task_type": "b"},
                {"task_name": "t3", "task_type": "c"},
            ],
            "模板A",
        )
        assert [t["task_name"] for t in result] == ["t1", "t2", "t3"]


class TestCheckWarningTrigger:
    @pytest.mark.asyncio
    async def test_no_warning_below_level_2(self, db_session, seeded_user_id):
        risk = _make_risk(seeded_user_id, level=1)
        db_session.add(risk)
        await db_session.flush()

        service = RiskService(db_session)
        assert await service.trigger_warning_for_risk(risk) is None

    @pytest.mark.asyncio
    async def test_first_assessment_previous_level_defaults_to_zero(
        self, db_session, seeded_user_id
    ):
        """H-Svc-7 (无历史评估分支): previous_level 应为 0, 不抛 TypeError。"""
        risk = _make_risk(seeded_user_id, level=2)
        db_session.add(risk)
        await db_session.flush()

        service = RiskService(db_session)
        warning = await service.trigger_warning_for_risk(risk)

        assert warning is not None
        assert warning.previous_level == 0
        assert warning.current_level == 2

    @pytest.mark.asyncio
    async def test_previous_level_none_treated_as_zero(
        self, db_session, seeded_user_id
    ):
        """H-Svc-7 (risk_level 为 None 分支): 同样降级为 0。

        直接用 stub 而非真实记录, 因为 RiskAssessment.risk_level 在库层面是
        NOT NULL, 无法真的插入一条 risk_level=NULL 的历史评估。
        """
        risk = _make_risk(seeded_user_id, level=3)
        db_session.add(risk)
        await db_session.flush()

        previous_stub = SimpleNamespace(risk_level=None)
        # 调用顺序: 历史评估 / 告警设置 / 重复检查 / 咨询师绑定
        fake_results = [
            _result(scalar=previous_stub),
            _result(scalar=None),
            _result(scalar=None),
            _result(first=None),
        ]

        service = RiskService(db_session)
        with patch.object(
            db_session, "execute", AsyncMock(side_effect=fake_results)
        ):
            warning = await service.trigger_warning_for_risk(risk)

        assert warning is not None
        assert warning.previous_level == 0
        assert warning.current_level == 3

    @pytest.mark.asyncio
    async def test_reason_text_on_level_increase(self, db_session, seeded_user_id):
        db_session.add(_make_risk(seeded_user_id, level=1))
        await db_session.flush()
        current = _make_risk(seeded_user_id, level=3)
        db_session.add(current)
        await db_session.flush()

        service = RiskService(db_session)
        warning = await service.trigger_warning_for_risk(current)

        assert warning is not None
        assert "从1级上升到3级" in warning.trigger_reason

    @pytest.mark.asyncio
    async def test_reason_text_when_level_not_increased(
        self, db_session, seeded_user_id
    ):
        """L-08: 等级持平时走 else 分支, reason 不含"上升"。"""
        db_session.add(_make_risk(seeded_user_id, level=3))
        await db_session.flush()
        current = _make_risk(seeded_user_id, level=3)
        db_session.add(current)
        await db_session.flush()

        service = RiskService(db_session)
        warning = await service.trigger_warning_for_risk(current)

        assert warning is not None
        assert "当前风险等级为3级" in warning.trigger_reason
        assert "上升" not in warning.trigger_reason

    @pytest.mark.asyncio
    async def test_user_threshold_blocks_warning(self, db_session, seeded_user_id):
        db_session.add(WarningSetting(user_id=seeded_user_id, threshold_level=4))
        risk = _make_risk(seeded_user_id, level=3)
        db_session.add(risk)
        await db_session.flush()

        service = RiskService(db_session)
        assert await service.trigger_warning_for_risk(risk) is None

    @pytest.mark.asyncio
    async def test_user_threshold_allows_warning_at_or_above(
        self, db_session, seeded_user_id
    ):
        db_session.add(WarningSetting(user_id=seeded_user_id, threshold_level=3))
        risk = _make_risk(seeded_user_id, level=3)
        db_session.add(risk)
        await db_session.flush()

        service = RiskService(db_session)
        assert await service.trigger_warning_for_risk(risk) is not None

    @pytest.mark.asyncio
    async def test_existing_warning_is_returned_unchanged(
        self, db_session, seeded_user_id
    ):
        """同一 risk_assessment 已有告警时直接回读, 不重复插入。"""
        risk = _make_risk(seeded_user_id, level=3)
        db_session.add(risk)
        await db_session.flush()
        existing = WarningNotification(
            user_id=seeded_user_id,
            risk_assessment_id=risk.id,
            previous_level=0,
            current_level=3,
            trigger_reason="已存在的告警",
        )
        db_session.add(existing)
        await db_session.flush()

        service = RiskService(db_session)
        warning = await service.trigger_warning_for_risk(risk)

        assert warning is not None
        assert warning.id == existing.id
        assert warning.trigger_reason == "已存在的告警"

    @pytest.mark.asyncio
    async def test_counselor_binding_attached(self, db_session, seeded_user_id):
        db_session.add(
            UserCounselorBinding(
                user_id=seeded_user_id,
                counselor_id=2,
                bind_code="B001",
                status=BindingStatus.ACTIVE,
                bound_at=datetime.now(timezone.utc),
            )
        )
        risk = _make_risk(seeded_user_id, level=3)
        db_session.add(risk)
        await db_session.flush()

        service = RiskService(db_session)
        warning = await service.trigger_warning_for_risk(risk)

        assert warning is not None
        assert warning.counselor_id == 2

    @pytest.mark.asyncio
    async def test_inactive_binding_is_ignored(self, db_session, seeded_user_id):
        db_session.add(
            UserCounselorBinding(
                user_id=seeded_user_id,
                counselor_id=2,
                bind_code="B002",
                status=BindingStatus.INACTIVE,
                bound_at=datetime.now(timezone.utc),
            )
        )
        risk = _make_risk(seeded_user_id, level=3)
        db_session.add(risk)
        await db_session.flush()

        service = RiskService(db_session)
        warning = await service.trigger_warning_for_risk(risk)

        assert warning is not None
        assert warning.counselor_id is None

    @pytest.mark.asyncio
    async def test_warning_created_event_published(self, db_session, seeded_user_id):
        risk = _make_risk(seeded_user_id, level=3)
        db_session.add(risk)
        await db_session.flush()

        service = RiskService(db_session)
        with patch("app.services.risk_service_warning.event_bus") as mock_bus:
            mock_bus.publish = AsyncMock()
            warning = await service.trigger_warning_for_risk(risk)

        assert warning is not None
        mock_bus.publish.assert_awaited_once()
        event_type, payload = mock_bus.publish.await_args.args
        assert event_type == "warning.created"
        assert payload["warning_id"] == warning.id
        assert payload["user_id"] == seeded_user_id
        assert payload["current_level"] == 3

    @pytest.mark.asyncio
    async def test_event_publish_failure_does_not_break_flow(
        self, db_session, seeded_user_id
    ):
        """事件总线异常被吞掉, 告警仍需正常返回。"""
        risk = _make_risk(seeded_user_id, level=3)
        db_session.add(risk)
        await db_session.flush()

        service = RiskService(db_session)
        with patch("app.services.risk_service_warning.event_bus") as mock_bus:
            mock_bus.publish = AsyncMock(side_effect=RuntimeError("bus down"))
            warning = await service.trigger_warning_for_risk(risk)

        assert warning is not None
        assert warning.current_level == 3

    @pytest.mark.asyncio
    async def test_duplicate_insert_falls_back_to_existing(
        self, db_session, seeded_user_id
    ):
        """C-2: savepoint 内 IntegrityError 时回读已有告警, 不向上抛。

        必须让"首次重复检查"返回 None, 否则代码会在到达 savepoint 之前就提前
        return 已有告警, 覆盖不到 C-2 的回读分支。冲突由并发插入造成, 因此
        第二次重复检查(冲突后)才返回 existing。
        """
        risk = _make_risk(seeded_user_id, level=3)
        db_session.add(risk)
        await db_session.flush()

        existing = WarningNotification(
            user_id=seeded_user_id,
            risk_assessment_id=risk.id,
            previous_level=1,
            current_level=3,
            trigger_reason="并发插入胜出",
        )
        db_session.add(existing)
        await db_session.flush()

        # 调用顺序: 历史评估 / 告警设置 / 首次重复检查 / 冲突后重查
        fake_results = [
            _result(scalar=None),
            _result(scalar=None),
            _result(scalar=None),
            _result(scalar=existing),
        ]

        service = RiskService(db_session)
        with (
            patch.object(db_session, "execute", AsyncMock(side_effect=fake_results)),
            patch.object(
                db_session,
                "begin_nested",
                side_effect=IntegrityError("INSERT", {}, Exception("UNIQUE")),
            ),
        ):
            warning = await service.trigger_warning_for_risk(risk)

        assert warning is not None
        assert warning.id == existing.id
        assert warning.trigger_reason == "并发插入胜出"

    @pytest.mark.asyncio
    async def test_duplicate_insert_reraises_when_no_warning_found(
        self, db_session, seeded_user_id
    ):
        """C-2 兜底: 冲突后重查仍为空说明不是重复插入, 必须向上抛 IntegrityError。"""
        risk = _make_risk(seeded_user_id, level=3)
        db_session.add(risk)
        await db_session.flush()

        service = RiskService(db_session)
        with (
            patch.object(
                db_session, "execute", AsyncMock(return_value=_result(scalar=None))
            ),
            patch.object(
                db_session,
                "begin_nested",
                side_effect=IntegrityError("INSERT", {}, Exception("other")),
            ),
        ):
            with pytest.raises(IntegrityError):
                await service.trigger_warning_for_risk(risk)


class TestAutoGenerateIntervention:
    @pytest.mark.asyncio
    async def test_skipped_below_level_2(self, db_session, seeded_user_id):
        db_session.add(_make_template("T", [1]))
        risk = _make_risk(seeded_user_id, level=1)
        db_session.add(risk)
        await db_session.flush()

        service = RiskService(db_session)
        await service.generate_intervention_for_risk(risk)

        plans = (await db_session.execute(select(InterventionPlan))).scalars().all()
        assert plans == []

    @pytest.mark.asyncio
    async def test_generates_plan_at_or_above_level_2(
        self, db_session, seeded_user_id
    ):
        """generate_intervention_for_risk 在 risk_level >= 2 时委托给 _auto_generate_intervention。"""
        db_session.add(_make_template("中风险模板", [2]))
        risk = _make_risk(seeded_user_id, level=2)
        db_session.add(risk)
        await db_session.flush()

        service = RiskService(db_session)
        await service.generate_intervention_for_risk(risk)

        plans = (await db_session.execute(select(InterventionPlan))).scalars().all()
        assert len(plans) == 1
        assert plans[0].plan_name == "中风险模板"
        assert plans[0].risk_level == 2

    @pytest.mark.asyncio
    async def test_creates_plan_and_tasks_from_matching_template(
        self, db_session, seeded_user_id
    ):
        db_session.add(
            _make_template(
                "高风险模板",
                [3],
                tasks=[
                    {
                        "task_name": "呼吸训练",
                        "task_type": "meditation",
                        "duration_minutes": 10,
                    },
                    {"task_name": "运动", "task_type": "exercise"},
                ],
                weeks=6,
            )
        )
        await db_session.flush()

        service = RiskService(db_session)
        plan = await service._auto_generate_intervention(
            user_id=seeded_user_id, risk_level=3
        )

        assert plan is not None
        assert plan.risk_level == 3
        assert plan.status == "active"
        assert plan.plan_name == "高风险模板"
        assert (plan.end_date - plan.start_date).days == 42  # 6 周

        tasks = (
            (
                await db_session.execute(
                    select(InterventionTask).where(InterventionTask.plan_id == plan.id)
                )
            )
            .scalars()
            .all()
        )
        assert len(tasks) == 2
        assert sorted(t.sort_order for t in tasks) == [0, 1]
        assert next(t for t in tasks if t.task_name == "呼吸训练").duration_minutes == 10
        assert next(t for t in tasks if t.task_name == "运动").duration_minutes == 15

    @pytest.mark.asyncio
    async def test_existing_plan_returned_when_level_not_higher(
        self, db_session, seeded_user_id
    ):
        db_session.add(_make_template("T", [2]))
        existing = _make_plan(seeded_user_id, risk_level=3)
        db_session.add(existing)
        await db_session.flush()

        service = RiskService(db_session)
        result = await service._auto_generate_intervention(
            user_id=seeded_user_id, risk_level=2
        )

        assert result is not None
        assert result.id == existing.id
        assert result.status == "active"

    @pytest.mark.asyncio
    async def test_escalation_replaces_old_plan(self, db_session, seeded_user_id):
        """M17: 等级升高时先建新计划, 成功后再取消旧计划。"""
        db_session.add(_make_template("升级模板", [4]))
        existing = _make_plan(seeded_user_id, risk_level=2)
        db_session.add(existing)
        await db_session.flush()

        service = RiskService(db_session)
        new_plan = await service._auto_generate_intervention(
            user_id=seeded_user_id, risk_level=4
        )

        assert new_plan is not None
        assert new_plan.id != existing.id
        assert new_plan.risk_level == 4
        assert new_plan.status == "active"
        assert existing.status == "cancelled"

    @pytest.mark.asyncio
    async def test_escalation_keeps_old_plan_when_no_template(
        self, db_session, seeded_user_id
    ):
        """M17 关键: 无可用模板时不得取消旧计划, 避免用户失去全部干预。"""
        existing = _make_plan(seeded_user_id, risk_level=2)
        db_session.add(existing)
        await db_session.flush()

        service = RiskService(db_session)
        result = await service._auto_generate_intervention(
            user_id=seeded_user_id, risk_level=4
        )

        assert result is not None
        assert result.id == existing.id
        assert existing.status == "active"

    @pytest.mark.asyncio
    async def test_no_active_template_returns_none(
        self, db_session, seeded_user_id, caplog
    ):
        """H-Svc-8: 无活跃模板返回 None 并记录告警, 不静默掩盖。"""
        db_session.add(_make_template("已下线模板", [3], status="inactive"))
        await db_session.flush()

        service = RiskService(db_session)
        with caplog.at_level("WARNING", logger="app.services.risk_service_warning"):
            result = await service._auto_generate_intervention(
                user_id=seeded_user_id, risk_level=3
            )

        assert result is None
        assert "No active intervention template" in caplog.text

    @pytest.mark.asyncio
    async def test_fallback_to_first_template_when_level_unmatched(
        self, db_session, seeded_user_id
    ):
        """无等级匹配的模板时回退到第一个活跃模板。"""
        db_session.add(_make_template("仅低风险", [1]))
        await db_session.flush()

        service = RiskService(db_session)
        plan = await service._auto_generate_intervention(
            user_id=seeded_user_id, risk_level=3
        )

        assert plan is not None
        assert plan.plan_name == "仅低风险"

    @pytest.mark.asyncio
    async def test_counselor_binding_copied_to_plan(self, db_session, seeded_user_id):
        db_session.add(
            UserCounselorBinding(
                user_id=seeded_user_id,
                counselor_id=2,
                bind_code="B010",
                status=BindingStatus.ACTIVE,
                bound_at=datetime.now(timezone.utc),
            )
        )
        db_session.add(_make_template("T", [3]))
        await db_session.flush()

        service = RiskService(db_session)
        plan = await service._auto_generate_intervention(
            user_id=seeded_user_id, risk_level=3
        )

        assert plan is not None
        assert plan.counselor_id == 2
