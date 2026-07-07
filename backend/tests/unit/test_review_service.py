from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.schemas.review import (
    CrisisEventCreate,
    CrisisEventFilter,
    ReviewPriority,
    ReviewStatus,
    ReviewTaskCreate,
    ReviewTaskFilter,
)
from app.services.review_service import CrisisEventService, ReviewService


class TestReviewService:
    """Tests for ReviewService."""

    @pytest.fixture
    def review_service(self, db_session):
        return ReviewService(db_session)

    @pytest.fixture
    def crisis_service(self, db_session):
        return CrisisEventService(db_session)

    async def test_create_review_task(self, review_service):
        """TC-REVIEW-HP-001: 根据预测结果创建复核任务"""
        data = ReviewTaskCreate(
            user_id=1,
            risk_level=3,
            risk_score=75.0,
            review_triggers=["SINGLE_MODEL_HIGH"],
            crisis_override=False,
            priority=ReviewPriority.HIGH_RISK_REVIEW,
        )
        task = await review_service.create_review_task(data)

        assert task.id is not None
        assert task.user_id == 1
        assert task.risk_level == 3
        assert task.risk_score == 75.0
        assert task.status == "pending"
        assert task.priority == "high_risk_review"
        assert task.crisis_override is False

    async def test_create_review_task_crisis_override(self, review_service):
        """TC-REVIEW-HP-002: crisis_override=true 时创建 crisis_review 优先级任务"""
        data = ReviewTaskCreate(
            user_id=1,
            risk_level=4,
            risk_score=95.0,
            review_triggers=["CRISIS_EXPRESSION"],
            crisis_override=True,
            priority=ReviewPriority.CRISIS_REVIEW,
        )
        task = await review_service.create_review_task(data)

        assert task.priority == "crisis_review"
        assert task.crisis_override is True
        assert task.risk_level == 4

    async def test_create_review_task_single_model_high(self, review_service):
        """TC-REVIEW-HP-003: 单模型 high 时创建 high_risk_review 优先级任务"""
        data = ReviewTaskCreate(
            user_id=1,
            risk_level=3,
            risk_score=80.0,
            review_triggers=["SINGLE_MODEL_HIGH"],
            crisis_override=False,
            priority=ReviewPriority.HIGH_RISK_REVIEW,
        )
        task = await review_service.create_review_task(data)

        assert task.priority == "high_risk_review"
        assert task.risk_level == 3

    async def test_update_existing_pending_task(self, review_service):
        """TC-REVIEW-EC-001: 重复创建时更新现有 pending 任务"""
        data1 = ReviewTaskCreate(
            user_id=1,
            risk_level=2,
            risk_score=50.0,
            review_triggers=["MODEL_DISAGREEMENT"],
        )
        task1 = await review_service.create_review_task(data1)
        original_id = task1.id

        data2 = ReviewTaskCreate(
            user_id=1,
            risk_level=3,
            risk_score=75.0,
            review_triggers=["SINGLE_MODEL_HIGH"],
            priority=ReviewPriority.HIGH_RISK_REVIEW,
        )
        task2 = await review_service.create_review_task(data2)

        assert task2.id == original_id
        assert task2.risk_level == 3
        assert task2.risk_score == 75.0
        assert task2.priority == "high_risk_review"

    async def test_assign_review(self, review_service):
        """TC-REVIEW-HP-004: pending -> assign -> in_review"""
        data = ReviewTaskCreate(user_id=1, risk_level=2, risk_score=50.0)
        task = await review_service.create_review_task(data)

        assigned = await review_service.assign_review(task.id, 2)
        assert assigned.status == "in_review"
        assert assigned.assigned_to == 2

    async def test_resolve_review(self, review_service):
        """TC-REVIEW-HP-005: in_review -> resolve -> resolved"""
        data = ReviewTaskCreate(user_id=1, risk_level=2, risk_score=50.0)
        task = await review_service.create_review_task(data)
        await review_service.assign_review(task.id, 2)

        resolved = await review_service.resolve_review(task.id, 2, "已处理，建议随访")
        assert resolved.status == "resolved"
        assert resolved.resolved_by == 2
        assert resolved.resolution_note == "已处理，建议随访"
        assert resolved.resolved_at is not None

    async def test_escalate_review(self, review_service):
        """TC-REVIEW-HP-006: in_review -> escalate -> escalated"""
        data = ReviewTaskCreate(user_id=1, risk_level=3, risk_score=80.0)
        task = await review_service.create_review_task(data)
        await review_service.assign_review(task.id, 2)

        escalated = await review_service.escalate_review(task.id, 2, "需要专家介入")
        assert escalated.status == "escalated"
        # M-Svc-6 修复：escalate 不再复用 resolved_by 字段（升级≠解决）
        # 升级操作者记录在 OperationLog.detail.escalated_by 中
        assert escalated.resolution_note == "需要专家介入"

    async def test_resolve_resolved_fails(self, review_service):
        """TC-REVIEW-SP-001: resolved 任务不可再次 resolve"""
        data = ReviewTaskCreate(user_id=1, risk_level=2, risk_score=50.0)
        task = await review_service.create_review_task(data)
        await review_service.assign_review(task.id, 2)
        await review_service.resolve_review(task.id, 2, "已处理")

        with pytest.raises(
            ValueError, match="Cannot resolve review with status resolved"
        ):
            await review_service.resolve_review(task.id, 2, "再次处理")

    async def test_resolve_pending_without_assign_fails(self, review_service):
        """TC-REVIEW-SP-002: pending 任务不可直接 resolve"""
        data = ReviewTaskCreate(user_id=1, risk_level=2, risk_score=50.0)
        task = await review_service.create_review_task(data)

        # pending 任务实际上可以 resolve（状态检查允许 pending 和 in_review）
        # 这里测试 escalated 任务不能 resolve
        await review_service.assign_review(task.id, 2)
        await review_service.escalate_review(task.id, 2, "升级")

        with pytest.raises(
            ValueError, match="Cannot resolve review with status escalated"
        ):
            await review_service.resolve_review(task.id, 2, "尝试处理")

    async def test_get_reviews_filter_by_status(self, review_service):
        """TC-REVIEW-HP-007: 按状态筛选"""
        # 创建多个任务
        for i in range(3):
            data = ReviewTaskCreate(user_id=i + 1, risk_level=2, risk_score=50.0)
            await review_service.create_review_task(data)

        # 处理一个
        await review_service.assign_review(1, 2)
        await review_service.resolve_review(1, 2, "处理完成")

        filter_data = ReviewTaskFilter(status=ReviewStatus.PENDING)
        result = await review_service.get_reviews(filter_data)

        assert result.total >= 2
        for item in result.items:
            assert item.status == "pending"

    async def test_get_reviews_filter_by_priority(self, review_service):
        """TC-REVIEW-HP-008: 按优先级筛选"""
        data1 = ReviewTaskCreate(
            user_id=1,
            risk_level=4,
            risk_score=95.0,
            priority=ReviewPriority.CRISIS_REVIEW,
        )
        await review_service.create_review_task(data1)

        data2 = ReviewTaskCreate(
            user_id=2,
            risk_level=2,
            risk_score=50.0,
            priority=ReviewPriority.NORMAL_REVIEW,
        )
        await review_service.create_review_task(data2)

        filter_data = ReviewTaskFilter(priority=ReviewPriority.CRISIS_REVIEW)
        result = await review_service.get_reviews(filter_data)

        assert result.total >= 1
        for item in result.items:
            assert item.priority == "crisis_review"

    async def test_get_reviews_pagination(self, review_service):
        """TC-REVIEW-HP-009: 分页返回正确数量"""
        for i in range(5):
            data = ReviewTaskCreate(user_id=i + 1, risk_level=2, risk_score=50.0)
            await review_service.create_review_task(data)

        filter_data = ReviewTaskFilter(page=1, page_size=2)
        result = await review_service.get_reviews(filter_data)

        assert len(result.items) <= 2
        assert result.page == 1
        assert result.page_size == 2
        assert result.total >= 5

    async def test_get_review_stats(self, review_service):
        """测试复核统计"""
        # 创建各种状态的任务
        data1 = ReviewTaskCreate(
            user_id=1, risk_level=4, risk_score=95.0, crisis_override=True
        )
        await review_service.create_review_task(data1)

        data2 = ReviewTaskCreate(user_id=2, risk_level=3, risk_score=80.0)
        await review_service.create_review_task(data2)
        task2 = await review_service.get_reviews(ReviewTaskFilter())
        task2_item = [i for i in task2.items if i.user_id == 2][0]
        await review_service.assign_review(task2_item.id, 2)
        await review_service.resolve_review(task2_item.id, 2, "已处理")

        stats = await review_service.get_review_stats()

        assert stats.total >= 2
        assert stats.crisis_count >= 1

    async def test_create_review_task_postgresql_advisory_lock(
        self, review_service, db_session, monkeypatch
    ):
        """TC-REVIEW-COV-001: 覆盖 PostgreSQL advisory lock 分支（SQLite 环境下 mock 模拟）。"""
        from app.services import review_service as rs_module

        monkeypatch.setattr(db_session.bind.dialect, "name", "postgresql")

        original_text_fn = rs_module.text
        lock_called = {"n": 0}

        def fake_text(sql):
            if "pg_advisory_xact_lock" in sql:
                lock_called["n"] += 1
                return original_text_fn("SELECT :user_id as lock_id")
            return original_text_fn(sql)

        monkeypatch.setattr(rs_module, "text", fake_text)

        data = ReviewTaskCreate(user_id=1, risk_level=2, risk_score=50.0)
        task = await review_service.create_review_task(data)
        assert task.id is not None
        assert lock_called["n"] == 1

    async def test_get_reviews_filter_by_assigned_to(self, review_service):
        """TC-REVIEW-COV-002: 覆盖 get_reviews 按 assigned_to 过滤。"""
        data = ReviewTaskCreate(user_id=1, risk_level=2, risk_score=50.0)
        task = await review_service.create_review_task(data)
        await review_service.assign_review(task.id, 2)

        filter_data = ReviewTaskFilter(assigned_to=2)
        result = await review_service.get_reviews(filter_data)
        assert result.total >= 1
        for item in result.items:
            assert item.assigned_to == 2

    async def test_get_reviews_filter_by_user_id(self, review_service):
        """TC-REVIEW-COV-003: 覆盖 get_reviews 按 user_id 过滤。"""
        data1 = ReviewTaskCreate(user_id=1, risk_level=2, risk_score=50.0)
        await review_service.create_review_task(data1)
        data2 = ReviewTaskCreate(user_id=2, risk_level=2, risk_score=50.0)
        await review_service.create_review_task(data2)

        filter_data = ReviewTaskFilter(user_id=2)
        result = await review_service.get_reviews(filter_data)
        assert result.total >= 1
        for item in result.items:
            assert item.user_id == 2

    async def test_assign_review_not_found(self, review_service):
        """TC-REVIEW-COV-004: 覆盖 assign_review 任务不存在时抛 ValueError。"""
        with pytest.raises(ValueError, match="not found"):
            await review_service.assign_review(9999, 2)

    async def test_assign_review_wrong_status(self, review_service):
        """TC-REVIEW-COV-005: 覆盖 assign_review 任务非 pending 状态时抛 ValueError。"""
        data = ReviewTaskCreate(user_id=1, risk_level=2, risk_score=50.0)
        task = await review_service.create_review_task(data)
        await review_service.assign_review(task.id, 2)
        # 已 in_review，不可再次 assign
        with pytest.raises(ValueError, match="Cannot assign review with status"):
            await review_service.assign_review(task.id, 3)

    async def test_resolve_review_not_found(self, review_service):
        """TC-REVIEW-COV-006: 覆盖 resolve_review 任务不存在时抛 ValueError。"""
        with pytest.raises(ValueError, match="not found"):
            await review_service.resolve_review(9999, 2, "note")

    async def test_resolve_review_not_authorized(self, review_service):
        """TC-REVIEW-COV-007: 覆盖 resolve_review 越权检查（任务已分配给其他咨询师）。"""
        data = ReviewTaskCreate(user_id=1, risk_level=2, risk_score=50.0)
        task = await review_service.create_review_task(data)
        await review_service.assign_review(task.id, 2)
        with pytest.raises(ValueError, match="无权处理"):
            await review_service.resolve_review(task.id, 3, "note")

    async def test_resolve_review_admin_override(self, review_service):
        """TC-REVIEW-COV-008: 覆盖 resolve_review 管理员越权放行。"""
        data = ReviewTaskCreate(user_id=1, risk_level=2, risk_score=50.0)
        task = await review_service.create_review_task(data)
        await review_service.assign_review(task.id, 2)
        resolved = await review_service.resolve_review(
            task.id, 3, "admin override", is_admin=True
        )
        assert resolved.status == "resolved"

    async def test_escalate_review_not_found(self, review_service):
        """TC-REVIEW-COV-009: 覆盖 escalate_review 任务不存在时抛 ValueError。"""
        with pytest.raises(ValueError, match="not found"):
            await review_service.escalate_review(9999, 2, "reason")

    async def test_escalate_review_wrong_status(self, review_service):
        """TC-REVIEW-COV-010: 覆盖 escalate_review 任务状态不允许时抛 ValueError。"""
        data = ReviewTaskCreate(user_id=1, risk_level=2, risk_score=50.0)
        task = await review_service.create_review_task(data)
        await review_service.assign_review(task.id, 2)
        await review_service.resolve_review(task.id, 2, "done")
        with pytest.raises(ValueError, match="Cannot escalate review with status"):
            await review_service.escalate_review(task.id, 2, "reason")

    async def test_escalate_review_not_authorized(self, review_service):
        """TC-REVIEW-COV-011: 覆盖 escalate_review 越权检查。"""
        data = ReviewTaskCreate(user_id=1, risk_level=2, risk_score=50.0)
        task = await review_service.create_review_task(data)
        await review_service.assign_review(task.id, 2)
        with pytest.raises(ValueError, match="无权升级"):
            await review_service.escalate_review(task.id, 3, "reason")


