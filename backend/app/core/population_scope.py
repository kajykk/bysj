"""Runtime population / validation-scope disclosure.

This module is metadata only: it never changes model routing, scores, thresholds,
or fallbacks. It declares the evidence boundary under which a prediction may be
interpreted, so callers cannot mistake a population-specific screening aid for a
general-population or clinical diagnosis.

SSOT for the evidence itself:
``docs/model-evaluation/POPULATION_EVIDENCE_MATRIX.md``.
"""

from __future__ import annotations

from copy import deepcopy
from typing import Any

POPULATION_SCOPE_VERSION = "2026-11-02"

POPULATION_SCOPES: dict[str, dict[str, Any]] = {
    "structured": {
        "scope_version": POPULATION_SCOPE_VERSION,
        "population_id": "students_self_report_v1_23",
        "population_label": "学生/青年自报问卷人群（Kaggle Student Depression + Mendeley PHQ-9）",
        "language": "en",
        "setting": "在线自报问卷",
        "label_definition": (
            "Kaggle 自报抑郁二分类（约 97.6%）+ Mendeley PHQ-9>=10"
            "（约 2.4%，样本权重 5x）；不是临床诊断标签"
        ),
        "validation_cohort": (
            "内部同源测试 n=4318（阳性率 58.13%）；"
            "干净跨来源 Kaggle->Mendeley n=682"
        ),
        "evidence_level": "internal_source_split",
        "transport_risk": "degraded",
        "calibration_scope": (
            "同源校准良好（ECE 0.0139）；跨来源 ECE 0.1435，"
            "未在目标域重新校准"
        ),
        "intended_use": "学生/青年自报问卷场景的风险筛查辅助与人工复核排序；不输出临床诊断",
        "out_of_scope": [
            "非学生成人（未验证）",
            "临床确诊人群（未验证）",
            "非英语人群（未验证）",
            "仅有文本或生理数据的场景",
            "自动诊断或自动处置",
        ],
        "automated_decision_allowed": False,
        "abstention_recommended": True,
        "abstention_reasons": [
            "运行时无法验证输入者是否属于登记人群",
            "跨来源校准与阈值未在目标域重建",
            "现有证据只支持筛查辅助，不支持自动决策",
        ],
        "disclosure": (
            "本结果仅在“学生/青年自报问卷”人群与自报/PHQ-9 标签口径内解释；"
            "用于其他人群或临床诊断时证据不足，应人工复核。"
        ),
    },
    "text": {
        "scope_version": POPULATION_SCOPE_VERSION,
        "population_id": "chinese_student_text_v1_27",
        "population_label": "中文学生文本（MMPsy 派生语料，groupwise 重训）",
        "language": "zh",
        "setting": "社交媒体/日记文本",
        "label_definition": "PHQ-9 二分类（按 user_id 聚合）；不是临床访谈诊断",
        "validation_cohort": (
            "sibling-aware groupwise OOF n=8379 / 1277 组"
            "（阳性率 21.63%）；AUC 0.8437 / F1 0.5864"
        ),
        "evidence_level": "groupwise_oof",
        "transport_risk": "not_evaluated",
        "calibration_scope": (
            "原始概率 ECE 0.0855；cross-fitted Platt 可改善但未上生产"
        ),
        "intended_use": "中文学生文本的筛查辅助；必须人工复核",
        "out_of_scope": [
            "非中文文本（未验证）",
            "非学生成人（未验证）",
            "临床访谈文本（未验证）",
            "跨域长文本（未验证）",
            "仅凭关键词自动决策",
        ],
        "automated_decision_allowed": False,
        "abstention_recommended": True,
        "abstention_reasons": [
            "groupwise OOF F1 仅 0.5864，跨人群覆盖未验证",
            "90% 覆盖下阳性自动告警比例约 0.353，其余需人工复核",
            "无独立中文专家标注外部集",
        ],
        "disclosure": (
            "本结果仅在“中文学生文本”人群与 PHQ-9 自报标签口径内解释；"
            "用于其他人群、其他语言或临床诊断时证据不足，应人工复核。"
        ),
    },
    "physiological": {
        "scope_version": POPULATION_SCOPE_VERSION,
        "population_id": "depresjon_clinical_v2",
        "population_label": (
            "Depresjon 临床队列的合成生理特征映射"
            "（n=1029；队列标签真实，5/7 原始特征由标签驱动生成）"
        ),
        "language": None,
        "setting": "活动记录队列 → 合成 7 列生理 schema（非真实传感器读数）",
        "label_definition": (
            "depression_label 是真实队列的病例/对照分组；"
            "phq9_score 与 heart_rate/sleep_hours/sleep_quality/systolic_bp/"
            "diastolic_bp 是转换脚本按标签分组生成的噪声副本，不是真实测量"
        ),
        "validation_cohort": (
            "固定切分 test n=157；AUC 0.9451 主要由合成特征解释"
            "（仅真实 actigraphy 派生列 5 折 OOF AUC 0.6443），"
            "不能解释为真实生理信号的抑郁识别性能"
        ),
        "evidence_level": "synthetic_label_derived",
        "transport_risk": "not_evaluated",
        "calibration_scope": (
            "校准对象是合成特征管线，不是真实生理信号；"
            "ECE 0.2160 / 校准斜率 3.760 仅作管线读数，不能外推到可穿戴设备"
        ),
        "intended_use": (
            "仅用于接口联调、生产管线回归与演示；"
            "不得作为真实生理信号筛查、诊断或风险排序依据"
        ),
        "out_of_scope": [
            "任何真实可穿戴/体检数据解释（训练特征为标签驱动合成）",
            "普通人群（未验证）",
            "消费级可穿戴用户（未验证）",
            "缺少睡眠/血压等字段的采集协议",
            "因果解释（剂量反应非单调）",
            "自动诊断或自动处置",
        ],
        "automated_decision_allowed": False,
        "abstention_recommended": True,
        "abstention_reasons": [
            "训练特征 5/7 为标签驱动合成，AUC/F1 不能读作真实生理性能",
            "仅真实 actigraphy 派生列的 5 折 OOF AUC 为 0.6443",
            "测试集仅 157 行，置信区间宽",
            "原始概率未校准（ECE 0.2160，斜率 3.760）",
            "无第二套同 schema 的真实生理外部抑郁数据集",
        ],
        "disclosure": (
            "本结果来自 Depresjon 队列标签驱动的合成特征管线，"
            "不代表模型能从真实心率、睡眠或血压识别抑郁；"
            "不得外推到普通人群、消费级可穿戴用户或临床诊断，应人工复核。"
        ),
    },
    "fusion": {
        "scope_version": POPULATION_SCOPE_VERSION,
        "population_id": "no_aligned_three_modality_cohort",
        "population_label": "无对齐三模态有标签人群",
        "language": None,
        "setting": "多模态信号汇总",
        "label_definition": "无可评估的统一抑郁标签",
        "validation_cohort": "无对齐三模态有标签样本；not_evaluable",
        "evidence_level": "not_evaluable",
        "transport_risk": "unknown",
        "calibration_scope": "不适用；不得从合成分数网格推断",
        "intended_use": "仅作多模态信号汇总展示，必须人工复核",
        "out_of_scope": [
            "任何融合性能声明",
            "任何模态贡献声明",
            "任何人群阈值声明",
            "全人群或临床诊断声明",
            "自动诊断或自动处置",
        ],
        "automated_decision_allowed": False,
        "abstention_recommended": True,
        "abstention_reasons": [
            "无对齐三模态有标签样本，融合性能不可评估",
            "融合分数不能作为人群级证据",
            "必须人工复核",
        ],
        "disclosure": (
            "融合结果没有对齐三模态有标签样本支持，不能作为人群级性能或"
            "临床结论；仅用于信号汇总展示，应人工复核。"
        ),
    },
}

