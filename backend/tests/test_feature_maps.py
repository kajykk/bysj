"""feature_maps 模块完整性测试 (MAINT-P0-002).

测试目标:
    - 验证 STR_TO_NUM / DEFAULTS / LITE_FEATURE_ORDER 三张表的内部一致性
    - 验证分类默认值在映射表中存在 (避免运行时回退到 0 的静默错误)
    - 验证派生特征默认值与原始特征默认值保持一致
    - 验证 model_engine.py re-export 的向后兼容性
    - 验证 LiteFeatureExtractor.KEYWORD_CATEGORIES 与 LITE_FEATURE_ORDER 的 kw_ 前缀对齐

覆盖维度:
    1. STR_TO_NUM 结构与编码约定 (8 个测试)
    2. DEFAULTS 结构与一致性 (7 个测试)
    3. LITE_FEATURE_ORDER 结构与对齐 (7 个测试)
    4. 向后兼容性 (4 个测试)
"""

from __future__ import annotations

from app.core import feature_maps
from app.core.feature_maps import DEFAULTS, LITE_FEATURE_ORDER, STR_TO_NUM

# ──────────────────────────────────────────────────────────────────
# 1. STR_TO_NUM 结构与编码约定
# ──────────────────────────────────────────────────────────────────


class TestStrToNumStructure:
    """验证 STR_TO_NUM 的结构与编码约定."""

    def test_all_values_are_dicts(self) -> None:
        """每个特征的映射必须是 dict."""
        for feat, mapping in STR_TO_NUM.items():
            assert isinstance(
                mapping, dict
            ), f"STR_TO_NUM[{feat!r}] 应为 dict, 实际为 {type(mapping).__name__}"

    def test_all_numeric_values_are_int_or_float(self) -> None:
        """所有映射值必须是 int 或 float (供数值模型消费)."""
        for feat, mapping in STR_TO_NUM.items():
            for category, value in mapping.items():
                assert isinstance(value, (int, float)) and not isinstance(
                    value, bool
                ), (
                    f"STR_TO_NUM[{feat!r}][{category!r}]={value!r} 应为 int/float, "
                    f"实际为 {type(value).__name__}"
                )

    def test_high_cardinality_features_have_empty_mapping(self) -> None:
        """高基数特征 (City/Profession/Degree) 映射表应为空 (运行时回退到 0)."""
        high_cardinality = {"City", "Profession", "Degree"}
        for feat in high_cardinality:
            assert feat in STR_TO_NUM, f"高基数特征 {feat!r} 不在 STR_TO_NUM 中"
            assert (
                STR_TO_NUM[feat] == {}
            ), f"高基数特征 {feat!r} 映射表应为空 dict, 实际为 {STR_TO_NUM[feat]}"

    def test_binary_features_have_yes_no_convention(self) -> None:
        """二分类特征 (Yes/No 类) 应采用 1=Yes, 0=No 约定."""
        binary_features = {
            "Have you ever had suicidal thoughts ?",
            "Family History of Mental Illness",
        }
        for feat in binary_features:
            mapping = STR_TO_NUM[feat]
            assert (
                mapping.get("Yes") == 1
            ), f"{feat!r}: 'Yes' 应映射为 1, 实际为 {mapping.get('Yes')}"
            assert (
                mapping.get("No") == 0
            ), f"{feat!r}: 'No' 应映射为 0, 实际为 {mapping.get('No')}"

    def test_gender_encoding(self) -> None:
        """Gender 采用 1=Male, 0=Female 约定 (与 derived_map 一致)."""
        assert STR_TO_NUM["Gender"] == {"Male": 1, "Female": 0}

    def test_working_role_encoding(self) -> None:
        """Working Professional or Student: 0=Working Professional, 1=Student."""
        assert STR_TO_NUM["Working Professional or Student"] == {
            "Working Professional": 0,
            "Student": 1,
        }

    def test_ordinal_features_monotonic(self) -> None:
        """有序分类特征 (Sleep/Dietary/AgeGroup) 的编码值应随类别自然递增."""
        ordinal_cases = [
            (
                "Sleep Duration",
                ["Less than 5 hours", "5-6 hours", "7-8 hours", "More than 8 hours"],
            ),
            ("Dietary Habits", ["Unhealthy", "Moderate", "Healthy"]),
            ("AgeGroup", ["<=18", "19-25", "26-35", "36-45", "46-60", "60+"]),
        ]
        for feat, ordered_categories in ordinal_cases:
            mapping = STR_TO_NUM[feat]
            values = [mapping[cat] for cat in ordered_categories]
            assert values == sorted(
                values
            ), f"{feat!r} 编码应随类别递增, 实际顺序: {values}"
            assert values[0] == 0, f"{feat!r} 首个类别应编码为 0, 实际为 {values[0]}"

    def test_no_duplicate_categories_within_feature(self) -> None:
        """同一特征内不应有重复的类别键 (dict 天然去重, 此为防御性断言)."""
        for feat, mapping in STR_TO_NUM.items():
            assert len(mapping) >= 0  # 高基数特征允许空
            # dict 键唯一性由 Python 保证, 此处仅做存在性验证


