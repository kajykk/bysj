"""ISS-02 第六轮：ReviewService / CrisisEventService 纯逻辑聚焦测试。

覆盖 app/services/review_service.py 的无 DB 路径：
- ReviewService.to_response：同步转换，验证 review_triggers JSON 反序列化与字段映射。
- CrisisEventService._validate_crisis_transition：同步状态机（detected/reviewed/
  escalated/resolved 四态转换表），合法转换通过、非法转换抛 ValueError。

说明：review_service 顶层经 app.services.__init__ 间接依赖 numpy；本地 coverage.py
插桩时偶发 SIGSEGV，故 pass/fail 验证，覆盖率数值以稳定 CI 为准。被测定方法均不
触发 DB/EventBus，属确定性逻辑。
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from app.services.review_service import CrisisEventService, ReviewService


# ── ReviewService.to_response ──────────────────────────────────────────────


def test_to_response_maps_fields_and_parses_triggers():
    from datetime import datetime, timezone

    ts = datetime(2026, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    task = MagicMock()
    task.configure_mock(
        id=7,
        user_id=42,
        risk_report_id=99,
        risk_level=3,
        risk_score=0.87,
        review_triggers='["a", "b"]',
        crisis_override=1,  # bool(1) → True
        status="pending",
        priority="high_risk_review",
        assigned_to=None,
        resolved_by=None,
        resolution_note=None,
        created_at=ts,
        updated_at=ts,
        resolved_at=None,
    )

    resp = ReviewService(db=None).to_response(task)
    assert resp.id == 7
    assert resp.user_id == 42
    assert resp.risk_level == 3
    assert resp.risk_score == 0.87
    assert resp.review_triggers == ["a", "b"]  # JSON 反序列化路径
    assert resp.crisis_override is True  # bool() 转换
    assert resp.status == "pending"
    assert resp.priority == "high_risk_review"


def test_to_response_empty_triggers_returns_empty_list():
    from datetime import datetime, timezone

    ts = datetime(2026, 2, 2, 8, 30, 0, tzinfo=timezone.utc)
    task = MagicMock()
    task.configure_mock(
        id=1,
        user_id=2,
        risk_report_id=3,
        risk_level=0,
        risk_score=0.0,
        review_triggers=None,  # → json.loads("[]") → []
        crisis_override=0,  # bool(0) → False
        status="resolved",
        priority="normal_review",
        assigned_to=None,
        resolved_by=None,
        resolution_note=None,
        created_at=ts,
        updated_at=ts,
        resolved_at=None,
    )
    resp = ReviewService(db=None).to_response(task)
    assert resp.review_triggers == []


# ── CrisisEventService._validate_crisis_transition ─────────────────────────


def _svc() -> CrisisEventService:
    # _validate_crisis_transition 仅用 (self, current, target)，不访问 self.db
    return CrisisEventService(db=None)


@pytest.mark.parametrize(
    "current,target",
    [
        ("detected", "reviewed"),
        ("detected", "escalated"),
        ("detected", "resolved"),
        ("reviewed", "reviewed"),
        ("reviewed", "escalated"),
        ("reviewed", "resolved"),
        ("escalated", "reviewed"),
        ("escalated", "resolved"),
    ],
)
def test_crisis_transition_valid(current, target):
    _svc()._validate_crisis_transition(current, target)  # 不应抛异常


@pytest.mark.parametrize(
    "current,target",
    [
        ("resolved", "reviewed"),  # 终态不可转
        ("resolved", "escalated"),
        ("resolved", "resolved"),
        ("detected", "bogus"),
        ("escalated", "escalated"),  # escalated 不允许回到 escalated
    ],
)
def test_crisis_transition_invalid_raises(current, target):
    with pytest.raises(ValueError, match="非法状态转换"):
        _svc()._validate_crisis_transition(current, target)


def test_crisis_transition_unknown_current_state_raises():
    # _CRISIS_STATE_TRANSITIONS 无该 key → 默认 frozenset() → 任何 target 皆非法
    with pytest.raises(ValueError, match="非法状态转换"):
        _svc()._validate_crisis_transition("nonexistent", "reviewed")
