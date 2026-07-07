from __future__ import annotations

from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class TabularPredictRequest(BaseModel):
    features: dict[str, Any] = Field(..., description="用于模型推理的特征字典")

    @field_validator("features")
    @classmethod
    def features_max_keys(cls, v: dict[str, Any]) -> dict[str, Any]:
        if len(v) > 50:
            raise ValueError("features 字典最多包含 50 个键")
        return v


class TextPredictRequest(BaseModel):
    text: str = Field(
        ..., min_length=1, max_length=5000, description="用于文本模型推理的原始文本"
    )


class TextPredictResult(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    prediction: int
    probability: float
    sentiment_label: str | None = None
    sentiment_score: float | None = None
    distress_score: float | None = Field(default=None, description="情绪困扰程度 0-100")
    crisis_score: float | None = Field(default=None, description="危机表达强度 0-100")
    risk_factors: list[str] = Field(
        default_factory=list, description="检测到的风险因素"
    )
    protective_factors: list[str] = Field(
        default_factory=list, description="检测到的保护因素"
    )
    crisis_detected: bool = Field(default=False, description="是否检测到危机表达")
    crisis_keywords: list[str] = Field(
        default_factory=list, description="命中的危机关键词"
    )
    risk_level: int = Field(default=0, description="风险等级 0-4")
    crisis_override: bool = Field(
        default=False, description="是否因危机检测覆盖风险等级"
    )
    model_used: str


class PhysiologicalPredictRequest(BaseModel):
    physiological: dict[str, Any] = Field(..., description="用于生理模型推理的特征字典")

    @field_validator("physiological")
    @classmethod
    def physiological_max_keys(cls, v: dict[str, Any]) -> dict[str, Any]:
        if len(v) > 50:
            raise ValueError("physiological 字典最多包含 50 个键")
        return v

    @field_validator("physiological")
    @classmethod
    def validate_ranges(cls, v: dict[str, Any]) -> dict[str, Any]:
        """校验生理数据范围。"""
        # P1-F5 修复：与 models/assessment.py 的 CheckConstraint 保持一致
        # 原范围（如 sleep_hours [0,16]、heart_rate [35,220]）与 DB 约束不一致，
        # 导致 schema 拒绝 DB 接受的数据，或 DB 拒绝 schema 接受的数据。
        ranges = {
            "sleep_hours": (0, 24),
            "sleep_quality": (0, 10),
            "exercise_minutes": (0, 1440),
            "heart_rate": (30, 250),
            "systolic_bp": (50, 300),
            "diastolic_bp": (30, 200),
            "steps": (0, 500000),
        }

        errors = []
        for field, (min_val, max_val) in ranges.items():
            if field in v:
                val = float(v[field])
                if val < min_val or val > max_val:
                    errors.append(f"{field}={val} 超出有效范围 [{min_val}, {max_val}]")

        if errors:
            raise ValueError("; ".join(errors))

        return v


class FusionPredictRequest(BaseModel):
    features: dict[str, Any] | None = Field(default=None, description="结构化特征")
    text: str | None = Field(default=None, description="文本特征")
    physiological: dict[str, Any] | None = Field(default=None, description="生理特征")


class FusionDetailItem(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    modality_scores: dict[str, dict[str, Any]] = Field(default_factory=dict)
    weights: dict[str, float] = Field(default_factory=dict)
    gate_weights: list[float] = Field(default_factory=list)
    keras_fusion: float | None = None
    dominant_modality: str | None = None
    modality_quality: dict[str, str] = Field(default_factory=dict)


class InterventionActionItem(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    level: str
    actions: list[str]


class DataQualityItem(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    missing_fields: list[str] = Field(default_factory=list, description="缺失的字段")
    confidence_penalty: float = Field(default=0.0, description="置信度惩罚值")
    quality_level: str = Field(
        default="complete", description="数据质量等级: complete/partial/poor"
    )


class TabularPredictResult(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    prediction: int
    probability: float
    risk_score: float
    risk_level: int
    model_used: str
    data_quality: DataQualityItem | None = Field(
        default=None, description="数据质量信息"
    )
    safety_flags: list[str] = Field(
        default_factory=list, description="安全标记，如 crisis_keyword_detected"
    )
    requires_human_review: bool = Field(default=False, description="是否需要人工复核")


class ModelPredictResponse(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    prediction: int | None = None
    probability: float | None = None
    risk_score: float | None = None
    risk_level: int | None = None
    model_used: str | None = None
    model_version: str | None = None
    model_family: str | None = None
    fallback_used: bool = False
    fallback_reason: str | None = None
    safety_flags: list[str] = Field(default_factory=list)
    requires_human_review: bool = False
    crisis_keywords_matched: list[str] = Field(default_factory=list)
    data_quality: DataQualityItem | None = None
    routing_info: RoutingInfo | None = None
    warning: str | None = None


class PhysiologicalPredictResult(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    prediction: int
    probability: float
    risk_score: float
    risk_level: int
    model_used: str
    confidence: float = Field(default=0.8, description="置信度 0-1")
    data_quality: str = Field(
        default="complete", description="数据质量: complete/partial/poor"
    )
    calibrated: bool = Field(default=True, description="是否经过校准")


class FusionPredictResult(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    risk_score: float
    risk_level: int
    severity: str
    model_used: list[str]
    model_version: str = Field(default="v1.16-risk-calibration", description="模型版本")
    fusion_detail: FusionDetailItem
    intervention_level: str
    intervention_actions: list[str]
    review_required: bool = Field(default=False, description="是否需要人工复核")
    review_triggers: list[str] = Field(
        default_factory=list, description="触发复核的原因列表"
    )
    crisis_override: bool = Field(
        default=False, description="是否因危机检测覆盖风险等级"
    )


class DatasetImportRequest(BaseModel):
    dataset_name: str = Field(..., min_length=1, max_length=120)
    source_type: str = Field(default="local", max_length=30)
    train_ratio: float = Field(default=0.7, ge=0.5, le=0.9)
    val_ratio: float = Field(default=0.15, ge=0.05, le=0.3)
    test_ratio: float = Field(default=0.15, ge=0.05, le=0.3)

    # P1-F6 修复：原代码未校验 train_ratio + val_ratio + test_ratio 是否等于 1.0，
    # 用户可传入 0.7/0.15/0.15（正确）或 0.9/0.3/0.3（错误，总和 1.5），
    # 后者会导致数据集切分异常或索引越界。
    @model_validator(mode="after")
    def _check_ratios_sum(self) -> "DatasetImportRequest":
        total = self.train_ratio + self.val_ratio + self.test_ratio
        # 允许浮点误差 ±0.001
        if abs(total - 1.0) > 0.001:
            raise ValueError(
                f"train_ratio + val_ratio + test_ratio 必须等于 1.0，当前总和为 {total:.4f}"
            )
        return self


class TrainRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    dataset_name: str = Field(..., min_length=1, max_length=120)
    model_name: str = Field(..., min_length=1, max_length=120)
    epochs: int = Field(default=3, ge=1, le=100)
    batch_size: int = Field(default=16, ge=1, le=256)
    learning_rate: float = Field(
        default=2e-5, gt=0, le=1.0
    )  # L-21 修复：限制学习率上限，防止训练不稳定


class EvaluateRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    dataset_name: str = Field(..., min_length=1, max_length=120)
    model_name: str = Field(..., min_length=1, max_length=120)
    split: str = Field(default="validation", pattern="^(validation|test)$")


class CompareRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    dataset_name: str = Field(..., min_length=1, max_length=120)
    model_names: list[str] = Field(
        default_factory=lambda: [
            "bert_text_classifier",
            "text_depression_model",
            "dnn_fusion_model_best",
        ]
    )


class RoutingInfo(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    selected_model_id: str | None = Field(default=None, description="实际使用的模型 ID")
    selected_model_family: str | None = Field(
        default=None, description="模型家族: structured/lite/fallback"
    )
    routing_reason: str | None = Field(default=None, description="路由原因")
    feature_coverage_ratio: float | None = Field(
        default=None, description="特征覆盖率 (0.0-1.0)"
    )
    prediction_confidence_band: str | None = Field(
        default=None, description="置信区间: high/medium/low"
    )


# L-23 修复：ModelPredictResponse 在 RoutingInfo 之前定义，routing_info 字段为前向引用，
# 需在 RoutingInfo 定义后调用 model_rebuild() 重建模型，确保运行时类型检查正确解析。
ModelPredictResponse.model_rebuild()