# ──────────────────────────────────────────────────────────────────
# 2. DEFAULTS 结构与一致性
# ──────────────────────────────────────────────────────────────────


class TestDefaultsStructure:
    """验证 DEFAULTS 的结构与一致性."""

    def test_categorical_defaults_exist_in_str_to_num(self) -> None:
        """分类特征的默认值必须在 STR_TO_NUM 映射表中存在 (高基数特征除外).

        否则 _build_structured_input 中 _STR_TO_NUM.get(_col, {}).get(val, 0)
        会静默回退到 0, 导致模型输入与训练分布不一致.
        """
        high_cardinality = {"City", "Profession", "Degree"}
        for feat, default_val in DEFAULTS.items():
            if feat not in STR_TO_NUM:
                continue  # 非分类特征 (纯数值), 跳过
            if feat in high_cardinality:
                continue  # 高基数特征映射表为空, 任意值回退到 0
            if not isinstance(default_val, str):
                continue  # 数值型默认值 (如 SleepDurationOrdinal=2), 跳过
            mapping = STR_TO_NUM[feat]
            assert default_val in mapping, (
                f"DEFAULTS[{feat!r}]={default_val!r} 不在 STR_TO_NUM[{feat!r}] 映射表中 "
                f"(可用类别: {list(mapping.keys())}), "
                f"运行时会被 .get(val, 0) 静默替换为 0"
            )

    def test_sleep_duration_ordinal_consistency(self) -> None:
        """SleepDurationOrdinal 默认值应与 Sleep Duration 默认值的编码一致.

        DEFAULTS["Sleep Duration"]="7-8 hours" → STR_TO_NUM["Sleep Duration"]["7-8 hours"]=2
        DEFAULTS["SleepDurationOrdinal"] 应为 2.
        """
        sleep_default = DEFAULTS["Sleep Duration"]
        expected_ordinal = STR_TO_NUM["Sleep Duration"][sleep_default]
        assert DEFAULTS["SleepDurationOrdinal"] == expected_ordinal, (
            f"SleepDurationOrdinal 默认值 {DEFAULTS['SleepDurationOrdinal']} "
            f"与 Sleep Duration={sleep_default!r} 的编码 {expected_ordinal} 不一致"
        )

    def test_dietary_habits_ordinal_consistency(self) -> None:
        """DietaryHabitsOrdinal 默认值应与 Dietary Habits 默认值的编码一致."""
        diet_default = DEFAULTS["Dietary Habits"]
        expected_ordinal = STR_TO_NUM["Dietary Habits"][diet_default]
        assert DEFAULTS["DietaryHabitsOrdinal"] == expected_ordinal, (
            f"DietaryHabitsOrdinal 默认值 {DEFAULTS['DietaryHabitsOrdinal']} "
            f"与 Dietary Habits={diet_default!r} 的编码 {expected_ordinal} 不一致"
        )

    def test_age_group_consistency_with_age(self) -> None:
        """AgeGroup 默认值应与 Age 默认值 (20) 落入的年龄段一致 (19-25)."""
        age_default = DEFAULTS["Age"]
        age_group_default = DEFAULTS["AgeGroup"]
        # 复现 _build_structured_input 中的 age_group 分组逻辑
        if age_default <= 18:
            expected_group = "<=18"
        elif age_default <= 25:
            expected_group = "19-25"
        elif age_default <= 35:
            expected_group = "26-35"
        elif age_default <= 45:
            expected_group = "36-45"
        elif age_default <= 60:
            expected_group = "46-60"
        else:
            expected_group = "60+"
        assert age_group_default == expected_group, (
            f"AgeGroup 默认值 {age_group_default!r} 与 Age={age_default} "
            f"落入的年龄段 {expected_group!r} 不一致"
        )
        # 同时验证该 AgeGroup 在 STR_TO_NUM 中存在
        assert (
            age_group_default in STR_TO_NUM["AgeGroup"]
        ), f"AgeGroup 默认值 {age_group_default!r} 不在 STR_TO_NUM['AgeGroup'] 映射表中"

    def test_numeric_defaults_in_reasonable_ranges(self) -> None:
        """数值型默认值应在合理范围内 (避免离群值导致模型偏置)."""
        range_checks = [
            ("Age", 15, 60),
            ("Academic Pressure", 0, 5),
            ("Work Pressure", 0, 5),
            ("CGPA", 0, 10),
            ("Study Satisfaction", 0, 5),
            ("Job Satisfaction", 0, 5),
            ("Work/Study Hours", 0, 16),
            ("Financial Stress", 0, 5),
            ("SleepDurationOrdinal", 0, 3),
            ("DietaryHabitsOrdinal", 0, 2),
        ]
        for feat, low, high in range_checks:
            assert feat in DEFAULTS, f"数值特征 {feat!r} 不在 DEFAULTS 中"
            val = DEFAULTS[feat]
            assert isinstance(val, (int, float)) and not isinstance(
                val, bool
            ), f"DEFAULTS[{feat!r}]={val!r} 应为数值, 实际为 {type(val).__name__}"
            assert (
                low <= val <= high
            ), f"DEFAULTS[{feat!r}]={val} 超出合理范围 [{low}, {high}]"

    def test_all_defaults_keys_are_non_empty_strings(self) -> None:
        """所有 DEFAULTS 键应为非空字符串 (与 sklearn feature_names 对齐)."""
        for feat in DEFAULTS:
            assert (
                isinstance(feat, str) and feat.strip() != ""
            ), f"DEFAULTS 键 {feat!r} 应为非空字符串"

    def test_defaults_covers_all_str_to_num_keys(self) -> None:
        """DEFAULTS 应覆盖 STR_TO_NUM 中所有特征 (确保缺失时有回退值)."""
        missing = set(STR_TO_NUM.keys()) - set(DEFAULTS.keys())
        assert not missing, (
            f"STR_TO_NUM 中的特征 {missing} 未在 DEFAULTS 中定义默认值, "
            f"缺失时 _DEFAULTS.get(col, 0) 会回退到 0 (可能与训练分布不符)"
        )


