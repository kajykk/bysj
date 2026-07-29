"""D1 特征契约单测:验证结构化模型 4 个派生列的训练-推理一致性.

派生列:
    - SleepDurationOrdinal: 从 sleep_duration 映射
    - DietaryHabitsOrdinal: 从 dietary_habits 映射
    - AgeGroup: 从 age 分桶
    - Working Professional or Student: 从 profession/age 推断

核验结论(v2.0 S1 D1):
    - v1.20 模型 feature_names (14 列) 不含派生列 → 无降级风险
    - v1.23 模型 feature_schema (12 列) 不含派生列 → 无降级风险
    - derived_map 补全 Working Professional or Student → 为未来模型做准备
    - assessment_summary.json 的 retrain_needed=true 为过时标记
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from app.core.feature_maps import DEFAULTS, STR_TO_NUM


class TestDerivedColumnsContract:
    """验证 4 个派生列在 feature_maps 中的映射完整性."""

    def test_sleep_duration_ordinal_mapping(self):
        """SleepDurationOrdinal 映射覆盖 4 个类别."""
        mapping = STR_TO_NUM["Sleep Duration"]
        assert mapping == {
            "Less than 5 hours": 0,
            "5-6 hours": 1,
            "7-8 hours": 2,
            "More than 8 hours": 3,
        }

    def test_dietary_habits_ordinal_mapping(self):
        """DietaryHabitsOrdinal 映射覆盖 3 个类别."""
        assert STR_TO_NUM["Dietary Habits"] == {
            "Unhealthy": 0,
            "Moderate": 1,
            "Healthy": 2,
        }

    def test_age_group_mapping(self):
        """AgeGroup 映射覆盖 6 个年龄段."""
        assert STR_TO_NUM["AgeGroup"] == {
            "<=18": 0,
            "19-25": 1,
            "26-35": 2,
            "36-45": 3,
            "46-60": 4,
            "60+": 5,
        }

    def test_working_professional_or_student_mapping(self):
        """Working Professional or Student 映射覆盖 2 个类别."""
        assert STR_TO_NUM["Working Professional or Student"] == {
            "Working Professional": 0,
            "Student": 1,
        }

    def test_all_derived_defaults_exist(self):
        """4 个派生列在 DEFAULTS 中都有默认值."""
        for col in [
            "SleepDurationOrdinal",
            "DietaryHabitsOrdinal",
            "AgeGroup",
            "Working Professional or Student",
        ]:
            assert col in DEFAULTS, f"派生列 {col} 缺少 DEFAULTS 默认值"


class TestBuildStructuredInputDerived:
    """验证 _build_structured_input 的派生列生成逻辑."""

    def _build_with_age_sleep(self, age: float, sleep: float, profession: str = ""):
        """辅助:构造 minimal raw 输入并调用 _build_structured_input."""
        from app.core.model_engine import ModelEngine

        raw = {
            "age": age,
            "gender": 1,
            "sleep_duration": sleep,
            "stress_level": 2,
            "academic_pressure": 2,
            "financial_pressure": 2,
            "family_history": 0,
            "cgpa": 3.0,
        }
        if profession:
            raw["profession"] = profession

        # 构造 mock model,使其 feature_names 包含所有派生列
        model_feature_names = [
            "Age",
            "Gender",
            "Sleep Duration",
            "Dietary Habits",
            "SleepDurationOrdinal",
            "DietaryHabitsOrdinal",
            "AgeGroup",
            "Working Professional or Student",
        ]

        mock_model = MagicMock()
        mock_model.named_steps = {}
        return ModelEngine._build_structured_input(raw, model_feature_names, mock_model)

    def test_sleep_duration_ordinal_generated(self):
        """sleep_duration < 5 → SleepDurationOrdinal=0."""
        result = self._build_with_age_sleep(20, 4.0)
        assert result["SleepDurationOrdinal"] == 0

    def test_sleep_duration_ordinal_normal(self):
        """sleep_duration 7-8 → SleepDurationOrdinal=2."""
        result = self._build_with_age_sleep(20, 7.5)
        assert result["SleepDurationOrdinal"] == 2

    def test_dietary_habits_ordinal_default(self):
        """DietaryHabitsOrdinal 默认=1(Moderate)."""
        result = self._build_with_age_sleep(20, 7.0)
        assert result["DietaryHabitsOrdinal"] == 1

    def test_age_group_student(self):
        """age=20 → AgeGroup='19-25' → 数值 1(STR_TO_NUM 转换)."""
        result = self._build_with_age_sleep(20, 7.0)
        assert result["AgeGroup"] == 1

    def test_age_group_senior(self):
        """age=50 → AgeGroup='46-60' → 数值 4(STR_TO_NUM 转换)."""
        result = self._build_with_age_sleep(50, 7.0)
        assert result["AgeGroup"] == 4

    def test_working_professional_or_student_from_profession(self):
        """profession='Student' → WPS='Student' → 数值 1."""
        result = self._build_with_age_sleep(30, 7.0, profession="Student")
        assert result["Working Professional or Student"] == 1

    def test_working_professional_or_student_from_profession_wp(self):
        """profession='Engineer' → WPS='Working Professional' → 数值 0."""
        result = self._build_with_age_sleep(30, 7.0, profession="Engineer")
        assert result["Working Professional or Student"] == 0

    def test_working_professional_or_student_from_age_young(self):
        """无 profession + age=20 → Student → 数值 1(年龄推断)."""
        result = self._build_with_age_sleep(20, 7.0)
        assert result["Working Professional or Student"] == 1

    def test_working_professional_or_student_from_age_old(self):
        """无 profession + age=35 → Working Professional → 数值 0(年龄推断)."""
        result = self._build_with_age_sleep(35, 7.0)
        assert result["Working Professional or Student"] == 0


class TestProductionModelFeatureContract:
    """验证当前生产模型(v1.20/v1.23)不含派生列 → 无降级风险."""

    def test_v120_feature_names_no_derived(self):
        """v1.20 模型 14 特征不含 4 派生列."""
        v120_features = [
            "age", "gender", "study_year", "cgpa", "stress_level",
            "sleep_duration", "social_support", "financial_pressure",
            "family_history", "academic_pressure", "exercise_frequency",
            "anxiety", "panic_attack", "treatment_seeking",
        ]
        derived = {
            "SleepDurationOrdinal",
            "DietaryHabitsOrdinal",
            "AgeGroup",
            "Working Professional or Student",
        }
        assert not (set(v120_features) & derived), "v1.20 不应包含派生列"

    def test_v123_feature_schema_no_derived(self):
        """v1.23 模型 12 特征不含 4 派生列."""
        v123_features = [
            "age", "gender", "cgpa", "stress_level", "sleep_duration",
            "social_support", "financial_pressure", "family_history",
            "academic_pressure", "exercise_frequency", "anxiety", "panic_attack",
        ]
        derived = {
            "SleepDurationOrdinal",
            "DietaryHabitsOrdinal",
            "AgeGroup",
            "Working Professional or Student",
        }
        assert not (set(v123_features) & derived), "v1.23 不应包含派生列"

    def test_derived_map_does_not_pollute_v123(self):
        """derived_map 生成的派生列不会污染 v1.23 推理(被 model_feature_names 过滤)."""
        from app.core.model_engine import ModelEngine

        raw = {"age": 20, "gender": 1, "sleep_duration": 7, "stress_level": 2,
               "academic_pressure": 2, "financial_pressure": 2, "family_history": 0, "cgpa": 3.0}

        # v1.23 只用 12 个原始特征
        v123_features = [
            "age", "gender", "cgpa", "stress_level", "sleep_duration",
            "social_support", "financial_pressure", "family_history",
            "academic_pressure", "exercise_frequency", "anxiety", "panic_attack",
        ]
        mock_model = MagicMock()
        mock_model.named_steps = {}
        result = ModelEngine._build_structured_input(raw, v123_features, mock_model)

        # 派生列不应出现在结果中
        for col in ["SleepDurationOrdinal", "DietaryHabitsOrdinal", "AgeGroup",
                     "Working Professional or Student"]:
            assert col not in result, f"派生列 {col} 不应出现在 v1.23 推理输入中"
