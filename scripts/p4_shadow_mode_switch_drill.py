"""S3 P4 影子模式双跑切换演练 (端到端).

v2.0 计划 P4 要求: 文本新模型必须双跑对拍后才允许替换 TF-IDF fallback.
本脚本对真实生产 TF-IDF + M2 BERT 在中文语料上做端到端双跑, 产出切换决策报告.

演练内容:
    1. 加载生产 TF-IDF + LR (models/artifacts/text_depression_classifier/)
    2. 加载 M2 BERT 推理器 (models/artifacts/text_m2_bert/)
    3. 在中文语料 (chinese_depression_corpus_v1.csv) 分层抽样 N 条
    4. 双跑对拍: 同一文本 → 生产 TF-IDF 预测 + M2 BERT 预测
    5. 通过 ShadowModeService 记录一致率统计 (真实集成验证)
    6. 计算双模型 F1/AUC/Recall/Precision, 验证 M2 非回退
    7. 输出切换决策报告 (JSON + 控制台汇总)

切换决策门禁:
    G1: M2 F1 ≥ 0.75 (S2 目标)
    G2: M2 AUC ≥ 0.85 (S2 目标)
    G3: M2 F1 显著优于生产 TF-IDF (ΔF1 ≥ 0.30, 域外场景)
    G4: M2 高危召回 Recall ≥ 0.90 (G5 子目标)
    G5: ShadowModeService 一致率统计正确 (集成验证)
    G6: 双跑无崩溃 (异常安全)

Usage:
    python scripts/p4_shadow_mode_switch_drill.py
    python scripts/p4_shadow_mode_switch_drill.py --n-samples 500
"""

from __future__ import annotations

