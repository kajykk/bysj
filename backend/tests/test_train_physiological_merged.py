"""
R-F2: 合并入口 train_physiological.py 测试.

覆盖合并后的共享逻辑（数据/权重/产物名/模型分发），不依赖 xgboost/lightgbm
安装（相关训练路径由原 test_train_xgboost.py / test_train_lightgbm.py 覆盖，
本文件只验证合并层的一致性与分发正确性）。
"""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import MagicMock

import numpy as np
import pytest

# Add repo root to path so `scripts` is importable
repo_root = Path(__file__).resolve().parents[2]
if str(repo_root) not in sys.path:
    sys.path.insert(0, str(repo_root))

try:
    from scripts.train_physiological import (
        _TRAINERS,
        DEFAULT_OUTPUT_DIRS,
        MODEL_ARTIFACT_NAMES,
        compute_class_weight,
        evaluate_model,
        parse_args,
    )
except ImportError:
    pytest.skip(
        "scripts/train_physiological.py 不存在, 跳过合并入口测试",
        allow_module_level=True,
    )


class TestMergedPipeline:
    def test_model_registry_covers_both_families(self) -> None:
        assert set(_TRAINERS) == {"xgb", "lgbm"}
        assert set(DEFAULT_OUTPUT_DIRS) == {"xgb", "lgbm"}
        assert set(MODEL_ARTIFACT_NAMES) == {"xgb", "lgbm"}

    def test_artifact_names_preserved(self) -> None:
        """产物文件名与旧脚本一致: xgb→model.json, lgbm→model.txt."""
        assert MODEL_ARTIFACT_NAMES["xgb"] == "model.json"
        assert MODEL_ARTIFACT_NAMES["lgbm"] == "model.txt"

    def test_default_output_dirs_preserved(self) -> None:
        assert DEFAULT_OUTPUT_DIRS["xgb"].as_posix().endswith(
            "models/artifacts/physiological/xgboost"
        )
        assert DEFAULT_OUTPUT_DIRS["lgbm"].as_posix().endswith(
            "models/artifacts/physiological/lightgbm"
        )

    def test_parse_args_default_model_xgb(self) -> None:
        args = parse_args([])
        assert args.model == "xgb"

    def test_parse_args_model_lgbm(self) -> None:
        args = parse_args(["--model", "lgbm"])
        assert args.model == "lgbm"

    def test_parse_args_invalid_model_rejected(self) -> None:
        with pytest.raises(SystemExit):
            parse_args(["--model", "svm"])

    def test_compute_class_weight_balanced(self) -> None:
        y = np.array([0, 1, 0, 1, 0, 1])
        assert compute_class_weight(y) == 1.0

    def test_compute_class_weight_imbalanced(self) -> None:
        y = np.array([0, 0, 0, 1])
        assert compute_class_weight(y) == 3.0

    def test_compute_class_weight_all_positive(self) -> None:
        # 原脚本语义: n_pos 为 0 时返回 1.0；全正样本时返回 n_neg/n_pos = 0.0
        y = np.array([1, 1, 1])
        assert compute_class_weight(y) == 0.0

    async def test_evaluate_lgbm_path_uses_numpy_predict(self) -> None:
        """lgbm 路径直接 predict numpy 数组（不构造 DMatrix）."""
        model = MagicMock()
        model.predict.return_value = np.array([0.9, 0.1, 0.7, 0.2])
        X = np.zeros((4, 3))
        y = np.array([1, 0, 1, 0])
        metrics = evaluate_model(model, X, y, ["a", "b", "c"], "lgbm")
        model.predict.assert_called_once()
        assert "f1" in metrics
        assert metrics["n_samples"] == 4
