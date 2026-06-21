from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.constants.task_types import TASK_TYPE_SET


class TemplateTaskItem(BaseModel):
    task_name: str = Field(min_length=1, max_length=200)
    task_type: str = Field(min_length=1, max_length=50)
    description: str | None = Field(default=None, max_length=500)
    schedule: str | None = Field(default=None, pattern="^(daily|weekly|monthly|once|manual)$")
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    sort_order: int | None = Field(default=None, ge=0)

    @model_validator(mode="after")
    def validate_task_type(self) -> "TemplateTaskItem":
        if self.task_type not in TASK_TYPE_SET:
            allowed = ", ".join(sorted(TASK_TYPE_SET))
            raise ValueError(f"task_type must be one of: {allowed}")
        return self


class TemplateUpsertRequest(BaseModel):
    id: int | None = Field(default=None, ge=1)
    template_name: str = Field(min_length=1, max_length=100)
    applicable_levels: list[int] = Field(min_length=1, max_length=10)
    task_list: list[TemplateTaskItem] = Field(min_length=1, max_length=100)
    estimated_weeks: int | None = Field(default=None, ge=1, le=52)
    status: str = Field(default="active", pattern="^(active|inactive)$")

    @model_validator(mode="after")
    def validate_applicable_levels(self) -> "TemplateUpsertRequest":
        if len(set(self.applicable_levels)) != len(self.applicable_levels):
            raise ValueError("applicable_levels must not contain duplicate values")
        return self


class ThresholdUpsertRequest(BaseModel):
    level: int = Field(ge=0, le=10)
    level_name: str = Field(min_length=1, max_length=20)
    min_score: float = Field(ge=0, le=100)
    max_score: float = Field(ge=0, le=100)
    color: str = Field(min_length=1, max_length=20)
    action_required: str = Field(min_length=1, max_length=1000)

    @model_validator(mode="after")
    def validate_score_order(self) -> "ThresholdUpsertRequest":
        if self.min_score > self.max_score:
            raise ValueError("min_score must be less than or equal to max_score")
        if self.min_score == self.max_score:
            raise ValueError("min_score and max_score must not be equal")
        return self


class ConfigUpsertRequest(BaseModel):
    config_key: str = Field(min_length=1, max_length=100)
    config_value: dict = Field(default_factory=dict)
    description: str | None = Field(default=None, max_length=500)

    @model_validator(mode="after")
    def validate_config_value(self) -> "ConfigUpsertRequest":
        allowed_scalar_types = (str, int, float, bool)

        def validate_value(value: object, path: str = "config_value", depth: int = 0) -> None:
            if depth > 3:
                raise ValueError(f"{path} nesting is too deep")
            if isinstance(value, dict):
                if not value:
                    raise ValueError(f"{path} must not be empty")
                for key, item in value.items():
                    if not isinstance(key, str) or not key.strip():
                        raise ValueError(f"{path} keys must be non-empty strings")
                    validate_value(item, f"{path}.{key}", depth + 1)
                return
            if isinstance(value, list):
                if len(value) > 100:
                    raise ValueError(f"{path} list is too long")
                for index, item in enumerate(value):
                    validate_value(item, f"{path}[{index}]", depth + 1)
                return
            if value is None:
                return
            if not isinstance(value, allowed_scalar_types):
                raise ValueError(f"{path} contains unsupported type: {type(value).__name__}")
            if isinstance(value, str) and len(value) > 5000:
                raise ValueError(f"{path} string value is too long")

        validate_value(self.config_value)
        return self


class ModelRegistryRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_id: str = Field(min_length=1, max_length=100)
    model_name: str = Field(min_length=1, max_length=200)
    model_type: str = Field(default="unknown", max_length=50)
    file_path: str = Field(default="", max_length=500)
    version: str = Field(default="1.0.0", max_length=20)
    status: str = Field(default="inactive", max_length=20, pattern="^(inactive|active|archived)$")
    accuracy: float | None = Field(default=None, ge=0, le=1)
    f1_score: float | None = Field(default=None, ge=0, le=1)
    latency_ms: float | None = Field(default=None, ge=0)


class ModelUpdateRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    model_name: str | None = Field(default=None, max_length=200)
    model_type: str | None = Field(default=None, max_length=50)
    file_path: str | None = Field(default=None, max_length=500)
    version: str | None = Field(default=None, max_length=20)
    status: str | None = Field(default=None, max_length=20, pattern="^(inactive|active|archived)$")
    accuracy: float | None = Field(default=None, ge=0, le=1)
    f1_score: float | None = Field(default=None, ge=0, le=1)
    latency_ms: float | None = Field(default=None, ge=0)
