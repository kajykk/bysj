"""ML 决策阈值口径的唯一事实源（ROUND_16 / P1-8）。

缺口实证（2026-10-19）：``backend/models/text/improved_bilingual_metrics.json``
顶层 ``threshold=0.3``（生产契约 ``settings.text_bilingual_decision_threshold``
亦为 0.30），但其 headline 块 ``groupwise_ooF`` 的混淆矩阵实测对应阈值扫描表
**threshold=0.5** 行（脚本 ``v1_27/04_retrain_bilingual_text_groupwise.py``
的 ``_evaluate`` 硬编码 ``p >= 0.5``）。同一文件里「标称阈值」与「实际计算
阈值」是两个值，任何按 0.3 解读 headline 的结论都会错。

本模块把散落的决策阈值集中为单一事实源，行为不变（纯口径显式化），并给出
**口径对照表**。原则：

1. 概率标度的「决策阈值」只有生产一个（双语文本 0.30，来自 Settings）；
2. 历史 headline 的「计算阈值」是既成事实（0.50），如实登记为独立口径，
   **不得**回改历史数字，也不得把两者混为一谈；
3. 风险分级 cutoff 是 0–100 风险分标度，与概率阈值不同量纲，分表登记；
4. 置信回退阈值 0.5 是可用性语义（``should_fallback``），与决策阈值不同用途。

| 口径 | 值 | 位置 | 消费方 |
|---|---|---|---|
| 双语文本决策阈值（概率） | 0.30 | 本模块 + Settings 同值 | ``predict.py`` 文本路径 |
| headline 历史计算阈值 | 0.50 | 本模块 + metrics JSON ``headline_eval_threshold`` | 仅历史评估读数 |
| DCA 临床合理阈值区间 | 0.10–0.40 | 本模块 → ``model_validation`` | 决策曲线汇总 |
| 置信回退阈值 | 0.50 | ``confidence.LOW_CONFIDENCE_THRESHOLD`` | ``risk_thresholds.should_fallback`` |
| 模态质量分档 | 0.80 / 0.50 | ``confidence.MODALITY_*`` | fusion 质量分档 |
| 风险分级 cutoff（0–100 分） | 18/35/55/72 | ``models/v1.23_external_lr/threshold_config.json`` | 结构化分级 |
"""

from __future__ import annotations

#: 双语文本决策阈值（概率标度）——与 ``settings.text_bilingual_decision_threshold``
#: 双向钉死：Settings 默认值引用本常量，一致性闸门
#: （test_p2_40 TestThresholdSsot）断言任何一侧漂移即红。
TEXT_BILINGUAL_DECISION_THRESHOLD: float = 0.30

#: improved_bilingual_metrics.json headline（groupwise_ooF）的**实际计算阈值**。
#: 历史事实（v1_27 脚本 ``_evaluate`` 硬编码 0.5），不回改历史数字；
#: metrics JSON 的 ``headline_eval_threshold`` 字段与本常量钉死。
BILINGUAL_HEADLINE_EVAL_THRESHOLD: float = 0.50

#: DCA 临床合理阈值区间（筛查式预警：不漏报优先，取中低阈值段）。
#: 只用于汇总判定（净获益是否压过极端线），不改变逐阈值曲线本身。
DCA_CLINICAL_RANGE: tuple[float, float] = (0.1, 0.4)