import argparse
import asyncio
import json
import logging
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from sklearn.metrics import (
    accuracy_score,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

# 添加 backend 到 path
BACKEND_ROOT = Path(__file__).resolve().parent.parent / "backend"
sys.path.insert(0, str(BACKEND_ROOT))

PROJECT_ROOT = Path(__file__).resolve().parent.parent
EXPERIMENTS_DIR = PROJECT_ROOT / "models" / "experiments"
# 使用 mmpsy (D3 域外集, 1275 条) 作为评估集 — M2 未在此数据上训练,
# 提供诚实的 out-of-sample 指标 (而非 chinese_depression_corpus 训练集的 in-sample F1=1.0)
DATA_PATH = PROJECT_ROOT / "data" / "external" / "mmpsy_scores.csv"

logging.basicConfig(level=logging.INFO, format="%(asctime)s [P4-DRILL] %(message)s")
logger = logging.getLogger("P4-DRILL")


def load_chinese_sample(n_samples: int, seed: int = 42) -> tuple[list[str], np.ndarray]:
    """分层抽样 mmpsy 中文语料 (D3 域外集, M2 未训练).

    mmpsy audio_transcript 字段为管道分隔的多段文本, 需合并为单条.
    """
    df = pd.read_csv(DATA_PATH)
    # 合并管道分隔的 audio_transcript
    if "text" not in df.columns:
        df["text"] = df["audio_transcript"].astype(str).str.split("|").apply(
            lambda parts: " ".join(p.strip() for p in parts)
        )
    df = df[df["text"].notna() & (df["text"].str.len() >= 10)].reset_index(drop=True)
    df["phq9_binary"] = df["phq9_binary"].astype(int)

    if n_samples < len(df):
        pos_n = int(round(n_samples * df["phq9_binary"].mean()))
        pos_n = max(1, min(pos_n, n_samples - 1))
        pos = df[df["phq9_binary"] == 1].sample(n=pos_n, random_state=seed)
        neg = df[df["phq9_binary"] == 0].sample(n=n_samples - pos_n, random_state=seed)
        df = pd.concat([pos, neg]).sample(frac=1, random_state=seed).reset_index(drop=True)

    texts = df["text"].astype(str).tolist()
    y = df["phq9_binary"].values
    logger.info(
        "mmpsy 域外样本: %d 条, 阳性率=%.2f%%, 平均文本长度=%.0f (M2 未训练集)",
        len(y), y.mean() * 100, np.mean([len(t) for t in texts]),
    )
    return texts, y


def load_production_tfidf() -> tuple[Any, Any]:
    """加载生产 TF-IDF + LR 模型."""
    import pickle

    tfidf_path = PROJECT_ROOT / "models" / "artifacts" / "text_depression_classifier" / "text_tfidf.pkl"
    model_path = PROJECT_ROOT / "models" / "artifacts" / "text_depression_classifier" / "text_model.pkl"

    if not tfidf_path.exists() or not model_path.exists():
        raise FileNotFoundError(f"生产 TF-IDF 模型缺失: {tfidf_path} / {model_path}")

    with open(tfidf_path, "rb") as f:
        tfidf = pickle.load(f)
    with open(model_path, "rb") as f:
        model = pickle.load(f)
    logger.info("生产 TF-IDF + LR 加载完成: tfidf=%s, model=%s", type(tfidf).__name__, type(model).__name__)
    return tfidf, model


def predict_tfidf_batch(tfidf: Any, model: Any, texts: list[str]) -> tuple[np.ndarray, np.ndarray]:
    """生产 TF-IDF 批量推理: 返回 (predictions, probabilities)."""
    vec = tfidf.transform(texts)
    preds = model.predict(vec).astype(int)
    probs = model.predict_proba(vec)[:, 1].astype(float)
    return preds, probs


async def predict_m2_batch(texts: list[str]) -> tuple[np.ndarray, np.ndarray, list[int]]:
    """M2 BERT 批量推理: 返回 (predictions, probabilities, failure_indices).

    逐条推理以复用 TextM2BertPredictor 单例 (避免重复加载 BERT).
    """
    from app.core.text_m2_bert_predictor import get_m2_bert_predictor

    predictor = get_m2_bert_predictor()
    await predictor._initialize()  # 预加载 (10s)

    preds = np.zeros(len(texts), dtype=int)
    probs = np.zeros(len(texts), dtype=float)
    failures: list[int] = []

    for i, text in enumerate(texts):
        result = await predictor.predict(text)
        if result is None:
            failures.append(i)
            preds[i] = 0
            probs[i] = 0.0
        else:
            preds[i] = int(result["prediction"])
            probs[i] = float(result["probability"])
        if (i + 1) % 50 == 0:
            logger.info("M2 BERT 推理进度: %d/%d", i + 1, len(texts))

    return preds, probs, failures


def compute_metrics(y_true: np.ndarray, y_pred: np.ndarray, y_prob: np.ndarray) -> dict[str, float]:
    """计算分类指标."""
    return {
        "accuracy": float(accuracy_score(y_true, y_pred)),
        "precision": float(precision_score(y_true, y_pred, zero_division=0)),
        "recall": float(recall_score(y_true, y_pred, zero_division=0)),
        "f1": float(f1_score(y_true, y_pred, zero_division=0)),
        "auc": float(roc_auc_score(y_true, y_prob)) if len(np.unique(y_true)) > 1 else 0.5,
    }


async def run_drill(n_samples: int) -> dict[str, Any]:
    """P4 双跑切换演练主流程."""
    start = time.time()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    logger.info("=" * 60)
    logger.info("P4 影子模式双跑切换演练 - 启动 (n_samples=%d)", n_samples)
    logger.info("=" * 60)

    # 1. 加载数据
    texts, y_true = load_chinese_sample(n_samples)

    # 2. 加载生产 TF-IDF
    tfidf, tfidf_model = load_production_tfidf()

    # 3. 生产 TF-IDF 批量推理
    t0 = time.perf_counter()
    tfidf_preds, tfidf_probs = predict_tfidf_batch(tfidf, tfidf_model, texts)
    tfidf_latency_s = time.perf_counter() - t0
    tfidf_p50_ms = tfidf_latency_s / len(texts) * 1000
    logger.info(
        "生产 TF-IDF 推理: %.2fs, 单条 P50=%.2fms, pred_pos=%d",
        tfidf_latency_s, tfidf_p50_ms, int(tfidf_preds.sum()),
    )

    # 4. M2 BERT 批量推理
    t0 = time.perf_counter()
    m2_preds, m2_probs, m2_failures = await predict_m2_batch(texts)
    m2_latency_s = time.perf_counter() - t0
    m2_p50_ms = m2_latency_s / len(texts) * 1000
    logger.info(
        "M2 BERT 推理: %.2fs, 单条 P50=%.2fms, pred_pos=%d, failures=%d",
        m2_latency_s, m2_p50_ms, int(m2_preds.sum()), len(m2_failures),
    )

    # 5. 通过 ShadowModeService 记录对拍 (真实集成验证)
    from app.services.shadow_mode_service import get_shadow_mode_service
    from app.core.text_m2_bert_predictor import get_m2_bert_predictor

    service = get_shadow_mode_service()
    service.reset_stats()
    # 关键: 将已加载的 M2 predictor 注入 shadow service, 避免重复加载 BERT
    # (fire_shadow_predict 内部调 _ensure_predictor, 但我们直接调 _shadow_predict 需手动设置)
    m2_predictor = get_m2_bert_predictor()
    service._predictor = m2_predictor
    service._predictor_loaded = True
    # 直接调用 _shadow_predict (绕过 fire-and-forget, 同步收集统计)
    for i, text in enumerate(texts):
        prod_result = {
            "prediction": int(tfidf_preds[i]),
            "probability": float(tfidf_probs[i]),
            "model_used": "text_depression_tfidf",
        }
        await service._shadow_predict(text, prod_result)
    shadow_stats = service.get_stats()
    logger.info(
        "ShadowModeService 集成验证: total=%d, agreement=%d (%.1f%%), disagreement=%d",
        shadow_stats["total_comparisons"],
        shadow_stats["agreement"],
        shadow_stats["agreement_rate"] * 100,
        shadow_stats["disagreement"],
    )

    # 6. 指标计算
    tfidf_metrics = compute_metrics(y_true, tfidf_preds, tfidf_probs)
    m2_metrics = compute_metrics(y_true, m2_preds, m2_probs)

    # 7. 双跑对比
    pred_agreement = float(np.mean(tfidf_preds == m2_preds))
    prob_diffs = np.abs(tfidf_probs - m2_probs)
    prob_diff_mean = float(prob_diffs.mean())
    prob_diff_max = float(prob_diffs.max())

    # 8. 切换决策门禁
    gates = {
        "G1_m2_f1_ge_0_75": m2_metrics["f1"] >= 0.75,
        "G2_m2_auc_ge_0_85": m2_metrics["auc"] >= 0.85,
        "G3_m2_f1_lift_ge_0_30": (m2_metrics["f1"] - tfidf_metrics["f1"]) >= 0.30,
        "G4_m2_recall_ge_0_90": m2_metrics["recall"] >= 0.90,
        "G5_shadow_service集成": (
            shadow_stats["total_comparisons"] == len(texts)
            and shadow_stats["agreement"] + shadow_stats["disagreement"] == len(texts)
        ),
        "G6_双跑无崩溃": len(m2_failures) == 0,
    }
    all_passed = all(gates.values())

    # 9. 切换决策
    if all_passed:
        decision = "APPROVED: M2 BERT 可切换为生产文本模型, TF-IDF 降级为 fallback"
    elif gates["G1_m2_f1_ge_0_75"] and gates["G2_m2_auc_ge_0_85"]:
        decision = "CONDITIONAL: M2 达标但其他门禁未过, 需排查后重测"
    else:
        decision = "REJECTED: M2 未达切换阈值, 保持 TF-IDF 生产"

    # 10. 汇总报告
    result = {
        "experiment_id": f"p4_shadow_drill_{timestamp}",
        "task": "S3 P4 影子模式双跑切换演练",
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "elapsed_s": round(time.time() - start, 1),
        "n_samples": int(len(texts)),
        "pos_rate": float(y_true.mean()),
        "production_tfidf": {
            "model_path": "models/artifacts/text_depression_classifier/",
            "metrics": tfidf_metrics,
            "total_latency_s": round(tfidf_latency_s, 2),
            "p50_ms": round(tfidf_p50_ms, 2),
            "pred_positive": int(tfidf_preds.sum()),
        },
        "m2_bert": {
            "model_path": "models/artifacts/text_m2_bert/",
            "metrics": m2_metrics,
            "total_latency_s": round(m2_latency_s, 2),
            "p50_ms": round(m2_p50_ms, 2),
            "pred_positive": int(m2_preds.sum()),
            "failures": len(m2_failures),
        },
        "shadow_mode_integration": {
            "total_comparisons": shadow_stats["total_comparisons"],
            "agreement": shadow_stats["agreement"],
            "disagreement": shadow_stats["disagreement"],
            "agreement_rate": shadow_stats["agreement_rate"],
            "avg_prob_diff": shadow_stats["avg_prob_diff"],
            "max_prob_diff": shadow_stats["max_prob_diff"],
            "predictor_loaded": shadow_stats["predictor_loaded"],
        },
        "comparison": {
            "pred_agreement_rate": round(pred_agreement, 4),
            "prob_diff_mean": round(prob_diff_mean, 4),
            "prob_diff_max": round(prob_diff_max, 4),
            "f1_lift": round(m2_metrics["f1"] - tfidf_metrics["f1"], 4),
            "auc_lift": round(m2_metrics["auc"] - tfidf_metrics["auc"], 4),
            "recall_lift": round(m2_metrics["recall"] - tfidf_metrics["recall"], 4),
        },
        "gates": gates,
        "all_gates_passed": all_passed,
        "decision": decision,
        "notes": (
            "本演练在 mmpsy 域外集 (1275 条中文, M2 未训练) 上对生产 TF-IDF (英文 Reddit 训练) "
            "与 M2 BERT (中文 D3+ 8379 条训练) 做端到端双跑. 预期 TF-IDF 域外失效 (D3 F1=0.0147), "
            "M2 应显著优于 TF-IDF. 一致率低属预期 (模型能力差异, 非故障). "
            "切换决策基于 M2 绝对指标达标 + 集成验证通过, 而非双模型一致率."
        ),
    }

    # 保存
    EXPERIMENTS_DIR.mkdir(parents=True, exist_ok=True)
    out_path = EXPERIMENTS_DIR / f"p4_shadow_drill_{timestamp}.json"
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    logger.info("报告已保存: %s", out_path)

    # 控制台汇总
    print("\n" + "=" * 60)
    print("P4 影子模式双跑切换演练 - 结果汇总")
    print("=" * 60)
    print(f"样本: {len(texts)} 条 (阳性率 {y_true.mean()*100:.1f}%)")
    print(f"\n生产 TF-IDF: F1={tfidf_metrics['f1']:.4f} AUC={tfidf_metrics['auc']:.4f} "
          f"Recall={tfidf_metrics['recall']:.4f} (P50={tfidf_p50_ms:.1f}ms)")
    print(f"M2 BERT:     F1={m2_metrics['f1']:.4f} AUC={m2_metrics['auc']:.4f} "
          f"Recall={m2_metrics['recall']:.4f} (P50={m2_p50_ms:.1f}ms)")
    print(f"\n双跑对比: 一致率={pred_agreement*100:.1f}% (低=预期, TF-IDF 域外失效)")
    print(f"          ΔF1=+{m2_metrics['f1']-tfidf_metrics['f1']:.4f} "
          f"ΔAUC=+{m2_metrics['auc']-tfidf_metrics['auc']:.4f}")
    print(f"\nShadow 集成: total={shadow_stats['total_comparisons']} "
          f"agree={shadow_stats['agreement']} disagree={shadow_stats['disagreement']}")
    print(f"\n切换门禁:")
    for k, v in gates.items():
        print(f"  {'✓' if v else '✗'} {k}: {v}")
    print(f"\n决策: {decision}")
    print("=" * 60)

    return result


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="P4 影子模式双跑切换演练")
    parser.add_argument("--n-samples", type=int, default=200, help="中文样本数 (默认 200)")
    args = parser.parse_args()
    result = asyncio.run(run_drill(args.n_samples))
    sys.exit(0 if result["all_gates_passed"] else 1)
