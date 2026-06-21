from __future__ import annotations

from datetime import date, time

import pytest
from pydantic import ValidationError

from app.schemas.admin import ConfigUpsertRequest, TemplateUpsertRequest, ThresholdUpsertRequest
from app.schemas.auth import ChangePasswordRequest, LoginRequest, RefreshTokenRequest
from app.schemas.content import MeditationLogRequest, RecentViewRequest
from app.schemas.intervention import TaskStatusUpdateRequest
from app.schemas.warning import WarningSettingsUpdateRequest


class TestAuthSchemaConstraints:
    @pytest.mark.parametrize(
        ("username", "password"),
        [
            ("valid-user", "valid-password"),
        ],
    )
    def test_login_request_accepts_valid_credentials(self, username: str, password: str) -> None:
        model = LoginRequest(username=username, password=password)
        assert model.username == username
        assert model.password == password

    @pytest.mark.parametrize(
        ("username", "password"),
        [
            ("", "valid-password"),
            ("ok", ""),
        ],
    )
    def test_login_request_rejects_invalid_credentials(self, username: str, password: str) -> None:
        with pytest.raises(ValidationError):
            LoginRequest(username=username, password=password)

    @pytest.mark.parametrize("refresh_token", ["x" * 32, "y" * 64])
    def test_refresh_token_request_accepts_valid_token(self, refresh_token: str) -> None:
        model = RefreshTokenRequest(refresh_token=refresh_token)
        assert model.refresh_token == refresh_token

    @pytest.mark.parametrize("refresh_token", ["short-token", "", "1234567890abcdef"])
    def test_refresh_token_request_rejects_invalid_token(self, refresh_token: str) -> None:
        with pytest.raises(ValidationError):
            RefreshTokenRequest(refresh_token=refresh_token)

    @pytest.mark.parametrize(
        ("old_password", "new_password"),
        [
            ("old-password", "valid-password-123"),
        ],
    )
    def test_change_password_request_accepts_valid_passwords(self, old_password: str, new_password: str) -> None:
        model = ChangePasswordRequest(old_password=old_password, new_password=new_password)
        assert model.old_password == old_password
        assert model.new_password == new_password

    @pytest.mark.parametrize(
        ("old_password", "new_password"),
        [
            ("", "valid-password-123"),
            ("old", "short"),
        ],
    )
    def test_change_password_request_rejects_invalid_passwords(self, old_password: str, new_password: str) -> None:
        with pytest.raises(ValidationError):
            ChangePasswordRequest(old_password=old_password, new_password=new_password)


class TestWarningSchemaConstraints:
    def test_warning_settings_accepts_valid_notify_channels_and_quiet_hours(self) -> None:
        model = WarningSettingsUpdateRequest(
            notify_channels={"in_app": True, "email": False},
            threshold_level=3,
            quiet_hours_start=time(22, 0),
            quiet_hours_end=time(7, 0),
        )
        assert model.notify_channels == {"in_app": True, "email": False}
        assert model.threshold_level == 3

    @pytest.mark.parametrize(
        "notify_channels",
        [
            {"push": True},
            {"email": "yes"},
            {"in_app": True, "sms": 1},
        ],
    )
    def test_warning_settings_rejects_invalid_notify_channels(self, notify_channels: dict) -> None:
        with pytest.raises(ValidationError):
            WarningSettingsUpdateRequest(notify_channels=notify_channels)

    @pytest.mark.parametrize(
        ("quiet_hours_start", "quiet_hours_end"),
        [
            (time(22, 0), time(22, 0)),
            (time(8, 0), time(8, 0)),
        ],
    )
    def test_warning_settings_rejects_equal_quiet_hours(self, quiet_hours_start: time, quiet_hours_end: time) -> None:
        with pytest.raises(ValidationError):
            WarningSettingsUpdateRequest(
                quiet_hours_start=quiet_hours_start,
                quiet_hours_end=quiet_hours_end,
            )


