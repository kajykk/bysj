"""Phase 3 模型验证基础设施测试.

覆盖 model_validation.py 的所有核心函数：
- _wilson_ci: Wilson score 置信区间
- _bootstrap_auc_ci: Bootstrap AUC 置信区间
- compute_brier_score: Brier Score
- compute_binary_metrics: 二分类临床指标
- compute_per_class_metrics: 多类 one-vs-rest 指标
- compute_fairness_metrics: 公平性检查 + 小样本保护
- generate_clinical_validation_report: 完整报告生成
"""

from __future__ import annotations

import numpy as np
import pytest

from app.ml.model_validation import (
    BinaryMetrics,
    _bootstrap_auc_ci,
    _wilson_ci,
    compute_binary_metrics,
    compute_brier_score,
    compute_fairness_metrics,
    compute_per_class_metrics,
    generate_clinical_validation_report,
)


class TestWilsonCI:
    """Test _wilson_ci."""

    def test_perfect_prediction(self):
        """全正确预测：CI 上下界应接近 1.0."""
        ci = _wilson_ci(100, 100, 0.95)
        assert len(ci) == 2
        assert ci[0] <= ci[1]
        assert ci[1] <= 1.0
        # 100/100 成功，下界应较高
        assert ci[0] > 0.9

    def test_zero_success(self):
        """全失败预测：CI 上下界应接近 0.0."""
        ci = _wilson_ci(0, 100, 0.95)
        assert ci[0] >= 0.0
        assert ci[1] < 0.1

    def test_half_success(self):
        """50% 成功：CI 应包含 0.5."""
        ci = _wilson_ci(50, 100, 0.95)
        assert ci[0] < 0.5 < ci[1]

    def test_zero_total(self):
        """total=0 时返回 [0.0, 0.0]."""
        ci = _wilson_ci(0, 0, 0.95)
        assert ci == [0.0, 0.0]

    def test_bounds_within_unit_interval(self):
        """CI 必须在 [0, 1] 范围内."""
        for successes in [1, 5, 10, 50, 99]:
            ci = _wilson_ci(successes, 100, 0.95)
            assert 0.0 <= ci[0] <= 1.0
            assert 0.0 <= ci[1] <= 1.0
            assert ci[0] <= ci[1]

    def test_higher_confidence_wider_interval(self):
        """更高置信水平应产生更宽的区间."""
        ci_90 = _wilson_ci(50, 100, 0.90)
        ci_99 = _wilson_ci(50, 100, 0.99)
        width_90 = ci_90[1] - ci_90[0]
        width_99 = ci_99[1] - ci_99[0]
        assert width_99 >= width_90


class TestBootstrapAucCI:
    """Test _bootstrap_auc_ci."""

    def test_perfect_separation(self):
        """完美分类：AUC 应为 1.0."""
        y_true = np.array([0, 0, 1, 1])
        y_score = np.array([0.1, 0.2, 0.8, 0.9])
        auc, ci, reliable = _bootstrap_auc_ci(y_true, y_score, n_bootstrap=100)
        assert auc == 1.0
        assert reliable is True
        assert len(ci) == 2

    def test_single_class_returns_unreliable(self):
        """单类 y_true：返回 unreliable."""
        y_true = np.array([0, 0, 0, 0])
        y_score = np.array([0.1, 0.2, 0.3, 0.4])
        auc, ci, reliable = _bootstrap_auc_ci(y_true, y_score, n_bootstrap=100)
        assert reliable is False
        assert auc == 0.5

    def test_random_scores_auc_near_half(self):
        """随机预测：AUC 应接近 0.5."""
        rng = np.random.RandomState(42)
        y_true = rng.randint(0, 2, size=200)
        y_score = rng.rand(200)
        auc, ci, reliable = _bootstrap_auc_ci(y_true, y_score, n_bootstrap=200)
        assert reliable is True
        assert 0.3 < auc < 0.7

    def test_ci_contains_point_estimate(self):
        """CI 应包含点估计 AUC."""
        rng = np.random.RandomState(0)
        y_true = rng.randint(0, 2, size=100)
        y_score = rng.rand(100)
        auc, ci, reliable = _bootstrap_auc_ci(y_true, y_score, n_bootstrap=200)
        if reliable and ci != [0.0, 0.0]:
            assert ci[0] <= auc <= ci[1]


