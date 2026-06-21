from pydantic import BaseModel, Field


class RiskTrendQuery(BaseModel):
    days: int = Field(default=30, ge=1, le=365)


class RiskExportQuery(BaseModel):
    format: str = Field(default="json", pattern="^(json|csv)$")
    days: int = Field(default=90, ge=1, le=365)
