from pydantic import BaseModel, Field


class MeditationLogRequest(BaseModel):
    content_id: int | None = Field(default=None, ge=1)
    completed: bool = False


class RecentViewRequest(BaseModel):
    content_id: int = Field(ge=1)
