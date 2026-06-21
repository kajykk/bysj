from datetime import time

from pydantic import BaseModel, Field, model_validator


class WarningListItem(BaseModel):
    id: int
    risk_level: int
    risk_level_label: str
    title: str
    content: str
    is_read: bool
    status: str
    created_at: str | None
    handled_at: str | None = None
    handled_by: int | None = None
    handled_note: str | None = None


class WarningSettingsUpdateRequest(BaseModel):
    notify_channels: dict | None = Field(default=None)
    threshold_level: int | None = Field(default=None, ge=0, le=10)
    quiet_hours_start: time | None = None
    quiet_hours_end: time | None = None

    @model_validator(mode="after")
    def validate_notify_channels_and_quiet_hours(self) -> "WarningSettingsUpdateRequest":
        if self.notify_channels is not None:
            allowed_keys = {"in_app", "email", "sms", "websocket"}
            if not isinstance(self.notify_channels, dict):
                raise ValueError("notify_channels must be an object")
            extra_keys = set(self.notify_channels) - allowed_keys
            if extra_keys:
                raise ValueError(f"notify_channels contains unsupported keys: {', '.join(sorted(extra_keys))}")
            for key, value in self.notify_channels.items():
                if not isinstance(value, bool):
                    raise ValueError(f"notify_channels.{key} must be a boolean")

        if self.quiet_hours_start is not None and self.quiet_hours_end is not None:
            if self.quiet_hours_start == self.quiet_hours_end:
                raise ValueError("quiet_hours_start and quiet_hours_end must not be equal")
        return self