class TestComputeBrierScore:
    """Test compute_brier_score."""

    def test_perfect_prediction(self):
        """完美预测：Brier Score = 0."""
        y_true = np.array([0, 1, 0, 1])
        y_score = np.array([0.0, 1.0, 0.0, 1.0])
        assert compute_brier_score(y_true, y_score) == 0.0

    def test_worst_prediction(self):
        """完全错误预测：Brier Score = 1."""
        y_true = np.array([0, 1])
        y_score = np.array([1.0, 0.0])
        assert compute_brier_score(y_true, y_score) == 1.0

    def test_random_prediction(self):
        """随机预测（0.5 概率）：Brier Score ≈ 0.25."""
        y_true = np.array([0, 1, 0, 1])
        y_score = np.array([0.5, 0.5, 0.5, 0.5])
        bs = compute_brier_score(y_true, y_score)
        assert abs(bs - 0.25) < 1e-6

    def test_empty_input(self):
        """空输入：返回 0.0."""
        assert compute_brier_score(np.array([]), np.array([])) == 0.0

    def test_value_range(self):
        """Brier Score 应在 [0, 1] 范围内."""
        rng = np.random.RandomState(7)
        y_true = rng.randint(0, 2, size=50)
        y_score = rng.rand(50)
        bs = compute_brier_score(y_true, y_score)
        assert 0.0 <= bs <= 1.0


class TestComputeBinaryMetrics:
    """Test compute_binary_metrics."""

    def test_perfect_prediction(self):
        """完美预测：所有指标应为 1.0，Brier Score 为 0."""
        y_true = np.array([0, 0, 1, 1])
        y_pred = np.array([0, 0, 1, 1])
        y_score = np.array([0.1, 0.2, 0.8, 0.9])
        m = compute_binary_metrics(y_true, y_pred, y_score, n_bootstrap=50)
        assert m.sensitivity == 1.0
        assert m.specificity == 1.0
        assert m.ppv == 1.0
        assert m.npv == 1.0
        assert m.auc == 1.0
        assert m.brier_score < 0.05
        assert m.tp == 2 and m.fp == 0 and m.tn == 2 and m.fn == 0

    def test_all_wrong_prediction(self):
        """全错预测：sensitivity/specificity 应为 0."""
        y_true = np.array([0, 0, 1, 1])
        y_pred = np.array([1, 1, 0, 0])
        y_score = np.array([0.8, 0.9, 0.1, 0.2])
        m = compute_binary_metrics(y_true, y_pred, y_score, n_bootstrap=50)
        assert m.sensitivity == 0.0
        assert m.specificity == 0.0
        assert m.ppv == 0.0
        assert m.npv == 0.0
        assert m.tp == 0 and m.fn == 2 and m.fp == 2 and m.tn == 0

    def test_confusion_matrix_counts(self):
        """混淆矩阵计数应正确."""
        y_true = np.array([0, 0, 0, 1, 1, 1])
        y_pred = np.array([0, 1, 0, 1, 0, 1])
        y_score = np.array([0.2, 0.6, 0.3, 0.7, 0.4, 0.8])
        m = compute_binary_metrics(y_true, y_pred, y_score, n_bootstrap=50)
        # y_true=0: [0,1,0] -> pred [0,1,0] => TN=2, FP=1
        # y_true=1: [1,1,1] -> pred [1,0,1] => TP=2, FN=1
        assert m.tp == 2
        assert m.fp == 1
        assert m.tn == 2
        assert m.fn == 1
        assert m.sensitivity == pytest.approx(2 / 3, rel=1e-3)
        assert m.specificity == pytest.approx(2 / 3, rel=1e-3)

    def test_confidence_intervals_present(self):
        """所有 CI 应为长度 2 的列表."""
        y_true = np.array([0, 0, 1, 1, 0, 1, 0, 1])
        y_pred = np.array([0, 0, 1, 1, 0, 1, 0, 1])
        y_score = np.array([0.1, 0.2, 0.9, 0.8, 0.3, 0.7, 0.2, 0.6])
        m = compute_binary_metrics(y_true, y_pred, y_score, n_bootstrap=50)
        assert len(m.sensitivity_ci) == 2
        assert len(m.specificity_ci) == 2
        assert len(m.ppv_ci) == 2
        assert len(m.npv_ci) == 2
        assert len(m.auc_ci) == 2

    def test_to_dict_roundtrip(self):
        """to_dict 应包含所有字段."""
        y_true = np.array([0, 1])
        y_pred = np.array([0, 1])
        y_score = np.array([0.2, 0.8])
        m = compute_binary_metrics(y_true, y_pred, y_score, n_bootstrap=20)
        d = m.to_dict()
        expected_keys = {
            "sensitivity", "specificity", "ppv", "npv", "auc", "brier_score",
            "sensitivity_ci", "specificity_ci", "ppv_ci", "npv_ci", "auc_ci",
            "confusion_matrix", "auc_reliable",
        }
        assert set(d.keys()) == expected_keys
        assert set(d["confusion_matrix"].keys()) == {"tp", "fp", "tn", "fn"}