_MODALITY_ALIASES: dict[str, str] = {
    "structured": "structured",
    "tabular": "structured",
    "text": "text",
    "physiological": "physiological",
    "physio": "physiological",
    "fusion": "fusion",
}


def get_population_scope(modality: str) -> dict[str, Any]:
    """Return a deep copy of the registered scope for ``modality``."""
    key = _MODALITY_ALIASES.get(modality, modality)
    if key not in POPULATION_SCOPES:
        raise ValueError(f"未登记的人群范围模态: {modality!r}")
    return deepcopy(POPULATION_SCOPES[key])


def get_population_scope_for_model_id(model_id: str) -> dict[str, Any] | None:
    """Best-effort mapping from registry model ID to a scope, for status views."""
    normalized = model_id.strip().lower()
    for prefix in ("structured", "text", "physiological", "fusion"):
        if normalized.startswith(prefix):
            return get_population_scope(prefix)
    return None


def attach_population_scope(
    result: dict[str, Any],
    modality: str,
) -> dict[str, Any]:
    """Attach (or refresh) ``population_scope`` on an inference result.

    Refreshing on every return path is deliberate: cached results written before
    this metadata existed must not be served without the disclosure.
    """
    if not isinstance(result, dict):
        return result

    scope = get_population_scope(modality)
    model_used = str(result.get("model_used") or "").lower()
    degraded = bool(result.get("fallback_used")) or any(
        token in model_used for token in ("fallback", "heuristic")
    )
    if degraded:
        scope["evidence_level"] = "heuristic_fallback"
        scope["transport_risk"] = "not_evaluated"
        scope["automated_decision_allowed"] = False
        scope["abstention_recommended"] = True
        scope["abstention_reasons"] = [
            *scope["abstention_reasons"],
            "本次结果来自启发式回退/降级路径，未经登记模型验证",
        ]
        scope["disclosure"] = (
            f"{scope['disclosure']} 本次结果来自启发式回退，证据等级进一步降低。"
        )

    result["population_scope"] = scope
    return result


__all__ = [
    "POPULATION_SCOPE_VERSION",
    "POPULATION_SCOPES",
    "attach_population_scope",
    "get_population_scope",
    "get_population_scope_for_model_id",
]
