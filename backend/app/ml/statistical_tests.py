"""Statistical tests for model evaluation."""

from __future__ import annotations

import logging
from typing import Callable

import numpy as np

logger = logging.getLogger(__name__)


def bootstrap_ci(
    y_true: np.ndarray,
    y_pred: np.ndarray,
    metric_fn: Callable,
    n_bootstrap: int = 1000,
    confidence: float = 0.95,
    random_state: int = 42,
) -> dict:
    """Compute bootstrap confidence interval for a metric.

    Args:
        y_true: True labels.
        y_pred: Predicted probabilities or labels.
        metric_fn: Function to compute metric (y_true, y_pred) -> float.
        n_bootstrap: Number of bootstrap samples.
        confidence: Confidence level (e.g., 0.95 for 95% CI).
        random_state: Random seed.

    Returns:
        Dictionary with metric, CI lower bound, and CI upper bound.
    """
    rng = np.random.RandomState(random_state)
    n_samples = len(y_true)

    # Compute original metric
    original_metric = metric_fn(y_true, y_pred)

    # Bootstrap
    bootstrap_metrics = []
    for i in range(n_bootstrap):
        # Sample with replacement
        indices = rng.randint(0, n_samples, n_samples)
        y_true_boot = y_true[indices]
        y_pred_boot = y_pred[indices]

        # Compute metric
        metric = metric_fn(y_true_boot, y_pred_boot)
        bootstrap_metrics.append(metric)

    bootstrap_metrics = np.array(bootstrap_metrics)

    # Compute percentile CI
    alpha = 1 - confidence
    ci_lower = np.percentile(bootstrap_metrics, alpha / 2 * 100)
    ci_upper = np.percentile(bootstrap_metrics, (1 - alpha / 2) * 100)

    result = {
        "metric": float(original_metric),
        "ci_lower": float(ci_lower),
        "ci_upper": float(ci_upper),
        "confidence": confidence,
        "n_bootstrap": n_bootstrap,
        "bootstrap_std": float(np.std(bootstrap_metrics)),
    }

    logger.info(
        "Bootstrap %d%% CI: %.4f [%.4f, %.4f]",
        int(confidence * 100),
        original_metric,
        ci_lower,
        ci_upper,
    )

    return result


def _chi2_sf_df1(statistic: float) -> float:
    """计算 chi-squared(df=1) 的生存函数 P(X > statistic)。

    ML-003 修复：使用精确的 p 值计算，替代原代码中不精确的近似公式。

    优先使用 scipy.stats.chi2.sf（精确数值积分）；
    若 scipy 不可用，回退到 math.erfc（精确等价公式）：
        对于 chi-squared(1): P(X > x) = erfc(sqrt(x/2))

    Args:
        statistic: McNemar 检验统计量（非负）。

    Returns:
        上尾概率 p-value，范围 [0, 1]。
    """
    if statistic <= 0:
        return 1.0
    try:
        from scipy.stats import chi2

        return float(chi2.sf(statistic, df=1))
    except ImportError:
        # scipy 不可用时使用 erfc 精确等价公式（与 scipy 结果一致到机器精度）
        from math import erfc, sqrt

        return float(erfc(sqrt(statistic / 2)))


def mcnemar_test(
    y_true: np.ndarray,
    y_pred1: np.ndarray,
    y_pred2: np.ndarray,
) -> dict:
    """Perform McNemar's test to compare two models.

    Tests whether the two models have the same error rate.

    Args:
        y_true: True labels.
        y_pred1: Predictions from model 1.
        y_pred2: Predictions from model 2.

    Returns:
        Dictionary with test statistic, p-value, and conclusion.
    """
    y_true_flat = y_true.flatten().astype(int)
    y_pred1_flat = (y_pred1.flatten() >= 0.5).astype(int)
    y_pred2_flat = (y_pred2.flatten() >= 0.5).astype(int)

    # Contingency table
    # b: model1 correct, model2 wrong
    # c: model1 wrong, model2 correct
    b = np.sum((y_pred1_flat == y_true_flat) & (y_pred2_flat != y_true_flat))
    c = np.sum((y_pred1_flat != y_true_flat) & (y_pred2_flat == y_true_flat))

    # McNemar's test statistic (with continuity correction)
    if b + c == 0:
        statistic = 0.0
        p_value = 1.0
    else:
        statistic = (abs(b - c) - 1) ** 2 / (b + c)
        # ML-003 修复：使用精确的 chi-squared(1) p 值计算
        # 优先使用 scipy.stats.chi2.sf（精确），回退到 math.erfc（精确等价公式）
        p_value = _chi2_sf_df1(statistic)

    result = {
        "statistic": float(statistic),
        "p_value": float(p_value),
        "b": int(b),
        "c": int(c),
        "significant": p_value < 0.05,
        "conclusion": (
            "Models have significantly different performance"
            if p_value < 0.05
            else "No significant difference between models"
        ),
    }

    logger.info(
        "McNemar test: statistic=%.4f, p-value=%.4f, b=%d, c=%d",
        statistic,
        p_value,
        b,
        c,
    )

    return result


def bonferroni_correction(
    p_values: list[float],
    alpha: float = 0.05,
) -> dict:
    """Apply Bonferroni correction for multiple comparisons.

    Args:
        p_values: List of p-values from multiple tests.
        alpha: Significance level.

    Returns:
        Dictionary with corrected alpha and significant results.
    """
    n_tests = len(p_values)
    if n_tests == 0:
        raise ValueError("p_values list cannot be empty")
    corrected_alpha = alpha / n_tests

    significant = [p < corrected_alpha for p in p_values]
    n_significant = sum(significant)

    result = {
        "n_tests": n_tests,
        "original_alpha": alpha,
        "corrected_alpha": corrected_alpha,
        "p_values": p_values,
        "significant": significant,
        "n_significant": n_significant,
    }

    logger.info(
        "Bonferroni correction: %d tests, corrected alpha=%.6f, %d significant",
        n_tests,
        corrected_alpha,
        n_significant,
    )

    return result


def compute_f1(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Helper function to compute F1 score for bootstrap."""
    y_pred_binary = (y_pred >= 0.5).astype(int)
    y_true_flat = y_true.flatten().astype(int)

    tp = np.sum((y_true_flat == 1) & (y_pred_binary == 1))
    fp = np.sum((y_true_flat == 0) & (y_pred_binary == 1))
    fn = np.sum((y_true_flat == 1) & (y_pred_binary == 0))

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return f1


def compute_accuracy(y_true: np.ndarray, y_pred: np.ndarray) -> float:
    """Helper function to compute accuracy for bootstrap."""
    y_pred_binary = (y_pred >= 0.5).astype(int)
    y_true_flat = y_true.flatten().astype(int)
    return np.mean(y_true_flat == y_pred_binary)