class TestComputePerClassMetrics:
    """Test compute_per_class_metrics."""

    def test_binary_case(self):
        """二分类：应输出 2 个类别."""
        y_true = np.array([0, 0, 1, 1])
        y_pred = np.array([0, 0, 1, 1])
        y_score = np.array([0.1, 0.2, 0.8, 0.9])
        result = compute_per_class_metrics(y_true, y_pred, y_score)
        assert "per_class" in result
        assert "macro_avg" in result
        assert len(result["per_class"]) == 2
        assert "0" in result["per_class"]
        assert "1" in result["per_class"]

    def test_multiclass_three_classes(self):
        """三分类：应输出 3 个类别的 one-vs-rest 指标."""
        y_true = np.array([0, 1, 2, 0, 1, 2])
        y_pred = np.array([0, 1, 2, 0, 1, 2])
        # 多类概率矩阵 (6, 3)
        y_score = np.array([
            [0.8, 0.1, 0.1],
            [0.1, 0.8, 0.1],
            [0.1, 0.1, 0.8],
            [0.7, 0.2, 0.1],
            [0.2, 0.6, 0.2],
            [0.1, 0.2, 0.7],
        ])
        result = compute_per_class_metrics(y_true, y_pred, y_score)
        assert len(result["per_class"]) == 3
        macro = result["macro_avg"]
        assert "sensitivity" in macro
        assert "specificity" in macro
        assert "ppv" in macro
        assert "npv" in macro
        assert "auc" in macro
        assert "brier_score" in macro

    def test_perfect_multiclass(self):
        """完美多分类：每个类别的 sensitivity 应为 1.0."""
        y_true = np.array([0, 1, 2, 0, 1, 2])
        y_pred = np.array([0, 1, 2, 0, 1, 2])
        y_score = np.array([
            [0.9, 0.05, 0.05],
            [0.05, 0.9, 0.05],
            [0.05, 0.05, 0.9],
            [0.85, 0.1, 0.05],
            [0.1, 0.85, 0.05],
            [0.05, 0.1, 0.85],
        ])
        result = compute_per_class_metrics(y_true, y_pred, y_score)
        for cls_metrics in result["per_class"].values():
            assert cls_metrics["sensitivity"] == 1.0

    def test_explicit_class_labels(self):
        """显式提供 class_labels."""
        y_true = np.array([0, 1])
        y_pred = np.array([0, 1])
        y_score = np.array([0.2, 0.8])
        result = compute_per_class_metrics(
            y_true, y_pred, y_score, class_labels=[0, 1]
        )
        assert len(result["per_class"]) == 2


