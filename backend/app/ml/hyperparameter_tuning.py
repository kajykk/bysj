from __future__ import annotations

import copy
import itertools
import logging

import numpy as np

from app.ml.loss import binary_cross_entropy_loss
from app.ml.model import PhysiologicalMLP
from app.ml.trainer import evaluate, train_model

logger = logging.getLogger(__name__)


def grid_search(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    param_grid: dict | None = None,
    epochs: int = 20,
    patience: int = 5,
    random_state: int = 42,
) -> tuple[dict, float]:
    """Simple grid search for hyperparameter tuning.

    .. warning::
        P1-ML-027 修复警告：返回的 best_val_f1 是在用于超参数选择的同一验证集上计算的，
        存在乐观偏差（selection bias）。请勿将其作为最终模型性能报告。
        最终性能评估必须在独立的测试集上进行，或使用 nested_cv_score 进行嵌套 CV 评估。

    Args:
        X_train: Training features.
        y_train: Training labels.
        X_val: Validation features (used for hyperparameter selection).
        y_val: Validation labels.
        param_grid: Dictionary of parameters to search.
        epochs: Number of epochs per trial.
        patience: Early stopping patience.
        random_state: Random seed for reproducibility.

    Returns:
        Tuple of (best_params, best_val_f1). Note: best_val_f1 is optimistically biased.
    """
    if param_grid is None:
        param_grid = {
            "hidden_dims": [[64, 32, 16], [32, 16], [64, 32]],
            "dropout_rate": [0.0, 0.2, 0.4],
            "learning_rate": [0.001, 0.01, 0.005],
            "weight_decay": [0.001, 0.01, 0.1],
            "batch_size": [32, 64],
        }

    # Generate all combinations
    keys = list(param_grid.keys())
    values = list(param_grid.values())
    combinations = list(itertools.product(*values))

    logger.info("Starting grid search: %d combinations", len(combinations))

    best_f1 = 0.0
    best_params = {}
    results = []

    for i, combo in enumerate(combinations):
        params = dict(zip(keys, combo))
        logger.info(
            "Trial %d/%d: %s",
            i + 1,
            len(combinations),
            params,
        )

        # Create model
        model = PhysiologicalMLP(
            input_dim=X_train.shape[1],
            hidden_dims=params["hidden_dims"],
            dropout_rate=params["dropout_rate"],
            use_batch_norm=False,
            random_state=random_state,
        )

        # Train
        history = train_model(
            model,
            X_train,
            y_train,
            X_val,
            y_val,
            epochs=epochs,
            batch_size=params["batch_size"],
            learning_rate=params["learning_rate"],
            weight_decay=params["weight_decay"],
            patience=patience,
            loss_fn=binary_cross_entropy_loss,
            random_state=random_state,
        )

        val_f1 = history["best_val_f1"]
        results.append({"params": params, "val_f1": val_f1})

        logger.info("Trial %d result: val_f1=%.4f", i + 1, val_f1)

        if val_f1 > best_f1:
            best_f1 = val_f1
            best_params = copy.deepcopy(params)
            logger.info("New best! val_f1=%.4f", best_f1)

    logger.info(
        "Grid search complete: best_val_f1=%.4f, best_params=%s",
        best_f1,
        best_params,
    )

    return best_params, best_f1


