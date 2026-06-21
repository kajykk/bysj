"""P1-D-8: ORM 约束测试.

验证 P0/P1 级别的 CheckConstraint 已正确声明在模型中:
- users.role/status 枚举约束
- alert_silences 时间顺序约束
- physiological_records 生理指标范围约束
- review_tasks 评分范围 + 枚举约束
- canary_records 流量百分比 + 枚举约束
"""
from __future__ import annotations

import pytest
from sqlalchemy import CheckConstraint

from app.models.admin import AlertSilence
from app.models.assessment import PhysiologicalRecord
from app.models.monitoring import CanaryRecord
from app.models.review import ReviewTask
from app.models.user import User


def _get_check_constraints(table) -> dict[str, str]:
    """从 SQLAlchemy Table 对象提取所有 CheckConstraint, 返回 {name: sqltext}."""
    result = {}
    for constraint in table.constraints:
        if isinstance(constraint, CheckConstraint):
            if constraint.name:
                result[constraint.name] = str(constraint.sqltext)
    return result


# ---------------------------------------------------------------------------
# P1-D-8 P0: User 枚举约束
# ---------------------------------------------------------------------------


class TestUserEnumConstraints:
    """P1-D-8: User 模型枚举约束."""

    def test_user_role_values_constraint_exists(self) -> None:
        """User 应有 role 枚举约束 (防止权限提升)."""
        constraints = _get_check_constraints(User.__table__)
        assert "ck_users_role_values" in constraints

    def test_user_role_values_constraint_content(self) -> None:
        """role 约束应只允许 user/admin/counselor."""
        constraints = _get_check_constraints(User.__table__)
        sqltext = constraints.get("ck_users_role_values", "")
        assert "user" in sqltext
        assert "admin" in sqltext
        assert "counselor" in sqltext

    def test_user_status_values_constraint_exists(self) -> None:
        """User 应有 status 枚举约束."""
        constraints = _get_check_constraints(User.__table__)
        assert "ck_users_status_values" in constraints

    def test_user_status_values_constraint_content(self) -> None:
        """status 约束应只允许 active/inactive/deleted."""
        constraints = _get_check_constraints(User.__table__)
        sqltext = constraints.get("ck_users_status_values", "")
        assert "active" in sqltext
        assert "inactive" in sqltext
        assert "deleted" in sqltext


# ---------------------------------------------------------------------------
# P1-D-8 P0: AlertSilence 时间顺序约束
# ---------------------------------------------------------------------------


class TestAlertSilenceTimeOrderConstraint:
    """P1-D-8: AlertSilence 时间顺序约束."""

    def test_time_order_constraint_exists(self) -> None:
        """AlertSilence 应有 ends_at > starts_at 约束."""
        constraints = _get_check_constraints(AlertSilence.__table__)
        assert "ck_alert_silences_time_order" in constraints

    def test_time_order_constraint_content(self) -> None:
        """约束应包含 ends_at > starts_at."""
        constraints = _get_check_constraints(AlertSilence.__table__)
        sqltext = constraints.get("ck_alert_silences_time_order", "")
        assert "ends_at" in sqltext
        assert "starts_at" in sqltext
        assert ">" in sqltext


# ---------------------------------------------------------------------------
# P1-D-8 P0: PhysiologicalRecord 生理指标范围约束
# ---------------------------------------------------------------------------


class TestPhysiologicalRecordRangeConstraints:
    """P1-D-8: PhysiologicalRecord 生理指标范围约束."""

    @pytest.mark.parametrize(
        "constraint_name",
        [
            "ck_physiological_records_sleep_hours",
            "ck_physiological_records_sleep_quality",
            "ck_physiological_records_exercise_minutes",
            "ck_physiological_records_heart_rate",
            "ck_physiological_records_systolic_bp",
            "ck_physiological_records_diastolic_bp",
            "ck_physiological_records_steps",
        ],
    )
    def test_range_constraint_exists(self, constraint_name: str) -> None:
        """每个生理指标字段应有范围约束."""
        constraints = _get_check_constraints(PhysiologicalRecord.__table__)
        assert constraint_name in constraints, f"缺少约束: {constraint_name}"

    def test_sleep_hours_range(self) -> None:
        """sleep_hours 应约束在 0-24 范围."""
        constraints = _get_check_constraints(PhysiologicalRecord.__table__)
        sqltext = constraints.get("ck_physiological_records_sleep_hours", "")
        assert "0" in sqltext
        assert "24" in sqltext

    def test_heart_rate_range(self) -> None:
        """heart_rate 应约束在 30-250 范围."""
        constraints = _get_check_constraints(PhysiologicalRecord.__table__)
        sqltext = constraints.get("ck_physiological_records_heart_rate", "")
        assert "30" in sqltext
        assert "250" in sqltext

    def test_systolic_bp_range(self) -> None:
        """systolic_bp 应约束在 50-300 范围."""
        constraints = _get_check_constraints(PhysiologicalRecord.__table__)
        sqltext = constraints.get("ck_physiological_records_systolic_bp", "")
        assert "50" in sqltext
        assert "300" in sqltext

    def test_diastolic_bp_range(self) -> None:
        """diastolic_bp 应约束在 30-200 范围."""
        constraints = _get_check_constraints(PhysiologicalRecord.__table__)
        sqltext = constraints.get("ck_physiological_records_diastolic_bp", "")
        assert "30" in sqltext
        assert "200" in sqltext


