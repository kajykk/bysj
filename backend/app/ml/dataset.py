from __future__ import annotations

import logging

import numpy as np

logger = logging.getLogger(__name__)


class PhysiologicalDataset:
    """Simple Dataset for physiological depression prediction (numpy-based).

    Avoids PyTorch dependency issues. Can be easily converted to PyTorch Dataset
    when PyTorch is available.

    Args:
        X: Feature matrix (n_samples, n_features).
        y: Target vector (n_samples,).
    """

    def __init__(self, X: np.ndarray, y: np.ndarray):
        """Initialize dataset.

        Args:
            X: Feature matrix.
            y: Target vector.
        """
        if len(X) != len(y):
            raise ValueError(f"X and y must have same length: {len(X)} != {len(y)}")

        self.X = X.astype(np.float32)
        self.y = y.astype(np.float32)
        self.n_samples = len(X)
        self.n_features = X.shape[1]

        logger.info(
            "Created PhysiologicalDataset: %d samples, %d features",
            self.n_samples,
            self.n_features,
        )

    def __len__(self) -> int:
        """Return dataset size."""
        return self.n_samples

    def __getitem__(self, idx: int) -> tuple[np.ndarray, np.ndarray]:
        """Get sample by index.

        Args:
            idx: Sample index.

        Returns:
            Tuple of (features, label).
        """
        return self.X[idx], self.y[idx]

    def get_class_distribution(self) -> dict[int, int]:
        """Get class distribution.

        Returns:
            Dictionary mapping class labels to counts.
        """
        unique, counts = np.unique(self.y, return_counts=True)
        return {int(u): int(c) for u, c in zip(unique, counts)}

    def get_batch(self, indices: list[int]) -> tuple[np.ndarray, np.ndarray]:
        """Get a batch of samples.

        Args:
            indices: List of sample indices.

        Returns:
            Tuple of (X_batch, y_batch).
        """
        return self.X[indices], self.y[indices]


class SimpleDataLoader:
    """Simple DataLoader implementation (numpy-based).

    Avoids PyTorch dependency issues.
    """

    def __init__(
        self,
        dataset: PhysiologicalDataset,
        batch_size: int = 32,
        shuffle: bool = True,
        random_state: int = 42,
    ):
        """Initialize DataLoader.

        Args:
            dataset: PhysiologicalDataset instance.
            batch_size: Batch size.
            shuffle: Whether to shuffle data.
            random_state: Random seed.
        """
        self.dataset = dataset
        self.batch_size = batch_size
        self.shuffle = shuffle
        self.rng = np.random.RandomState(random_state)
        self.indices = np.arange(len(dataset))

        if shuffle:
            self.rng.shuffle(self.indices)

    def __len__(self) -> int:
        """Return number of batches."""
        return (len(self.dataset) + self.batch_size - 1) // self.batch_size

    def __iter__(self):
        """Iterate over batches."""
        if self.shuffle:
            self.rng.shuffle(self.indices)

        for i in range(0, len(self.dataset), self.batch_size):
            batch_indices = self.indices[i : i + self.batch_size]
            yield self.dataset.get_batch(batch_indices.tolist())


def create_dataloaders(
    X_train: np.ndarray,
    X_val: np.ndarray,
    X_test: np.ndarray,
    y_train: np.ndarray,
    y_val: np.ndarray,
    y_test: np.ndarray,
    batch_size: int = 32,
) -> tuple[SimpleDataLoader, SimpleDataLoader, SimpleDataLoader]:
    """Create DataLoaders for train/val/test sets.

    Args:
        X_train, X_val, X_test: Feature matrices.
        y_train, y_val, y_test: Target vectors.
        batch_size: Batch size for DataLoaders.

    Returns:
        Tuple of (train_loader, val_loader, test_loader).
    """
    train_dataset = PhysiologicalDataset(X_train, y_train)
    val_dataset = PhysiologicalDataset(X_val, y_val)
    test_dataset = PhysiologicalDataset(X_test, y_test)

    train_loader = SimpleDataLoader(train_dataset, batch_size=batch_size, shuffle=True)
    val_loader = SimpleDataLoader(val_dataset, batch_size=batch_size, shuffle=False)
    test_loader = SimpleDataLoader(test_dataset, batch_size=batch_size, shuffle=False)

    logger.info(
        "Created DataLoaders: train=%d batches, val=%d batches, test=%d batches",
        len(train_loader),
        len(val_loader),
        len(test_loader),
    )

    return train_loader, val_loader, test_loader
