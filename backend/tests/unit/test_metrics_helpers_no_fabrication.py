"""P0-FIX-2026-10-11: 模型质量指标必须来自真实实验产物，不得硬编码占位值。

背景（来自 2026-10-11 全量源码审查）：

``metrics_helpers._ML_QUALITY`` 硬编码了四个模态的 auc/f1/ece/p95/recall/
precision，并直接 set 到 Prometheus。看板"有数据"，但：

* 这些数字不对应任何一次真实实验，无法区分"模型退化"与"根本没测"；
* 与真实产物严重不符（本机实测对比见下方``test_real_values_differ_from_old_fabricated_table``）。

修复：``collect_ml_quality_metrics`` 改为只读真实实验产物，
读不到的指标**不上报**（Prometheus 中该序列不存在 = 未知；
上报 0 会被误读为"指标为 0"，同样有害）。
"""

from __future__ import annotations

import json

import pytest

from app.api.v1 import metrics_helpers as mh


class TestNoFabricatedTable:
    def test_hardcoded_table_is_gone(self):
        """硬编码表必须彻底删除，不能只是"默认不用"。"""
        assert not hasattr(mh, "_ML_QUALITY"), (
            "_ML_QUALITY 硬编码指标表仍在 —— 会随时被误用回写路径"
        )

    def test_source_files_are_declared(self):
        assert set(mh._MODALITY_METRIC_SOURCES) == {
            "structured",
            "text",
            "physiological",
            "fusion",
        }


class TestRealArtifactExtraction:
    def test_structured_matches_real_file(self, monkeypatch, tmp_path):
        payload = {
            "test_metrics": {
                "roc_auc": 0.9203305831766602,
                "f1": 0.8728130528798899,
                "precision": 0.842185128983308,
                "recall": 0.9057527539779682,
            }
        }
        _patch_loader(monkeypatch, payload)
        got = mh._extract_modality_metrics("structured")
        assert got["auc"] == pytest.approx(0.92033, abs=1e-5)
        assert got["f1"] == pytest.approx(0.87281, abs=1e-5)

    def test_text_cv_mean_is_used(self, monkeypatch):
        """text 模态的产物只有 cv_results.auc_mean/f1_mean。"""
        _patch_loader(
            monkeypatch,
            {"cv_results": {"auc_mean": 0.9523146403151013, "f1_mean": 0.8231183976530442}},
        )
        got = mh._extract_modality_metrics("text")
        assert got["auc"] == pytest.approx(0.95231, abs=1e-5)
        assert got["f1"] == pytest.approx(0.82312, abs=1e-5)

    def test_fusion_cv_list_is_handled(self, monkeypatch):
        """fusion 的 cv_results 是数组而非 dict。"""
        _patch_loader(
            monkeypatch,
            {
                "cv_results": [
                    {"strategy": "baseline", "auc_mean": 0.80, "f1_mean": 0.70},
                    {"strategy": "stacking_gbdt", "auc_mean": 0.9189, "f1_mean": 0.7229},
                ]
            },
        )
        got = mh._extract_modality_metrics("fusion")
        assert got["auc"] is not None

    def test_missing_artifact_yields_no_metrics(self, monkeypatch):
        monkeypatch.setattr(mh, "_load_json", lambda rel: None)
        assert mh._extract_modality_metrics("structured") == {}

    def test_empty_or_broken_sections_yield_nothing(self, monkeypatch):
        _patch_loader(monkeypatch, {"test_metrics": {"accuracy": 0.8}})
        got = mh._extract_modality_metrics("structured")
        assert "auc" not in got and "f1" not in got

    def test_boolean_is_not_treated_as_number(self, monkeypatch):
        """bool 是 int 的子类；``True`` 不应被当成 1.0 报成 AUC。"""
        _patch_loader(monkeypatch, {"test_metrics": {"roc_auc": True, "f1": False}})
        assert mh._extract_modality_metrics("structured") == {}


