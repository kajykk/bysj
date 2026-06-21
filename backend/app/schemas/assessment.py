from datetime import datetime

from pydantic import BaseModel, Field


class StructuredCollectRequest(BaseModel):
    assessment_type: str = Field(default="comprehensive", min_length=1, max_length=50)
    data_payload: dict = Field(...)


class StructuredCollectResponse(BaseModel):
    assessment_id: int
    risk_score: float
    risk_level: int
    severity: str
    risk_factors: list[dict]
    warning_generated: bool
    warning_id: int | None


class DraftUpsertRequest(BaseModel):
    draft_type: str = Field(..., min_length=1, max_length=50)
    data_payload: dict = Field(...)


class TextAnalyzeRequest(BaseModel):
    entry_type: str = Field(..., min_length=1, max_length=50)
    content: str = Field(..., min_length=1, max_length=10000)
    emotion_tags: list[str] = Field(default_factory=list, max_length=10)
    mood_score: int | None = Field(default=None, ge=1, le=5)


class PhysiologicalRecordRequest(BaseModel):
    source: str = Field(default="manual", min_length=1, max_length=50)
    sleep_hours: float | None = Field(default=None, ge=0, le=24)
    sleep_quality: int | None = Field(default=None, ge=1, le=5)
    exercise_minutes: int | None = Field(default=None, ge=0, le=1440)
    heart_rate: int | None = Field(default=None, ge=30, le=250)
    systolic_bp: int | None = Field(default=None, ge=60, le=300)
    diastolic_bp: int | None = Field(default=None, ge=40, le=200)
    steps: int | None = Field(default=None, ge=0, le=500000)
    data_payload: dict = Field(default_factory=dict, max_length=5000)


class DataHistoryItem(BaseModel):
    id: int
    type: str
    created_at: datetime
    data: dict
