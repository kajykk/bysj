"""结构化模型特征映射常量集中模块.

本模块集中定义 model_engine.py 中此前散落在文件顶部的三类硬编码常量:
1. :data:`STR_TO_NUM` —— 分类特征的字符串→数值映射表
2. :data:`DEFAULTS` —— 缺失特征的默认值字典
3. :data:`LITE_FEATURE_ORDER` —— Lite 模型推理时的特征顺序

抽离目的 (MAINT-P0-002):
    - 集中维护与审查特征工程逻辑, 避免 2036 行的 model_engine.py 顶部混杂常量定义
    - 便于单独编写完整性测试 (``tests/test_feature_maps.py``)
    - 为后续按 module 拆分 model_engine.py (MAINT-P2-001) 奠定基础

使用方式:
    >>> from app.core.feature_maps import STR_TO_NUM, DEFAULTS, LITE_FEATURE_ORDER

向后兼容:
    ``model_engine.py`` 通过 ``from app.core.feature_maps import ...`` 重新导出
    这三个常量, 旧代码 ``from app.core.model_engine import LITE_FEATURE_ORDER``
    可继续使用, 无需修改。

约束:
    - 本模块仅包含常量定义, 不含任何可执行逻辑
    - 修改常量必须同步更新 ``tests/test_feature_maps.py`` 中的完整性断言
"""

from __future__ import annotations

from typing import Any

__all__ = ["STR_TO_NUM", "DEFAULTS", "LITE_FEATURE_ORDER"]


# ──────────────────────────────────────────────────────────────────
# 1. 字符串→数值映射表 (STR_TO_NUM)
# ──────────────────────────────────────────────────────────────────

STR_TO_NUM: dict[str, dict[str, int | float]] = {
    "Gender": {"Male": 1, "Female": 0},
    "Sleep Duration": {
        "Less than 5 hours": 0,
        "5-6 hours": 1,
        "7-8 hours": 2,
        "More than 8 hours": 3,
    },
    "Dietary Habits": {"Unhealthy": 0, "Moderate": 1, "Healthy": 2},
    "Have you ever had suicidal thoughts ?": {"Yes": 1, "No": 0},
    "Family History of Mental Illness": {"Yes": 1, "No": 0},
    "Working Professional or Student": {"Working Professional": 0, "Student": 1},
    "AgeGroup": {"<=18": 0, "19-25": 1, "26-35": 2, "36-45": 3, "46-60": 4, "60+": 5},
    "City": {},
    "Profession": {},
    "Degree": {},
}
"""分类特征的字符串→数值映射表.

用于 :meth:`ModelEngine._build_structured_input` 中将 sklearn Pipeline
``numeric_pipe_cols`` 内的字符串特征转换为数值, 供 LR/Scaler 等数值模型消费。

键:
    特征名 (与训练时 sklearn Pipeline 的 ``feature_names_in_`` 对齐)。
值:
    ``{原始字符串类别: 数值编码}`` 字典。

编码约定:
    - **二分类特征** (Gender / Suicidal / Family History / Working Professional):
      采用 ``1=Yes/Male/Student``, ``0=No/Female/Working Professional`` 约定。
    - **有序分类特征** (Sleep Duration / Dietary Habits / AgeGroup):
      编码保留自然顺序, 值随类别严重度/年龄递增。
    - **高基数分类特征** (City / Profession / Degree):
      此处留空 ``{}``, 表示未知类别在转换时回退到 ``0``
      (由 ``_STR_TO_NUM.get(_col, {}).get(val, 0)`` 兜底)。

注意:
    修改本表必须同步检查 :data:`DEFAULTS` 中对应分类特征的默认值是否仍存在于映射中。
"""


# ──────────────────────────────────────────────────────────────────
# 2. 缺失特征默认值 (DEFAULTS)
# ──────────────────────────────────────────────────────────────────