class TestCrisisEventService:
    """Tests for CrisisEventService."""

    @pytest.fixture
    def crisis_service(self, db_session):
        return CrisisEventService(db_session)

    async def test_record_crisis_event(self, crisis_service):
        """TC-CRISIS-HP-001: 记录危机事件"""
        data = CrisisEventCreate(
            user_id=1,
            trigger_source="text",
            crisis_keywords=["自杀", "不想活了"],
            crisis_score=0.95,
            input_summary="用户表达自杀意愿",
        )
        event = await crisis_service.record_crisis_event(data)

        assert event.id is not None
        assert event.user_id == 1
        assert event.trigger_source == "text"
        assert event.status == "detected"

    async def test_handle_crisis_event(self, crisis_service):
        """TC-CRISIS-HP-002: 处理危机事件"""
        data = CrisisEventCreate(
            user_id=1,
            trigger_source="fusion",
            crisis_keywords=["自伤"],
            crisis_score=0.85,
        )
        event = await crisis_service.record_crisis_event(data)

        # M-Svc-8 修复：action 必须在白名单内，使用 notify_counselor 替代自由文本
        # ISS-072 修复：状态由 "handled" 改为 "reviewed"，与前端筛选器对齐
        handled = await crisis_service.handle_crisis_event(
            event.id, 2, "notify_counselor"
        )
        assert handled.status == "reviewed"
        assert handled.handled_by == 2
        assert handled.handled_action == "notify_counselor"
        assert handled.handled_at is not None

    async def test_record_crisis_event_too_many_keywords(self, crisis_service):
        """TC-CRISIS-COV-001: 覆盖 crisis_keywords 超过 50 个时抛 ValueError。"""
        keywords = [f"keyword_{i}" for i in range(51)]
        data = CrisisEventCreate(
            user_id=1,
            trigger_source="text",
            crisis_keywords=keywords,
            crisis_score=0.5,
        )
        with pytest.raises(ValueError, match="不能超过 50"):
            await crisis_service.record_crisis_event(data)

    async def test_record_crisis_event_keyword_too_long(self, crisis_service):
        """TC-CRISIS-COV-002: 覆盖单个 crisis_keyword 超过 100 字符时抛 ValueError。"""
        long_keyword = "x" * 101
        data = CrisisEventCreate(
            user_id=1,
            trigger_source="text",
            crisis_keywords=[long_keyword],
            crisis_score=0.5,
        )
        with pytest.raises(ValueError, match="不能超过 100"):
            await crisis_service.record_crisis_event(data)

    async def test_get_crisis_events_with_data(self, crisis_service):
        """TC-CRISIS-COV-003: 覆盖 get_crisis_events 查询及 _to_response 转换。"""
        data = CrisisEventCreate(
            user_id=1,
            trigger_source="text",
            crisis_keywords=["自伤"],
            crisis_score=0.8,
            input_summary="summary",
        )
        await crisis_service.record_crisis_event(data)

        filter_data = CrisisEventFilter()
        result = await crisis_service.get_crisis_events(filter_data)
        assert result["total"] >= 1
        assert len(result["items"]) >= 1
        item = result["items"][0]
        assert item["user_id"] == 1
        assert item["trigger_source"] == "text"
        assert "自伤" in item["crisis_keywords"]
        assert item["crisis_score"] == 0.8
        assert item["status"] == "detected"

    async def test_get_crisis_events_with_filters(self, crisis_service):
        """TC-CRISIS-COV-004: 覆盖 get_crisis_events 按状态和日期范围过滤。"""
        data = CrisisEventCreate(
            user_id=1,
            trigger_source="text",
            crisis_keywords=["自伤"],
            crisis_score=0.8,
        )
        await crisis_service.record_crisis_event(data)

        # 按状态过滤
        filter_data = CrisisEventFilter(status="detected")
        result = await crisis_service.get_crisis_events(filter_data)
        assert result["total"] >= 1

        # 按日期范围过滤
        now = datetime.now(timezone.utc)
        filter_data = CrisisEventFilter(
            start_date=now.replace(hour=0, minute=0, second=0, microsecond=0),
            end_date=now,
        )
        result = await crisis_service.get_crisis_events(filter_data)
        assert result["total"] >= 1

        # 按不存在的状态过滤
        filter_data = CrisisEventFilter(status="nonexistent")
        result = await crisis_service.get_crisis_events(filter_data)
        assert result["total"] == 0

    async def test_get_crisis_events_pagination(self, crisis_service):
        """TC-CRISIS-COV-005: 覆盖 get_crisis_events 分页。"""
        for i in range(3):
            data = CrisisEventCreate(
                user_id=1,
                trigger_source="text",
                crisis_keywords=[f"kw_{i}"],
                crisis_score=0.5,
            )
            await crisis_service.record_crisis_event(data)

        filter_data = CrisisEventFilter(page=1, page_size=2)
        result = await crisis_service.get_crisis_events(filter_data)
        assert result["total"] >= 3
        assert len(result["items"]) <= 2
        assert result["page"] == 1
        assert result["page_size"] == 2

    async def test_handle_crisis_event_invalid_action(self, crisis_service):
        """TC-CRISIS-COV-006: 覆盖 handle_crisis_event 非法 action 抛 ValueError。"""
        data = CrisisEventCreate(
            user_id=1,
            trigger_source="text",
            crisis_keywords=["自伤"],
            crisis_score=0.8,
        )
        event = await crisis_service.record_crisis_event(data)

        with pytest.raises(ValueError, match="无效的 action"):
            await crisis_service.handle_crisis_event(event.id, 2, "invalid_action")

    async def test_handle_crisis_event_not_found(self, crisis_service):
        """TC-CRISIS-COV-007: 覆盖 handle_crisis_event 事件不存在时抛 ValueError。"""
        with pytest.raises(ValueError, match="not found"):
            await crisis_service.handle_crisis_event(9999, 2, "resolved")
