#!/usr/bin/env python
"""ROUND_27 (G2)：外部迁移评估——两个「降级单元」。

⚠️ 先读结论：**本轮没有任何「真外迁」单元可评估**。实测裁定（见
docs/model-evaluation/TRANSFER_MATRIX.md）：

1. 文本模型 × `ood_test_set_v2`：1275 条 original 全在训练语料 v1（`in_v1_original=1275`）、
   1175 条 mmpsy_augmented 全在训练增强集（`in_train_augmented=1175`）⇒ **标签泄漏**；
   仅 eda 的 2523 条与训练语料**精确**不重叠，但它们是 original 的 EDA 改写（兄弟泄漏）
   ⇒ 只能作**域内压力测试**，不是外迁。
2. 结构化模型 × `PHQ-9_Dataset_5th Edition.csv`：`PHQ_Total` 的逐值分布与训练母表
   `data/external/aligned_features.csv` **完全相同**（0:43,1:40,2:44,…）,且 aligned 的
   label_binary 恰为 `phq9_total>=10` ⇒ **PHQ-9 就是结构化模型的训练标签母体**，不是外部数据。
3. 生理模型 × actverse：原始 actigraphy 与 13 个临床/生活派生特征**不相交** ⇒ N/A。
4. 生理模型 × Kaggle Wearable：**未确证未参与训练**（v2 训练脚本从未入库），
   且 13 个特征只有 3 个可直接映射 ⇒ 只能作**跨数据集压力测试（下界）**。

因此本脚本只产出两个**明确标注为非公平基准/域内**的单元：

    text_ood     文本模型 × OOD 的 S2_ood_strict（2523 条，与训练语料精确去重）
    physio_kaggle  生理模型 × Kaggle Wearable（10,000 条，3/13 特征映射 + 4 列按生产默认值填充）

口径与 ROUND_27 A 摊一致：
- 逐样本落盘（`.17g` 全精度）+ `.sha256`
- 指标与 CI **按落盘行序**计算（否则 bootstrap 抽样落点不同）
- `--report-only` 从 csv 重算并**同时重写 JSON + 报告**（提交产物 == 单命令产物）

用法：

    cd backend
    .venv/Scripts/python.exe scripts/modeling/eval/v1_29/02_transfer_eval.py --unit text_ood
    .venv/Scripts/python.exe scripts/modeling/eval/v1_29/02_transfer_eval.py --unit physio_kaggle
    .venv/Scripts/python.exe scripts/modeling/eval/v1_29/02_transfer_eval.py --unit text_ood --report-only
"""

from __future__ import annotations

import argparse
import hashlib
import importlib
import json
import sys
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parents[4]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

_THIS_DIR = Path(__file__).resolve().parent
if str(_THIS_DIR) not in sys.path:
    sys.path.insert(0, str(_THIS_DIR))

# 复用 A 摊（01）的指标/CI 实现，避免两套口径
ev = importlib.import_module("01_reproducible_eval")

REPO = BACKEND.parent
OUT_DIR = BACKEND / "models" / "artifacts" / "eval_transfer"
DOCS = REPO / "docs" / "model-evaluation"

OOD_PATH = REPO / "data" / "external" / "ood_test_set_v2.csv"
ZH_V1 = REPO / "data" / "external" / "chinese_depression_corpus_v1.csv"
ZH_V2 = REPO / "data" / "external" / "chinese_depression_corpus_v2_clean.csv"
EN_PATH = REPO / "datasets" / "text" / "depression_dataset_reddit_cleaned.csv"
KAGGLE_PATH = (
    REPO / "datasets" / "physiological" / "external" / "kaggle_wearable" / "mental_health_wearable_data.csv"
)

TEXT_MODEL = BACKEND / "models" / "text" / "improved_bilingual_model.pkl"
TEXT_TFIDF = BACKEND / "models" / "text" / "improved_bilingual_tfidf.pkl"


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def write_predictions(path: Path, rows: list[tuple[int, int, float]]) -> None:
    """列：sample_id,row_index,y_true,y_score,y_pred（`:.17g` 往返精度）。"""
    lines = ["sample_id,row_index,y_true,y_score,y_pred"]
    for i, (row_index, y_true, score) in enumerate(rows):
        pred = int(score >= 0.5)
        lines.append(f"{path.stem}_{i:05d},{row_index},{y_true},{score:.17g},{pred}")
    path.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    path.with_suffix(".csv.sha256").write_text(
        f"{sha(path)}  {path.name}\n", encoding="utf-8", newline="\n"
    )


