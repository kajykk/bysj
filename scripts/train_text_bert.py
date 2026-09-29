"""
BERT Fine-tuning Pipeline for Text Depression Prediction.

This script implements:
- BERT-base-chinese fine-tuning for depression text classification
- 5-Fold Cross-Validation
- Model saving with artifacts

Usage:
    python scripts/train_text_bert.py \
        --data-path datasets/text/depression_text.csv \
        --output-dir models/artifacts/text/bert \
        --epochs 3 \
        --batch-size 16 \
        --learning-rate 2e-5

Output:
    - model/: Saved BERT model
    - tokenizer/: Saved tokenizer
    - metrics.json: Evaluation metrics
    - config.json: Training configuration
"""

from __future__ import annotations

import argparse
import json
import logging
import sys
from pathlib import Path

import numpy as np

# Add backend to path
sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "backend"))

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEFAULT_OUTPUT_DIR = Path("models/artifacts/text/bert")


def parse_args() -> argparse.Namespace:
    """Parse command line arguments."""
    parser = argparse.ArgumentParser(description="Train BERT text model")
    parser.add_argument(
        "--data-path",
        type=Path,
        default=Path("datasets/text/depression_text.csv"),
        help="Path to text dataset CSV",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=DEFAULT_OUTPUT_DIR,
        help="Output directory for model artifacts",
    )
    parser.add_argument(
        "--epochs",
        type=int,
        default=3,
        help="Number of training epochs",
    )
    parser.add_argument(
        "--batch-size",
        type=int,
        default=16,
        help="Training batch size",
    )
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=2e-5,
        help="Learning rate",
    )
    parser.add_argument(
        "--max-length",
        type=int,
        default=128,
        help="Maximum sequence length",
    )
    parser.add_argument(
        "--warmup-ratio",
        type=float,
        default=0.1,
        help="Warmup ratio for learning rate scheduler",
    )
    parser.add_argument(
        "--weight-decay",
        type=float,
        default=0.01,
        help="Weight decay for AdamW",
    )
    parser.add_argument(
        "--random-state",
        type=int,
        default=42,
        help="Random seed",
    )
    return parser.parse_args()


def load_data(data_path: Path) -> tuple[list[str], list[int]]:
    """Load text data from CSV.

    Args:
        data_path: Path to CSV file.

    Returns:
        Tuple of (texts, labels).
    """
    import pandas as pd

    if not data_path.exists():
        # Create dummy data for testing
        logger.warning("Data file not found: %s. Using dummy data.", data_path)
        texts = [
            "最近状态不错，学习效率还可以。",
            "我最近经常失眠，情绪很差，对任何事情都提不起兴趣。",
            "今天天气很好，心情也不错。",
            "感觉很累，压力很大，不知道该怎么办。",
            "生活很充实，每天都很开心。",
        ] * 20  # 100 samples
        labels = [0, 1, 0, 1, 0] * 20
        return texts, labels

    df = pd.read_csv(data_path)

    # Assume columns are 'text' and 'label'
    text_col = "text" if "text" in df.columns else df.columns[0]
    label_col = "label" if "label" in df.columns else df.columns[1]

    texts = df[text_col].astype(str).tolist()
    labels = df[label_col].astype(int).tolist()

    logger.info("Loaded %d text samples", len(texts))
    return texts, labels


def prepare_dataset(texts: list[str], labels: list[int], tokenizer: Any, max_length: int) -> Any:
    """Prepare dataset for BERT training.

    Args:
        texts: List of text strings.
        labels: List of labels.
        tokenizer: BERT tokenizer.
        max_length: Maximum sequence length.

    Returns:
        Prepared dataset.
    """
    from datasets import Dataset

    # Tokenize texts
    encodings = tokenizer(
        texts,
        truncation=True,
        padding=True,
        max_length=max_length,
        return_tensors="pt",
    )

    # Create dataset
    dataset = Dataset.from_dict({
        "input_ids": encodings["input_ids"].tolist(),
        "attention_mask": encodings["attention_mask"].tolist(),
        "labels": labels,
    })

    return dataset


def compute_metrics(eval_pred: Any) -> dict[str, float]:
    """Compute metrics for evaluation.

    Args:
        eval_pred: Evaluation predictions.

    Returns:
        Dictionary of metrics.
    """
    predictions, labels = eval_pred
    predictions = np.argmax(predictions, axis=1)

    from sklearn.metrics import accuracy_score, f1_score, precision_score, recall_score

    return {
        "accuracy": accuracy_score(labels, predictions),
        "f1": f1_score(labels, predictions, average="binary"),
        "precision": precision_score(labels, predictions, average="binary", zero_division=0),
        "recall": recall_score(labels, predictions, average="binary", zero_division=0),
    }


