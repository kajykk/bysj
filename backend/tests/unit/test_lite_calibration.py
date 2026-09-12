"""v1.27: lite LR 概率校准层契约与行为测试.

覆盖 (scripts/modeling/v1_27/01_calibrate_lite_lr.py 产物的运行时接入):
1. _apply_lite_calibration 数学契约: Platt/Isotonic 映射单调且输出在 [0,1]
2. 降级契约: 产物缺失/加载失败/执行失败 → raw 概率原样返回, 不降级预测
3. 开关契约: lite_calibration_enabled=False 时即使产物存在也不应用
4. 注册表/配置契约: mmpsy_lite_calibrator 已注册, 阈值配置与 meta 一致
5. 行为契约: predict_lite 结果携带 probability_calibrated 标志, 阈值按空间切换
"""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pytest
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression

from app.core.model_engine import ModelEngine

BACKEND_DIR = Path(__file__).resolve().parents[2]
CALIB_DIR = BACKEND_DIR / "models" / "v1.27_lite_calibration"
CALIB_PKL = CALIB_DIR / "calibrator.pkl"
CALIB_META = CALIB_DIR / "calibrator_meta.json"

# v1.25 mmpsy_lite 端到端行为测试依赖的真实产物 (backend/models/* 被 .gitignore,
# CI 检出不含这些 pkl; 仅本地训练资产存在时才能跑真实加载路径).
LITE_MODEL_PKL = BACKEND_DIR / "models" / "v1.25_mmpsy_lite" / "mmpsy_lite_model.pkl"
LITE_SCALER_PKL = BACKEND_DIR / "models" / "v1.25_mmpsy_lite" / "mmpsy_lite_scaler.pkl"

_requires_lite_artifacts = pytest.mark.skipif(
    not (LITE_MODEL_PKL.exists() and LITE_SCALER_PKL.exists()),
    reason="v1.25 mmpsy_lite 模型/缩放器产物不存在 (backend/models/* 已 gitignore)",
)


def _run(coro):
    return asyncio.run(coro)


def _fit_platt_fixture() -> LogisticRegression:
    """近恒等 Platt fixture: 在合成可分数据上拟合, 输出单调且接近输入排序."""
    rng = np.random.RandomState(42)
    p_raw = np.linspace(0.05, 0.95, 200)
    y = (rng.rand(200) < p_raw).astype(int)
    logit = np.log(p_raw / (1 - p_raw))
    lr = LogisticRegression(C=1e10, max_iter=1000)
    lr.fit(logit.reshape(-1, 1), y)
    return lr


def _fit_isotonic_fixture() -> IsotonicRegression:
    rng = np.random.RandomState(42)
    p_raw = np.linspace(0.05, 0.95, 200)
    y = (rng.rand(200) < p_raw).astype(int)
    iso = IsotonicRegression(out_of_bounds="clip", y_min=0.0, y_max=1.0)
    iso.fit(p_raw, y)
    return iso


@pytest.fixture
def engine() -> ModelEngine:
    return ModelEngine()


class TestLiteCalibrationMath:
    """校准映射数学契约 (monkeypatch _load_model_async, 不依赖真实产物)."""

    def _patch_loader(self, engine: ModelEngine, calibrator):
        async def _load(model_id: str):
            if model_id == "mmpsy_lite_calibrator":
                return calibrator
            raise FileNotFoundError(model_id)

        return patch.object(engine, "_load_model_async", side_effect=_load)

    def test_platt_applied_and_monotone(self, engine):
        with self._patch_loader(engine, _fit_platt_fixture()):
            p_low, flag_low = _run(engine._apply_lite_calibration(0.20))
            p_high, flag_high = _run(engine._apply_lite_calibration(0.80))
        assert flag_low is True and flag_high is True
        assert 0.0 <= p_low <= 1.0 and 0.0 <= p_high <= 1.0
        assert p_high > p_low, "校准映射必须保持单调"

    def test_isotonic_applied_and_monotone(self, engine):
        with self._patch_loader(engine, _fit_isotonic_fixture()):
            p_low, _ = _run(engine._apply_lite_calibration(0.15))
            p_high, flag = _run(engine._apply_lite_calibration(0.85))
        assert flag is True
        assert 0.0 <= p_low <= 1.0 and 0.0 <= p_high <= 1.0
        assert p_high >= p_low

    def test_load_failure_keeps_raw_probability(self, engine):
        async def _boom(model_id: str):
            raise FileNotFoundError(model_id)

        with patch.object(engine, "_load_model_async", side_effect=_boom):
            p, flag = _run(engine._apply_lite_calibration(0.42))
        assert flag is False
        assert p == 0.42, "加载失败必须原样返回 raw 概率"

    def test_apply_failure_keeps_raw_probability(self, engine):
        class _Broken:
            def predict(self, *_a, **_k):
                raise RuntimeError("boom")

            def predict_proba(self, *_a, **_k):
                raise RuntimeError("boom")

        with self._patch_loader(engine, _Broken()):
            p, flag = _run(engine._apply_lite_calibration(0.42))
        assert flag is False
        assert p == 0.42, "校准执行失败必须保底 raw 概率, 不降级整条预测"

    def test_disabled_switch_keeps_raw_probability(self, engine):
        with self._patch_loader(engine, _fit_platt_fixture()), patch(
            "app.core.model_engine.predict.settings.lite_calibration_enabled", False
        ):
            p, flag = _run(engine._apply_lite_calibration(0.42))
        assert flag is False
        assert p == 0.42

    def test_output_clamped_to_unit_interval(self, engine):
        class _Extreme:
            def predict_proba(self, x):
                logit = float(np.asarray(x)[0][0])
                # 极端线性映射, 验证 [0,1] 裁剪
                return [[0.0, 1.0 / (1 + np.exp(-10 * logit))]]

        with self._patch_loader(engine, _Extreme()):
            p, flag = _run(engine._apply_lite_calibration(0.999999))
        assert flag is True
        assert 0.0 <= p <= 1.0


