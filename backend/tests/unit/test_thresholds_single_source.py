"""阈值单一来源契约：阈值只能来自后端配置，并随预测响应下发。

回归背景：前端曾保留一份风险阈值副本，后端调阈值后前端不跟随，导致同一份
风险分在页面上被划进不同等级。本文件锁定四件事：

1. 结构化响应必须带 ``thresholds``（mild/moderate/high/critical）与
   ``threshold_source``，数值等于 ``risk_thresholds.get_structured_thresholds()``；
2. 只改 ``risk_thresholds.py`` 一处，响应里的四值与风险等级随之变化
   （证明是单一来源，不是复制到 schema/路由的副本）；
3. 启发式/降级路径必须把 ``threshold_source`` 标成 ``fallback``；
4. 文本侧 ``text_decision_thresholds`` 同时下发 0.30 / 0.55 与来源标记。
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.core import risk_thresholds
from app.core.config import settings
from app.core.ml_decision_thresholds import TEXT_DECISION_THRESHOLD_SOURCE
from app.core.model_engine import ModelEngine
from app.core.risk_thresholds import (
    FALLBACK_THRESHOLD_SOURCE,
    STRUCTURED_THRESHOLD_SOURCE,
    get_structured_thresholds,
)
from app.schemas.model_predict import ModelPredictResponse, TabularPredictResult

#: 14 个结构化特征全部给齐，覆盖率 1.0，确保路由走主模型而不是 lite/降级。
_FEATURES: dict[str, float | int] = {
    "age": 20,
    "gender": 1,
    "study_year": 2,
    "cgpa": 3.5,
    "stress_level": 3,
    "sleep_duration": 6,
    "social_support": 3,
    "financial_pressure": 3,
    "family_history": 0,
    "academic_pressure": 3,
    "exercise_frequency": 1,
    "anxiety": 3,
    "panic_attack": 0,
    "treatment_seeking": 0,
}


class _DummyStructuredModel:
    """固定概率的结构化模型替身（风险分 = probability * 100）。"""

    def __init__(self, probability: float) -> None:
        self._probability = probability

    def predict(self, features) -> list[int]:
        return [1 if self._probability >= 0.5 else 0]

    def predict_proba(self, features) -> list[list[float]]:
        return [[1 - self._probability, self._probability]]


def _model_loader(model: _DummyStructuredModel):
    """只让主结构化模型加载成功，其余（scaler/实验路径）如实缺失。"""

    async def _load(model_id: str):
        if model_id in {
            "structured_v1.23_external_lr",
            "structured_logistic_regression_quick",
        }:
            return model
        raise FileNotFoundError(model_id)

    return _load


@pytest.fixture
def engine() -> ModelEngine:
    return ModelEngine()


@pytest.mark.asyncio
async def test_structured_response_carries_thresholds_and_source(
    engine: ModelEngine, monkeypatch
) -> None:
    """结构化响应必须随包下发四档阈值与口径来源。"""
    monkeypatch.setattr(settings, "structured_experimental_enabled", False)
    monkeypatch.setattr(settings, "structured_model_mode", "primary", raising=False)
    model = _DummyStructuredModel(0.9052)

    with patch.object(engine, "_load_model_async", side_effect=_model_loader(model)):
        result = await engine.predict_structured(dict(_FEATURES))

    # 数值不写死，直接与 SSOT 读取函数比对（schema/路由都不得存副本）。
    assert result["thresholds"] == get_structured_thresholds()
    assert set(result["thresholds"]) == {"mild", "moderate", "high", "critical"}
    assert all(isinstance(value, int) for value in result["thresholds"].values())
    assert result["threshold_source"] == STRUCTURED_THRESHOLD_SOURCE


@pytest.mark.asyncio
async def test_changing_ssot_threshold_propagates_to_response(
    engine: ModelEngine, monkeypatch
) -> None:
    """只改 risk_thresholds.py 一处，响应四值与等级随之变化。"""
    monkeypatch.setattr(settings, "structured_experimental_enabled", False)
    monkeypatch.setattr(settings, "structured_model_mode", "primary", raising=False)
    model = _DummyStructuredModel(0.9052)

    with patch.object(engine, "_load_model_async", side_effect=_model_loader(model)):
        before = await engine.predict_structured(dict(_FEATURES))

    # 改前：90.52 落在 moderate(70) 与 high(93) 之间 → 2 级。
    assert before["risk_level"] == 2

    # 唯一一处改动：SSOT 里 structured 的 critical 阈值改成当前分数。
    new_critical = int(before["risk_score"])
    monkeypatch.setitem(
        risk_thresholds.MODALITY_RISK_THRESHOLDS["structured"],
        "critical",
        new_critical,
    )

    with patch.object(engine, "_load_model_async", side_effect=_model_loader(model)):
        after = await engine.predict_structured(dict(_FEATURES))

    assert after["risk_score"] == before["risk_score"], "分数不受阈值改动影响"
    assert after["thresholds"] == get_structured_thresholds()
    assert after["thresholds"]["critical"] == new_critical
    assert after["thresholds"] != before["thresholds"], "四档阈值应随 SSOT 一起变"
    assert after["risk_level"] == 4, "同一分数在新 critical 阈值下应升到 critical"


@pytest.mark.asyncio
async def test_fallback_path_marks_threshold_source_fallback(
    engine: ModelEngine, monkeypatch
) -> None:
    """启发式/降级路径必须让调用方看得出这是兜底口径。"""
    monkeypatch.setattr(settings, "structured_experimental_enabled", False)

    async def _load(model_id: str):
        raise FileNotFoundError(model_id)

    with patch.object(engine, "_load_model_async", side_effect=_load):
        result = await engine.predict_structured(dict(_FEATURES))

    assert result["fallback_used"] is True
    assert result["threshold_source"] == FALLBACK_THRESHOLD_SOURCE
    # 兜底口径下阈值数值仍来自同一份 SSOT，不是另一套硬编码。
    assert result["thresholds"] == get_structured_thresholds()


def test_schema_defaults_read_from_ssot() -> None:
    """schema 默认值也必须来自 SSOT，而不是在 schema 里写数字。"""
    tabular = TabularPredictResult(
        prediction=0,
        probability=0.1,
        risk_score=10.0,
        risk_level=0,
        model_used="dummy",
    )
    assert tabular.thresholds == get_structured_thresholds()
    assert tabular.threshold_source == STRUCTURED_THRESHOLD_SOURCE

    response = ModelPredictResponse()
    assert response.thresholds == get_structured_thresholds()
    assert response.threshold_source == STRUCTURED_THRESHOLD_SOURCE


def test_text_decision_thresholds_include_both_boundaries_and_source(
    engine: ModelEngine, monkeypatch
) -> None:
    """文本侧必须同时下发 0.30 / 0.55 两个阈值及口径来源。"""
    monkeypatch.setattr(settings, "text_bilingual_decision_threshold", 0.30)
    monkeypatch.setattr(settings, "text_bilingual_review_threshold", 0.55)

    result = engine._apply_text_decision_state({}, 0.40)

    assert result["text_decision_state"] == "suspect"
    assert result["text_decision_thresholds"] == {
        "suspect_lower": 0.30,
        "high_upper": 0.55,
        "source": TEXT_DECISION_THRESHOLD_SOURCE,
    }