def read_predictions(path: Path) -> tuple[np.ndarray, np.ndarray]:
    lines = path.read_text(encoding="utf-8").strip().splitlines()[1:]
    y = np.array([int(ln.split(",")[2]) for ln in lines], dtype=np.int64)
    s = np.array([float(ln.split(",")[3]) for ln in lines], dtype=np.float64)
    return y, s


# ────────────────────────── 向量化 bootstrap（n=10^4 必需） ──────────────────────────
#
# 01 的 `auc_score` 是纯 Python 的 tie 处理循环，`bootstrap_ci` 逐次重采样 n 个样本；
# 在 n=10,000 × B=10,000 时是 10^8 级 Python 操作（实测 >5 分钟）。
# 这里做**数学等价**的加速，并用 `--verify-fast` 在 text_ood（n=2523）上与 01 逐位对拍：
#   · 阈值指标：对 n 个样本重采样 ⟺ 对 (TP,FP,FN,TN) 计数做 Multinomial(n, p)
#   · AUC：用 scipy 的向量化平均秩（tie-aware），与 01 的 mergesort+平均秩同值


def fast_auc(y: np.ndarray, score: np.ndarray) -> float:
    from scipy.stats import rankdata

    pos = y == 1
    n_pos = int(pos.sum())
    n_neg = len(y) - n_pos
    if n_pos == 0 or n_neg == 0:
        return float("nan")
    r = rankdata(score, method="average")
    u = float(r[pos].sum()) - n_pos * (n_pos + 1) / 2.0
    return u / (n_pos * n_neg)


def fast_bootstrap(y: np.ndarray, score: np.ndarray, B: int, seed: int) -> dict:
    """与 01 的 `bootstrap_ci` **同一抽样序列**，只把 AUC 换成向量化平均秩。

    关键：`rng.randint(0, n, n)` 的调用次数与顺序必须与 01 完全一致，
    否则抽到的重采样集合不同 ⇒ CI 端点差 1e-4 级（实测多项分布近似会差 3.9e-4）。
    加速点仅在 AUC：01 的 tie 处理是纯 Python 循环，这里用 scipy.rankdata（数学同值）。
    """
    rng = np.random.RandomState(seed)
    n = len(y)
    accs, precs, recs, f1s, aucs = [], [], [], [], []
    for _ in range(B):
        idx = rng.randint(0, n, n)
        ys, ss = y[idx], score[idx]
        m = ev.threshold_metrics(ys, ss)
        accs.append(m["acc"])
        precs.append(m["prec"])
        recs.append(m["rec"])
        f1s.append(m["f1"])
        a = fast_auc(ys, ss)
        if not np.isnan(a):
            aucs.append(a)
    out = {}
    for k, vals in (
        ("acc", accs),
        ("prec", precs),
        ("rec", recs),
        ("f1", f1s),
        ("roc_auc", aucs),
    ):
        arr = np.array(vals, dtype=np.float64)
        out[k] = {
            "ci95": [float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5))],
            "bootstrap_mean": float(arr.mean()),
            "bootstrap_n": int(len(arr)),
        }
    return out


