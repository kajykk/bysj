"""P1-D-1 / P1-D-2: 模型一致性测试.

验证:
1. CrisisEvent 模型声明了迁移中已创建的 2 个复合索引 (避免 autogenerate 误删)
2. CrisisEvent.crisis_score 类型为 Float (与迁移一致)
3. 14 个外键均声明了 ondelete="SET NULL" 策略
"""

from __future__ import annotations

import pytest
from sqlalchemy import Float, Integer

from app.models.admin import (
    AlertSilence,
    MeditationLog,
    ModelFeedback,
    OperationLog,
    SystemConfig,
)
from app.models.counselor import ConsultationAppointment, ConsultationRecord
from app.models.intervention import InterventionPlan, InterventionTemplate
from app.models.review import CrisisEvent
from app.models.risk import WarningNotification

# ---------------------------------------------------------------------------
# P1-D-1: CrisisEvent 模型一致性
# ---------------------------------------------------------------------------


class TestCrisisEventModelConsistency:
    """P1-D-1: 验证 CrisisEvent 模型与迁移一致."""

    def test_crisis_event_has_status_created_at_index(self) -> None:
        """CrisisEvent 应声明 ix_crisis_events_status_created_at 复合索引."""
        table = CrisisEvent.__table__
        index_names = {idx.name for idx in table.indexes}
        assert "ix_crisis_events_status_created_at" in index_names

    def test_crisis_event_has_trigger_source_created_at_index(self) -> None:
        """CrisisEvent 应声明 ix_crisis_events_trigger_source_created_at 复合索引."""
        table = CrisisEvent.__table__
        index_names = {idx.name for idx in table.indexes}
        assert "ix_crisis_events_trigger_source_created_at" in index_names

    def test_crisis_event_status_created_at_index_columns(self) -> None:
        """复合索引应包含 (status, created_at) 列."""
        table = CrisisEvent.__table__
        idx = next(
            (
                i
                for i in table.indexes
                if i.name == "ix_crisis_events_status_created_at"
            ),
            None,
        )
        assert idx is not None
        col_names = [c.name for c in idx.columns]
        assert col_names == ["status", "created_at"]

    def test_crisis_event_trigger_source_created_at_index_columns(self) -> None:
        """复合索引应包含 (trigger_source, created_at) 列."""
        table = CrisisEvent.__table__
        idx = next(
            (
                i
                for i in table.indexes
                if i.name == "ix_crisis_events_trigger_source_created_at"
            ),
            None,
        )
        assert idx is not None
        col_names = [c.name for c in idx.columns]
        assert col_names == ["trigger_source", "created_at"]

    def test_crisis_score_is_float_type(self) -> None:
        """crisis_score 字段类型应为 Float (与迁移一致)."""
        column = CrisisEvent.__table__.c.crisis_score
        assert isinstance(
            column.type, Float
        ), f"crisis_score 应为 Float, 实际为 {type(column.type).__name__}"

    def test_crisis_score_is_not_integer_type(self) -> None:
        """crisis_score 字段类型不应为 Integer."""
        column = CrisisEvent.__table__.c.crisis_score
        assert not isinstance(
            column.type, Integer
        ), "crisis_score 不应为 Integer (与迁移 Float 类型不一致)"


# ---------------------------------------------------------------------------
# P1-D-2: 外键 ondelete 策略
# ---------------------------------------------------------------------------


def _get_fk_ondelete(table, column_name: str) -> str | None:
    """从 SQLAlchemy Table 对象提取指定列外键的 ondelete 策略."""
    column = table.c[column_name]
    for fk in column.foreign_keys:
        return fk.ondelete
    return None


