from typing import Literal

from pydantic import BaseModel, Field


class WarningHandleRequest(BaseModel):
    action: Literal["handle", "ignore"] = Field(default="handle")
    note: str | None = None


class ConsultationCreateRequest(BaseModel):
    warning_id: int | None = Field(default=None, ge=1)
    main_topics: str | None = Field(default=None, min_length=1, max_length=500)
    client_status: str | None = Field(default=None, max_length=200)
    interventions: str | None = Field(default=None, max_length=1000)
    next_plan: str | None = None
    notes: str | None = None


class GroupCreateRequest(BaseModel):
    group_name: str = Field(min_length=1, max_length=100)
    description: str | None = None
    color_tag: str = Field(default="#409EFF", pattern=r"^#[0-9A-Fa-f]{6}$")


class GroupMemberAddRequest(BaseModel):
    user_id: int = Field(ge=1)


class BindCodeRequest(BaseModel):
    bind_code: str = Field(min_length=4, max_length=10)