class TestAdminSchemaConstraints:
    def test_threshold_request_accepts_valid_score_range(self) -> None:
        model = ThresholdUpsertRequest(
            level=2,
            level_name="中风险",
            min_score=20,
            max_score=60,
            color="#ff0000",
            action_required="handle",
        )
        assert model.min_score == 20
        assert model.max_score == 60

    @pytest.mark.parametrize(
        ("min_score", "max_score"),
        [
            (80, 60),
            (10.5, 10.4),
        ],
    )
    def test_threshold_request_rejects_inverted_score_range(self, min_score: float, max_score: float) -> None:
        with pytest.raises(ValidationError):
            ThresholdUpsertRequest(
                level=2,
                level_name="中风险",
                min_score=min_score,
                max_score=max_score,
                color="#ff0000",
                action_required="handle",
            )

    def test_template_request_accepts_valid_task_list(self) -> None:
        model = TemplateUpsertRequest(
            template_name="模板A",
            applicable_levels=[1, 2],
            task_list=[
                {
                    "task_name": "呼吸训练",
                    "task_type": "meditation",
                    "description": "放松训练",
                    "schedule": "daily",
                    "duration_minutes": 10,
                    "sort_order": 0,
                }
            ],
            estimated_weeks=4,
            status="active",
        )
        assert model.template_name == "模板A"
        assert model.task_list[0].task_type == "meditation"

    @pytest.mark.parametrize(
        "applicable_levels",
        [
            [1, 1, 2],
            [3, 4, 4],
        ],
    )
    def test_template_request_rejects_duplicate_applicable_levels(self, applicable_levels: list[int]) -> None:
        with pytest.raises(ValidationError):
            TemplateUpsertRequest(
                template_name="模板A",
                applicable_levels=applicable_levels,
                task_list=[{"task_name": "呼吸训练", "task_type": "meditation"}],
                estimated_weeks=4,
                status="active",
            )

    @pytest.mark.parametrize(
        "task_list",
        [
            [{"task_name": "呼吸训练", "task_type": "sleep"}],
            [{"task_name": "", "task_type": "meditation"}],
            [{"task_type": "meditation"}],
            [{"task_name": "呼吸训练", "task_type": "meditation", "duration_minutes": 0}],
            [{"task_name": "呼吸训练", "task_type": "meditation", "schedule": "hourly"}],
        ],
    )
    def test_template_request_rejects_invalid_task_items(self, task_list: list[dict]) -> None:
        with pytest.raises(ValidationError):
            TemplateUpsertRequest(
                template_name="模板A",
                applicable_levels=[1, 2],
                task_list=task_list,
                estimated_weeks=4,
                status="active",
            )

    @pytest.mark.parametrize("config_value", ["not-a-dict", [], None])
    def test_config_request_rejects_non_dict_config_value(self, config_value) -> None:
        with pytest.raises(ValidationError):
            ConfigUpsertRequest(config_key="system.mode", config_value=config_value)

    def test_config_request_accepts_valid_config_dict(self) -> None:
        model = ConfigUpsertRequest(
            config_key="system.mode",
            config_value={"enabled": True, "name": "prod"},
            description="system mode",
        )
        assert model.config_key == "system.mode"
        assert model.config_value["enabled"] is True


class TestInterventionSchemaConstraints:
    def test_task_status_update_accepts_valid_postpone_date(self) -> None:
        model = TaskStatusUpdateRequest(
            scheduled_date=date(2026, 4, 10),
            postpone_to=date(2026, 4, 12),
            note="delay due to user request",
        )
        assert model.postpone_to == date(2026, 4, 12)

    @pytest.mark.parametrize(
        ("scheduled_date", "postpone_to"),
        [
            (date(2026, 4, 10), date(2026, 4, 9)),
            (date(2026, 4, 10), date(2026, 4, 1)),
        ],
    )
    def test_task_status_update_rejects_past_postpone_date(self, scheduled_date: date, postpone_to: date) -> None:
        with pytest.raises(ValidationError):
            TaskStatusUpdateRequest(
                scheduled_date=scheduled_date,
                postpone_to=postpone_to,
            )


class TestContentSchemaConstraints:
    def test_meditation_log_accepts_valid_content_id(self) -> None:
        model = MeditationLogRequest(content_id=1, completed=True)
        assert model.content_id == 1
        assert model.completed is True

    @pytest.mark.parametrize("content_id", [0, -1])
    def test_meditation_log_requires_positive_content_id(self, content_id: int) -> None:
        with pytest.raises(ValidationError):
            MeditationLogRequest(content_id=content_id)

    def test_recent_view_accepts_valid_content_id(self) -> None:
        model = RecentViewRequest(content_id=12)
        assert model.content_id == 12

    @pytest.mark.parametrize("content_id", [0, -5])
    def test_recent_view_requires_positive_content_id(self, content_id: int) -> None:
        with pytest.raises(ValidationError):
            RecentViewRequest(content_id=content_id)