def build_payload(
    unit: str, y: np.ndarray, s: np.ndarray, meta_extra: dict, csv_path: Path
) -> dict:
    metrics = ev.threshold_metrics(y, s)
    ci = fast_bootstrap(y, s, ev.BOOTSTRAP_B, ev.BOOTSTRAP_SEED)
    auc_point = fast_auc(y, s)
    return {
        "_note": (
            "ROUND_27 G2 迁移评估（降级单元）——见 TRANSFER_MATRIX.md 的裁定；"
            "本文件不是「公平基线」，指标只作下界/压力测试解读"
        ),
        "unit": unit,
        "method": "bootstrap over persisted per-sample scores",
        "threshold": 0.5,
        "fairness": meta_extra["fairness"],
        "dataset": meta_extra["dataset"],
        "feature_mapping": meta_extra.get("feature_mapping"),
        "missing_handling": meta_extra.get("missing_handling"),
        "acc": {"point": round(metrics["acc"], 6), "ci95": [round(v, 6) for v in ci["acc"]["ci95"]]},
        "prec": {"point": round(metrics["prec"], 6), "ci95": [round(v, 6) for v in ci["prec"]["ci95"]]},
        "rec": {"point": round(metrics["rec"], 6), "ci95": [round(v, 6) for v in ci["rec"]["ci95"]]},
        "f1": {"point": round(metrics["f1"], 6), "ci95": [round(v, 6) for v in ci["f1"]["ci95"]]},
        "roc_auc": {"point": round(auc_point, 6), "ci95": [round(v, 6) for v in ci["roc_auc"]["ci95"]]},
        "meta": {
            "n": metrics["n"],
            "TP": metrics["TP"],
            "FP": metrics["FP"],
            "FN": metrics["FN"],
            "TN": metrics["TN"],
            "bootstrap_B": ev.BOOTSTRAP_B,
            "seed": ev.BOOTSTRAP_SEED,
            "point_estimator": "full-sample statistic (not bootstrap mean)",
        },
        "reproducibility": {
            "predictions_csv": csv_path.name,
            "predictions_csv_sha256": sha(csv_path),
            "env": ev.env_fingerprint(),
            "rerun": f"cd backend && .venv/Scripts/python.exe "
            f"scripts/modeling/eval/v1_29/02_transfer_eval.py --unit {unit}",
            "recompute_command": f"cd backend && .venv/Scripts/python.exe "
            f"scripts/modeling/eval/v1_29/02_transfer_eval.py --unit {unit} --report-only",
        },
    }


def write_json_and_report(unit: str, payload: dict) -> Path:
    DOCS.mkdir(parents=True, exist_ok=True)
    jp = DOCS / f"transfer_{unit}_eval.json"
    jp.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )
    m = payload["meta"]
    d = payload["dataset"]
    lines = [
        f"# 迁移评估（降级单元）：{unit}",
        "",
        f"> **样本量先说：n = {m['n']}。** 本单元是"
        f"**{payload['fairness']}**，指标只能读作下界/压力测试，不是公平基线。",
        "",
        f"- 数据集：{d['name']}（{d['rows']} 行；{d['note']}）",
        f"- 判定阈值：`y_score >= 0.5`",
        f"- CI：bootstrap 分位（B={payload['meta']['bootstrap_B']}, seed={payload['meta']['seed']}）",
        "",
        "| 指标 | 点估计 | 95% CI |",
        "|---|---|---|",
    ]
    for k, label in (("acc", "Accuracy"), ("prec", "Precision"), ("rec", "Recall"), ("f1", "F1"), ("roc_auc", "ROC AUC")):
        p = payload[k]
        lines.append(f"| {label} | {p['point']:.4f} | [{p['ci95'][0]:.4f}, {p['ci95'][1]:.4f}] |")
    lines += [
        "",
        f"混淆矩阵：TP={m['TP']} / FP={m['FP']} / FN={m['FN']} / TN={m['TN']}",
        "",
        f"- 逐样本：`backend/models/artifacts/eval_transfer/{payload['reproducibility']['predictions_csv']}`"
        f"（sha256 `{payload['reproducibility']['predictions_csv_sha256'][:16]}…`）",
        f"- 复跑：`{payload['reproducibility']['rerun']}`",
        f"- 复算：`{payload['reproducibility']['recompute_command']}`",
    ]
    mp = DOCS / f"transfer_{unit}_report.md"
    mp.write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")
    return mp


# ────────────────────────── 单元 A：文本 × OOD(strict) ──────────────────────────


