from __future__ import annotations

import math
import re
from typing import Any

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    ValidationInfo,
    field_validator,
    model_validator,
)

from app.core.risk_thresholds import (
    STRUCTURED_THRESHOLD_SOURCE,
    get_structured_thresholds,
)


class PopulationScope(BaseModel):
    """人群/验证范围披露：只描述证据边界，不改变预测或风险等级。"""

    model_config = ConfigDict(protected_namespaces=())

    scope_version: str = Field(..., description="人群范围登记版本")
    population_id: str = Field(..., description="运行时人群 ID")
    population_label: str = Field(..., description="人类可读的人群描述")
    language: str | None = Field(default=None, description="适用语言")
    setting: str | None = Field(default=None, description="采集/使用场景")
    label_definition: str = Field(..., description="训练与验证标签的定义")
    validation_cohort: str = Field(..., description="验证队列与协议摘要")
    evidence_level: str = Field(
        ...,
        description=(
            "证据等级: internal_source_split/groupwise_oof/cross_source/"
            "small_internal_split/small_external/synthetic_label_derived/"
            "not_evaluable/heuristic_fallback"
        ),
    )
    transport_risk: str = Field(
        ..., description="跨人群迁移风险: unknown/not_evaluated/degraded"
    )
    calibration_scope: str | None = Field(
        default=None, description="校准范围与目标域校准状态"
    )
    intended_use: str = Field(..., description="登记用途")
    out_of_scope: list[str] = Field(
        default_factory=list, description="明确未验证/不适用的人群与场景"
    )
    automated_decision_allowed: bool = Field(
        default=False, description="是否允许仅凭本结果自动决策"
    )
    abstention_recommended: bool = Field(
        default=True, description="是否建议弃权/转人工复核"
    )
    abstention_reasons: list[str] = Field(
        default_factory=list, description="建议弃权的原因"
    )
    disclosure: str = Field(..., description="面向调用方的人群与弃权提示")


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

    prediction: int = Field(
        ...,
        description=(
            "模型原始 0/1 判定，未融合启发式与危机规则"
            "（ML 不可用时为启发式回退），不等同于最终风险结论"
        ),
    )
    probability: float = Field(..., description="模型原始正类概率，未融合")
    sentiment_label: str | None = Field(
        default=None, description="融合后的情感标签（非 prediction 原值）"
    )
    sentiment_score: float | None = Field(
        default=None, description="融合后的风险分 0-1（不是置信度）"
    )
    distress_score: float | None = Field(default=None, description="情绪困扰程度 0-100")
    crisis_score: float | None = Field(default=None, description="危机表达强度 0-100")
    risk_factors: list[str] = Field(
        default_factory=list, description="检测到的风险因素"
    )
    protective_factors: list[str] = Field(
        default_factory=list, description="检测到的保护因素"
    )
    risk_evidence: dict[str, list[str]] = Field(
        default_factory=dict, description="各风险类别命中的关键词"
    )
    protective_evidence: dict[str, list[str]] = Field(
        default_factory=dict, description="各保护类别命中的关键词"
    )
    crisis_detected: bool = Field(default=False, description="是否检测到危机表达")
    crisis_keywords: list[str] = Field(
        default_factory=list, description="命中的危机关键词"
    )
    risk_level: int | None = Field(
        default=None,
        description=(
            "风险等级 0-4；null 表示未判定（不等于 0 级无风险），"
            "需结合 requires_human_review 与 text_decision_state 复核"
        ),
    )
    text_decision_state: str | None = Field(
        default=None,
        description="文本概率三态门控：normal / suspect / high_risk",
    )
    text_decision_thresholds: dict[str, float | str] | None = Field(
        default=None,
        description=(
            "本次文本门控实际使用的双阈值：suspect_lower / high_upper / source"
        ),
    )
    third_person_matches: list[dict[str, Any]] = Field(
        default_factory=list,
        description="D4：第三人称/转述命中，只记录不升级",
    )
    crisis_override: bool = Field(
        default=False, description="是否因危机检测覆盖风险等级"
    )
    requires_human_review: bool = Field(
        default=False, description="是否建议人工复核"
    )
    review_reasons: list[str] = Field(
        default_factory=list, description="触发人工复核的原因"
    )
    matched_categories: list[str] = Field(
        default_factory=list, description="命中的危机信号类别"
    )
    suppressed_crisis_keywords: list[str] = Field(
        default_factory=list, description="被否定/元话语上下文过滤的危机关键词"
    )
    score_components: dict[str, Any] | None = Field(
        default=None, description="融合分量（ML/启发式/权重/危机规则），非置信度"
    )
    chunk_info: dict[str, Any] | None = Field(
        default=None, description="长文本分块信息（仅当文本被切块时返回）"
    )
    model_used: str
    population_scope: PopulationScope | None = Field(
        default=None, description="本次文本推理的人群与验证范围披露"
    )


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
                raw = v[field]
                if raw is None:
                    errors.append(f"{field} 不能为 null")
                    continue
                try:
                    val = float(raw)
                except (TypeError, ValueError):
                    errors.append(f"{field}={raw!r} 不是数值")
                else:
                    if not math.isfinite(val):
                        errors.append(f"{field}={val!r} 不是有限数值")
                    elif val < min_val or val > max_val:
                        errors.append(
                            f"{field}={val} 超出有效范围 [{min_val}, {max_val}]"
                        )

        # 拒绝空/全未知字段输入。旧行为会把空字典补成「默认人」
        # （sleep 7h / quality 5 / HR 70 / …）并返回可落库的风险分，
        # 等同于凭空生成评估结论。
        recognized = {
            "sleep_hours",
            "sleep_quality",
            "exercise_minutes",
            "heart_rate",
            "systolic_bp",
            "diastolic_bp",
            "steps",
        }
        if not any(key in recognized and value is not None for key, value in v.items()):
            errors.append(
                "physiological 至少需要包含一项可识别的生理字段（"
                "sleep_hours/sleep_quality/exercise_minutes/heart_rate/"
                "systolic_bp/diastolic_bp/steps）"
            )

        if errors:
            raise ValueError("; ".join(errors))

        return v