def random_search(
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    n_trials: int = 20,
    epochs: int = 20,
    patience: int = 5,
    random_state: int = 42,
) -> tuple[dict, float]:
    """Random search for hyperparameter tuning.

    .. warning::
        P1-ML-027 修复警告：返回的 best_val_f1 是在用于超参数选择的同一验证集上计算的，
        存在乐观偏差（selection bias）。请勿将其作为最终模型性能报告。
        最终性能评估必须在独立的测试集上进行，或使用 nested_cv_score 进行嵌套 CV 评估。

    Args:
        X_train: Training features.
        y_train: Training labels.
        X_val: Validation features (used for hyperparameter selection).
        y_val: Validation labels.
        n_trials: Number of random trials.
        epochs: Number of epochs per trial.
        patience: Early stopping patience.
        random_state: Random seed.

    Returns:
        Tuple of (best_params, best_val_f1). Note: best_val_f1 is optimistically biased.
    """
    rng = np.random.RandomState(random_state)

    # Define search space
    hidden_dims_options = [[64, 32, 16], [32, 16], [64, 32], [128, 64, 32]]
    dropout_rates = [0.0, 0.1, 0.2, 0.3, 0.4]
    learning_rates = [0.0001, 0.0005, 0.001, 0.005, 0.01]
    weight_decays = [0.0001, 0.001, 0.01, 0.1]
    batch_sizes = [16, 32, 64, 128]

    logger.info("Starting random search: %d trials", n_trials)

    best_f1 = 0.0
    best_params = {}

    for i in range(n_trials):
        params = {
            "hidden_dims": hidden_dims_options[rng.randint(len(hidden_dims_options))],
            "dropout_rate": dropout_rates[rng.randint(len(dropout_rates))],
            "learning_rate": learning_rates[rng.randint(len(learning_rates))],
            "weight_decay": weight_decays[rng.randint(len(weight_decays))],
            "batch_size": batch_sizes[rng.randint(len(batch_sizes))],
        }

        logger.info(
            "Trial %d/%d: hidden=%s, dropout=%.1f, lr=%.4f, wd=%.4f, bs=%d",
            i + 1,
            n_trials,
            params["hidden_dims"],
            params["dropout_rate"],
            params["learning_rate"],
            params["weight_decay"],
            params["batch_size"],
        )

        # Create model
        model = PhysiologicalMLP(
            input_dim=X_train.shape[1],
            hidden_dims=params["hidden_dims"],
            dropout_rate=params["dropout_rate"],
            use_batch_norm=False,
            random_state=random_state,
        )

        # Train
        history = train_model(
            model,
            X_train,
            y_train,
            X_val,
            y_val,
            epochs=epochs,
            batch_size=params["batch_size"],
            learning_rate=params["learning_rate"],
            weight_decay=params["weight_decay"],
            patience=patience,
            loss_fn=binary_cross_entropy_loss,
            random_state=random_state,
        )

        val_f1 = history["best_val_f1"]
        logger.info("Trial %d result: val_f1=%.4f", i + 1, val_f1)

        if val_f1 > best_f1:
            best_f1 = val_f1
            best_params = copy.deepcopy(params)
            logger.info("New best! val_f1=%.4f", best_f1)

    logger.info(
        "Random search complete: best_val_f1=%.4f, best_params=%s",
        best_f1,
        best_params,
    )

    return best_params, best_f1