DEFAULTS: dict[str, Any] = {
    "Gender": "Male",
    "Age": 20,
    "City": "Unknown",
    "Working Professional or Student": "Student",
    "Profession": "Student",
    "Academic Pressure": 3,
    "Work Pressure": 0,
    "CGPA": 7.0,
    "Study Satisfaction": 3,
    "Job Satisfaction": 0,
    "Sleep Duration": "7-8 hours",
    "Dietary Habits": "Moderate",
    "Degree": "Undergraduate",
    "Have you ever had suicidal thoughts ?": "No",
    "Work/Study Hours": 8,
    "Financial Stress": 2,
    "Family History of Mental Illness": "No",
    "SleepDurationOrdinal": 2,
    "DietaryHabitsOrdinal": 1,
    "AgeGroup": "19-25",
}
"""缺失特征的默认值字典。

用于以下三处, 当用户输入缺失某特征时回退到该默认值:

1. :meth:`ModelEngine._build_structured_input` (model_engine.py L713)
2. :meth:`ModelEngine._run_experimental_v121` (model_engine.py L1038)
3. :meth:`ModelEngine._run_experimental_v123` (model_engine.py L1086)

设计原则:
    - **分类特征** 的默认值必须在 :data:`STR_TO_NUM` 对应映射表中存在
      (高基数特征 City/Profession/Degree 除外, 它们映射表为空, 任意值回退到 0)。
    - **数值特征** 的默认值取训练集中位数/众数, 避免偏置。
    - **派生特征** (SleepDurationOrdinal / DietaryHabitsOrdinal / AgeGroup)
      的默认值需与对应原始特征的默认值保持一致:

      ============= ============================ ======================
      原始特征       默认值                       派生特征默认值
      ============= ============================ ======================
      Sleep Duration ``"7-8 hours"``             SleepDurationOrdinal=2
      Dietary Habits ``"Moderate"``              DietaryHabitsOrdinal=1
      Age            ``20`` (落在 19-25 区间)     AgeGroup=``"19-25"``
      ============= ============================ ======================

注意:
    :meth:`_build_structured_input` 中的 ``derived_map`` 会在 ``_DEFAULTS`` 之后应用,
    因此这里的默认值仅在用户完全未提供相关输入时生效。
"""


# ──────────────────────────────────────────────────────────────────
# 3. Lite 模型特征顺序 (LITE_FEATURE_ORDER)
# ──────────────────────────────────────────────────────────────────

LITE_FEATURE_ORDER: list[str] = [
    "gad7_score",
    "total_keywords",
    "unique_categories",
    "age",
    "gender",
    "cgpa",
    "kw_academic_pressure",
    "kw_sleep_problem",
    "kw_social_withdrawal",
    "kw_self_harm_crisis",
    "kw_exercise_deficit",
    "kw_low_mood",
    "kw_anxiety_somatic",
    "text_length",
    "chinese_ratio",
    "text_quality_flag",
    "coverage_density",
]
"""Lite 模型 (``mmpsy_lite_model``) 推理时的特征顺序。

共 **17 个特征**, 必须与训练脚本 ``scripts/modeling/v1_25/01_build_lite_features.py``
中的特征顺序完全一致, 否则 ``scaler.transform`` / ``model.predict_proba`` 结果错误。

特征分组 (共 4 组):

    1. **问卷+关键词统计** (3 个):
       ``gad7_score``, ``total_keywords``, ``unique_categories``
    2. **用户基础信息** (3 个):
       ``age``, ``gender``, ``cgpa``
    3. **7 类关键词计数** (7 个, 对应 :class:`LiteFeatureExtractor.KEYWORD_CATEGORIES`):
       ``kw_academic_pressure``, ``kw_sleep_problem``,
       ``kw_social_withdrawal``, ``kw_self_harm_crisis``,
       ``kw_exercise_deficit``, ``kw_low_mood``, ``kw_anxiety_somatic``
    4. **文本质量指标** (4 个):
       ``text_length``, ``chinese_ratio``, ``text_quality_flag``, ``coverage_density``

约束:
    - 顺序固定, 不可重排 (sklearn Pipeline 假设特征按列对齐)。
    - 新增特征需同步: 训练脚本 + scaler 重训练 + 此处更新 +
      ``tests/test_feature_maps.py`` 中的 ``len == 17`` 断言更新。

外部引用:
    ``scripts/modeling/v1_25/test_v1_25_backend.py`` 通过
    ``from app.core.model_engine import LITE_FEATURE_ORDER`` 引用,
    model_engine.py 通过 re-export 保持向后兼容。
"""
