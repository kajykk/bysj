"""
PyTorch Lightweight MLP for Physiological Depression Prediction.

Architecture: Input(13) -> 32 -> 16 -> Output(1)
- Parameter count: < 5,000 (for < 5,000 samples dataset)
- Regularization: Dropout(0.4) + BatchNorm + L2(weight_decay=1e-3)
- Training: Early stopping (patience=10) + ReduceLROnPlateau
- Gradient clipping: max_norm=1.0

- Learning rate scheduler: ReduceLROnPlateau
"""

from __future__ import annotations

import json
import logging
from pathlib import Path

import numpy as np

try:
    import torch
    import torch.nn as nn
    import torch.optim as optim
    from torch.utils.data import DataLoader, TensorDataset
    TORCH_AVAILABLE = True
except ImportError:
    TORCH_AVAILABLE = False
    # Create dummy classes for type checking
    class nn:  # type: ignore
        class Module:
            pass
        class Linear:
            pass
        class BatchNorm1d:
            pass
        class Dropout:
            pass
        class ReLU:
            pass
        class Sigmoid:
            pass
    class torch:  # type: ignore
        pass

logger = logging.getLogger(__name__)


class PyTorchMLP(nn.Module if TORCH_AVAILABLE else object):
    """Lightweight PyTorch MLP for physiological depression prediction.

    Architecture: Input(13) -> 32 -> 16 -> Output(1)
    Total parameters: ~1,000 (well under 5,000 limit)

    Args:
        input_dim: Number of input features (default: 13).
        hidden_dims: List of hidden layer dimensions (default: [32, 16]).
        dropout_rate: Dropout probability (default: 0.4).
        use_batch_norm: Whether to use batch normalization (default: True).
    """

    def __init__(
        self,
        input_dim: int = 13,
        hidden_dims: list[int] | None = None,
        dropout_rate: float = 0.4,
        use_batch_norm: bool = True,
    ):
        """Initialize PyTorch MLP model."""
        if not TORCH_AVAILABLE:
            raise ImportError("PyTorch not installed. Install with: pip install torch")

        super().__init__()

        if hidden_dims is None:
            hidden_dims = [32, 16]

        self.input_dim = input_dim
        self.hidden_dims = hidden_dims
        self.dropout_rate = dropout_rate
        self.use_batch_norm = use_batch_norm

        # Build network architecture
        layers = []
        dims = [input_dim] + hidden_dims + [1]

        for i in range(len(dims) - 1):
            # Linear layer
            layers.append((f"linear_{i}", nn.Linear(dims[i], dims[i + 1])))

            # BatchNorm (except last layer)
            if use_batch_norm and i < len(dims) - 2:
                layers.append((f"bn_{i}", nn.BatchNorm1d(dims[i + 1])))

            # Activation and Dropout (except last layer)
            if i < len(dims) - 2:
                layers.append((f"relu_{i}", nn.ReLU()))
                layers.append((f"dropout_{i}", nn.Dropout(dropout_rate)))
            else:
                # Output layer: Sigmoid
                layers.append(("sigmoid", nn.Sigmoid()))

        self.network = nn.Sequential()
        for name, layer in layers:
            self.network.add_module(name, layer)

        # Initialize weights with He (Kaiming) initialization
        self._init_weights()

        # Count parameters
        self._param_count = sum(p.numel() for p in self.parameters())
        logger.info(
            "Created PyTorchMLP: %d layers, %d parameters",
            len(hidden_dims) + 1,
            self._param_count,
        )

    def _init_weights(self) -> None:
        """Initialize weights with He (Kaiming) initialization."""
        for name, module in self.named_modules():
            if isinstance(module, nn.Linear):
                nn.init.kaiming_normal_(module.weight, mode="fan_in", nonlinearity="relu")
                if module.bias is not None:
                    nn.init.zeros_(module.bias)

    def forward(self, x: torch.Tensor) -> torch.Tensor:
        """Forward pass through the network.

        Args:
            x: Input features (batch_size, input_dim).

        Returns:
            Predicted probabilities (batch_size, 1).
        """
        return self.network(x)

    def predict_proba(self, X: np.ndarray) -> np.ndarray:
        """Predict probabilities.

        Args:
            X: Input features as numpy array.

        Returns:
            Predicted probabilities as numpy array.
        """
        self.eval()
        with torch.no_grad():
            # M26: handle model on GPU/non-default device
            device = next(self.parameters()).device
            X_tensor = torch.FloatTensor(X).to(device)
            output = self.forward(X_tensor)
            return output.cpu().numpy()

    def predict(self, X: np.ndarray, threshold: float = 0.5) -> np.ndarray:
        """Predict class labels.

        Args:
            X: Input features.
            threshold: Classification threshold.

        Returns:
            Predicted labels (0 or 1) with shape (n_samples,).
        """
        proba = self.predict_proba(X)
        return (proba >= threshold).astype(np.int32).flatten()

    def count_parameters(self) -> int:
        """Count total number of parameters."""
        return self._param_count

    def save(self, path: Path | str) -> None:
        """Save model to file.

        Args:
            path: Path to save the model.
        """
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)

        # Save model state dict
        torch.save({
            "state_dict": self.state_dict(),
            "input_dim": self.input_dim,
            "hidden_dims": self.hidden_dims,
            "dropout_rate": self.dropout_rate,
            "use_batch_norm": self.use_batch_norm,
            "param_count": self._param_count,
        }, path)

        logger.info("Saved PyTorch model to %s (%d parameters)", path, self._param_count)

    @classmethod
    def load(cls, path: Path | str, trusted_root: Path | str | None = "default") -> "PyTorchMLP":
        """Load model from file.

        Args:
            path: Path to the saved model.
            trusted_root: 受信根目录，用于路径白名单校验。
                ``"default"`` (默认): 使用项目 models 目录作为受信根。
                ``None``: 跳过路径校验（仅用于单元测试，生产代码应使用默认值）。
                其他值: 使用指定目录作为受信根。

        Returns:
            Loaded PyTorchMLP model.
        """
        if not TORCH_AVAILABLE:
            raise ImportError("PyTorch not installed")

        # ML-006 修复：使用安全加载器（路径校验 + 大小校验 + 审计日志）
        # 检查点包含模型架构元信息（input_dim/hidden_dims 等），需 weights_only=False，
        # 通过 safe_torch_load 的路径白名单提供补偿防护（trusted_root 限制可加载目录）。
        from app.core.safe_pickle import safe_torch_load

        # 受信根目录：默认为项目 models 目录，防止路径穿越加载任意位置文件
        if trusted_root == "default":
            _trusted_root: Path | None = Path(__file__).resolve().parent.parent.parent.parent / "models"
        else:
            _trusted_root = Path(trusted_root) if trusted_root else None

        checkpoint = safe_torch_load(
            path,
            weights_only=False,
            trusted_root=_trusted_root,
            model_id=f"pytorch_mlp/{Path(path).name}",
        )

        model = cls(
            input_dim=checkpoint["input_dim"],
            hidden_dims=checkpoint["hidden_dims"],
            dropout_rate=checkpoint["dropout_rate"],
            use_batch_norm=checkpoint["use_batch_norm"],
        )
        model.load_state_dict(checkpoint["state_dict"])

        logger.info("Loaded PyTorch model from %s", path)
        return model