def nested_cv_score(
    X: np.ndarray,
    y: np.ndarray,
    outer_folds: int = 5,
    inner_folds: int = 3,
    param_grid: dict | None = None,
    epochs: int = 20,
    patience: int = 5,
    random_state: int = 42,
) -> dict:
    """嵌套交叉验证评估（P1-ML-027 修复）.

    实现嵌套 CV，避免超参数选择偏差：
    - 外层循环：将数据划分为 train/test，用于无偏性能评估
    - 内层循环：在 train 上使用 80/20 hold-out 划分进行超参数选择
      （注：inner_folds 参数当前保留但未使用，内层使用单次 hold-out 而非 K-fold CV）
    - 用最佳超参数在完整 train 上重新训练，在 test 上评估

    Args:
        X: 完整特征矩阵.
        y: 完整标签向量.
        outer_folds: 外层 CV 折数.
        inner_folds: 内层 CV 折数（当前保留未用，内层使用 80/20 hold-out）.
        param_grid: 超参数搜索空间.
        epochs: 每次训练的 epoch 数.
        patience: 早停 patience.
        random_state: 随机种子.

    Returns:
        包含 outer_scores、mean_score、std_score 和 best_params_per_fold 的字典.
    """
    if inner_folds != 3:
        logger.warning(
            "inner_folds=%d 已设置但当前实现使用 80/20 hold-out，该参数将被忽略",
            inner_folds,
        )
    rng = np.random.RandomState(random_state)
    n_samples = len(y)
    indices = np.arange(n_samples)
    rng.shuffle(indices)

    # 创建外层 fold
    fold_size = n_samples // outer_folds
    outer_folds_list = []
    for i in range(outer_folds):
        start = i * fold_size
        end = start + fold_size if i < outer_folds - 1 else n_samples
        outer_folds_list.append(indices[start:end])

    outer_scores = []
    best_params_per_fold = []

    for outer_idx in range(outer_folds):
        logger.info("=" * 50)
        logger.info("Nested CV - Outer fold %d/%d", outer_idx + 1, outer_folds)
        logger.info("=" * 50)

        # 外层划分：test = 当前 fold, train = 其余
        test_indices = outer_folds_list[outer_idx]
        train_indices = np.concatenate(
            [outer_folds_list[i] for i in range(outer_folds) if i != outer_idx]
        )

        X_train_outer = X[train_indices]
        y_train_outer = y[train_indices]
        X_test_outer = X[test_indices]
        y_test_outer = y[test_indices]

        # 内层：在 train 上进行 grid_search 选择超参数
        # 将 train 再划分为 train_inner/val_inner 用于 grid_search
        inner_split = int(len(X_train_outer) * 0.8)
        inner_shuffle = np.random.RandomState(random_state + outer_idx).permutation(
            len(X_train_outer)
        )
        X_train_inner = X_train_outer[inner_shuffle[:inner_split]]
        y_train_inner = y_train_outer[inner_shuffle[:inner_split]]
        X_val_inner = X_train_outer[inner_shuffle[inner_split:]]
        y_val_inner = y_train_outer[inner_shuffle[inner_split:]]

        best_params, _ = grid_search(
            X_train_inner,
            y_train_inner,
            X_val_inner,
            y_val_inner,
            param_grid=param_grid,
            epochs=epochs,
            patience=patience,
            random_state=random_state + outer_idx,
        )
        best_params_per_fold.append(best_params)

        # 用最佳超参数在完整外层 train 上重新训练
        model = PhysiologicalMLP(
            input_dim=X_train_outer.shape[1],
            hidden_dims=best_params["hidden_dims"],
            dropout_rate=best_params["dropout_rate"],
            use_batch_norm=False,
            random_state=random_state + outer_idx,
        )

        # C-2 修复：从外层训练集再切出一个验证子集用于早停，测试集只在最终评估时使用一次。
        # 原实现将 X_test_outer 作为 train_model 的验证集传入，触发 EarlyStopping 基于
        # 测试集表现选择权重，导致嵌套 CV 的无偏性被破坏、报告的 F1 存在乐观偏差。
        es_split = int(len(X_train_outer) * 0.85)
        rng_es = np.random.RandomState(random_state + outer_idx + 100)
        es_perm = rng_es.permutation(len(X_train_outer))
        X_tr_es, X_val_es = (
            X_train_outer[es_perm[:es_split]],
            X_train_outer[es_perm[es_split:]],
        )
        y_tr_es, y_val_es = (
            y_train_outer[es_perm[:es_split]],
            y_train_outer[es_perm[es_split:]],
        )

        _history = train_model(
            model,
            X_tr_es,
            y_tr_es,
            X_val_es,
            y_val_es,
            epochs=epochs,
            batch_size=best_params["batch_size"],
            learning_rate=best_params["learning_rate"],
            weight_decay=best_params["weight_decay"],
            patience=patience,
            loss_fn=binary_cross_entropy_loss,
            random_state=random_state + outer_idx,
        )

        # 在外层 test 上评估（无偏估计，仅使用一次）
        test_loss, test_metrics = evaluate(
            model, X_test_outer, y_test_outer, binary_cross_entropy_loss
        )
        outer_scores.append(test_metrics["f1"])

        logger.info(
            "Outer fold %d: test_f1=%.4f (best_params=%s)",
            outer_idx + 1,
            test_metrics["f1"],
            best_params,
        )

    mean_score = float(np.mean(outer_scores))
    std_score = float(np.std(outer_scores))

    logger.info(
        "Nested CV complete: mean_f1=%.4f ± %.4f (n=%d folds)",
        mean_score,
        std_score,
        outer_folds,
    )

    return {
        "outer_scores": outer_scores,
        "mean_score": mean_score,
        "std_score": std_score,
        "best_params_per_fold": best_params_per_fold,
    }