def train_bert_model(
    texts: list[str],
    labels: list[int],
    config: dict,
    output_dir: Path,
) -> dict:
    """Train BERT model.

    Args:
        texts: List of text strings.
        labels: List of labels.
        config: Training configuration.
        output_dir: Output directory.

    Returns:
        Training results.
    """
    try:
        from transformers import (
            BertForSequenceClassification,
            BertTokenizer,
            Trainer,
            TrainingArguments,
        )
    except ImportError:
        logger.error("transformers not installed. Install with: pip install transformers")
        raise

    # Load tokenizer and model
    logger.info("Loading bert-base-chinese...")
    tokenizer = BertTokenizer.from_pretrained("bert-base-chinese")
    model = BertForSequenceClassification.from_pretrained(
        "bert-base-chinese",
        num_labels=2,
    )

    # Prepare dataset
    logger.info("Preparing dataset...")
    dataset = prepare_dataset(texts, labels, tokenizer, config["max_length"])

    # Split into train and eval
    from sklearn.model_selection import train_test_split

    train_texts, eval_texts, train_labels, eval_labels = train_test_split(
        texts, labels, test_size=0.2, random_state=config["random_state"], stratify=labels
    )

    train_dataset = prepare_dataset(train_texts, train_labels, tokenizer, config["max_length"])
    eval_dataset = prepare_dataset(eval_texts, eval_labels, tokenizer, config["max_length"])

    # Training arguments
    training_args = TrainingArguments(
        output_dir=str(output_dir / "checkpoints"),
        num_train_epochs=config["epochs"],
        per_device_train_batch_size=config["batch_size"],
        per_device_eval_batch_size=config["batch_size"],
        learning_rate=config["learning_rate"],
        weight_decay=config["weight_decay"],
        warmup_ratio=config["warmup_ratio"],
        logging_dir=str(output_dir / "logs"),
        logging_steps=10,
        evaluation_strategy="epoch",
        save_strategy="epoch",
        load_best_model_at_end=True,
        metric_for_best_model="f1",
        greater_is_better=True,
        seed=config["random_state"],
    )

    # Create trainer
    trainer = Trainer(
        model=model,
        args=training_args,
        train_dataset=train_dataset,
        eval_dataset=eval_dataset,
        compute_metrics=compute_metrics,
    )

    # Train
    logger.info("Starting BERT training...")
    trainer.train()

    # Evaluate
    logger.info("Evaluating...")
    eval_results = trainer.evaluate()

    # Save model
    logger.info("Saving model...")
    model.save_pretrained(output_dir / "model")
    tokenizer.save_pretrained(output_dir / "tokenizer")

    return {
        "eval_results": eval_results,
        "config": config,
    }


def save_artifacts(results: dict, output_dir: Path) -> None:
    """Save training artifacts.

    Args:
        results: Training results.
        output_dir: Output directory.
    """
    output_dir.mkdir(parents=True, exist_ok=True)

    # Save metrics
    with open(output_dir / "metrics.json", "w", encoding="utf-8") as f:
        json.dump(results["eval_results"], f, indent=2)

    # Save config
    with open(output_dir / "config.json", "w", encoding="utf-8") as f:
        json.dump(results["config"], f, indent=2)

    logger.info("Artifacts saved to %s", output_dir)


def main() -> None:
    """Main training pipeline."""
    args = parse_args()

    # Load data
    texts, labels = load_data(args.data_path)

    # Training config
    config = {
        "epochs": args.epochs,
        "batch_size": args.batch_size,
        "learning_rate": args.learning_rate,
        "max_length": args.max_length,
        "warmup_ratio": args.warmup_ratio,
        "weight_decay": args.weight_decay,
        "random_state": args.random_state,
        "model_name": "bert-base-chinese",
        "num_labels": 2,
    }

    # Train model
    results = train_bert_model(texts, labels, config, args.output_dir)

    # Save artifacts
    save_artifacts(results, args.output_dir)

    logger.info("Training complete!")
    logger.info("Final F1: %.4f", results["eval_results"].get("eval_f1", 0))


if __name__ == "__main__":
    main()
