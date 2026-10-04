"""置信度阈值与「低置信灰区」口径的唯一事实源。

AUDIT-2026-10-04（P2-2 立项核查）：此前置信度阈值散落在多处硬编码，且文档里
误写成「四处灰区判定」。实测真实结构是**一条链**：

    fusion_priority_engine 产生触发标记(low_confidence_high_risk_{modality})
        -> review_reasons.ReviewReason 枚举定义
        -> risk_service_report 按前缀消费成报告 feature

其中**真正的判定只有一处**（fusion_priority_engine 的 `confidence < 0.5 and
risk_level >= 3`），另有一处是模态质量分档（fusion 的 0.8/0.5），两处是定义与消费。
本模块把阈值集中，行为保持不变（纯消除魔法数），并为 P2-2 预留灰区接口。

注意两种「低置信」的用途不同，**不要混用**：

| 概念 | 用途 | 是否进生产 |
|---|---|---|
| `LOW_CONFIDENCE_THRESHOLD` + 高风险 | 模型自评把握不足 **且** 风险高 -> 触发**人工**复核 | 是（现有行为） |
| `LLM_REVIEW_ZONE` | 给 LLM 第二意见的**灰区**（0.3~0.6） | **否**，P2-2 实验中，先离线评估 |
"""

from __future__ import annotations

#: 模态置信度低于此值 -> 质量分档为 low_confidence（fusion.py 用）
MODALITY_LOW_CONFIDENCE_THRESHOLD: float = 0.5
#: 模态置信度不低于此值 -> 质量分档为 primary（fusion.py 用）
MODALITY_PRIMARY_CONFIDENCE_THRESHOLD: float = 0.8
#: 触发人工复核的置信度下限（fusion_priority_engine 用）
LOW_CONFIDENCE_THRESHOLD: float = 0.5
#: 触发人工复核所需的风险等级下限（risk_level 0~4）
HIGH_RISK_LEVEL_THRESHOLD: int = 3

#: P2-2 LLM 第二意见的灰区（闭区间下界、开区间上界）。
#: ⚠️ **未接入任何生产路径** —— 合规路径（数据是否出境）确定前不得启用。
LLM_REVIEW_ZONE: tuple[float, float] = (0.3, 0.6)


def is_low_confidence_high_risk(confidence: float, risk_level: int) -> bool:
    """现有生产语义：置信度低 **且** 风险高 -> 需要人工复核。

    供 fusion_priority_engine 使用，抽取自其原先的内联判断（行为等价）。
    """
    return confidence < LOW_CONFIDENCE_THRESHOLD and risk_level >= HIGH_RISK_LEVEL_THRESHOLD


def modality_quality(confidence: float) -> str:
    """模态质量分档：primary / secondary / low_confidence（fusion.py 用，行为等价）。"""
    if confidence >= MODALITY_PRIMARY_CONFIDENCE_THRESHOLD:
        return "primary"
    if confidence >= MODALITY_LOW_CONFIDENCE_THRESHOLD:
        return "secondary"
    return "low_confidence"


def in_llm_review_zone(confidence: float) -> bool:
    """是否落在 P2-2 的 LLM 复核灰区。

    ⚠️ 实验用函数，**当前无生产调用方**。启用前必须先决定合规路径
    （见 docs/planning/P2_NEXT_RELEASE_PROPOSALS.md 的 P2-2 节）。
    """
    lo, hi = LLM_REVIEW_ZONE
    return lo <= confidence < hi
