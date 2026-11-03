"""ML 决策阈值口径的唯一事实源（ROUND_16 / P1-8）。

缺口实证（2026-10-19）：``backend/models/text/improved_bilingual_metrics.json``
顶层 ``threshold=0.3``（生产契约 ``settings.text_bilingual_decision_threshold``
亦为 0.30），但其 headline 块 ``groupwise_ooF`` 的混淆矩阵实测对应阈值扫描表
**threshold=0.5** 行（脚本 ``v1_27/04_retrain_bilingual_text_groupwise.py``
的 ``_evaluate`` 硬编码 ``p >= 0.5``）。同一文件里「标称阈值」与「实际计算
阈值」是两个值，任何按 0.3 解读 headline 的结论都会错。

本模块把散落的决策阈值集中为单一事实源，行为不变（纯口径显式化），并给出
**口径对照表**。原则：

1. 概率标度的「决策阈值」只有生产一套（双语文本双阈值 0.30 / 0.55，来自 Settings）；
2. 历史 headline 的「计算阈值」是既成事实（0.50），如实登记为独立口径，
   **不得**回改历史数字，也不得把两者混为一谈；
3. 风险分级 cutoff 是 0–100 风险分标度，与概率阈值不同量纲，分表登记；
4. 置信回退阈值 0.5 是可用性语义（``should_fallback``），与决策阈值不同用途。

| 口径 | 值 | 位置 | 消费方 |
|---|---|---|---|
| 双语文本疑似下界（概率） | 0.30 | 本模块 + Settings 同值 | ``predict.py`` 文本路径 |
| 双语文本高风险上界（概率） | 0.55 | 本模块 + Settings 同值 | ``predict.py`` 文本路径 |
| headline 历史计算阈值 | 0.50 | 本模块 + metrics JSON ``headline_eval_threshold`` | 仅历史评估读数 |
| DCA 临床合理阈值区间 | 0.10–0.40 | 本模块 → ``model_validation`` | 决策曲线汇总 |
| 置信回退阈值 | 0.50 | ``confidence.LOW_CONFIDENCE_THRESHOLD`` | ``risk_thresholds.should_fallback`` |
| 模态质量分档 | 0.80 / 0.50 | ``confidence.MODALITY_*`` | fusion 质量分档 |
| 风险分级 cutoff（0–100 分，生产） | 20/70/93/97（structured） | ``risk_thresholds.MODALITY_RISK_THRESHOLDS`` | 结构化/服务端分级 |
| 风险分级 cutoff（0–100 分，评估） | 18/35/55/72 | ``models/v1.23_external_lr/threshold_config.json`` | 仅评估对照，不接入生产 |

结构化风险分 cutoff 的 **20/70/93/97** 依据 v1.23 外部校准集分位点
（``models/v1.23_external_lr/calibration_config.json``：p25=20.18 /
p50=69.68 / p75=92.82 / p90=97.46），是在输入域钳制与缺失中性化完成后
重新选定的，不是从旧 25/45/65/85 直接调参得来。
"""

from __future__ import annotations

#: 双语文本决策阈值（概率标度）——与 ``settings.text_bilingual_decision_threshold``
#: 双向钉死：Settings 默认值引用本常量，一致性闸门
#: （test_p2_40 TestThresholdSsot）断言任何一侧漂移即红。
TEXT_BILINGUAL_DECISION_THRESHOLD: float = 0.30

#: D2 双阈值门控的上界：概率 > 本值才直接判「高风险」。
#: 0.30–0.55 之间为「疑似、必须人工复核」，不直接判高风险；
#: < 0.30 为正常。与 ``settings.text_bilingual_review_threshold`` 双向钉死。
TEXT_BILINGUAL_REVIEW_THRESHOLD: float = 0.55

#: 文本阈值随响应下发时的来源标记，供前端区分「Settings 生产口径」。
TEXT_DECISION_THRESHOLD_SOURCE: str = "settings_text_bilingual_decision"

#: 文本概率三态标签（对外契约，不随大小写变化）。
TEXT_DECISION_STATE_NORMAL: str = "normal"
TEXT_DECISION_STATE_SUSPECT: str = "suspect"
TEXT_DECISION_STATE_HIGH_RISK: str = "high_risk"


def classify_text_probability(
    probability: float,
    *,
    lower_threshold: float = TEXT_BILINGUAL_DECISION_THRESHOLD,
    upper_threshold: float = TEXT_BILINGUAL_REVIEW_THRESHOLD,
) -> str:
    """按 D2 双阈值把文本概率归类为三态。

    - ``probability < lower_threshold`` → ``normal``
    - ``lower_threshold <= probability <= upper_threshold`` → ``suspect``
    - ``probability > upper_threshold`` → ``high_risk``

    Raises:
        ValueError: 阈值配置非法（上界不大于下界）或概率非有限值。
    """
    import math

    if not (math.isfinite(probability)):
        raise ValueError(f"文本概率不是有限数值: {probability!r}")
    if upper_threshold <= lower_threshold:
        raise ValueError(
            "文本双阈值配置非法：上界必须大于下界 "
            f"(lower={lower_threshold}, upper={upper_threshold})"
        )
    if probability < lower_threshold:
        return TEXT_DECISION_STATE_NORMAL
    if probability <= upper_threshold:
        return TEXT_DECISION_STATE_SUSPECT
    return TEXT_DECISION_STATE_HIGH_RISK


#: improved_bilingual_metrics.json headline（groupwise_ooF）的**实际计算阈值**。
#: 历史事实（v1_27 脚本 ``_evaluate`` 硬编码 0.5），不回改历史数字；
#: metrics JSON 的 ``headline_eval_threshold`` 字段与本常量钉死。
BILINGUAL_HEADLINE_EVAL_THRESHOLD: float = 0.50

#: DCA 临床合理阈值区间（筛查式预警：不漏报优先，取中低阈值段）。
#: 只用于汇总判定（净获益是否压过极端线），不改变逐阈值曲线本身。
DCA_CLINICAL_RANGE: tuple[float, float] = (0.1, 0.4)
