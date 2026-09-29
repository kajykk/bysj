"""M2 BERT 推理链路验证 (阶段三).

验证:
1. model_engine 能正确加载 M2 BERT 部署产物 (config.json + classifier.pkl + scaler.pkl)
2. feature_extraction 模式推理正确
3. 三条测试文本 (正常 / 抑郁 / 危机) 推理结果符合预期

Usage:
    python scripts/verify_m2_bert_inference.py
"""

from __future__ import annotations

import asyncio
import logging
import os
import sys
from pathlib import Path

# 设置环境变量 (避免 transformers 联网)
os.environ["TRANSFORMERS_OFFLINE"] = "1"
os.environ["HF_HUB_OFFLINE"] = "1"

# 添加 backend 到 path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT / "backend"))

logging.basicConfig(level=logging.INFO, format="%(asctime)s [Verify] %(message)s")
logger = logging.getLogger("Verify")


async def verify_inference() -> None:
    """验证 M2 BERT 推理链路."""
    logger.info("=" * 60)
    logger.info("M2 BERT 推理链路验证 (阶段三)")
    logger.info("=" * 60)

    # 1. 验证部署产物存在
    deploy_dir = PROJECT_ROOT / "models" / "text" / "bert_text_classifier"
    required_files = ["config.json", "classifier.pkl", "scaler.pkl", "metadata.json"]
    for f in required_files:
        path = deploy_dir / f
        if not path.exists():
            logger.error("❌ 缺失文件: %s", path)
            sys.exit(1)
        logger.info("✅ %s 存在 (%d bytes)", f, path.stat().st_size)

    # 2. 加载 model_engine
    logger.info("--- 加载 ModelEngine ---")
    from app.core.model_engine import model_engine

    # 3. 验证 M2 BERT 模型加载
    logger.info("--- 加载 text_bert_classifier 模型 ---")
    try:
        bundle = await model_engine._load_model_async("text_bert_classifier")
        logger.info("✅ 模型加载成功")
        logger.info("  mode=%s", bundle.get("mode"))
        logger.info("  threshold=%.4f", bundle.get("threshold", 0))
        logger.info("  max_seq_len=%d", bundle.get("max_seq_len", 256))
        logger.info("  bert_model=%s", type(bundle.get("bert_model")).__name__)
        logger.info("  classifier=%s", type(bundle.get("classifier")).__name__)
        logger.info("  scaler=%s", type(bundle.get("scaler")).__name__)
    except Exception as e:
        logger.error("❌ 模型加载失败: %s", str(e)[:200])
        sys.exit(1)

    # 4. 测试推理
    test_cases = [
        {
            "text": "今天天气真好,和朋友一起出去玩,心情很愉快。",
            "desc": "正常文本",
            "expect_pred": 0,
        },
        {
            "text": "最近总是失眠,什么都提不起兴趣,觉得活着没意思,想一个人呆着。",
            "desc": "抑郁文本",
            "expect_pred": 1,
        },
        {
            "text": "我撑不下去了,想结束这一切,每天都很痛苦。",
            "desc": "危机文本",
            "expect_pred": 1,
        },
    ]

    logger.info("--- 推理测试 ---")
    all_pass = True
    for i, case in enumerate(test_cases):
        try:
            result = await model_engine._predict_text_bert_single(case["text"])
            if result is None:
                logger.error("❌ [%d] %s: 返回 None", i + 1, case["desc"])
                all_pass = False
                continue

            pred = result.get("prediction")
            prob = result.get("probability", 0)
            model_used = result.get("model_used")
            correct = "✅" if pred == case["expect_pred"] else "❌"
            logger.info(
                "%s [%d] %s: pred=%d (expect=%d) prob=%.4f model=%s",
                correct, i + 1, case["desc"], pred, case["expect_pred"],
                prob, model_used,
            )
            if pred != case["expect_pred"]:
                all_pass = False
        except Exception as e:
            logger.error("❌ [%d] %s: 推理异常 %s", i + 1, case["desc"], str(e)[:150])
            all_pass = False

    # 5. 测试完整 predict_text 流程 (含 fallback)
    logger.info("--- 完整 predict_text 流程测试 ---")
    try:
        result = await model_engine.predict_text(test_cases[1]["text"])
        logger.info(
            "✅ predict_text: pred=%s prob=%s model=%s sentiment=%s crisis=%s",
            result.get("prediction"),
            result.get("probability"),
            result.get("model_used"),
            result.get("sentiment_label"),
            result.get("crisis_detected"),
        )
    except Exception as e:
        logger.error("❌ predict_text 异常: %s", str(e)[:200])
        all_pass = False

    # 6. 结论
    logger.info("=" * 60)
    if all_pass:
        logger.info("✅ M2 BERT 推理链路验证通过")
        logger.info("  - 模型加载: text_bert_classifier (feature_extraction 模式)")
        logger.info("  - 三条测试文本推理正确")
        logger.info("  - 完整 predict_text 流程正常")
        logger.info("  - 阶段三前提满足: 可切换 TF-IDF → M2 BERT")
    else:
        logger.error("❌ 验证失败, 请检查上述错误")
    logger.info("=" * 60)


if __name__ == "__main__":
    asyncio.run(verify_inference())
