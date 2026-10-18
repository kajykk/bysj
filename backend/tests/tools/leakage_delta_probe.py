"""方向 B：划分口径泄漏对照探针（random vs groupwise）。

**这是方向 B 的核心证据生成器。**

判据：在**完全相同的数据、特征、模型、阈值**上，只换划分协议：
  - 口径 R（random / 文本级）：StratifiedKFold —— 同一原始样本的增强变体可跨 fold
  - 口径 G（groupwise / 组级）：StratifiedGroupKFold —— 同组永不跨 train/eval

两者指标差 Δ = R − G 即**兄弟泄漏（sibling leakage）造成的虚高幅度**。
若某入口只用 R 口径报数，则它报告的是 X。真正的泛化性能是 X − Δ。

理论依据（与提示词一致）：
  - 2607.02920 / 2610.06465：random-split 与 best-of-N 调参是系统性高估源
  - 本项目 P2-1 实测：groupwise F1 0.5864 vs textwise 0.9964（差 0.41）

设计纪律：
  - 两种口径必须共享同一份 vectorizer 超参与 LR 超参，否则比较无效
  - 阈值固定（生产口径 0.3），**不得**在评估折上选阈值（那会引入第二种选择偏差）
  - 本探针只报 OOF（out-of-fold）指标，不报样本内指标

用法：
    # 真实语料对照（约数分钟）
    .venv/Scripts/python.exe tests/tools/leakage_delta_probe.py -o leak_delta.json
    # 自检（合成语料，快，供闸门用）
    .venv/Scripts/python.exe tests/tools/leakage_delta_probe.py --self-test
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import numpy as np
import pandas as pd
from sklearn.feature_extraction.text import TfidfVectorizer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import f1_score, roc_auc_score
from sklearn.model_selection import StratifiedGroupKFold, StratifiedKFold

BACKEND = Path(__file__).resolve().parents[2]
TOP_ROOT = BACKEND.parent

# 与生产 train_bilingual_text.py 完全一致的超参（改这里等于改口径，禁止）
TFIDF_KWARGS = dict(
    lowercase=True,
    sublinear_tf=True,
    min_df=2,
    max_df=0.95,
    max_features=120000,
    ngram_range=(1, 2),
)
LR_KWARGS = dict(C=1.0, class_weight="balanced", max_iter=3000, random_state=42)

N_FOLDS = 5
RANDOM_STATE = 42
THRESHOLD = 0.3  # 生产固定阈值


def _tokenizer(text: str) -> list[str]:
    """生产同款分词器（延迟导入，避免探针把后端包拖进来）。"""
    sys.path.insert(0, str(BACKEND))
    from app.core.text_tokenizer import zh_bilingual_tokenize  # noqa: PLC0415

    return zh_bilingual_tokenize(text)


def _oof_predict(
    texts: np.ndarray,
    y: np.ndarray,
    groups: np.ndarray | None,
    n_folds: int,
    random_state: int,
    tfidf_kwargs: dict,
    lr_kwargs: dict,
) -> np.ndarray:
    """产出 OOF 概率。groups=None ⇒ 随机分层划分；否则组级划分。"""
    oof = np.full(len(y), np.nan)
    if groups is not None:
        splitter = StratifiedGroupKFold(
            n_splits=n_folds, shuffle=True, random_state=random_state
        )
        splits = splitter.split(texts, y, groups=groups)
    else:
        splitter = StratifiedKFold(
            n_splits=n_folds, shuffle=True, random_state=random_state
        )
        splits = splitter.split(texts, y)

    for tr, te in splits:
        vec = TfidfVectorizer(tokenizer=_tokenizer, **tfidf_kwargs)
        Xtr = vec.fit_transform(texts[tr])
        Xte = vec.transform(texts[te])
        clf = LogisticRegression(**lr_kwargs)
        clf.fit(Xtr, y[tr])
        oof[te] = clf.predict_proba(Xte)[:, 1]
    return oof


def _metrics(y: np.ndarray, oof: np.ndarray, threshold: float) -> dict:
    yhat = (oof >= threshold).astype(int)
    return {
        "n": int(len(y)),
        "positive_rate": round(float(y.mean()), 4),
        "f1": round(float(f1_score(y, yhat, zero_division=0)), 4),
        "roc_auc": (
            round(float(roc_auc_score(y, oof)), 4) if len(np.unique(y)) > 1 else None
        ),
    }


def compare_split_protocols(
    texts: list[str] | np.ndarray,
    y: list[int] | np.ndarray,
    groups: list[int] | np.ndarray | None,
    n_folds: int = N_FOLDS,
    random_state: int = RANDOM_STATE,
    threshold: float = THRESHOLD,
    tfidf_kwargs: dict | None = None,
    lr_kwargs: dict | None = None,
) -> dict:
    """在同一批数据上并行跑 R/G 两口径，返回指标与差值。

    groups=None 时无法跑组级口径，返回 random_only 标记。
    """
    tfidf_kwargs = dict(tfidf_kwargs or TFIDF_KWARGS)
    lr_kwargs = dict(lr_kwargs or LR_KWARGS)

    texts = np.asarray(texts, dtype=object)
    y = np.asarray(y, dtype=int)

    oof_r = _oof_predict(texts, y, None, n_folds, random_state, tfidf_kwargs, lr_kwargs)
    m_r = _metrics(y, oof_r, threshold)
    m_r["protocol"] = "random_textwise"
    m_r["n_groups"] = None

    if groups is None:
        return {
            "random": m_r,
            "groupwise": None,
            "delta": None,
            "random_only": True,
        }

    groups = np.asarray(groups)
    oof_g = _oof_predict(texts, y, groups, n_folds, random_state, tfidf_kwargs, lr_kwargs)
    m_g = _metrics(y, oof_g, threshold)
    m_g["protocol"] = "groupwise"
    m_g["n_groups"] = int(len(np.unique(groups)))

    delta = {
        "d_f1": round(m_r["f1"] - m_g["f1"], 4),
        "d_roc_auc": (
            round(m_r["roc_auc"] - m_g["roc_auc"], 4)
            if m_r["roc_auc"] is not None and m_g["roc_auc"] is not None
            else None
        ),
    }
    return {"random": m_r, "groupwise": m_g, "delta": delta, "random_only": False}


def compare_tabular_protocols(
    df: pd.DataFrame,
    feature_cols: list[str],
    label_col: str,
    n_folds: int = N_FOLDS,
    random_state: int = RANDOM_STATE,
    threshold: float = THRESHOLD,
    lr_kwargs: dict | None = None,
) -> dict:
    """表格数据的口径对照：按「特征行完全相同」分组。

    结构化特征粒度粗时，不同受试者会碰撞出完全相同的特征行。
    随机划分 ⇒ 测试样本的精确副本出现在训练集 ⇒ 可直接记忆 ⇒ 虚高。
    组级划分 ⇒ 同一特征组合永不跨 train/eval ⇒ 真口径。

    返回含 group_stats（重复组数/涉及行数/组内标签一致率）。
    """
    lr_kwargs = dict(lr_kwargs or LR_KWARGS)
    X = df[feature_cols].astype(float).values
    y = df[label_col].astype(int).values

    key = df[feature_cols].astype(str).agg("|".join, axis=1)
    codes, _ = pd.factorize(key)
    groups = np.asarray(codes, dtype=int)

    sizes = pd.Series(groups).value_counts()
    dup_mask = sizes > 1
    n_dup_groups = int(dup_mask.sum())
    n_rows_in_dup = int(sizes[dup_mask].sum())

    pure = mixed = 0
    for g, idx in pd.Series(range(len(groups))).groupby(groups).groups.items():
        idx = np.asarray(idx)
        if len(idx) < 2:
            continue
        if len(np.unique(df[label_col].values[idx])) == 1:
            pure += 1
        else:
            mixed += 1
    purity = pure / (pure + mixed) if (pure + mixed) else None

    oof_r = np.full(len(y), np.nan)
    skf = StratifiedKFold(n_splits=n_folds, shuffle=True, random_state=random_state)
    for tr, te in skf.split(X, y):
        clf = LogisticRegression(**lr_kwargs)
        clf.fit(X[tr], y[tr])
        oof_r[te] = clf.predict_proba(X[te])[:, 1]

    oof_g = np.full(len(y), np.nan)
    sgkf = StratifiedGroupKFold(n_splits=n_folds, shuffle=True, random_state=random_state)
    for tr, te in sgkf.split(X, y, groups=groups):
        clf = LogisticRegression(**lr_kwargs)
        clf.fit(X[tr], y[tr])
        oof_g[te] = clf.predict_proba(X[te])[:, 1]

    m_r = _metrics(y, oof_r, threshold)
    m_r["protocol"] = "random"
    m_g = _metrics(y, oof_g, threshold)
    m_g["protocol"] = "groupwise_by_feature_collision"
    m_g["n_groups"] = int(len(np.unique(groups)))

    return {
        "random": m_r,
        "groupwise": m_g,
        "delta": {
            "d_f1": round(m_r["f1"] - m_g["f1"], 4),
            "d_roc_auc": (
                round(m_r["roc_auc"] - m_g["roc_auc"], 4)
                if m_r["roc_auc"] is not None and m_g["roc_auc"] is not None
                else None
            ),
        },
        "group_stats": {
            "n_rows": int(len(df)),
            "n_unique_feature_rows": int(df[feature_cols].drop_duplicates().shape[0]),
            "n_dup_groups": n_dup_groups,
            "n_rows_in_dup_groups": n_rows_in_dup,
            "dup_row_share": round(n_rows_in_dup / len(df), 4),
            "label_pure_groups": pure,
            "label_mixed_groups": mixed,
            "intra_group_label_purity": round(purity, 4) if purity is not None else None,
        },
    }


def detect_target_leakage(
    df: pd.DataFrame,
    feature_cols: list[str],
    label_col: str,
    auc_threshold: float = 0.99,
) -> dict:
    """目标泄漏检测：单特征 AUC 达到阈值的特征即为「标签的确定性函数」。

    与划分协议无关——这类泄漏**换任何 CV 都修不好**，因为特征本身就是
    标签的单调变换（如 stress_level = phq9_score / 27 * 5）。

    实测（本仓库）：mmpsy_structured_features.csv 的 stress_level 单特征
    AUC = 1.0000，corr(stress_level, phq9_score) = 1.0 ⇒ 目标泄漏。

    返回 {leaky: [...], clean_max_auc, verdict}。
    """
    y = df[label_col].astype(int).values
    leaky: list[dict] = []
    max_clean = 0.0
    for c in feature_cols:
        try:
            x = df[c].astype(float).values
        except (ValueError, TypeError):
            continue
        if len(np.unique(x)) < 2:
            continue
        if len(np.unique(y)) < 2:
            continue
        auc = float(roc_auc_score(y, x))
        auc = max(auc, 1.0 - auc)  # 反向也判泄漏
        if auc >= auc_threshold:
            leaky.append({"feature": c, "auc": round(auc, 4)})
        else:
            max_clean = max(max_clean, auc)
    return {
        "leaky": leaky,
        "n_leaky": len(leaky),
        "clean_max_auc": round(max_clean, 4),
        "verdict": "target_leakage" if leaky else "ok",
        "auc_threshold": auc_threshold,
    }


# ── 自检：合成语料（硬检出兄弟泄漏） ──────────────────────────────
def _synthetic_corpus(n_groups: int = 60, variants: int = 6, seed: int = 0) -> tuple[list[str], list[int], list[int]]:
    """构造「标签只与组身份绑定」的语料。

    每组的文本 = 组唯一 token + 共享填充词。
    - random 口径：测试折样本的训练兄弟携带同一个组 token ⇒ 模型可记忆 ⇒ F1 高
    - groupwise 口径：整组被 held out ⇒ 组 token OOV ⇒ 判别力崩塌 ⇒ F1 低

    这样两种口径必然产生可分辨的差值，可作为探针有效性的正向证据。
    """
    rng = np.random.default_rng(seed)
    texts: list[str] = []
    labels: list[int] = []
    gids: list[int] = []
    filler = "的 了 是 我 有 在 和 就 不 人 都 一 个 上 也 很 到 说 要 去"
    for g in range(n_groups):
        lab = int(rng.integers(0, 2))
        for v in range(variants):
            # 变体只换填充词顺序，组 token 恒定 ⇒ 兄弟高度相似
            toks = filler.split()
            rng.shuffle(toks)
            texts.append(f"gtok{g:03d} " + " ".join(toks[:8]))
            labels.append(lab)
            gids.append(g)
    return texts, labels, gids


def self_test() -> int:
    """探针有效性自检：合成语料上必须检出显著正差值。"""
    texts, y, groups = _synthetic_corpus()
    res = compare_split_protocols(texts, y, groups)
    print(json.dumps(res, ensure_ascii=False, indent=2))

    # 判据用 **ΔAUC**（阈值无关，纯排序质量），不用 ΔF1。
    # 理由（自检实测）：固定阈值 0.3 下，组级 held-out 使测试组 token 全部 OOV
    # ⇒ TF-IDF 向量近似全零 ⇒ LR 输出近似常数 ⇒ 预测退化为全 1
    # ⇒ F1 与 random 口径完全相同（实测 ΔF1=0.0），无法体现口径差。
    # AUC 不受阈值影响，能如实反映「排序质量是否来自兄弟记忆」。
    d_auc = res["delta"]["d_roc_auc"]
    if d_auc is None or d_auc < 0.20:
        print(f"[FAIL] 探针未检出兄弟泄漏：ΔAUC={d_auc} < 0.20", file=sys.stderr)
        return 1
    # 组级口径下判别力应崩塌到接近随机（合成语料标签只绑定组身份）
    g_auc = res["groupwise"]["roc_auc"]
    if g_auc > 0.65:
        print(f"[FAIL] 组级口径未崩塌：AUC={g_auc} > 0.65，说明组结构未被真正隔离", file=sys.stderr)
        return 1
    print(f"[OK] 探针检出兄弟泄漏：ΔAUC={d_auc}（组级 AUC={g_auc} ≈ 随机）")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("-o", "--out", help="输出 JSON 路径")
    ap.add_argument("--self-test", action="store_true", help="跑合成语料自检")
    ap.add_argument(
        "--corpus",
        default=str(TOP_ROOT / "data" / "external" / "chinese_depression_corpus_v1.csv"),
        help="语料路径",
    )
    ap.add_argument("--folds", type=int, default=N_FOLDS)
    ap.add_argument(
        "--tabular",
        action="store_true",
        help="表格数据模式：按特征行碰撞分组做口径对照（mmpsy 线）",
    )
    ap.add_argument("--label-col", default="phq9_binary")
    args = ap.parse_args()

    if args.self_test:
        return self_test()

    if args.tabular:
        df_feat = pd.read_csv(args.corpus)
        feat_cols = [c for c in df_feat.columns if not c.endswith("_source")]
        raw = pd.read_csv(str(TOP_ROOT / "data" / "external" / "mmpsy_scores.csv"))
        df_feat = df_feat.copy()
        df_feat[args.label_col] = raw[args.label_col].values
        res = compare_tabular_protocols(
            df_feat, feat_cols, args.label_col, n_folds=args.folds
        )
        res["corpus"] = str(Path(args.corpus).resolve().relative_to(TOP_ROOT))
        text = json.dumps(res, ensure_ascii=False, indent=2)
        if args.out:
            Path(args.out).write_text(text, encoding="utf-8")
            print(f"[leakage-probe] 写入 {args.out}")
        print(text)
        return 0

    df = pd.read_csv(args.corpus)
    df = df[df["text"].astype(str).str.len() >= 5].copy()
    df["text"] = df["text"].astype(str)
    df["label"] = df["phq9_binary"].astype(int)

    # 复用项目既有分组实现（不要另造一套口径）
    sys.path.insert(0, str(TOP_ROOT / "scripts"))
    from m2_group_cv_eval import build_group_ids  # noqa: PLC0415

    groups = build_group_ids(df)

    res = compare_split_protocols(
        df["text"].values, df["label"].values, groups, n_folds=args.folds
    )
    res["corpus"] = str(Path(args.corpus).relative_to(TOP_ROOT))
    res["n_rows"] = int(len(df))
    res["n_groups"] = int(len(np.unique(groups)))

    text = json.dumps(res, ensure_ascii=False, indent=2)
    if args.out:
        Path(args.out).write_text(text, encoding="utf-8")
        print(f"[leakage-probe] 写入 {args.out}")
    print(text)
    return 0


if __name__ == "__main__":
    sys.exit(main())
