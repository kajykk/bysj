"""
T-QA-002 融合逻辑集成测试

测试多模型融合结果正确性
验证标准: 融合输出在预期范围内
"""

from typing import Dict, List, Tuple

import numpy as np
import pytest

pytestmark = pytest.mark.integration


def weighted_fusion(
    predictions: List[float], weights: List[float], method: str = "weighted_average"
) -> float:
    """
    多模型融合逻辑

    Args:
        predictions: 各模型的预测概率
        weights: 各模型的权重
        method: 融合方法 (weighted_average, max_voting, average)

    Returns:
        融合后的预测概率
    """
    if len(predictions) != len(weights):
        raise ValueError("预测值和权重数量必须相同")

    if not predictions:
        raise ValueError("预测值不能为空")

    # 归一化权重
    total_weight = sum(weights)
    if total_weight == 0:
        raise ValueError("权重总和不能为 0")
    normalized_weights = [w / total_weight for w in weights]

    if method == "weighted_average":
        return sum(p * w for p, w in zip(predictions, normalized_weights))
    elif method == "average":
        return sum(predictions) / len(predictions)
    elif method == "max_voting":
        # 对于二分类，使用多数投票
        votes = [1 if p >= 0.5 else 0 for p in predictions]
        vote_count = sum(votes)
        return vote_count / len(votes)
    else:
        raise ValueError(f"未知的融合方法: {method}")


def ensemble_predict(
    model_predictions: Dict[str, float],
    model_weights: Dict[str, float],
    method: str = "weighted_average",
) -> Tuple[float, Dict[str, float]]:
    """
    集成预测：返回融合结果和各个模型的贡献

    Returns:
        (融合概率, 各模型贡献字典)
    """
    predictions = list(model_predictions.values())
    weights = list(model_weights.values())

    fused = weighted_fusion(predictions, weights, method)

    contributions = {
        name: pred * weight / sum(weights)
        for name, pred, weight in zip(model_predictions.keys(), predictions, weights)
    }

    return fused, contributions


class TestWeightedFusion:
    """加权融合逻辑测试"""

    def test_equal_weights_fusion(self):
        """测试等权重融合"""
        predictions = [0.3, 0.5, 0.7]
        weights = [1.0, 1.0, 1.0]

        result = weighted_fusion(predictions, weights, "weighted_average")

        # 等权重融合应等于平均值
        expected = sum(predictions) / len(predictions)
        assert (
            abs(result - expected) < 1e-6
        ), f"等权重融合结果应为 {expected}，实际为 {result}"

    def test_unequal_weights_fusion(self):
        """测试不等权重融合"""
        predictions = [0.3, 0.5, 0.7]
        weights = [0.5, 1.0, 0.5]

        result = weighted_fusion(predictions, weights, "weighted_average")

        # 归一化权重: [0.25, 0.5, 0.25]
        expected = 0.3 * 0.25 + 0.5 * 0.5 + 0.7 * 0.25
        assert (
            abs(result - expected) < 1e-6
        ), f"不等权重融合结果应为 {expected}，实际为 {result}"

    def test_single_model_fusion(self):
        """测试单模型融合"""
        predictions = [0.6]
        weights = [1.0]

        result = weighted_fusion(predictions, weights)

        assert result == pytest.approx(0.6), "单模型融合应返回原值"

    def test_output_range(self):
        """测试融合输出范围：应在 [0, 1] 之间"""
        predictions = [0.1, 0.9, 0.5]
        weights = [1.0, 2.0, 1.0]

        result = weighted_fusion(predictions, weights)

        assert 0 <= result <= 1, f"融合输出 {result} 超出 [0, 1] 范围"

    def test_high_confidence_model_dominance(self):
        """测试高置信度模型主导"""
        predictions = [0.1, 0.9]
        weights = [0.1, 10.0]  # 第二个模型权重极高

        result = weighted_fusion(predictions, weights)

        # 结果应接近高权重模型的预测值
        assert result > 0.8, f"高权重模型应主导结果，实际为 {result}"

    def test_zero_weights_error(self):
        """测试全零权重应抛出错误"""
        predictions = [0.5, 0.5]
        weights = [0.0, 0.0]

        with pytest.raises(ValueError, match="权重总和不能为 0"):
            weighted_fusion(predictions, weights)

    def test_empty_predictions_error(self):
        """测试空预测应抛出错误"""
        with pytest.raises(ValueError, match="预测值不能为空"):
            weighted_fusion([], [])

    def test_mismatched_length_error(self):
        """测试长度不匹配应抛出错误"""
        predictions = [0.5, 0.5]
        weights = [1.0]

        with pytest.raises(ValueError, match="预测值和权重数量必须相同"):
            weighted_fusion(predictions, weights)