class TestComputeFairnessMetrics:
    """Test compute_fairness_metrics."""

    def test_two_groups_above_min_size(self):
        """两个群体都满足最小样本量：应输出两组指标 + 差异."""
        rng = np.random.RandomState(42)
        n = 100
        y_true = rng.randint(0, 2, size=n)
        y_pred = rng.randint(0, 2, size=n)
        y_score = rng.rand(n)
        groups = np.array(["male"] * 50 + ["female"] * 50)
        result = compute_fairness_metrics(
            y_true, y_pred, y_score, groups, min_group_size=30
        )
        assert "per_group" in result
        assert "suppressed_groups" in result
        assert "disparities" in result
        assert "male" in result["per_group"]
        assert "female" in result["per_group"]
        assert len(result["suppressed_groups"]) == 0
        # 至少有一种差异指标
        assert len(result["disparities"]) >= 1

    def test_small_group_suppressed(self):
        """小样本群体应被抑制，不出现在 per_group 中."""
        rng = np.random.RandomState(42)
        # 大组 50 + 小组 5（低于 min_group_size=30）
        y_true = np.concatenate([rng.randint(0, 2, size=50), np.array([0, 1, 0, 1, 0])])
        y_pred = np.concatenate([rng.randint(0, 2, size=50), np.array([0, 1, 0, 1, 0])])
        y_score = np.concatenate([rng.rand(50), np.array([0.2, 0.8, 0.3, 0.7, 0.4])])
        groups = np.array(["A"] * 50 + ["B"] * 5)
        result = compute_fairness_metrics(
            y_true, y_pred, y_score, groups, min_group_size=30
        )
        assert "A" in result["per_group"]
        assert "B" not in result["per_group"]
        assert "B" in result["suppressed_groups"]

    def test_single_class_group_suppressed(self):
        """群体内只有单类标签：应被抑制."""
        y_true = np.array([0] * 50 + [1] * 50)
        y_pred = np.array([0] * 50 + [1] * 50)
        y_score = np.array([0.1] * 50 + [0.9] * 50)
        groups = np.array(["X"] * 50 + ["Y"] * 50)
        result = compute_fairness_metrics(
            y_true, y_pred, y_score, groups, min_group_size=30
        )
        # X 组全是 0，Y 组全是 1，两者都是单类
        assert "X" in result["suppressed_groups"] or "X(single_class)" in result["suppressed_groups"]
        assert "Y" in result["suppressed_groups"] or "Y(single_class)" in result["suppressed_groups"]

    def test_disparity_calculation(self):
        """两组间差异应为 max - min."""
        # 组 1: 完美预测
        y_true_1 = np.array([0, 0, 1, 1] * 15)  # 60 个
        y_pred_1 = np.array([0, 0, 1, 1] * 15)
        y_score_1 = np.array([0.1, 0.2, 0.8, 0.9] * 15)
        # 组 2: 全错预测
        y_true_2 = np.array([0, 0, 1, 1] * 15)  # 60 个
        y_pred_2 = np.array([1, 1, 0, 0] * 15)
        y_score_2 = np.array([0.9, 0.8, 0.1, 0.2] * 15)

        y_true = np.concatenate([y_true_1, y_true_2])
        y_pred = np.concatenate([y_pred_1, y_pred_2])
        y_score = np.concatenate([y_score_1, y_score_2])
        groups = np.array(["good"] * 60 + ["bad"] * 60)

        result = compute_fairness_metrics(
            y_true, y_pred, y_score, groups, min_group_size=30
        )
        assert "sensitivity_gap" in result["disparities"]
        # 组 1 sensitivity=1.0, 组 2 sensitivity=0.0 => gap=1.0
        assert result["disparities"]["sensitivity_gap"] == pytest.approx(1.0, abs=0.01)

    def test_custom_min_group_size(self):
        """自定义 min_group_size."""
        rng = np.random.RandomState(0)
        y_true = rng.randint(0, 2, size=20)
        y_pred = rng.randint(0, 2, size=20)
        y_score = rng.rand(20)
        groups = np.array(["A"] * 10 + ["B"] * 10)
        # min_group_size=10，两组都满足
        result = compute_fairness_metrics(
            y_true, y_pred, y_score, groups, min_group_size=10
        )
        assert "A" in result["per_group"]
        assert "B" in result["per_group"]
        # min_group_size=15，两组都不满足
        result_strict = compute_fairness_metrics(
            y_true, y_pred, y_score, groups, min_group_size=15
        )
        assert len(result_strict["per_group"]) == 0


