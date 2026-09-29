"""
BERT Training Environment Check Script.

Verifies:
- transformers library availability
- torch availability
- bert-base-chinese model accessibility
- GPU/CPU availability
- Required dependencies

Usage:
    python scripts/check_bert_environment.py

Output:
    - Environment check report
    - Recommendations for setup
"""

from __future__ import annotations

import logging
import sys

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def check_transformers() -> bool:
    """Check if transformers library is available."""
    try:
        import transformers

        logger.info("✅ transformers: %s", transformers.__version__)
        return True
    except ImportError:
        logger.error("❌ transformers not installed")
        logger.info("   Install: pip install transformers>=4.36.2")
        return False


def check_torch() -> bool:
    """Check if torch is available."""
    try:
        import torch

        logger.info("✅ torch: %s", torch.__version__)
        logger.info("   CUDA available: %s", torch.cuda.is_available())
        if torch.cuda.is_available():
            logger.info("   CUDA devices: %d", torch.cuda.device_count())
            logger.info("   Current device: %s", torch.cuda.get_device_name(0))
        return True
    except ImportError:
        logger.error("❌ torch not installed")
        logger.info("   Install: pip install torch>=2.2.0")
        return False


def check_bert_model() -> bool:
    """Check if BERT model can be loaded."""
    try:
        from transformers import BertModel, BertTokenizer

        logger.info("Loading bert-base-chinese...")
        tokenizer = BertTokenizer.from_pretrained("bert-base-chinese")
        model = BertModel.from_pretrained("bert-base-chinese")

        logger.info("✅ bert-base-chinese loaded successfully")
        logger.info("   Vocab size: %d", tokenizer.vocab_size)
        logger.info("   Hidden size: %d", model.config.hidden_size)
        logger.info("   Num layers: %d", model.config.num_hidden_layers)
        return True
    except Exception as exc:
        logger.error("❌ Failed to load bert-base-chinese: %s", exc)
        logger.info("   This requires internet connection for first download")
        return False


def check_datasets() -> bool:
    """Check if datasets library is available."""
    try:
        import datasets

        logger.info("✅ datasets: %s", datasets.__version__)
        return True
    except ImportError:
        logger.warning("⚠️ datasets not installed (optional)")
        logger.info("   Install: pip install datasets")
        return False


def check_sklearn() -> bool:
    """Check if scikit-learn is available."""
    try:
        import sklearn

        logger.info("✅ scikit-learn: %s", sklearn.__version__)
        return True
    except ImportError:
        logger.error("❌ scikit-learn not installed")
        return False


def main() -> None:
    """Main environment check."""
    logger.info("=" * 50)
    logger.info("BERT Training Environment Check")
    logger.info("=" * 50)

    checks = {
        "torch": check_torch(),
        "transformers": check_transformers(),
        "bert-base-chinese": check_bert_model(),
        "datasets": check_datasets(),
        "scikit-learn": check_sklearn(),
    }

    logger.info("=" * 50)
    logger.info("Check Summary")
    logger.info("=" * 50)

    passed = sum(checks.values())
    total = len(checks)

    for name, result in checks.items():
        status = "✅ PASS" if result else "❌ FAIL"
        logger.info("%s: %s", name, status)

    logger.info("-" * 50)
    logger.info("Result: %d/%d checks passed", passed, total)

    if passed == total:
        logger.info("🎉 All checks passed! Ready for BERT training.")
        sys.exit(0)
    else:
        logger.warning("⚠️ Some checks failed. Please install missing dependencies.")
        sys.exit(1)


if __name__ == "__main__":
    main()