# ---------------------------------------------------------------------------
# P1-D-8 P0: ReviewTask 评分范围约束
# ---------------------------------------------------------------------------


class TestReviewTaskRangeConstraints:
    """P1-D-8: ReviewTask 评分范围约束."""

    def test_risk_level_range_constraint_exists(self) -> None:
        """ReviewTask 应有 risk_level 范围约束 (0-10)."""
        constraints = _get_check_constraints(ReviewTask.__table__)
        assert "ck_review_tasks_risk_level" in constraints

    def test_risk_score_range_constraint_exists(self) -> None:
        """ReviewTask 应有 risk_score 范围约束 (0-100)."""
        constraints = _get_check_constraints(ReviewTask.__table__)
        assert "ck_review_tasks_risk_score" in constraints

    def test_risk_level_range_content(self) -> None:
        """risk_level 约束应包含 0-10 范围."""
        constraints = _get_check_constraints(ReviewTask.__table__)
        sqltext = constraints.get("ck_review_tasks_risk_level", "")
        assert "0" in sqltext
        assert "10" in sqltext

    def test_risk_score_range_content(self) -> None:
        """risk_score 约束应包含 0-100 范围."""
        constraints = _get_check_constraints(ReviewTask.__table__)
        sqltext = constraints.get("ck_review_tasks_risk_score", "")
        assert "0" in sqltext
        assert "100" in sqltext


# ---------------------------------------------------------------------------
# P1-D-8 P1: ReviewTask 枚举约束
# ---------------------------------------------------------------------------


class TestReviewTaskEnumConstraints:
    """P1-D-8: ReviewTask 枚举约束."""

    def test_status_values_constraint_exists(self) -> None:
        """ReviewTask 应有 status 枚举约束."""
        constraints = _get_check_constraints(ReviewTask.__table__)
        assert "ck_review_tasks_status_values" in constraints

    def test_status_values_content(self) -> None:
        """status 约束应包含所有合法值."""
        constraints = _get_check_constraints(ReviewTask.__table__)
        sqltext = constraints.get("ck_review_tasks_status_values", "")
        for value in ("pending", "in_review", "resolved", "escalated", "archived"):
            assert value in sqltext, f"status 约束缺少值: {value}"

    def test_priority_values_constraint_exists(self) -> None:
        """ReviewTask 应有 priority 枚举约束."""
        constraints = _get_check_constraints(ReviewTask.__table__)
        assert "ck_review_tasks_priority_values" in constraints

    def test_priority_values_content(self) -> None:
        """priority 约束应包含所有合法值."""
        constraints = _get_check_constraints(ReviewTask.__table__)
        sqltext = constraints.get("ck_review_tasks_priority_values", "")
        for value in ("normal_review", "high_risk_review", "crisis_review"):
            assert value in sqltext, f"priority 约束缺少值: {value}"


# ---------------------------------------------------------------------------
# P1-D-8 P0: CanaryRecord 流量百分比约束
# ---------------------------------------------------------------------------


class TestCanaryRecordConstraints:
    """P1-D-8: CanaryRecord 约束."""

    def test_traffic_percent_range_constraint_exists(self) -> None:
        """CanaryRecord 应有 traffic_percent 范围约束 (1-100)."""
        constraints = _get_check_constraints(CanaryRecord.__table__)
        assert "ck_canary_records_traffic_percent" in constraints

    def test_traffic_percent_range_content(self) -> None:
        """traffic_percent 约束应包含 1-100 范围."""
        constraints = _get_check_constraints(CanaryRecord.__table__)
        sqltext = constraints.get("ck_canary_records_traffic_percent", "")
        assert "1" in sqltext
        assert "100" in sqltext

    def test_status_values_constraint_exists(self) -> None:
        """CanaryRecord 应有 status 枚举约束."""
        constraints = _get_check_constraints(CanaryRecord.__table__)
        assert "ck_canary_records_status_values" in constraints

    def test_status_values_content(self) -> None:
        """status 约束应包含所有合法值."""
        constraints = _get_check_constraints(CanaryRecord.__table__)
        sqltext = constraints.get("ck_canary_records_status_values", "")
        for value in ("pending", "running", "paused", "rolled_back", "completed"):
            assert value in sqltext, f"status 约束缺少值: {value}"
