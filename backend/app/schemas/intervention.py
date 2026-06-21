from datetime import date

from pydantic import BaseModel, Field, model_validator


class TaskCompleteRequest(BaseModel):
    scheduled_date: date | None = None


class TaskFeedbackRequest(BaseModel):
    scheduled_date: date | None = None
    feedback_score: int | None = Field(default=None, ge=1, le=5)
    feedback_note: str | None = Field(default=None, max_length=1000)


class TaskStatusUpdateRequest(BaseModel):
    scheduled_date: date | None = None
    postpone_to: date | None = None
    note: str | None = Field(default=None, max_length=1000)

    @model_validator(mode="after")
    def validate_postpone_date(self) -> "TaskStatusUpdateRequest":
        if self.scheduled_date and self.postpone_to and self.postpone_to < self.scheduled_date:
            raise ValueError("postpone_to must be later than or equal to scheduled_date")
        return self
