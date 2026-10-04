"""P2-1: 句向量(MiniLM) vs TF-IDF 的同口径 A/B 评估.

设计要点（为什么这样比）:
  1. 同一语料、同一标签、同一分组（防泄露）、同一分类器 —— **只换特征**。
     任何其他变量变化都会让「换不换特征」这个问题无法归因。
  2. 分组复用 m2_group_cv_eval.build_group_ids: 原始样本与其增强变体必须同组,
     否则 GroupKFold 形同虚设（m2 脚本记录过标准随机 CV 虚高到 0.9709 的教训）。
  3. 复用 t1_group_cv_tool.evaluate_group_cv: 阈值在**训练折内**按最佳 F1 选取,
     避免用测试折调阈值的信息泄漏。
  4. TF-IDF 是稀疏矩阵 -> scale=False; MiniLM 稠密 384 维 -> scale=True。

用法:
    python scripts/t1_sentence_embedding_eval.py            # A/B 全跑
    python scripts/t1_sentence_embedding_eval.py --max-rows 2000   # 快速冒烟
环境:
    HF_ENDPOINT=https://hf-mirror.com   # 本机 huggingface.co 直连不通
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "scripts"))

CORPUS_PATH = REPO_ROOT / "data" / "external" / "chinese_depression_corpus_v1.csv"
# 权重已用断点续传下载到本地（HF 直连不通，见 memory 2026-10-04）。
MODEL_DIR = REPO_ROOT / "models" / "_cache" / "minilm-l12"
OUT_JSON = REPO_ROOT / "docs" / "planning" / "p2_1_sentence_embedding_eval.json"
N_SPLITS = 5
SEED = 42
# 判定门槛（先定死，事后不许自我说服）
MIN_DELTA_F1 = 0.02


def build_labels_and_groups(df: pd.DataFrame) -> tuple[np.ndarray, np.ndarray]:
    """标签 = phq9_binary; 分组 = build_group_ids（原始样本与其增强变体同组）。"""
    from m2_group_cv_eval import build_group_ids  # 复用既有实现, 避免口径漂移

    y = df["phq9_binary"].astype(int).values
    groups = build_group_ids(df)
    return y, groups


def eval_tfidf(texts: list[str], y: np.ndarray, groups: np.ndarray) -> dict:
    """A: TF-IDF(1-2gram) + LR, scale=False（稀疏矩阵不能标准化）。"""
    from t1_group_cv_tool import evaluate_group_cv

    t0 = time.time()
    vec = TfidfVectorizer(
        ngram_range=(1, 2), min_df=2, sublinear_tf=True, max_features=200_000
    )
    X = vec.fit_transform(texts)
    print(f"[A] TF-IDF 特征: {X.shape}, 耗时 {time.time() - t0:.1f}s")

    clf_factory = lambda seed: LogisticRegression(  # noqa: E731
        C=1.0, class_weight="balanced", max_iter=3000, random_state=seed, solver="lbfgs"
    )
    res = evaluate_group_cv(
        np.asarray(X.todense()), y, groups, clf_factory=clf_factory,
        label="tfidf_group_cv", scale=False,
    )
    d = res.to_dict()
    d["n_features"] = int(X.shape[1])
    d["feature_extract_seconds"] = round(time.time() - t0, 1)
    return d


def eval_minilm(texts: list[str], y: np.ndarray, groups: np.ndarray, batch_size: int) -> dict:
    """B: MiniLM 句向量 384 维 + LR, scale=True（稠密低维, 标准化有益）。

    不用 sentence_transformers: ST 6.1.0 会调 transformers 5.x 的 AutoProcessor,
    而该 2023 年的模型仓库没有 processor 配置 -> ValueError。改为手工
    AutoTokenizer + AutoModel + mean pooling（与 1_Pooling/config.json 里
    pooling_mode_mean_tokens=true 一致, 即 ST 内部的等价实现）。
    """
    from t1_group_cv_tool import evaluate_group_cv

    t0 = time.time()
    import torch
    from transformers import AutoModel, AutoTokenizer

    tok = AutoTokenizer.from_pretrained(str(MODEL_DIR))
    mdl = AutoModel.from_pretrained(str(MODEL_DIR)).eval()
    dim = mdl.config.hidden_size
    print(f"[B] MiniLM 已加载({dim} 维), 开始编码 {len(texts)} 条...")

    embs: list[np.ndarray] = []
    with torch.no_grad():
        for i in range(0, len(texts), batch_size):
            chunk = texts[i : i + batch_size]
            enc = tok(chunk, padding=True, truncation=True, max_length=512, return_tensors="pt")
            h = mdl(**enc).last_hidden_state
            m = enc["attention_mask"].unsqueeze(-1).float()
            emb = (h * m).sum(1) / m.sum(1).clamp(min=1e-9)   # mean pooling
            embs.append(torch.nn.functional.normalize(emb, p=2, dim=1).numpy())
            if (i // batch_size) % 20 == 0:
                done = min(i + batch_size, len(texts))
                print(f"    编码 {done}/{len(texts)} ({time.time() - t0:.0f}s)", flush=True)
    X = np.vstack(embs)
    enc_sec = time.time() - t0
    print(f"[B] 编码完成: {X.shape}, 耗时 {enc_sec / 60:.1f} min")

    clf_factory = lambda seed: LogisticRegression(  # noqa: E731
        C=1.0, class_weight="balanced", max_iter=3000, random_state=seed, solver="lbfgs"
    )
    res = evaluate_group_cv(
        X, y, groups, clf_factory=clf_factory, label="minilm_group_cv", scale=True
    )
    d = res.to_dict()
    d["n_features"] = int(X.shape[1])
    d["encode_seconds"] = round(enc_sec, 1)
    d["encode_docs_per_sec"] = round(len(texts) / max(enc_sec, 1e-6), 1)
    return d


def eval_tfidf_svd(texts: list[str], y: np.ndarray, groups: np.ndarray, n_components: int) -> dict:
    """C: TF-IDF -> TruncatedSVD(300) + LR（**合理调优的 TF-IDF 基线**）。

    为什么必须有这一组: A 组用 89,988 维稀疏特征配 6,703 训练样本, 属维度诅咒
    (LR 过拟合并概率极端化 -> 多折 F1=0), 拿它当基线会把「维度优势」误读成
    「语义表征优势」。C 组把 TF-IDF 压到与句向量同量级(300 维)后重比, 才是公平对照。
    """
    from t1_group_cv_tool import evaluate_group_cv
    from sklearn.decomposition import TruncatedSVD

    t0 = time.time()
    vec = TfidfVectorizer(
        ngram_range=(1, 2), min_df=2, sublinear_tf=True, max_features=200_000
    )
    Xs = vec.fit_transform(texts)
    svd = TruncatedSVD(n_components=n_components, random_state=SEED)
    X = svd.fit_transform(Xs)
    print(f"[C] TF-IDF {Xs.shape} -> SVD {X.shape}, "
          f"解释方差 {svd.explained_variance_ratio_.sum():.3f}, 耗时 {time.time() - t0:.1f}s")

    clf_factory = lambda seed: LogisticRegression(  # noqa: E731
        C=1.0, class_weight="balanced", max_iter=3000, random_state=seed, solver="lbfgs"
    )
    res = evaluate_group_cv(
        X, y, groups, clf_factory=clf_factory, label="tfidf_svd_group_cv", scale=False
    )
    d = res.to_dict()
    d["n_features"] = int(X.shape[1])
    d["tfidf_raw_features"] = int(Xs.shape[1])
    d["svd_explained_variance"] = round(float(svd.explained_variance_ratio_.sum()), 4)
    return d


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--max-rows", type=int, default=0, help=">0 则截断（冒烟用，会破坏分组完整性）")
    ap.add_argument("--batch-size", type=int, default=32)
    ap.add_argument("--skip-minilm", action="store_true", help="只跑 TF-IDF 基线")
    ap.add_argument("--skip-tfidf", action="store_true", help="跳过 A 组（已测过）")
    ap.add_argument("--only-groups", default="", help="只跑指定组, 逗号分隔, 如 'A,C'")
    args = ap.parse_args()
    only = {g.strip().upper() for g in args.only_groups.split(",") if g.strip()}

    df = pd.read_csv(CORPUS_PATH)
    df = df[df["phq9_binary"].notna()].copy()
    df["text"] = df["text"].fillna("").astype(str)
    df = df[df["text"].str.len() > 0]
    if args.max_rows:
        df = df.head(args.max_rows)

    y, groups = build_labels_and_groups(df)
    texts = df["text"].tolist()
    print(f"语料: {len(texts):,} 条 | 唯一 group: {len(set(groups.tolist())):,} | 正例率 {y.mean():.1%}")

    out: dict = {}
    out_path = OUT_JSON
    if out_path.exists():
        try:
            out = json.loads(out_path.read_text(encoding="utf-8"))
        except Exception:
            out = {}
    out.update({
        "corpus": str(CORPUS_PATH.relative_to(REPO_ROOT)),
        "n_rows": int(len(texts)), "n_groups": int(len(set(groups.tolist()))),
        "pos_rate": round(float(y.mean()), 4),
        "label": "phq9_binary", "cv": f"GroupKFold(n_splits={N_SPLITS}, by source_idx)",
        "classifier": "LogisticRegression(C=1.0, balanced, max_iter=3000)",
        "gate_min_delta_f1": MIN_DELTA_F1,
        "caveat_ci": "GroupKFold 确定性, SEEDS 循环只重排 fold 顺序 -> 15 次评估实为 5 折重复, "
                      "CI95 按 n=15 计算偏窄, 只看点估计; 另: 阈值在训练折选取, 分布漂移的折会 F1=0",
    })
    if only:
        out["_only_groups"] = sorted(only)

    if not args.skip_tfidf and (not only or "A" in only):
        out["A_tfidf"] = eval_tfidf(texts, y, groups)
    if not only or "C" in only:
        out["C_tfidf_svd300"] = eval_tfidf_svd(texts, y, groups, 300)
    if (not args.skip_minilm) and (not only or "B" in only):
        out["B_minilm"] = eval_minilm(texts, y, groups, args.batch_size)

    if "A_tfidf" in out and "B_minilm" in out:
        a = out["A_tfidf"]["f1_mean"]; b = out["B_minilm"]["f1_mean"]
        delta = b - a
        out["delta_f1_B_minus_A"] = round(delta, 4)
        out["ci_overlap_B_A"] = not (
            out["B_minilm"]["f1_ci_upper"] < out["A_tfidf"]["f1_ci_lower"]
            or out["A_tfidf"]["f1_ci_upper"] < out["B_minilm"]["f1_ci_lower"]
        )
    if "C_tfidf_svd300" in out and "B_minilm" in out:
        c = out["C_tfidf_svd300"]["f1_mean"]; b = out["B_minilm"]["f1_mean"]
        out["delta_f1_B_minus_C"] = round(b - c, 4)
        out["delta_auc_B_minus_C"] = round(
            out["B_minilm"]["auc_mean"] - out["C_tfidf_svd300"]["auc_mean"], 4
        )
        out["ci_overlap_B_C"] = not (
            out["B_minilm"]["f1_ci_upper"] < out["C_tfidf_svd300"]["f1_ci_lower"]
            or out["C_tfidf_svd300"]["f1_ci_upper"] < out["B_minilm"]["f1_ci_lower"]
        )
        # 决策以 C（合理基线）为准, A 只作对照说明「维度诅咒」的影响
        out["verdict_vs_C"] = (
            f"换（ΔF1={b - c:+.4f} ≥ +{MIN_DELTA_F1}）" if b - c >= MIN_DELTA_F1
            else f"不换（ΔF1={b - c:+.4f} < +{MIN_DELTA_F1}）"
        )

    print("\n" + "=" * 66)
    for k in ("A_tfidf", "C_tfidf_svd300", "B_minilm"):
        if k in out:
            d = out[k]
            print(f"{k:18s} F1={d['f1_mean']:.4f}  AUC={d['auc_mean']:.4f}  "
                  f"dim={d.get('n_features', '?')}")
    if "delta_f1_B_minus_A" in out:
        print(f"ΔF1 (B-A) = {out['delta_f1_B_minus_A']:+.4f}  [坏基线对照]")
    if "delta_f1_B_minus_C" in out:
        print(f"ΔF1 (B-C) = {out['delta_f1_B_minus_C']:+.4f}  "
              f"ΔAUC = {out['delta_auc_B_minus_C']:+.4f}  [公平对照] "
              f"CI {'重叠' if out['ci_overlap_B_C'] else '不重叠'}")
        print(f"结论（以 C 为基线）: {out['verdict_vs_C']}")

    out.pop("_only_groups", None)
    OUT_JSON.parent.mkdir(parents=True, exist_ok=True)
    OUT_JSON.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n结果写入: {OUT_JSON}")


if __name__ == "__main__":
    main()