def ood_strict_rows() -> tuple[list[int], np.ndarray, np.ndarray]:
    """构造 S2_ood_strict（与训练语料精确去重），复用 v1_27/02 的泄漏标注口径。"""
    import joblib
    import pandas as pd

    ood = pd.read_csv(OOD_PATH)
    ood = ood[ood["text"].astype(str).str.len() >= 5].copy()
    ood["label"] = ood["phq9_binary"].astype(int)
    ood["text"] = ood["text"].astype(str)

    v1 = pd.read_csv(ZH_V1)
    v1 = v1[v1["text"].astype(str).str.len() >= 5].copy()
    v1["text"] = v1["text"].astype(str)
    v1_groups = {
        str(k): set(v1[v1["augmentation"].fillna("original") == k]["text"])
        for k in v1["augmentation"].fillna("original").unique()
    }
    v2 = pd.read_csv(ZH_V2)
    v2 = v2[v2["augmentation"].fillna("original") == "original"]
    v2_texts = set(v2["text"].astype(str))

    train_texts: set[str] = set()
    for k, texts in v1_groups.items():
        if k != "original":
            train_texts |= texts
    if EN_PATH.exists():
        en = pd.read_csv(EN_PATH)
        en = en.dropna(subset=["clean_text", "is_depression"])
        train_texts |= set(en["clean_text"].astype(str))

    mask = ~(
        ood["text"].isin(v1_groups.get("original", set()))
        | ood["text"].isin(v2_texts)
        | ood["text"].isin(train_texts)
    )
    sub = ood[mask].reset_index(drop=True)

    tfidf = joblib.load(TEXT_TFIDF)
    model = joblib.load(TEXT_MODEL)
    score = model.predict_proba(tfidf.transform(sub["text"].tolist()))[:, 1]
    return list(range(len(sub))), sub["label"].to_numpy(dtype=np.int64), np.asarray(score, dtype=np.float64)


# ────────────────────────── 单元 B：生理 × Kaggle Wearable ──────────────────────────


#: 生产路径对未提供字段使用的默认值（predict.py::_predict_physiological_sync 的 raw_data）
PROD_DEFAULTS = {
    "sleep_quality": 5.0,
    "exercise_minutes": 30.0,
    "systolic_bp": 120.0,
    "diastolic_bp": 80.0,
}


def kaggle_rows() -> tuple[list[int], np.ndarray, np.ndarray]:
    import pandas as pd

    from app.ml.feature_engineering import engineer_features
    from app.ml.model_loader import load_cleaner, load_feature_names, load_model, load_scaler

    k = pd.read_csv(KAGGLE_PATH)
    df = pd.DataFrame(
        {
            "sleep_hours": k["Sleep_Duration_Hours"].astype(float),
            "heart_rate": k["Heart_Rate_BPM"].astype(float),
            "steps": k["Physical_Activity_Steps"].astype(float),
        }
    )
    for col, default in PROD_DEFAULTS.items():
        df[col] = default
    df = df[["sleep_hours", "sleep_quality", "exercise_minutes", "heart_rate", "systolic_bp", "diastolic_bp", "steps"]]
    y = k["Mental_Health_Condition"].to_numpy(dtype=np.int64)

    cleaner = load_cleaner()
    feats = load_feature_names()
    model = load_model()
    scaler = load_scaler()

    cleaned = cleaner.transform(df)  # 已无 NaN ⇒ 不会被 drop_high_missing_samples 丢弃
    engineered = engineer_features(cleaned)
    X = engineered[feats].values.astype(np.float32)
    score = np.asarray(model.predict_proba(scaler.transform(X))).reshape(-1)
    return list(range(len(k))), y, np.asarray(score, dtype=np.float64)