def train_pytorch_mlp(
    model: PyTorchMLP,
    X_train: np.ndarray,
    y_train: np.ndarray,
    X_val: np.ndarray,
    y_val: np.ndarray,
    epochs: int = 100,
    batch_size: int = 32,
    learning_rate: float = 0.001,
    weight_decay: float = 1e-3,
    patience: int = 10,
    device: str = "cpu",
    random_state: int = 42,
) -> dict:
    """Train PyTorch MLP model with early stopping and learning rate scheduling.

    Args:
        model: PyTorchMLP model.
        X_train: Training features.
        y_train: Training labels.
        X_val: Validation features.
        y_val: Validation labels.
        epochs: Maximum number of epochs.
        batch_size: Batch size.
        learning_rate: Learning rate.
        weight_decay: L2 regularization strength.
        patience: Early stopping patience.
        device: Device to train on (cpu or cuda).
        random_state: Random seed for reproducibility (权重初始化/Dropout/DataLoader shuffle).

    Returns:
        Training history dictionary.
    """
    if not TORCH_AVAILABLE:
        raise ImportError("PyTorch not installed")

    # 可复现性：设置 PyTorch 全局随机种子（控制权重初始化、Dropout、DataLoader shuffle）
    torch.manual_seed(random_state)
    if torch.cuda.is_available():
        torch.cuda.manual_seed_all(random_state)
    np.random.seed(random_state)

    # Move model to device
    model = model.to(device)

    # Create data loaders（使用受控 generator 确保 shuffle 可复现）
    _generator = torch.Generator()
    _generator.manual_seed(random_state)
    train_dataset = TensorDataset(
        torch.FloatTensor(X_train),
        torch.FloatTensor(y_train).reshape(-1, 1),
    )
    train_loader = DataLoader(
        train_dataset, batch_size=batch_size, shuffle=True, generator=_generator
    )

    val_dataset = TensorDataset(
        torch.FloatTensor(X_val),
        torch.FloatTensor(y_val).reshape(-1, 1),
    )
    val_loader = DataLoader(val_dataset, batch_size=batch_size, shuffle=False)

    # Loss function and optimizer
    criterion = nn.BCELoss()
    optimizer = optim.Adam(model.parameters(), lr=learning_rate, weight_decay=weight_decay)

    # Learning rate scheduler
    scheduler = optim.lr_scheduler.ReduceLROnPlateau(
        optimizer, mode="max", factor=0.5, patience=patience // 2
    )

    # Early stopping
    best_val_f1 = 0.0
    best_epoch = 0
    patience_counter = 0
    best_state_dict = None

    history = {
        "train_loss": [],
        "val_loss": [],
        "train_f1": [],
        "val_f1": [],
        "best_epoch": 0,
        "best_val_f1": 0.0,
        "learning_rates": [],
    }

    logger.info("Starting PyTorch training: epochs=%d, lr=%.4f, wd=%.4f", epochs, learning_rate, weight_decay)

    for epoch in range(epochs):
        # Training phase
        model.train()
        train_loss = 0.0
        train_preds = []
        train_true = []

        for X_batch, y_batch in train_loader:
            X_batch, y_batch = X_batch.to(device), y_batch.to(device)

            optimizer.zero_grad()
            outputs = model(X_batch)
            loss = criterion(outputs, y_batch)
            loss.backward()

            # Gradient clipping (max_norm=1.0)
            torch.nn.utils.clip_grad_norm_(model.parameters(), max_norm=1.0)

            optimizer.step()

            train_loss += loss.item() * len(X_batch)
            train_preds.extend(outputs.detach().cpu().numpy())
            train_true.extend(y_batch.detach().cpu().numpy())

        train_loss /= len(train_dataset)
        train_f1 = _compute_f1(np.array(train_true), np.array(train_preds))

        # Validation phase
        model.eval()
        val_loss = 0.0
        val_preds = []
        val_true = []

        with torch.no_grad():
            for X_batch, y_batch in val_loader:
                X_batch, y_batch = X_batch.to(device), y_batch.to(device)
                outputs = model(X_batch)
                loss = criterion(outputs, y_batch)

                val_loss += loss.item() * len(X_batch)
                val_preds.extend(outputs.cpu().numpy())
                val_true.extend(y_batch.cpu().numpy())

        val_loss /= len(val_dataset)
        val_f1 = _compute_f1(np.array(val_true), np.array(val_preds))

        # Record history
        history["train_loss"].append(train_loss)
        history["val_loss"].append(val_loss)
        history["train_f1"].append(train_f1)
        history["val_f1"].append(val_f1)
        history["learning_rates"].append(optimizer.param_groups[0]["lr"])

        # Learning rate scheduling
        scheduler.step(val_f1)

        # Early stopping
        if val_f1 > best_val_f1:
            best_val_f1 = val_f1
            best_epoch = epoch
            patience_counter = 0
            best_state_dict = model.state_dict().copy()
        else:
            patience_counter += 1

        # Log progress
        if epoch % 10 == 0 or epoch < 5:
            logger.info(
                "Epoch %d: train_loss=%.4f, val_loss=%.4f, train_f1=%.4f, val_f1=%.4f, lr=%.6f",
                epoch,
                train_loss,
                val_loss,
                train_f1,
                val_f1,
                optimizer.param_groups[0]["lr"],
            )

        if patience_counter >= patience:
            logger.info("Early stopping triggered at epoch %d", epoch)
            break

    # Restore best weights
    if best_state_dict is not None:
        model.load_state_dict(best_state_dict)
        logger.info("Restored best model weights (epoch=%d, val_f1=%.4f)", best_epoch, best_val_f1)

    history["best_epoch"] = best_epoch
    history["best_val_f1"] = best_val_f1

    logger.info(
        "Training complete: best_epoch=%d, best_val_f1=%.4f",
        best_epoch,
        best_val_f1,
    )

    return history


