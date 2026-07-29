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
