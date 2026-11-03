"""结构化输入域钳制 / 缺失中性化 / cgpa 归一回归（ROUND_2）。"""

from __future__ import annotations

from app.core.feature_maps import DEFAULTS
from app.core.model_engine import ModelEngine


V123_FEATURES = [
    "age",
    "gender",
    "cgpa",
    "stress_level",
    "sleep_duration",
    "social_support",
    "financial_pressure",
    "family_history",
    "academic_pressure",
    "exercise_frequency",
    "anxiety",
    "panic_attack",
]


class _FakeModel:
    pass


def _build(raw: dict, degradation: dict | None = None) -> dict:
    return ModelEngine._build_structured_input(
        raw, V123_FEATURES, _FakeModel(), degradation=degradation
    )


def test_out_of_domain_sliders_are_clamped_to_training_range() -> None:
    adjustments: dict = {}
    input_dict = _build(
        {"stress_level": 6, "academic_pressure": 5, "anxiety": 7},
        degradation=adjustments,
    )
    assert input_dict["stress_level"] == 4
    assert input_dict["academic_pressure"] == 4
    assert input_dict["anxiety"] == 4

    clamped = {item["field"]: item for item in adjustments["clamped_fields"]}
    assert clamped["stress_level"] == {
        "field": "stress_level",
        "original": 6.0,
        "value": 4.0,
        "policy": "clamp_to_training_domain_0_4",
    }
    assert clamped["academic_pressure"]["original"] == 5.0
    assert clamped["anxiety"]["original"] == 7.0


def test_missing_binary_fields_default_to_neutral_zero_and_are_marked() -> None:
    adjustments: dict = {}
    input_dict = _build(
        {"stress_level": 3, "academic_pressure": 2, "anxiety": 2},
        degradation=adjustments,
    )

    for field in ("panic_attack", "treatment_seeking", "family_history", "suicidal_thoughts"):
        assert field not in input_dict or input_dict[field] == 0

    defaulted = {
        item["field"]: item for item in adjustments["defaulted_missing_fields"]
    }
    assert defaulted["panic_attack"] == {
        "field": "panic_attack",
        "value": 0,
        "policy": "missing_neutral_zero",
    }
    # 不再使用训练中位数 1，且缺失与显式 0 可通过标记区分。
    assert "panic_attack" in defaulted


def test_explicit_zero_is_not_marked_as_missing() -> None:
    adjustments: dict = {}
    _build(
        {"stress_level": 3, "academic_pressure": 2, "anxiety": 2, "panic_attack": 0},
        degradation=adjustments,
    )
    defaulted_fields = {
        item["field"] for item in adjustments["defaulted_missing_fields"]
    }
    assert "panic_attack" not in defaulted_fields


def test_missing_and_explicit_zero_share_same_model_input() -> None:
    """缺失 panic_attack 与用户显式填 0 的模型输入必须一致（只差留痕）。"""
    base = {"stress_level": 3, "academic_pressure": 2, "anxiety": 2}
    missing = _build(dict(base))
    explicit_zero = _build(dict(base, panic_attack=0))
    assert missing["panic_attack"] == explicit_zero["panic_attack"] == 0


def test_cgpa_0_10_is_normalized_to_0_4_and_marked() -> None:
    adjustments: dict = {}
    input_dict = _build({"cgpa": 8.5}, degradation=adjustments)
    assert input_dict["cgpa"] == 3.4
    normalized = {
        item["field"]: item for item in adjustments["normalized_fields"]
    }
    assert normalized["cgpa"]["original"] == 8.5
    assert normalized["cgpa"]["value"] == 3.4
    assert normalized["cgpa"]["policy"] == "cgpa_0_10_to_0_4"


def test_cgpa_already_0_4_is_passed_through() -> None:
    adjustments: dict = {}
    input_dict = _build({"cgpa": 3.5}, degradation=adjustments)
    assert input_dict["cgpa"] == 3.5
    assert adjustments["normalized_fields"] == []


def test_missing_continuous_fields_keep_training_median() -> None:
    """连续特征仍走训练中位数；只有二值字段改为中性 0。"""
    adjustments: dict = {}
    input_dict = _build({}, degradation=adjustments)
    assert input_dict["stress_level"] == DEFAULTS["stress_level"]
    assert input_dict["sleep_duration"] == DEFAULTS["sleep_duration"]
    assert input_dict["panic_attack"] == 0
