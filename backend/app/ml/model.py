from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

logger = logging.getLogger(__name__)


def relu(x: np.ndarray) -> np.ndarray:
    """ReLU activation function."""
    return np.maximum(0, x)


def relu_derivative(x: np.ndarray) -> np.ndarray:
    """Derivative of ReLU."""
    return (x > 0).astype(np.float32)


def sigmoid(x: np.ndarray) -> np.ndarray:
    """Sigmoid activation function."""
    return 1 / (1 + np.exp(-np.clip(x, -500, 500)))


def he_init(
    shape: tuple[int, ...], rng: np.random.RandomState | None = None
) -> np.ndarray:
    """He (Kaiming) initialization for ReLU activations.

    Args:
        shape: Shape of the array to initialize.
        rng: Optional NumPy RandomState for reproducibility. If None, uses
            the global np.random (not reproducible).
    """
    fan_in = shape[0] if len(shape) == 2 else np.prod(shape[1:])
    std = np.sqrt(2.0 / fan_in)
    sampler = rng if rng is not None else np.random
    return sampler.randn(*shape).astype(np.float32) * std


class PhysiologicalMLP:
    """Lightweight MLP for physiological depression prediction.

    Pure numpy implementation to avoid PyTorch dependency issues.

    Args:
        input_dim: Number of input features.
        hidden_dims: List of hidden layer dimensions.
        dropout_rate: Dropout probability.
        use_batch_norm: Whether to use batch normalization.
        random_state: Random seed for reproducible weight init and dropout.
    """

    def __init__(
        self,
        input_dim: int = 13,
        hidden_dims: list[int] | None = None,
        dropout_rate: float = 0.4,
        use_batch_norm: bool = True,
        random_state: int | None = 42,
    ):
        """Initialize MLP model."""
        if hidden_dims is None:
            hidden_dims = [64, 32, 16]

        self.input_dim = input_dim
        self.hidden_dims = hidden_dims
        self.dropout_rate = dropout_rate
        self.use_batch_norm = use_batch_norm
        # Reproducible RNG for weight init and dropout (M25)
        self.rng = np.random.RandomState(random_state)

        # Build network architecture
        self.layers: list[dict] = []
        dims = [input_dim] + hidden_dims + [1]

        for i in range(len(dims) - 1):
            layer = {
                "W": he_init((dims[i], dims[i + 1]), rng=self.rng),
                "b": np.zeros(dims[i + 1], dtype=np.float32),
            }

            if use_batch_norm and i < len(dims) - 2:  # No BN on output layer
                layer["bn_gamma"] = np.ones(dims[i + 1], dtype=np.float32)
                layer["bn_beta"] = np.zeros(dims[i + 1], dtype=np.float32)
                layer["bn_running_mean"] = np.zeros(dims[i + 1], dtype=np.float32)
                layer["bn_running_var"] = np.ones(dims[i + 1], dtype=np.float32)

            self.layers.append(layer)

        self.training = True
        self._param_count = self.count_parameters()
        logger.info(
            "Created PhysiologicalMLP: %d layers, %d parameters",
            len(self.layers),
            self._param_count,
        )

    def count_parameters(self) -> int:
        """Count total number of parameters."""
        count = 0
        for layer in self.layers:
            count += layer["W"].size
            count += layer["b"].size
            if "bn_gamma" in layer:
                count += layer["bn_gamma"].size
                count += layer["bn_beta"].size
        return count

    def _batch_norm_forward(
        self, x: np.ndarray, layer: dict, training: bool
    ) -> tuple[np.ndarray, dict]:
        """Batch normalization forward pass."""
        if training:
            mean = np.mean(x, axis=0)
            var = np.var(x, axis=0)
            # Update running statistics
            momentum = 0.1
            layer["bn_running_mean"] = (1 - momentum) * layer[
                "bn_running_mean"
            ] + momentum * mean
            layer["bn_running_var"] = (1 - momentum) * layer[
                "bn_running_var"
            ] + momentum * var
        else:
            mean = layer["bn_running_mean"]
            var = layer["bn_running_var"]

        eps = 1e-5
        x_norm = (x - mean) / np.sqrt(var + eps)
        out = layer["bn_gamma"] * x_norm + layer["bn_beta"]
        cache = {"x": x, "mean": mean, "var": var, "x_norm": x_norm}
        return out, cache

    def _dropout_forward(
        self, x: np.ndarray, rate: float, training: bool = True
    ) -> tuple[np.ndarray, np.ndarray]:
        """Dropout forward pass.

        C-ML-1 修复：原实现检查 self.training 实例属性而非局部 training 参数。
        当 trainer.py 的 evaluate() 设置 model.training = False 后，
        另一线程的 train_epoch 调用 forward(training=True) 进入本方法时，
        self.training 已被改为 False，导致 Dropout 被静默跳过，
        模型在无正则化下训练。
        """
        if not training or rate == 0:
            return x, np.ones_like(x)
        mask = (self.rng.rand(*x.shape) > rate).astype(np.float32)
        return x * mask / (1 - rate), mask

    def forward(
        self, X: np.ndarray, training: bool | None = None
    ) -> tuple[np.ndarray, list[dict]]:
        """Forward pass through the network.

        Args:
            X: Input features (batch_size, input_dim).
            training: M-3 修复：显式传入 training 状态，避免修改实例状态导致多线程竞态。
                None 时回退到 self.training（向后兼容）。

        Returns:
            Tuple of (output, caches).
        """
        # M-3 修复：使用局部变量避免多线程并发修改 self.training 导致 BatchNorm/Dropout 行为异常
        if training is None:
            training = self.training
        caches = []
        current = X

        for i, layer in enumerate(self.layers):
            # Linear
            z = current @ layer["W"] + layer["b"]
            cache = {"x": current, "z": z}

            # BatchNorm (except last layer)
            if self.use_batch_norm and "bn_gamma" in layer:
                z, bn_cache = self._batch_norm_forward(z, layer, training)
                cache["bn"] = bn_cache
                cache["z"] = z  # Update to post-BatchNorm z (actual ReLU input)

            # Activation
            if i < len(self.layers) - 1:  # Hidden layers
                a = relu(z)
                # Dropout with decreasing rate
                drop_rate = self.dropout_rate * (1.0 - 0.2 * i)
                # M-3 修复：允许 dropout_rate=0 生效（原 max(0.1, ...) 强制最小 0.1）
                drop_rate = max(0.0, drop_rate)
                # 推理阶段不应用 dropout
                if not training or drop_rate == 0:
                    a, mask = a, np.ones_like(a)
                else:
                    # C-ML-1 修复：传入局部 training 参数，避免 _dropout_forward 回退到 self.training
                    a, mask = self._dropout_forward(a, drop_rate, training=training)
                cache["dropout_mask"] = mask
                cache["dropout_rate"] = drop_rate
            else:  # Output layer
                a = sigmoid(z)

            cache["a"] = a
            caches.append(cache)
            current = a

        return current, caches

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict probabilities.

        Args:
            X: Input features.

        Returns:
            Predicted probabilities.
        """
        # M-3 修复：通过参数传入 training=False，避免修改实例状态（线程安全）
        output, _ = self.forward(X, training=False)
        return output

    def predict(self, X: np.ndarray, threshold: float = 0.5) -> np.ndarray:
        """Predict class labels.

        Args:
            X: Input features.
            threshold: Classification threshold.

        Returns:
            Predicted labels (0 or 1).
        """
        proba = self.predict_proba(X)
        return (proba >= threshold).astype(np.int32)

    def save(self, path: Path | str) -> None:
        """Save model to JSON file.

        Args:
            path: Path to save the model.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        layers_data = []
        for layer in self.layers:
            layer_data = {
                "W": layer["W"].tolist(),
                "b": layer["b"].tolist(),
            }
            if "bn_gamma" in layer:
                layer_data["bn_gamma"] = layer["bn_gamma"].tolist()
                layer_data["bn_beta"] = layer["bn_beta"].tolist()
                layer_data["bn_running_mean"] = layer["bn_running_mean"].tolist()
                layer_data["bn_running_var"] = layer["bn_running_var"].tolist()
            layers_data.append(layer_data)

        model_data = {
            "input_dim": self.input_dim,
            "hidden_dims": self.hidden_dims,
            "dropout_rate": self.dropout_rate,
            "use_batch_norm": self.use_batch_norm,
            "layers": layers_data,
            "param_count": self._param_count,
        }

        with open(path, "w", encoding="utf-8") as f:
            json.dump(model_data, f, ensure_ascii=False, indent=2)

        # C-ML-2 修复：生成 .sha256 侧车校验文件，与 load_model 的 require_checksum=True 对齐
        # 治理循环依赖：改从 app.utils.checksum 导入，避免反向依赖 model_loader 形成环。
        from app.utils.checksum import write_sha256_sidecar

        write_sha256_sidecar(path)

        logger.info("Saved model to %s (%d parameters)", path, self._param_count)

    @classmethod
    def load(cls, path: Path | str) -> "PhysiologicalMLP":
        """Load model from JSON file.

        Args:
            path: Path to the saved model.

        Returns:
            Loaded PhysiologicalMLP model.
        """
        path = Path(path)
        with open(path, "r", encoding="utf-8") as f:
            model_data = json.load(f)

        model = cls(
            input_dim=model_data["input_dim"],
            hidden_dims=model_data["hidden_dims"],
            dropout_rate=model_data["dropout_rate"],
            use_batch_norm=model_data.get("use_batch_norm", False),
        )

        for i, layer_data in enumerate(model_data["layers"]):
            model.layers[i]["W"] = np.array(layer_data["W"], dtype=np.float32)
            model.layers[i]["b"] = np.array(layer_data["b"], dtype=np.float32)
            if "bn_gamma" in layer_data:
                model.layers[i]["bn_gamma"] = np.array(
                    layer_data["bn_gamma"], dtype=np.float32
                )
                model.layers[i]["bn_beta"] = np.array(
                    layer_data["bn_beta"], dtype=np.float32
                )
                model.layers[i]["bn_running_mean"] = np.array(
                    layer_data["bn_running_mean"], dtype=np.float32
                )
                model.layers[i]["bn_running_var"] = np.array(
                    layer_data["bn_running_var"], dtype=np.float32
                )

        logger.info("Loaded model from %s", path)
        return model