UNITS = {
    "text_ood": {
        "builder": ood_strict_rows,
        "fairness": "域内压力测试（OOD 与训练语料精确去重，但仍是同源 original 的 EDA 改写）——非外迁、非公平基准",
        "dataset": {
            "name": "data/external/ood_test_set_v2.csv（S2_ood_strict 子集）",
            "rows": 2523,
            "note": "1275 original 全在训练语料、1175 mmpsy_augmented 全在训练增强集（均泄漏）；此处仅保留与训练语料精确不重叠的 2523 条",
        },
        "feature_mapping": {"text": "TF-IDF（improved_bilingual_tfidf.pkl）"},
        "missing_handling": "不适用（文本列齐全）",
    },
    "physio_kaggle": {
        "builder": kaggle_rows,
        "fairness": "跨数据集压力测试（4/7 原始特征为生产默认常量、3/13 派生特征真实）——下界、非公平基准",
        "dataset": {
            "name": "datasets/physiological/external/kaggle_wearable/mental_health_wearable_data.csv",
            "rows": 10000,
            "note": "未确证未参与 v2 训练（训练脚本未入库）；标签 = Mental_Health_Condition",
        },
        "feature_mapping": {
            "Sleep_Duration_Hours": "sleep_hours",
            "Heart_Rate_BPM": "heart_rate",
            "Physical_Activity_Steps": "steps",
            "（缺）sleep_quality": "生产默认 5.0",
            "（缺）exercise_minutes": "生产默认 30.0",
            "（缺）systolic_bp": "生产默认 120.0",
            "（缺）diastolic_bp": "生产默认 80.0",
        },
        "missing_handling": (
            "缺列按 predict.py::_predict_physiological_sync 的 raw_data 默认值填充"
            "（sleep_quality=5, exercise_minutes=30, systolic_bp=120, diastolic_bp=80），"
            "随后仍走 artifact cleaner 的 winsor 边界；不丢弃任何行"
        ),
    },
}


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--unit", required=True, choices=sorted(UNITS))
    ap.add_argument("--report-only", action="store_true")
    ap.add_argument(
        "--verify-fast",
        action="store_true",
        help="在 text_ood 上对拍 fast_* 与 01 的 bootstrap_ci/auc_score（应逐位一致）",
    )
    args = ap.parse_args(argv)

    if args.verify_fast:
        y, s = read_predictions(OUT_DIR / "transfer_text_ood_predictions.csv")
        a1 = ev.auc_score(y, s)
        a2 = fast_auc(y, s)
        c1 = ev.bootstrap_ci(y, s, ev.BOOTSTRAP_B, ev.BOOTSTRAP_SEED)
        c2 = fast_bootstrap(y, s, ev.BOOTSTRAP_B, ev.BOOTSTRAP_SEED)
        diffs = {k: (abs(c1[k]["ci95"][0] - c2[k]["ci95"][0]), abs(c1[k]["ci95"][1] - c2[k]["ci95"][1])) for k in c1}
        print(f"auc: slow={a1!r} fast={a2!r} diff={abs(a1-a2):.3e}")
        for k, (d0, d1) in diffs.items():
            print(f"  {k}: slow={c1[k]['ci95']} fast={c2[k]['ci95']} diff=({d0:.3e},{d1:.3e})")
        worst = max(max(v) for v in diffs.values())
        print(f"[verify-fast] max ci diff = {worst:.3e} -> {'PASS' if worst < 1e-9 else 'DIFF'}")
        return 0 if worst < 1e-9 else 1

    spec = UNITS[args.unit]
    OUT_DIR.mkdir(parents=True, exist_ok=True)
    csv_path = OUT_DIR / f"transfer_{args.unit}_predictions.csv"

    if args.report_only:
        y, s = read_predictions(csv_path)
        payload = build_payload(args.unit, y, s, spec, csv_path)
        mp = write_json_and_report(args.unit, payload)
        print(f"[report-only] {args.unit} n={payload['meta']['n']} "
              f"f1={payload['f1']['point']} -> {mp.name}")
        return 0

    idx, y, s = spec["builder"]()
    rows = [(int(i), int(y[i]), float(s[i])) for i in range(len(y))]
    rows.sort(key=lambda r: r[0])  # 落盘序 == 计算序（与 A 摊同口径）
    write_predictions(csv_path, rows)

    y_sorted = np.array([r[1] for r in rows], dtype=np.int64)
    s_sorted = np.array([r[2] for r in rows], dtype=np.float64)
    payload = build_payload(args.unit, y_sorted, s_sorted, spec, csv_path)
    mp = write_json_and_report(args.unit, payload)

    m = payload["meta"]
    print(
        f"[{args.unit}] n={m['n']} TP={m['TP']} FP={m['FP']} FN={m['FN']} TN={m['TN']}\n"
        f"  f1={payload['f1']['point']} {payload['f1']['ci95']}\n"
        f"  auc={payload['roc_auc']['point']} {payload['roc_auc']['ci95']}\n"
        f"  rec={payload['rec']['point']} prec={payload['prec']['point']}\n"
        f"  csv sha256={payload['reproducibility']['predictions_csv_sha256']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