class TestEnsemblePredict:
    """集成预测测试"""

    def test_ensemble_with_multiple_models(self):
        """测试多模型集成预测"""
        model_predictions = {
            "xgboost": 0.7,
            "lightgbm": 0.75,
            "mlp": 0.65,
        }
        model_weights = {
            "xgboost": 2.0,
            "lightgbm": 2.0,
            "mlp": 1.0,
        }

        fused, contributions = ensemble_predict(model_predictions, model_weights)

        # 验证融合结果
        assert 0 <= fused <= 1, f"融合结果 {fused} 应在 [0, 1] 范围内"

        # 验证贡献值
        assert len(contributions) == 3, "应返回所有模型的贡献值"
        assert all(v >= 0 for v in contributions.values()), "贡献值应非负"

    def test_contributions_sum(self):
        """测试贡献值之和应等于融合结果"""
        model_predictions = {
            "model_a": 0.6,
            "model_b": 0.4,
        }
        model_weights = {
            "model_a": 1.0,
            "model_b": 1.0,
        }

        fused, contributions = ensemble_predict(model_predictions, model_weights)

        total_contribution = sum(contributions.values())
        assert (
            abs(fused - total_contribution) < 1e-6
        ), f"贡献值之和 {total_contribution} 应等于融合结果 {fused}"


class TestFusionMethods:
    """不同融合方法测试"""

    def test_average_method(self):
        """测试简单平均法"""
        predictions = [0.3, 0.5, 0.7]
        weights = [1.0, 1.0, 1.0]

        result = weighted_fusion(predictions, weights, "average")
        expected = sum(predictions) / len(predictions)

        assert result == pytest.approx(expected), "平均法结果不正确"

    def test_max_voting_method(self):
        """测试多数投票法"""
        predictions = [0.6, 0.4, 0.7]  # 2 个 >= 0.5, 1 个 < 0.5
        weights = [1.0, 1.0, 1.0]

        result = weighted_fusion(predictions, weights, "max_voting")

        # 2/3 的模型预测为正类
        assert result == pytest.approx(2 / 3), "多数投票结果不正确"

    def test_max_voting_all_positive(self):
        """测试多数投票：全部为正类"""
        predictions = [0.6, 0.7, 0.8]
        weights = [1.0, 1.0, 1.0]

        result = weighted_fusion(predictions, weights, "max_voting")

        assert result == pytest.approx(1.0), "全部正类应返回 1.0"

    def test_max_voting_all_negative(self):
        """测试多数投票：全部为负类"""
        predictions = [0.1, 0.2, 0.3]
        weights = [1.0, 1.0, 1.0]

        result = weighted_fusion(predictions, weights, "max_voting")

        assert result == pytest.approx(0.0), "全部负类应返回 0.0"


class TestFusionEdgeCases:
    """融合边界情况测试"""

    def test_extreme_predictions(self):
        """测试极端预测值"""
        predictions = [0.0, 1.0]
        weights = [1.0, 1.0]

        result = weighted_fusion(predictions, weights)

        assert result == pytest.approx(0.5), "极端值融合应为 0.5"

    def test_boundary_predictions(self):
        """测试边界预测值"""
        predictions = [0.01, 0.99]
        weights = [1.0, 1.0]

        result = weighted_fusion(predictions, weights)

        assert 0 <= result <= 1, "边界值融合应在 [0, 1] 范围内"

    def test_many_models_fusion(self):
        """测试多模型融合（10 个模型）"""
        np.random.seed(42)
        predictions = list(np.random.uniform(0, 1, 10))
        weights = list(np.random.uniform(0.5, 2.0, 10))

        result = weighted_fusion(predictions, weights)

        assert 0 <= result <= 1, f"10 模型融合结果 {result} 应在 [0, 1] 范围内"

    def test_identical_predictions(self):
        """测试相同预测值"""
        predictions = [0.5, 0.5, 0.5, 0.5]
        weights = [1.0, 2.0, 3.0, 4.0]

        result = weighted_fusion(predictions, weights)

        assert result == pytest.approx(0.5), "相同预测值的融合应等于原值"

    def test_weighted_towards_zero(self):
        """测试权重偏向 0 预测"""
        predictions = [0.1, 0.9]
        weights = [10.0, 1.0]  # 第一个模型权重极高

        result = weighted_fusion(predictions, weights)

        assert result < 0.5, f"权重偏向低预测值，结果应 < 0.5，实际为 {result}"

    def test_weighted_towards_one(self):
        """测试权重偏向 1 预测"""
        predictions = [0.1, 0.9]
        weights = [1.0, 10.0]  # 第二个模型权重极高

        result = weighted_fusion(predictions, weights)

        assert result > 0.5, f"权重偏向高预测值，结果应 > 0.5，实际为 {result}"
