"""S-02: 验证结构化预测默认模型配置开关.

测试 structured_default_model 配置项:
- "v1.20" (默认): structured_logistic_regression_quick + scaler
- "v1.23": structured_v1.23_external_lr (Pipeline, 自带 preprocessor)

同时验证 _patch_simple_imputer 修复（_fill_dtype 从 _fit_dtype 复制）
和 _run_experimental_v123 修复（传 DataFrame 替代 numpy array）。
"""

from __future__ import annotations

import asyncio
from pathlib import Path
from unittest.mock import patch

import pytest

from app.core.model_engine import ModelEngine

V123_MODEL_PATH = (
    Path(__file__).resolve().parents[1]
    / "models"
    / "v1.23_external_lr"
    / "model.pkl"
)
skip_no_v123 = pytest.mark.skipif(
    not V123_MODEL_PATH.exists(),
    reason="v1.23 model.pkl 不存在 (models/v1.23_external_lr/)",
)


def _run(coro):
    return asyncio.run(coro)


@pytest.fixture
def model_engine():
    return ModelEngine()


@skip_no_v123
class TestS02StructuredV123Default:
    """S-02: 结构化预测默认模型配置开关测试."""

    def test_default_config_uses_v1_20(self, model_engine):
        """默认配置 structured_default_model=v1.20 时使用 v1.20 模型."""
        with patch("app.core.config.settings.structured_default_model", "v1.20"):
            features = {
                "age": 22,
                "gender": 1,
                "cgpa": 3.5,
                "stress_level": 3,
                "sleep_duration": 7,
                "social_support": 4,
                "financial_pressure": 2,
                "family_history": 0,
                "academic_pressure": 3,
                "exercise_frequency": 2,
                "anxiety": 2,
                "panic_attack": 0,
                "treatment_seeking": 1,
            }
            result = _run(model_engine.predict_structured(features))
            assert result["model_used"] == "structured_logistic_regression_quick"
            assert result["model_version"] == "v1.20"
            assert 0 <= result["risk_score"] <= 100

    def test_v1_23_config_uses_v1_23_model(self, model_engine):
        """配置 structured_default_model=v1.23 时使用 v1.23 模型."""
        with patch("app.core.config.settings.structured_default_model", "v1.23"):
            features = {
                "age": 22,
                "gender": 1,
                "cgpa": 3.5,
                "stress_level": 3,
                "sleep_duration": 7,
                "social_support": 4,
                "financial_pressure": 2,
                "family_history": 0,
                "academic_pressure": 3,
                "exercise_frequency": 2,
                "anxiety": 2,
                "panic_attack": 0,
            }
            result = _run(model_engine.predict_structured(features))
            assert result["model_used"] == "structured_v1.23_external_lr"
            assert result["model_version"] == "v1.23"
            assert 0 <= result["risk_score"] <= 100
            # v1.23 是 Pipeline, 不需要单独 scaler
            # 验证预测成功即说明 _patch_simple_imputer 修复生效

    def test_v1_23_config_missing_values_uses_defaults(self, model_engine):
        """v1.23 配置下部分缺失值仍能预测 (满足 _route_structured 80% 覆盖率)."""
        with patch("app.core.config.settings.structured_default_model", "v1.23"):
            # _route_structured 要求 14 个结构化特征覆盖率 >= 80% (至少 12 个)
            # 提供 v1.23 所需的 12 个特征, 缺 study_year 和 treatment_seeking
            # (v1.23 不使用这两个特征, 由 _build_structured_input 用 _DEFAULTS 填充)
            features = {
                "age": 22,
                "gender": 1,
                "cgpa": 3.5,
                "stress_level": 3,
                "sleep_duration": 7,
                "social_support": 4,
                "financial_pressure": 2,
                "family_history": 0,
                "academic_pressure": 3,
                "exercise_frequency": 2,
                "anxiety": 2,
                "panic_attack": 0,
            }
            result = _run(model_engine.predict_structured(features))
            assert result["model_used"] == "structured_v1.23_external_lr"
            assert 0 <= result["risk_score"] <= 100

    def test_v1_23_config_experimental_path_still_works(self, model_engine):
        """v1.23 配置下实验路径仍能运行 (v1.21 + v1.23 + adapter)."""
        with patch("app.core.config.settings.structured_default_model", "v1.23"), patch(
            "app.core.config.settings.structured_experimental_enabled", True
        ):
            features = {
                "age": 22,
                "gender": 1,
                "cgpa": 3.5,
                "stress_level": 3,
                "sleep_duration": 7,
                "social_support": 4,
                "financial_pressure": 2,
                "family_history": 0,
                "academic_pressure": 3,
                "exercise_frequency": 2,
                "anxiety": 2,
                "panic_attack": 0,
            }
            result = _run(model_engine.predict_structured(features))
            # 主路径用 v1.23
            assert result["model_used"] == "structured_v1.23_external_lr"
            # 实验路径仍暴露 experimental_external_* 字段
            # (v1.23 实验路径会再次加载 v1.23 模型作为对比)
            assert "experimental_external_score" in result
            assert "experimental_external_available" in result

    def test_v1_23_config_high_risk_input_produces_high_score(self, model_engine):
        """v1.23 配置下高风险输入产生高分 (验证模型真实预测, 非随机)."""
        with patch("app.core.config.settings.structured_default_model", "v1.23"):
            # 高风险特征组合: 高压力 + 低睡眠 + 低社交支持 + 家族史
            features = {
                "age": 21,
                "gender": 1,
                "cgpa": 3.0,
                "stress_level": 5,
                "sleep_duration": 4,
                "social_support": 1,
                "financial_pressure": 5,
                "family_history": 1,
                "academic_pressure": 5,
                "exercise_frequency": 0,
                "anxiety": 1,
                "panic_attack": 1,
            }
            result = _run(model_engine.predict_structured(features))
            assert result["model_used"] == "structured_v1.23_external_lr"
            # v1.23 模型对高风险输入应产生较高分 (基于之前测试 score=90.91)
            assert result["risk_score"] > 50

    def test_patch_simple_imputer_fixes_fill_dtype(self):
        """验证 _patch_simple_imputer 修复: 缺失 _fill_dtype 时从 _fit_dtype 复制."""
        import joblib

        m = joblib.load(str(V123_MODEL_PATH))
        preprocessor = m.named_steps["preprocessor"]
        num_pipe = preprocessor.transformers_[0][1]
        imputer = num_pipe.named_steps["imputer"]

        # 模拟旧模型加载后 _fill_dtype 缺失的场景
        if hasattr(imputer, "_fill_dtype"):
            del imputer._fill_dtype
        assert not hasattr(imputer, "_fill_dtype")

        # 应用 patch
        ModelEngine._patch_simple_imputer(m)

        # 验证 _fill_dtype 已从 _fit_dtype 复制
        assert hasattr(imputer, "_fill_dtype")
        assert imputer._fill_dtype == imputer._fit_dtype


