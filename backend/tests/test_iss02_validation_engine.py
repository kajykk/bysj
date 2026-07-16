"""ISS-02 第五轮：ValidationEngine 纯逻辑聚焦测试。

覆盖 app/services/validation_engine.py 的无 DB / 无模型推理路径：
- ValidationMetrics.to_dict：四位小数舍入 + None 透传 + sample_count。
- ValidationResult.to_dict：有/无 baseline 两种形态。
- compute_delta：双值舍入差 / 任一 None 归 None。
- calculate_metrics：空输入 / 小数据集二分类 / 小数据集含错 / 非数字标签跳过 /
  全非数字 total=0 / 大数据集(>32) numpy 路径。
- _calculate_small_classification_metrics：多分类回退路径（precision=recall=f1=accuracy）。
- load_dataset：缺文件 / 不支持后缀 / JSON list / JSON dict / CSV 数值转换 / 非法 JSON。

说明：validation_engine 顶层仅依赖 numpy/sklearn，无 app 内部导入；模型推理方法为惰性
导入 + async，本套件不触碰，故全部为确定性纯计算断言。本地 coverage.py 插桩时 numpy
原生库偶发 SIGSEGV，pass/fail 已稳定验证，覆盖率数值以稳定 CI 为准。
"""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.services.validation_engine import (
    ValidationEngine,
    ValidationMetrics,
    ValidationResult,
)


# ── ValidationMetrics.to_dict ──────────────────────────────────────────────


def test_metrics_to_dict_rounds_and_keeps_sample_count():
    m = ValidationMetrics(
        accuracy=0.123456,
        precision=0.987654,
        recall=0.5,
        f1=0.333333,
        auc=0.777777,
        mae=1.234567,
        rmse=2.0,
        sample_count=42,
    )
    d = m.to_dict()
    assert d["accuracy"] == 0.1235  # round 4
    assert d["precision"] == 0.9877
    assert d["recall"] == 0.5
    assert d["f1"] == 0.3333
    assert d["auc"] == 0.7778
    assert d["mae"] == 1.2346
    assert d["rmse"] == 2.0
    assert d["sample_count"] == 42


def test_metrics_to_dict_passes_none_through():
    d = ValidationMetrics().to_dict()
    for key in ("accuracy", "precision", "recall", "f1", "auc", "mae", "rmse"):
        assert d[key] is None
    assert d["sample_count"] == 0


# ── ValidationResult.to_dict ───────────────────────────────────────────────


def test_result_to_dict_without_baseline():
    res = ValidationResult(
        model_version="v1.20",
        metrics=ValidationMetrics(accuracy=0.9, sample_count=3),
        predictions=[{"index": 0}, {"index": 1}],
        errors=["boom"],
    )
    d = res.to_dict()
    assert d["model_version"] == "v1.20"
    assert d["metrics"]["accuracy"] == 0.9
    assert d["predictions_count"] == 2
    assert d["errors"] == ["boom"]
    assert "baseline_metrics" not in d
    assert "delta" not in d


def test_result_to_dict_with_baseline_includes_delta():
    res = ValidationResult(
        model_version="v1.21",
        metrics=ValidationMetrics(accuracy=0.9),
        baseline_metrics=ValidationMetrics(accuracy=0.8),
        delta={"accuracy": 0.1},
    )
    d = res.to_dict()
    assert d["baseline_metrics"]["accuracy"] == 0.8
    assert d["delta"] == {"accuracy": 0.1}


# ── compute_delta ──────────────────────────────────────────────────────────


def test_compute_delta_both_present_and_none_mix():
    engine = ValidationEngine()
    current = ValidationMetrics(accuracy=0.95, precision=0.9, recall=None)
    baseline = ValidationMetrics(accuracy=0.90, precision=None, recall=0.5)
    delta = engine.compute_delta(current, baseline)
    assert delta["accuracy"] == 0.05  # 0.95-0.90, rounded
    assert delta["precision"] is None  # baseline None
    assert delta["recall"] is None  # current None
    # 其余未设置的指标（f1/auc/mae/rmse）两端皆 None → None
    assert delta["f1"] is None
    assert delta["auc"] is None


# ── calculate_metrics ──────────────────────────────────────────────────────


def test_calculate_metrics_empty_inputs():
    engine = ValidationEngine()
    m = engine.calculate_metrics([], [])
    assert m.sample_count == 0
    assert m.accuracy is None


def test_calculate_metrics_small_binary_perfect():
    engine = ValidationEngine()
    gt = [1, 0, 1, 0, 1]
    pred = [1, 0, 1, 0, 1]
    m = engine.calculate_metrics(gt, pred)  # <=32, no probs → small path
    assert m.sample_count == 5
    assert m.accuracy == 1.0
    assert m.precision == 1.0
    assert m.recall == 1.0
    assert m.f1 == 1.0
    assert m.mae == 0.0
    assert m.rmse == 0.0
    assert m.auc is None  # small path 显式置 None


