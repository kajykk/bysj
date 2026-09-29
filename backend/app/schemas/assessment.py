from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator

# ── AUDIT-2026-09-28-P1-2: data_payload 的真实大小约束 ──────────────────
# 背景：原先写成 `data_payload: dict = Field(...)`（完全无约束）以及
# `dict = Field(default_factory=dict, max_length=5000)`（**假防护**）——
# Pydantic 的 max_length 只对 str/list 等序列类型生效，对 dict 不产生任何校验，
# 注释里声称的 5000 上限从未生效。攻击者可提交超大或深层嵌套的 JSON，
# 在 JSON 解析与后续特征工程链路上造成 CPU/内存放大。
#
# 说明：本校验发生在请求体已被 ASGI 读取之后，因此不能替代网关层的
# body size 限制（nginx client_max_body_size / uvicorn --limit-max-requests）。
# 它的作用是守住业务处理链，避免畸形 payload 进入特征工程。
_MAX_PAYLOAD_KEYS = 200
_MAX_PAYLOAD_JSON_CHARS = 50_000
_MAX_PAYLOAD_DEPTH = 10


def _payload_depth(value: Any) -> int:
    """迭代计算嵌套深度（避免递归导致深嵌套输入爆栈）."""
    depth = 0
    level: list[Any] = [value]
    while level:
        depth += 1
        nxt: list[Any] = []
        for item in level:
            if isinstance(item, dict):
                nxt.extend(item.values())
            elif isinstance(item, (list, tuple)):
                nxt.extend(item)
        level = nxt
        if depth > _MAX_PAYLOAD_DEPTH:
            return depth
    return depth


def _validate_data_payload(v: dict[str, Any]) -> dict[str, Any]:
    if len(v) > _MAX_PAYLOAD_KEYS:
        raise ValueError(
            f"data_payload 顶层键数量 {len(v)} 超过上限 {_MAX_PAYLOAD_KEYS}"
        )
    try:
        import json

        size = len(json.dumps(v, ensure_ascii=False, default=str))
    except (TypeError, ValueError) as exc:
        raise ValueError(f"data_payload 无法序列化为 JSON: {exc}") from exc
    if size > _MAX_PAYLOAD_JSON_CHARS:
        raise ValueError(
            f"data_payload 序列化后 {size} 字符，超过上限 {_MAX_PAYLOAD_JSON_CHARS}"
        )
    depth = _payload_depth(v)
    if depth > _MAX_PAYLOAD_DEPTH:
        raise ValueError(
            f"data_payload 嵌套深度 {depth} 超过上限 {_MAX_PAYLOAD_DEPTH}"
        )
    return v


class StructuredCollectRequest(BaseModel):
    assessment_type: str = Field(default="comprehensive", min_length=1, max_length=50)
    data_payload: dict[str, Any] = Field(...)

    @field_validator("data_payload")
    @classmethod
    def _check_payload(cls, v: dict[str, Any]) -> dict[str, Any]:
        return _validate_data_payload(v)


class StructuredCollectResponse(BaseModel):
    assessment_id: int
    risk_score: float
    risk_level: int
    severity: str
    risk_factors: list[dict]
    # PERF-P1-004: warning 异步处理, None 表示 pending (响应时未确定)
    warning_generated: bool | None
    warning_id: int | None


class DraftUpsertRequest(BaseModel):
    draft_type: str = Field(..., min_length=1, max_length=50)
    data_payload: dict[str, Any] = Field(...)

    @field_validator("data_payload")
    @classmethod
    def _check_payload(cls, v: dict[str, Any]) -> dict[str, Any]:
        return _validate_data_payload(v)


class TextAnalyzeRequest(BaseModel):
    entry_type: str = Field(..., min_length=1, max_length=50)
    content: str = Field(..., min_length=1, max_length=10000)
    emotion_tags: list[str] = Field(default_factory=list, max_length=10)
    mood_score: int | None = Field(default=None, ge=1, le=5)


class PhysiologicalRecordRequest(BaseModel):
    source: str = Field(default="manual", min_length=1, max_length=50)
    # P1-F5 修复：与 models/assessment.py 的 CheckConstraint 保持一致
    # 原 schemas/assessment.py 与 schemas/model_predict.py 范围不一致，
    # 且与 DB 约束冲突（schema 拒绝 DB 接受的数据，或 schema 接受 DB 拒绝的数据导致 IntegrityError）
    sleep_hours: float | None = Field(default=None, ge=0, le=24)
    sleep_quality: int | None = Field(default=None, ge=0, le=10)
    exercise_minutes: int | None = Field(default=None, ge=0, le=1440)
    heart_rate: int | None = Field(default=None, ge=30, le=250)
    systolic_bp: int | None = Field(default=None, ge=50, le=300)
    diastolic_bp: int | None = Field(default=None, ge=30, le=200)
    steps: int | None = Field(default=None, ge=0, le=500000)
    # AUDIT-2026-09-28-P1-2: 原先的 max_length=5000 对 dict 无效（假防护），改为真实校验
    data_payload: dict[str, Any] = Field(default_factory=dict)

    @field_validator("data_payload")
    @classmethod
    def _check_payload(cls, v: dict[str, Any]) -> dict[str, Any]:
        return _validate_data_payload(v)


class DataHistoryItem(BaseModel):
    id: int
    type: str
    created_at: datetime
    data: dict