class TestLiteCalibrationContracts:
    """注册表 / 配置 / 产物一致性契约."""

    def test_calibrator_registered_in_model_paths(self):
        from app.core.model_registry import MODEL_PATHS

        assert "mmpsy_lite_calibrator" in MODEL_PATHS
        assert MODEL_PATHS["mmpsy_lite_calibrator"].endswith("calibrator.pkl")

    def test_config_has_calibrated_threshold(self):
        from app.core.config import settings

        assert hasattr(settings, "lite_calibrated_decision_threshold")
        assert hasattr(settings, "lite_calibration_enabled")
        assert 0.0 < settings.lite_calibrated_decision_threshold < 1.0

    @pytest.mark.skipif(
        not CALIB_META.exists(), reason="v1.27 calibrator 产物不存在 (本地训练资产)"
    )
    def test_meta_threshold_matches_config_default(self):
        """meta 中的校准空间阈值必须与配置默认值一致 (防止脚本与代码漂移)."""
        from app.core.config import settings

        meta = json.loads(CALIB_META.read_text(encoding="utf-8"))
        assert meta["method"] in ("platt", "isotonic")
        assert (
            meta["decision_threshold_calibrated"]
            == settings.lite_calibrated_decision_threshold
        )

    @pytest.mark.skipif(
        not CALIB_PKL.exists(), reason="v1.27 calibrator 产物不存在 (本地训练资产)"
    )
    def test_artifact_sha256_sidecar_exists(self):
        """产物必须携带 .sha256 sidecar (safe_pickle 严格校验路径)."""
        sidecar = CALIB_DIR / "calibrator.pkl.sha256"
        assert sidecar.exists()
        expected = sidecar.read_text(encoding="utf-8").strip().splitlines()[0].split()[0]
        assert len(expected) == 64


@_requires_lite_artifacts
class TestPredictLiteCalibrationBehavior:
    """predict_lite 端到端行为 (monkeypatch 模型加载, 校准器为近恒等 Platt)."""

    @pytest.fixture
    def engine_with_models(self) -> ModelEngine:
        import joblib

        eng = ModelEngine()
        model = joblib.load(LITE_MODEL_PKL)
        scaler = joblib.load(LITE_SCALER_PKL)

        async def _load(model_id: str):
            if model_id == "mmpsy_lite_model":
                return model
            if model_id == "mmpsy_lite_scaler":
                return scaler
            if model_id == "mmpsy_lite_calibrator":
                return _fit_platt_fixture()
            raise FileNotFoundError(model_id)

        eng._load_model_async = _load  # type: ignore[method-assign]
        return eng

    def test_result_carries_probability_calibrated_flag(self, engine_with_models):
        with patch(
            "app.core.model_engine.predict.settings.lite_calibration_enabled", True
        ):
            result = _run(
                engine_with_models.predict_lite(
                    gad7_score=15,
                    audio_transcript="我最近总是睡不着，对什么都没兴趣，感觉撑不下去了，压力太大了。"*2,
                    age=22,
                    gender=1,
                    cgpa=3.0,
                )
            )
        assert result["model_used"] == "mmpsy_lite_model"
        assert result["probability_calibrated"] is True
        assert 0.0 <= result["probability"] <= 1.0
        # 预测必须与校准空间阈值一致 (0.40)
        assert result["prediction"] == int(result["probability"] >= 0.40)

    def test_calibration_disabled_keeps_flag_false(self, engine_with_models):
        with patch(
            "app.core.model_engine.predict.settings.lite_calibration_enabled", False
        ):
            result = _run(
                engine_with_models.predict_lite(
                    gad7_score=15,
                    audio_transcript="我最近总是睡不着，对什么都没兴趣，感觉撑不下去了，压力太大了。"*2,
                    age=22,
                    gender=1,
                    cgpa=3.0,
                )
            )
        assert result["probability_calibrated"] is False
        assert result["model_used"] == "mmpsy_lite_model"