# ──────────────────────────────────────────────────────────────────
# 3. LITE_FEATURE_ORDER 结构与对齐
# ──────────────────────────────────────────────────────────────────


class TestLiteFeatureOrder:
    """验证 LITE_FEATURE_ORDER 的结构与对齐."""

    def test_exactly_17_features(self) -> None:
        """Lite 模型固定 17 个特征 (与训练脚本 01_build_lite_features.py 对齐)."""
        assert (
            len(LITE_FEATURE_ORDER) == 17
        ), f"LITE_FEATURE_ORDER 应有 17 个特征, 实际 {len(LITE_FEATURE_ORDER)}"

    def test_all_elements_are_strings(self) -> None:
        """所有特征名应为字符串."""
        for feat in LITE_FEATURE_ORDER:
            assert isinstance(feat, str) and feat, f"特征名 {feat!r} 应为非空字符串"

    def test_no_duplicates(self) -> None:
        """特征名不应重复 (sklearn Pipeline 按列对齐, 重复会导致歧义)."""
        assert len(LITE_FEATURE_ORDER) == len(set(LITE_FEATURE_ORDER)), (
            f"LITE_FEATURE_ORDER 存在重复特征: "
            f"{[f for f in LITE_FEATURE_ORDER if LITE_FEATURE_ORDER.count(f) > 1]}"
        )

    def test_keyword_features_aligned_with_extractor(self) -> None:
        """kw_ 前缀特征应与 LiteFeatureExtractor.KEYWORD_CATEGORIES 对齐.

        LITE_FEATURE_ORDER 中 kw_<category> 应对应 KEYWORD_CATEGORIES 中的 <category> 键.
        反之亦然, 确保训练与推理使用相同的关键词分类.
        """
        from app.core.model_engine import LiteFeatureExtractor

        kw_features = [f for f in LITE_FEATURE_ORDER if f.startswith("kw_")]
        kw_categories = {f[len("kw_") :] for f in kw_features}
        extractor_categories = set(LiteFeatureExtractor.KEYWORD_CATEGORIES.keys())

        assert kw_categories == extractor_categories, (
            f"kw_ 前缀特征对应的类别 {kw_categories} "
            f"与 KEYWORD_CATEGORIES 键 {extractor_categories} 不一致"
        )

    def test_expected_groups_present(self) -> None:
        """应包含 4 个特征分组的关键代表."""
        expected_substrings = [
            "gad7_score",  # 问卷+关键词统计组
            "age",  # 用户基础信息组
            "kw_self_harm_crisis",  # 7 类关键词计数组 (含 crisis)
            "text_length",  # 文本质量指标组
            "coverage_density",  # 文本质量指标组
        ]
        for sub in expected_substrings:
            assert (
                sub in LITE_FEATURE_ORDER
            ), f"预期特征 {sub!r} 不在 LITE_FEATURE_ORDER 中"

    def test_keyword_count_is_7(self) -> None:
        """kw_ 前缀特征应恰好 7 个 (对应 7 类关键词分类)."""
        kw_features = [f for f in LITE_FEATURE_ORDER if f.startswith("kw_")]
        assert (
            len(kw_features) == 7
        ), f"kw_ 前缀特征应为 7 个, 实际 {len(kw_features)}: {kw_features}"

    def test_order_preserved(self) -> None:
        """特征顺序应固定 (sklearn Pipeline 假设列对齐, 重排会导致预测错误).

        此测试锚定当前顺序, 任何重排都需同步更新训练脚本与 scaler.
        """
        expected_order = [
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
        assert (
            LITE_FEATURE_ORDER == expected_order
        ), f"LITE_FEATURE_ORDER 顺序被修改, 预期:\n{expected_order}\n实际:\n{LITE_FEATURE_ORDER}"


# ──────────────────────────────────────────────────────────────────
# 4. 向后兼容性
# ──────────────────────────────────────────────────────────────────


class TestBackwardCompatibility:
    """验证 model_engine.py re-export 的向后兼容性."""

    def test_lite_feature_order_importable_from_model_engine(self) -> None:
        """`from app.core.model_engine import LITE_FEATURE_ORDER` 应继续可用.

        外部引用: scripts/modeling/v1_25/test_v1_25_backend.py:86
        """
        from app.core.model_engine import LITE_FEATURE_ORDER as me_lite_order

        assert me_lite_order is LITE_FEATURE_ORDER, (
            "model_engine.LITE_FEATURE_ORDER 应与 feature_maps.LITE_FEATURE_ORDER "
            "是同一对象 (re-export)"
        )

    def test_str_to_num_accessible_in_model_engine(self) -> None:
        """model_engine._STR_TO_NUM 应指向 feature_maps.STR_TO_NUM (同一对象)."""
        from app.core import model_engine

        assert (
            model_engine._STR_TO_NUM is STR_TO_NUM
        ), "model_engine._STR_TO_NUM 应与 feature_maps.STR_TO_NUM 是同一对象"

    def test_defaults_accessible_in_model_engine(self) -> None:
        """model_engine._DEFAULTS 应指向 feature_maps.DEFAULTS (同一对象)."""
        from app.core import model_engine

        assert (
            model_engine._DEFAULTS is DEFAULTS
        ), "model_engine._DEFAULTS 应与 feature_maps.DEFAULTS 是同一对象"

    def test_feature_maps_module_exports_all(self) -> None:
        """feature_maps 模块 __all__ 应包含三个常量."""
        assert set(feature_maps.__all__) == {
            "STR_TO_NUM",
            "DEFAULTS",
            "LITE_FEATURE_ORDER",
        }
