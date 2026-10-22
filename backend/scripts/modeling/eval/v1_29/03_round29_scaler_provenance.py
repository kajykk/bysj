#!/usr/bin/env python
"""ROUND_29 (T1)：scaler provenance 诊断——现有 model.json 权重是否与
「当前 depresjon 数据 + 训练切分拟合的 scaler」配套？

纪律（ROUND_29 提示词 §一 T1 / §二）
------------------------------------
- **全部 train-only**：scaler 只在训练切分（或 CV 折的训练侧）上拟合；
  绝不 fit 在任何含 test 的数据上；test/折-验证侧只做推理评估。
- 诊断不改任何工件、不写任何文件（只打印；数字由审计文档收录）。
- 复用评估壳 01 的同一套函数（split_indices / build_features / predict_scores /
  threshold_metrics / auc_score）⇒ 与生产链、与已提交评估同源。

判定规则（**先注册后运行**，防「看完结果再定标准」）
--------------------------------------------------
在**非 test 的 872 行**上做 5 折 × 3 次重抽的重复 CV（每次折：生产 cleaner 固定，
scaler 在折-训练侧重拟合，固定权重推理，在折-验证侧算 recall）：

- 拟合-scaler 的 recall **均值 ≥ 0.90 且 std ≤ 0.03 且 min ≥ 0.85**
  ⇒ 权重与当前数据兼容 ⇒ **路径 A**（只重建 scaler，不换权重）；
- 否则（剧烈波动或远低于 0.94）⇒ 权重来自别的数据 ⇒ **路径 B**（端到端重训）。

同时做两项连续性断言（证明诊断口径与已提交产物同源）：
1. 生产（错配）scaler 在 test 上的分数 == 已提交 csv 的 `y_score` 列；
2. 训练切分重拟合 scaler 在 test 上的分数 == 已提交 csv 的
   `y_score_refit_scaler` 列 ⇒ 已公布的「诊断对照 0.9455/0.9369」就是本口径。

用法：
    cd backend
    .venv/Scripts/python.exe scripts/modeling/eval/v1_29/03_round29_scaler_provenance.py
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parents[4]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.ml.data_loader import load_depresjon_data  # noqa: E402
from app.ml.model_loader import (  # noqa: E402
    load_cleaner,
    load_feature_names,
    load_model,
    load_scaler,
)
from app.ml.scaler import SimpleStandardScaler  # noqa: E402

EVAL01_PATH = Path(__file__).resolve().parent / "01_reproducible_eval.py"
PREDICTIONS_CSV = (
    BACKEND / "models" / "artifacts" / "physiological_optimized" / "test_predictions.csv"
)
EVAL_JSON = BACKEND.parent / "docs" / "model-evaluation" / "physio_v2_current_data_eval.json"


def _load_eval01():
    """把评估壳 01 当模块导入（其 main 有 __main__ 保护，无副作用）。"""
    spec = importlib.util.spec_from_file_location("eval01_round29", EVAL01_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def stratified_folds(y: np.ndarray, idx: np.ndarray, k: int, seed: int) -> list[np.ndarray]:
    """确定性分层 k 折：正/负各自 shuffle 后轮询分配；返回每折的验证侧索引。"""
    rng = np.random.RandomState(seed)
    folds: list[list[int]] = [[] for _ in range(k)]
    for cls in np.unique(y):
        cls_idx = idx[y[idx] == cls]
        cls_idx = cls_idx.copy()
        rng.shuffle(cls_idx)
        for j, sample in enumerate(cls_idx):
            folds[j % k].append(int(sample))
    return [np.array(sorted(f), dtype=np.int64) for f in folds]


def main() -> int:
    e01 = _load_eval01()

    df = load_depresjon_data()
    y = df["depression_label"].values.astype(np.int64)

    tri, vai, tei = e01.split_indices(y)
    assert (len(tri), len(vai), len(tei)) == (719, 153, 157), (
        f"切分尺寸异常：{len(tri)}/{len(vai)}/{len(tei)}"
    )

    # 已提交 csv 的 row_index 必须正是本次切分的 test 集（口径连续性）
    csv_lines = PREDICTIONS_CSV.read_text(encoding="utf-8").strip().splitlines()[1:]
    csv_rows = sorted(int(ln.split(",")[1]) for ln in csv_lines)
    assert csv_rows == sorted(int(i) for i in tei), (
        "已提交 test_predictions.csv 的 row_index 与本次切分 test 集不一致——"
        "csv 不是同一测试集，诊断前提不成立"
    )
    # csv 按 row_index 升序落盘 ⇒ 复算分数也必须按 row_index 升序对齐后再比
    # （tei 本身是 shuffle 序，直接比会得到「连续性断裂」的假象——本轮实测踩过）
    csv_sorted = sorted(
        ((int(ln.split(",")[1]), int(ln.split(",")[2]),
          float(ln.split(",")[3]), float(ln.split(",")[5])) for ln in csv_lines),
        key=lambda r: r[0],
    )
    y_csv = np.array([r[1] for r in csv_sorted], dtype=np.int64)
    s_csv = np.array([r[2] for r in csv_sorted], dtype=np.float64)
    s_refit_csv = np.array([r[3] for r in csv_sorted], dtype=np.float64)

    def _align(scores: np.ndarray) -> np.ndarray:
        """把 tei 顺序的分数重排为 row_index 升序（与 csv 落盘序一致）。"""
        pairs = sorted(zip((int(i) for i in tei), scores), key=lambda p: p[0])
        return np.array([p[1] for p in pairs], dtype=np.float64)

    cleaner = load_cleaner()
    model = load_model()
    broken = load_scaler()
    feats = load_feature_names()
    assert broken.n_features_in_ == len(feats) == 13

    X_train = e01.build_features(df, tri, cleaner, feats)
    X_test = e01.build_features(df, tei, cleaner, feats)
    y_test = y[tei]

    # ── 1) 单次确定性切分：训练侧重拟合 scaler ──
    fitted = SimpleStandardScaler().fit(X_train)
    s_broken_test = e01.predict_scores(X_test, model, broken)
    s_fitted_test = e01.predict_scores(X_test, model, fitted)

    assert np.allclose(_align(s_broken_test), s_csv, rtol=0, atol=1e-12), (
        "错配 scaler 的 test 分数与已提交 csv 生产列不一致（连续性断裂）"
    )
    assert np.allclose(_align(s_fitted_test), s_refit_csv, rtol=0, atol=1e-12), (
        "训练侧重拟合 scaler 的 test 分数与已提交 csv 诊断列不一致——"
        "已公布的 0.9455/0.9369 不是 train-only 口径？"
    )

    m_broken = e01.threshold_metrics(y_test, s_broken_test)
    m_fitted = e01.threshold_metrics(y_test, s_fitted_test)
    auc_broken = e01.auc_score(y_test, s_broken_test)
    auc_fitted = e01.auc_score(y_test, s_fitted_test)

    payload = json.loads(EVAL_JSON.read_text(encoding="utf-8"))
    diag = payload["diagnostic_refit_scaler"]
    for key, got in (("f1", m_fitted["f1"]), ("rec", m_fitted["rec"]),
                     ("roc_auc", auc_fitted)):
        assert abs(float(diag[key]) - got) < 1e-6, (
            f"诊断列与 json {key} 不符：json {diag[key]} vs 复算 {got}"
        )

    print("=" * 78)
    print("T1-1 确定性切分（train 719 拟合 scaler，test 157 只推理）")
    print("=" * 78)
    print(f"  错配 scaler（修复前生产口径）: rec={m_broken['rec']:.4f} "
          f"f1={m_broken['f1']:.4f} auc={auc_broken:.4f}  CM TP={m_broken['TP']} "
          f"FP={m_broken['FP']} FN={m_broken['FN']} TN={m_broken['TN']}")
    print(f"  重拟合 scaler（修复后口径）  : rec={m_fitted['rec']:.4f} "
          f"f1={m_fitted['f1']:.4f} auc={auc_fitted:.4f}  CM TP={m_fitted['TP']} "
          f"FP={m_fitted['FP']} FN={m_fitted['FN']} TN={m_fitted['TN']}")
    print(f"  json 诊断块对照             : f1={diag['f1']} rec={diag['rec']} "
          f"auc={diag['roc_auc']}（逐项一致，容差 1e-6）")
    print(f"  连续性：csv 生产列/诊断列均与本次复算逐点相等（atol=1e-12）")

    print()
    print("  重拟合 scaler 参数（按 feature_names.json 顺序）：")
    for name, mu, sd in zip(feats, fitted.mean_, fitted.scale_):
        print(f"    {name:24s} mean={mu:14.6f}  scale={sd:14.6f}")

    # ── 2) 重复 CV（只用非 test 的 872 行）──
    non_test = np.concatenate([tri, vai])
    assert not set(int(i) for i in non_test) & set(int(i) for i in tei), (
        "非 test 集与 test 集有交集——CV 前提被破坏"
    )

    repeats, k = 3, 5
    rows = []
    for rep in range(repeats):
        folds = stratified_folds(y, non_test, k=k, seed=100 + rep)
        for fi, val_idx in enumerate(folds, 1):
            tr_idx = np.array(sorted(set(int(i) for i in non_test) - set(int(i) for i in val_idx)),
                              dtype=np.int64)
            X_tr = e01.build_features(df, tr_idx, cleaner, feats)
            X_va = e01.build_features(df, val_idx, cleaner, feats)
            y_va = y[val_idx]
            sc = SimpleStandardScaler().fit(X_tr)
            s_new = e01.predict_scores(X_va, model, sc)
            s_old = e01.predict_scores(X_va, model, broken)
            m_new = e01.threshold_metrics(y_va, s_new)
            m_old = e01.threshold_metrics(y_va, s_old)
            rows.append({
                "repeat": rep, "fold": fi, "n_val": len(val_idx),
                "rec_new": m_new["rec"], "f1_new": m_new["f1"],
                "auc_new": e01.auc_score(y_va, s_new),
                "rec_old": m_old["rec"], "f1_old": m_old["f1"],
            })

    rec_new = np.array([r["rec_new"] for r in rows])
    f1_new = np.array([r["f1_new"] for r in rows])
    auc_new = np.array([r["auc_new"] for r in rows])
    rec_old = np.array([r["rec_old"] for r in rows])

    print()
    print("=" * 78)
    print(f"T1-2 重复 CV：非 test 872 行，{k} 折 × {repeats} 次重抽（生产 cleaner 固定，"
          f"scaler 只在折-训练侧拟合）")
    print("=" * 78)
    for r in rows:
        print(f"  rep{r['repeat']} fold{r['fold']} (n={r['n_val']:3d}): "
              f"重拟合 rec={r['rec_new']:.4f} f1={r['f1_new']:.4f} auc={r['auc_new']:.4f} | "
              f"错配 rec={r['rec_old']:.4f} f1={r['f1_old']:.4f}")
    print("-" * 78)
    print(f"  重拟合 scaler: recall mean={rec_new.mean():.4f} std={rec_new.std(ddof=1):.4f} "
          f"min={rec_new.min():.4f} max={rec_new.max():.4f}")
    print(f"                 f1     mean={f1_new.mean():.4f} std={f1_new.std(ddof=1):.4f} "
          f"min={f1_new.min():.4f} max={f1_new.max():.4f}")
    print(f"                 auc    mean={auc_new.mean():.4f} std={auc_new.std(ddof=1):.4f}")
    print(f"  错配 scaler  : recall mean={rec_old.mean():.4f} std={rec_old.std(ddof=1):.4f} "
          f"min={rec_old.min():.4f} max={rec_old.max():.4f}")

    # ── 3) 判定（规则见 docstring，先注册后运行）──
    stable = (rec_new.mean() >= 0.90) and (rec_new.std(ddof=1) <= 0.03) and (rec_new.min() >= 0.85)
    print()
    print("=" * 78)
    if stable:
        print("判定：**路径 A**——权重与当前数据兼容（重拟合 scaler 的 recall 分布稳定在高位，")
        print("      且错配 scaler 在所有折上都低）⇒ 只重建 scaler，不换权重。")
    else:
        print("判定：**路径 B**——重拟合 scaler 的 recall 分布不稳定或低位 ⇒ 权重与当前数据")
        print("      不兼容，须端到端重训（训练脚本入库）。")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