def _compute_f1(y_true: np.ndarray, y_pred_proba: np.ndarray, threshold: float = 0.5) -> float:
    """Compute F1 score.

    Args:
        y_true: True labels.
        y_pred_proba: Predicted probabilities.
        threshold: Classification threshold.

    Returns:
        F1 score.
    """
    y_pred = (y_pred_proba >= threshold).astype(int)
    y_true = y_true.flatten().astype(int)
    y_pred = y_pred.flatten()

    tp = np.sum((y_true == 1) & (y_pred == 1))
    fp = np.sum((y_true == 0) & (y_pred == 1))
    fn = np.sum((y_true == 1) & (y_pred == 0))

    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0

    return float(f1)


def evaluate_pytorch_mlp(
    model: PyTorchMLP,
    X: np.ndarray,
    y: np.ndarray,
    device: str = "cpu",
) -> dict:
    """Evaluate PyTorch MLP model.

    Args:
        model: Trained PyTorchMLP model.
        X: Features.
        y: Labels.
        device: Device to evaluate on.

    Returns:
        Dictionary with metrics.
    """
    if not TORCH_AVAILABLE:
        raise ImportError("PyTorch not installed")

    model = model.to(device)
    model.eval()

    with torch.no_grad():
        X_tensor = torch.FloatTensor(X).to(device)
        y_tensor = torch.FloatTensor(y).reshape(-1, 1).to(device)

        outputs = model(X_tensor)

        # Compute loss
        criterion = nn.BCELoss()
        loss = criterion(outputs, y_tensor).item()

    # Compute metrics using numpy
    y_pred_proba = outputs.cpu().numpy()
    from app.ml.trainer import compute_metrics

    metrics = compute_metrics(y.reshape(-1, 1), y_pred_proba)
    metrics["loss"] = loss
    metrics["n_samples"] = len(y)

    return metrics