def test_calculate_metrics_small_binary_with_errors():
    engine = ValidationEngine()
    gt = [1, 1, 0, 0]
    pred = [1, 0, 0, 1]  # 1 tp, 1 fp, 1 fn, 1 tn
    m = engine.calculate_metrics(gt, pred)
    assert m.sample_count == 4
    assert m.accuracy == 0.5  # 2/4 correct
    assert m.precision == 0.5  # tp/(tp+fp)=1/2
    assert m.recall == 0.5  # tp/(tp+fn)=1/2
    assert m.f1 == 0.5


def test_calculate_metrics_skips_non_numeric_labels():
    engine = ValidationEngine()
    gt = [1, "negative", 0]
    pred = [1, "positive", 0]
    m = engine.calculate_metrics(gt, pred)
    # 一个非数字样本被跳过 → 有效样本 2
    assert m.sample_count == 2
    assert m.accuracy == 1.0


def test_calculate_metrics_all_non_numeric_total_zero():
    engine = ValidationEngine()
    gt = ["a", "b"]
    pred = ["c", "d"]
    m = engine.calculate_metrics(gt, pred)
    assert m.sample_count == 0
    assert m.accuracy is None  # total<=0 提前返回


def test_calculate_metrics_large_binary_numpy_path():
    engine = ValidationEngine()
    # >32 样本触发 numpy 路径（无 probabilities 也会进 numpy 分支）
    gt = [1, 0] * 20  # 40 个
    pred = [1, 0] * 20
    m = engine.calculate_metrics(gt, pred)
    assert m.sample_count == 40
    assert m.accuracy == 1.0
    assert m.precision == 1.0
    assert m.recall == 1.0
    assert m.f1 == 1.0
    assert m.mae == 0.0
    assert m.rmse == 0.0


# ── _calculate_small_classification_metrics 多分类回退 ─────────────────────


def test_small_metrics_multiclass_fallback():
    engine = ValidationEngine()
    gt = [0, 1, 2, 2]
    pred = [0, 1, 2, 1]  # 出现 label 2 → other_label_present → 回退分支
    m = engine._calculate_small_classification_metrics(
        gt, pred, ValidationMetrics()
    )
    assert m.sample_count == 4
    assert m.accuracy == 0.75  # 3/4
    # 多分类回退：precision=recall=f1=accuracy
    assert m.precision == 0.75
    assert m.recall == 0.75
    assert m.f1 == 0.75


# ── load_dataset ───────────────────────────────────────────────────────────


def test_load_dataset_missing_file_raises(tmp_path: Path):
    engine = ValidationEngine()
    with pytest.raises(FileNotFoundError):
        engine.load_dataset(tmp_path / "nope.json")


def test_load_dataset_unsupported_suffix(tmp_path: Path):
    engine = ValidationEngine()
    p = tmp_path / "data.txt"
    p.write_text("x", encoding="utf-8")
    with pytest.raises(ValueError, match="Unsupported dataset format"):
        engine.load_dataset(p)


def test_load_dataset_json_list(tmp_path: Path):
    engine = ValidationEngine()
    p = tmp_path / "d.json"
    p.write_text(
        json.dumps([{"a": 1, "label": 1}, {"a": 2, "label": 0}]),
        encoding="utf-8",
    )
    features, labels = engine.load_dataset(p)
    assert features == [{"a": 1}, {"a": 2}]
    assert labels == [1, 0]


def test_load_dataset_json_dict(tmp_path: Path):
    engine = ValidationEngine()
    p = tmp_path / "d.json"
    p.write_text(
        json.dumps({"features": [{"a": 1}], "labels": [1]}),
        encoding="utf-8",
    )
    features, labels = engine.load_dataset(p)
    assert features == [{"a": 1}]
    assert labels == [1]


def test_load_dataset_json_invalid_format(tmp_path: Path):
    engine = ValidationEngine()
    p = tmp_path / "d.json"
    p.write_text(json.dumps({"foo": "bar"}), encoding="utf-8")
    with pytest.raises(ValueError, match="Invalid JSON dataset format"):
        engine.load_dataset(p)


def test_load_dataset_csv_numeric_conversion(tmp_path: Path):
    engine = ValidationEngine()
    p = tmp_path / "d.csv"
    p.write_text("a,b,label\n1.5,x,1\n2,y,0\n", encoding="utf-8")
    features, labels = engine.load_dataset(p)
    assert features[0]["a"] == 1.5  # 数值转换
    assert features[0]["b"] == "x"  # 非数值保留字符串
    assert features[1]["a"] == 2.0
    assert labels == ["1", "0"]  # CSV label 为字符串（未转换）