class TestEceExtraction:
    def test_ece_from_calibration_artifact(self, monkeypatch):
        _patch_loader(
            monkeypatch,
            {
                "modalities": [
                    {
                        "modality": "structured_gbdt",
                        "calibration": {"raw_metrics": {"ece": 0.016423749476464154}},
                    }
                ]
            },
        )
        assert mh._extract_ece()["structured"] == pytest.approx(0.01642, abs=1e-5)

    def test_unknown_modality_is_skipped(self, monkeypatch):
        _patch_loader(
            monkeypatch,
            {"modalities": [{"modality": "mystery", "calibration": {"raw_metrics": {"ece": 0.1}}}]},
        )
        assert mh._extract_ece() == {}


class TestCollectDoesNotFabricate:
    @pytest.mark.asyncio
    async def test_nothing_reported_when_artifacts_missing(self, monkeypatch):
        """真实产物全部不可读时，必须「一条都不报」，而不是回退到占位值。"""
        monkeypatch.setattr(mh, "_load_json", lambda rel: None)
        monkeypatch.setattr(mh, "_extract_ece", lambda: {})

        set_calls: list[tuple] = []
        for gauge in mh._METRIC_GAUGE_BY_KEY.values():
            monkeypatch.setattr(
                gauge, "set", lambda *a, **kw: set_calls.append((a, kw)), raising=False
            )

        await mh.collect_ml_quality_metrics()
        assert set_calls == [], "无真实来源时仍上报了模型质量指标（编造数据）"

    @pytest.mark.asyncio
    async def test_reports_only_keys_present_in_artifact(self, monkeypatch):
        """产物只有 auc/f1 时，不得凭空补出 recall/precision/ece。"""
        _patch_loader(monkeypatch, {"test_metrics": {"roc_auc": 0.93, "f1": 0.87}})

        set_calls: list[tuple] = []
        for key, gauge in mh._METRIC_GAUGE_BY_KEY.items():
            monkeypatch.setattr(
                gauge,
                "set",
                lambda *a, _k=key, **kw: set_calls.append((_k, a)),
                raising=False,
            )

        await mh.collect_ml_quality_metrics()
        keys = {k for k, _ in set_calls}
        assert keys == {"auc", "f1"}, f"上报了产物里不存在的指标: {keys}"


class TestRealValuesDifferFromOldFabricatedTable:
    """固化"硬编码值与真实产物不符"这一事实 —— 若将来又出现编造，本测试会红。"""

    # 2026-10-11 删除的硬编码值（保留作为对照，防止有人把它们再抄回去）
    OLD_FABRICATED = {
        "structured": {"auc": 0.9121, "f1": 0.8541},
        "text": {"auc": 0.9876, "f1": 0.9409},
        "physiological": {"auc": 0.9716, "f1": 0.9385},
        "fusion": {"auc": 0.9241, "f1": 0.8712},
    }

    def test_old_fabricated_values_absent_from_code(self):
        """编造值不得以**字面量**形式出现在代码里。

        用 AST 取所有数值常量比对 —— 注释里为了说明"改了什么"而引用这些数字
        是合理的（也是必要的记录），不应因此让本测试失败。
        """
        import ast

        import app.api.v1.metrics_helpers as mod

        tree = ast.parse(open(mod.__file__, encoding="utf-8").read())
        literals: set[float] = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.Constant) and isinstance(node.value, (int, float)):
                if not isinstance(node.value, bool):
                    literals.add(float(node.value))

        fabricated = {
            value
            for metrics in self.OLD_FABRICATED.values()
            for value in metrics.values()
        }
        leaked = literals & fabricated
        assert not leaked, f"编造指标值以字面量形式回到源码: {sorted(leaked)}"


def _patch_loader(monkeypatch, payload: dict) -> None:
    """让 ``_load_json`` 对所有相对路径返回同一份 payload。"""
    monkeypatch.setattr(mh, "_load_json", lambda rel: json.loads(json.dumps(payload)))