class FusionPredictRequest(BaseModel):
    # P0-FIX-2026-10-11: 本模型此前**完全没有入参约束**，与同文件
    # TextPredictRequest（max_length=5000）形成明显不一致。
    # 后果：
    #   * text 无长度上限 —— 融合推理会把整段文本喂进 BERT 分词，超长输入
    #     在推理侧被截断（行为不可预期）且请求体可被撑到很大，是廉价的
    #     资源耗尽面；
    #   * features / physiological 键数无上限 —— 与 StructuredPredictRequest
    #     已有的 50 键上限不一致，同一份特征表在不同端点校验结果不同。
    features: dict[str, Any] | None = Field(default=None, description="结构化特征")
    text: str | None = Field(
        default=None,
        max_length=5000,
        description="文本特征（与 TextPredictRequest 同上限）",
    )
    physiological: dict[str, Any] | None = Field(default=None, description="生理特征")

    @field_validator("features")
    @classmethod
    def features_max_keys(cls, v: dict[str, Any] | None) -> dict[str, Any] | None:
        if v is not None and len(v) > 50:
            raise ValueError("features 字典最多包含 50 个键")
        return v

    @field_validator("physiological")
    @classmethod
    def physiological_max_keys(
        cls, v: dict[str, Any] | None
    ) -> dict[str, Any] | None:
        if v is not None and len(v) > 50:
            raise ValueError("physiological 字典最多包含 50 个键")
        return v


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
    population_scope: PopulationScope | None = Field(
        default=None, description="本次结构化推理的人群与验证范围披露"
    )
    input_adjustments: dict[str, Any] = Field(
        default_factory=dict, description="输入域钳制/归一与缺失中性化留痕"
    )
    defaulted_missing_fields: list[dict[str, Any]] = Field(
        default_factory=list, description="未填→中性 0 的字段（与用户填 0 区分）"
    )
    thresholds: dict[str, int] = Field(
        default_factory=get_structured_thresholds,
        description=(
            "本次分级使用的四档阈值，形状固定 mild/moderate/high/critical；"
            "数值唯一来源 app/core/risk_thresholds.py，前端不得保存副本"
        ),
    )
    threshold_source: str = Field(
        default=STRUCTURED_THRESHOLD_SOURCE,
        description=(
            "阈值口径来源：calibration_v123_p25_p50_p75_p90（校准路径）"
            "或 fallback（启发式/降级兜底）"
        ),
    )


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
    population_scope: PopulationScope | None = Field(
        default=None, description="本次推理的人群与验证范围披露"
    )
    input_adjustments: dict[str, Any] = Field(
        default_factory=dict, description="输入域钳制/归一与缺失中性化留痕"
    )
    defaulted_missing_fields: list[dict[str, Any]] = Field(
        default_factory=list, description="未填→中性 0 的字段（与用户填 0 区分）"
    )
    thresholds: dict[str, int] = Field(
        default_factory=get_structured_thresholds,
        description=(
            "本次分级使用的四档阈值（mild/moderate/high/critical），"
            "唯一来源 app/core/risk_thresholds.py"
        ),
    )
    threshold_source: str = Field(
        default=STRUCTURED_THRESHOLD_SOURCE,
        description=(
            "阈值口径来源：calibration_v123_p25_p50_p75_p90 或 fallback"
        ),
    )


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
    population_scope: PopulationScope | None = Field(
        default=None, description="本次生理推理的人群与验证范围披露"
    )


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
    population_scope: PopulationScope | None = Field(
        default=None, description="本次融合推理的人群与验证范围披露"
    )