class TestGenerateClinicalValidationReport:
    """Test generate_clinical_validation_report."""

    def test_binary_report_without_groups(self):
        """二分类报告（无公平性检查）."""
        y_true = np.array([0, 0, 1, 1, 0, 1])
        y_pred = np.array([0, 0, 1, 1, 0, 1])
        y_score = np.array([0.1, 0.2, 0.8, 0.9, 0.3, 0.7])
        report = generate_clinical_validation_report(y_true, y_pred, y_score)
        assert report["sample_size"] == 6
        assert "binary_metrics" in report
        assert "calibration" in report
        assert "fairness" not in report

    def test_binary_report_with_groups(self):
        """二分类报告（含公平性检查）."""
        rng = np.random.RandomState(1)
        n = 80
        y_true = rng.randint(0, 2, size=n)
        y_pred = rng.randint(0, 2, size=n)
        y_score = rng.rand(n)
        groups = np.array(["M"] * 40 + ["F"] * 40)
        report = generate_clinical_validation_report(
            y_true, y_pred, y_score, groups=groups, group_name="gender"
        )
        assert "fairness" in report
        assert "gender" in report["fairness"]

    def test_multiclass_report(self):
        """多类报告."""
        y_true = np.array([0, 1, 2, 0, 1, 2])
        y_pred = np.array([0, 1, 2, 0, 1, 2])
        y_score = np.array([
            [0.8, 0.1, 0.1],
            [0.1, 0.8, 0.1],
            [0.1, 0.1, 0.8],
            [0.7, 0.2, 0.1],
            [0.2, 0.6, 0.2],
            [0.1, 0.2, 0.7],
        ])
        report = generate_clinical_validation_report(
            y_true, y_pred, y_score, class_labels=[0, 1, 2]
        )
        assert "multiclass_metrics" in report
        assert "binary_metrics" not in report
        assert "calibration" in report

    def test_report_contains_required_fields(self):
        """报告应包含必需字段."""
        y_true = np.array([0, 1, 0, 1])
        y_pred = np.array([0, 1, 0, 1])
        y_score = np.array([0.2, 0.8, 0.3, 0.7])
        report = generate_clinical_validation_report(y_true, y_pred, y_score)
        assert "sample_size" in report
        assert "confidence_level" in report
        assert "calibration" in report

    def test_confidence_level_propagated(self):
        """置信水平应传递到报告."""
        y_true = np.array([0, 1, 0, 1])
        y_pred = np.array([0, 1, 0, 1])
        y_score = np.array([0.2, 0.8, 0.3, 0.7])
        report = generate_clinical_validation_report(
            y_true, y_pred, y_score, confidence=0.90
        )
        assert report["confidence_level"] == 0.90


class TestBinaryMetricsDataclass:
    """Test BinaryMetrics dataclass."""

    def test_default_values(self):
        """默认值应正确."""
        m = BinaryMetrics(
            sensitivity=0.5, specificity=0.5, ppv=0.5, npv=0.5, auc=0.5, brier_score=0.25
        )
        assert m.tp == 0
        assert m.fp == 0
        assert m.tn == 0
        assert m.fn == 0
        assert m.auc_reliable is True
        assert m.sensitivity_ci == []
        assert m.auc_ci == []

    def test_to_dict_roundtrip(self):
        """to_dict 返回的字典应可序列化."""
        m = BinaryMetrics(
            sensitivity=0.9, specificity=0.8, ppv=0.7, npv=0.6,
            auc=0.85, brier_score=0.15,
            sensitivity_ci=[0.8, 0.95], specificity_ci=[0.7, 0.9],
            ppv_ci=[0.6, 0.8], npv_ci=[0.5, 0.7], auc_ci=[0.75, 0.92],
            tp=10, fp=3, tn=20, fn=2, auc_reliable=True,
        )
        d = m.to_dict()
        # 应可 JSON 序列化
        import json
        json_str = json.dumps(d)
        assert "sensitivity" in json_str