@skip_no_v123
class TestV123MissingFeatureDefaults:
    """v1.23 特征缺失时的默认值契约.

    背景: v1.23 模型 feature_names_in_ 为小写原始列, _build_structured_input
    对缺失特征用 _DEFAULTS.get(col, 0) 兜底。修复前 DEFAULTS 无小写键, 缺失
    特征被填 0 —— 不在训练分布内 (cgpa 2.01-4.0 / sleep 4-9h / stress 0-4),
    实测风险概率偏移 -51pt~+13pt (stress/sleep 系数 |0.90|/|0.24|)。

    修复: DEFAULTS 补 v1.23 训练集中位数 (与 Pipeline 内置
    SimpleImputer(strategy="median") 语义一致)。
    """

    V123_FEATURES = [
        "age", "gender", "cgpa", "stress_level", "sleep_duration",
        "social_support", "financial_pressure", "family_history",
        "academic_pressure", "exercise_frequency", "anxiety", "panic_attack",
    ]

    def _load_model(self):
        import joblib

        m = joblib.load(str(V123_MODEL_PATH))
        ModelEngine._patch_simple_imputer(m)
        return m

    def test_defaults_dict_contains_v123_lowercase_keys(self):
        """DEFAULTS 必须覆盖 v1.23 全部 12 个小写特征 (契约锚点)."""
        from app.core.feature_maps import DEFAULTS

        for col in self.V123_FEATURES:
            assert col in DEFAULTS, f"DEFAULTS 缺失 v1.23 特征: {col}"

    def test_missing_features_filled_with_training_median_not_zero(self):
        """raw 缺失的 v1.23 特征应填训练集中位数, 而非分布外 0."""
        raw = {
            "age": 22, "gender": 1,
            # 故意缺失: cgpa / sleep_duration / stress_level
            "social_support": 4, "financial_pressure": 2, "family_history": 0,
            "academic_pressure": 3, "exercise_frequency": 2, "anxiety": 2,
            "panic_attack": 0,
        }
        input_dict = ModelEngine._build_structured_input(
            raw, self.V123_FEATURES, self._load_model()
        )
        from app.core.feature_maps import DEFAULTS

        for col in ("cgpa", "sleep_duration", "stress_level"):
            assert input_dict[col] == DEFAULTS[col], (
                f"{col} 缺失时应填 DEFAULTS[{col}]={DEFAULTS[col]}, 实际 {input_dict[col]}"
            )
            assert input_dict[col] != 0

    def test_present_raw_values_override_defaults(self):
        """raw 已提供的特征值必须原样透传, 不被默认值覆盖."""
        raw = dict(
            age=22, gender=1, cgpa=3.5, stress_level=3, sleep_duration=7,
            social_support=4, financial_pressure=2, family_history=0,
            academic_pressure=3, exercise_frequency=2, anxiety=2, panic_attack=0,
        )
        input_dict = ModelEngine._build_structured_input(
            raw, self.V123_FEATURES, self._load_model()
        )
        for col, expected in raw.items():
            assert input_dict[col] == expected, f"{col} 应透传 raw 值 {expected}"

    def test_predict_with_missing_cgpa_differs_from_explicit_zero(self, model_engine):
        """行为回归: 缺失 cgpa 的预测 != 显式 cgpa=0 的预测 (防默认值退化为 0)."""
        with patch("app.core.config.settings.structured_default_model", "v1.23"):
            base = {
                "age": 22, "gender": 1, "stress_level": 3, "sleep_duration": 7,
                "social_support": 4, "financial_pressure": 2, "family_history": 0,
                "academic_pressure": 3, "exercise_frequency": 2, "anxiety": 2,
                "panic_attack": 0, "treatment_seeking": 1, "study_year": 3,
            }
            # 13/14 特征覆盖 (缺 cgpa), 满足 _route_structured >= 0.8 路由门槛
            r_missing = _run(model_engine.predict_structured(dict(base)))
            r_zero = _run(model_engine.predict_structured(dict(base, cgpa=0.0)))
            assert r_missing["model_used"] == "structured_v1.23_external_lr"
            assert r_zero["model_used"] == "structured_v1.23_external_lr"
            # 若默认值退化为 0, 两次预测完全一致 → 断言失败
            assert r_missing["risk_score"] != r_zero["risk_score"]