# H-CONTRACT-01: 数据集/模型名用于拼接文件路径 (experiment_data.py dataset_path),
# 仅允许安全字符, 阻断路径穿越与非法文件名 (控制字符会触发 OSError → 500)
_SAFE_NAME_RE = re.compile(r"^[A-Za-z0-9_.\-]+$")


def _validate_safe_name(v: str, field: str) -> str:
    if not _SAFE_NAME_RE.fullmatch(v):
        raise ValueError(f"{field} 只能包含字母、数字、点、下划线和连字符")
    return v


class DatasetImportRequest(BaseModel):
    dataset_name: str = Field(..., min_length=1, max_length=120)
    source_type: str = Field(default="local", max_length=30)
    train_ratio: float = Field(default=0.7, ge=0.5, le=0.9)
    val_ratio: float = Field(default=0.15, ge=0.05, le=0.3)
    test_ratio: float = Field(default=0.15, ge=0.05, le=0.3)

    @field_validator("dataset_name")
    @classmethod
    def _dataset_name_safe(cls, v: str) -> str:
        return _validate_safe_name(v, "dataset_name")

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

    @field_validator("dataset_name", "model_name")
    @classmethod
    def _names_safe(cls, v: str, info: ValidationInfo) -> str:
        return _validate_safe_name(v, info.field_name or "name")


class EvaluateRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    dataset_name: str = Field(..., min_length=1, max_length=120)
    model_name: str = Field(..., min_length=1, max_length=120)
    split: str = Field(default="validation", pattern="^(validation|test)$")


class CompareRequest(BaseModel):
    model_config = ConfigDict(protected_namespaces=())

    dataset_name: str = Field(..., min_length=1, max_length=120)
    # 2026-10-04 (P0-1): 默认比较列表移除 bert_text_classifier —— 其权重已于同日归档到
    # models/_archive/bert_text_classifier_20261004/。留在默认值里会让「不传 model_names」
    # 的请求稳定命中一个已不存在的模型路径(静默降级为 500/回退, 反而更难排查)。
    # 前端 ExperimentTab 三个操作均显式传 model_names, 不受此变更影响。
    model_names: list[str] = Field(
        default_factory=lambda: [
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