class TestForeignKeyOndeleteStrategies:
    """P1-D-2: 验证 14 个外键均声明了 ondelete="SET NULL"."""

    # admin.py (6 处)
    def test_operation_logs_operator_id_ondelete(self) -> None:
        """operation_logs.operator_id -> users.id, ondelete=SET NULL."""
        assert _get_fk_ondelete(OperationLog.__table__, "operator_id") == "SET NULL"

    def test_system_configs_updated_by_ondelete(self) -> None:
        """system_configs.updated_by -> users.id, ondelete=SET NULL."""
        assert _get_fk_ondelete(SystemConfig.__table__, "updated_by") == "SET NULL"

    def test_meditation_logs_content_id_ondelete(self) -> None:
        """meditation_logs.content_id -> education_contents.id, ondelete=SET NULL."""
        assert _get_fk_ondelete(MeditationLog.__table__, "content_id") == "SET NULL"

    def test_model_feedbacks_counselor_id_ondelete(self) -> None:
        """model_feedbacks.counselor_id -> users.id, ondelete=SET NULL."""
        assert _get_fk_ondelete(ModelFeedback.__table__, "counselor_id") == "SET NULL"

    def test_model_feedbacks_assessment_id_ondelete(self) -> None:
        """model_feedbacks.assessment_id -> risk_assessments.id, ondelete=SET NULL."""
        assert _get_fk_ondelete(ModelFeedback.__table__, "assessment_id") == "SET NULL"

    def test_alert_silences_created_by_ondelete(self) -> None:
        """alert_silences.created_by -> users.id, ondelete=SET NULL."""
        assert _get_fk_ondelete(AlertSilence.__table__, "created_by") == "SET NULL"

    # counselor.py (4 处)
    def test_consultation_appointments_counselor_id_ondelete(self) -> None:
        """consultation_appointments.counselor_id -> users.id, ondelete=SET NULL."""
        assert (
            _get_fk_ondelete(ConsultationAppointment.__table__, "counselor_id")
            == "SET NULL"
        )

    def test_consultation_records_appointment_id_ondelete(self) -> None:
        """consultation_records.appointment_id -> consultation_appointments.id, ondelete=SET NULL."""
        assert (
            _get_fk_ondelete(ConsultationRecord.__table__, "appointment_id")
            == "SET NULL"
        )

    def test_consultation_records_warning_id_ondelete(self) -> None:
        """consultation_records.warning_id -> warning_notifications.id, ondelete=SET NULL."""
        assert (
            _get_fk_ondelete(ConsultationRecord.__table__, "warning_id") == "SET NULL"
        )

    def test_consultation_records_counselor_id_ondelete(self) -> None:
        """consultation_records.counselor_id -> users.id, ondelete=SET NULL."""
        assert (
            _get_fk_ondelete(ConsultationRecord.__table__, "counselor_id") == "SET NULL"
        )

    # intervention.py (2 处)
    def test_intervention_plans_counselor_id_ondelete(self) -> None:
        """intervention_plans.counselor_id -> users.id, ondelete=SET NULL."""
        assert (
            _get_fk_ondelete(InterventionPlan.__table__, "counselor_id") == "SET NULL"
        )

    def test_intervention_templates_created_by_ondelete(self) -> None:
        """intervention_templates.created_by -> users.id, ondelete=SET NULL."""
        assert (
            _get_fk_ondelete(InterventionTemplate.__table__, "created_by") == "SET NULL"
        )

    # risk.py (2 处)
    def test_warning_notifications_risk_assessment_id_ondelete(self) -> None:
        """warning_notifications.risk_assessment_id -> risk_assessments.id, ondelete=SET NULL."""
        assert (
            _get_fk_ondelete(WarningNotification.__table__, "risk_assessment_id")
            == "SET NULL"
        )

    def test_warning_notifications_counselor_id_ondelete(self) -> None:
        """warning_notifications.counselor_id -> users.id, ondelete=SET NULL."""
        assert (
            _get_fk_ondelete(WarningNotification.__table__, "counselor_id")
            == "SET NULL"
        )


class TestAllForeignKeysHaveOndelete:
    """P1-D-2: 验证所有模型的所有外键都有 ondelete 策略 (无遗漏)."""

    @pytest.mark.parametrize(
        "model_class",
        [
            OperationLog,
            SystemConfig,
            MeditationLog,
            ModelFeedback,
            AlertSilence,
            ConsultationAppointment,
            ConsultationRecord,
            InterventionPlan,
            InterventionTemplate,
            WarningNotification,
            CrisisEvent,
        ],
    )
    def test_all_fks_have_ondelete(self, model_class) -> None:
        """每个模型的每个外键都应声明 ondelete 策略."""
        table = model_class.__table__
        missing = []
        for column in table.columns:
            for fk in column.foreign_keys:
                if fk.ondelete is None:
                    missing.append(
                        f"{table.name}.{column.name} -> {fk.target_fullname}"
                    )
        assert not missing, f"以下外键缺少 ondelete 策略: {missing}"
