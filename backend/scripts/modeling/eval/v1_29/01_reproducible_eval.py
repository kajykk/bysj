#!/usr/bin/env python
"""ROUND_26 (G1)：physiological_optimized 的可复跑评估。

设计原则（对应 docs/P2_53_ROUND26_EVAL_REPRODUCIBILITY_AUDIT.md §二 五条门槛）：

1. **可复算**：同一输入连跑两次，`test_predictions.csv` 字节一致（sha256 相同）。
   切分、bootstrap、行序、浮点格式全部确定性；无时间戳进入产物。
2. **自洽**：报告的 n / TP/FP/FN/TN 由逐样本预测直接数出，与 `meta` 同源。
3. **CI 口径**：AUC 与阈值类指标的 95% CI 一律 **bootstrap 分位**（B=10000, seed=42），
   不使用 Hanley-McNeil 解析近似。
4. **可核验**：报告里每个数字都能由 `test_predictions.csv` + 一条命令复算
   （`--report-only` 模式就是那条命令）。
5. **不得自证**：脚本**不读取** `docs/model-evaluation/physio_v2_test_ci.json`
   的任何旧值；`--report-only` 只信 csv。

关于「原测试集」的实测结论（2026-10-23 诊断；ROUND_29 已修复其中缺陷）：

    仓内唯一的切分函数 `app.ml.data_split.stratified_split`（两个历史版本逐行相同）
    在 depresjon 1029 行（359 阳性 / 670 阴性）上恒给出 719 / 153 / 157，
    **不是** `metrics.json` 记录的 719 / 171 / 139。且**修复前** artifact 的
    `scaler.json` 统计量与仓内三份生理数据（depresjon / augmented / kaggle）任一都不匹配
    （sleep_quality 均值 5.43 超出 1-5 量表），用那个 scaler 变换当前数据后
    z 分数整体偏移（多列 |mean_z| > 1）。
    ⇒ 原 139 行测试集**不可复现**（训练数据版本不在仓内、训练脚本从未入库）。
    本脚本因此**不冒充原测试集**：它评估的是「当前仓内数据上的确定性切分」，
    并在报告与 json 里显式标注 `dataset = "depresjon_physiological.csv@当前版本"`。

ROUND_29（D-R26-1 整改，路径 B 端到端重训）：
    上述「scaler 与数据版本不配套」缺陷已由 `v1_29/04_round29_retrain_physiological.py`
    修复——cleaner/scaler 只在 train 719 行上拟合、模型经该 scaler 训练
    （co-consistent by construction），固定 seed 42，同 seed 两跑产物逐字节一致；
    修复前工件存档为 `*.broken_round29`。本报告评估的是**新生产链**；
    `y_score_refit_scaler` 列由「缺陷定位」变为「co-consistency 证明」——它与
    `y_score` 逐位相等，不相等即缺陷复发（参数级判据见
    `tests/test_p2_56_round29_scaler_consistency.py` 第一层）。

用法：

    cd backend
    .venv/Scripts/python.exe scripts/modeling/eval/v1_29/01_reproducible_eval.py
        # 完整评估：重建测试集 → 生产链推理 → 写 csv + json + 报告

    .venv/Scripts/python.exe scripts/modeling/eval/v1_29/01_reproducible_eval.py --verify-original
        # 只做「能否复现 719/171/139」的诊断（不写产物）

    .venv/Scripts/python.exe scripts/modeling/eval/v1_29/01_reproducible_eval.py --report-only
        # 只读 test_predictions.csv 重算指标/CI 并重写报告（外部审稿人的复算入口）
"""

from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parents[4]  # backend/
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.ml.data_loader import load_depresjon_data  # noqa: E402
from app.ml.feature_engineering import engineer_features  # noqa: E402
from app.ml.model_loader import (  # noqa: E402
    load_cleaner,
    load_feature_names,
    load_model,
    load_scaler,
)

ARTIFACTS_DIR = BACKEND / "models" / "artifacts" / "physiological_optimized"
PREDICTIONS_CSV = ARTIFACTS_DIR / "test_predictions.csv"
PREDICTIONS_SHA = ARTIFACTS_DIR / "test_predictions.csv.sha256"
EVAL_JSON = BACKEND.parent / "docs" / "model-evaluation" / "physio_v2_current_data_eval.json"
REPORT_MD = BACKEND.parent / "docs" / "model-evaluation" / "PHYSIO_V2_EVAL_REPORT.md"

BOOTSTRAP_B = 10000
BOOTSTRAP_SEED = 42
THRESHOLD = 0.5
EXPECTED_SPLIT = {"train": 719, "val": 171, "test": 139}  # metrics.json 的记录值
RECORDED_META = {"n": 139, "TP": 41, "FP": 3, "FN": 11, "TN": 84}


# ────────────────────────── 确定性切分 ──────────────────────────


def split_indices(y: np.ndarray, seed: int = 42) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """复刻 app.ml.data_split.stratified_split 的索引（0.7/0.15/0.15, rs=42）。

    函数本身只返回切分后的数组；为保留 sample_id，这里按同一算法算索引，
    并在 main 里用 `stratified_split` 的返回形状做一致性断言（见 _assert_split_matches）。
    """
    rng = np.random.RandomState(seed)
    tri, vai, tei = [], [], []
    for cls in np.unique(y):
        idx = np.where(y == cls)[0]
        rng.shuffle(idx)
        n_train = int(len(idx) * 0.7)
        n_val = int(len(idx) * 0.15)
        tri.extend(idx[:n_train])
        vai.extend(idx[n_train : n_train + n_val])
        tei.extend(idx[n_train + n_val :])
    rng.shuffle(tri)
    rng.shuffle(vai)
    rng.shuffle(tei)
    return np.array(tri), np.array(vai), np.array(tei)


def _assert_split_matches(y: np.ndarray, tri, vai, tei) -> None:
    """与库函数互证：索引长度必须等于 stratified_split 的返回长度。"""
    from app.ml.data_split import stratified_split

    dummy = np.zeros((len(y), 1), dtype=np.float32)
    _, _, _, yt, yv, ys = stratified_split(dummy, y.astype(np.float32).reshape(-1, 1))
    assert (len(tri), len(vai), len(tei)) == (len(yt), len(yv), len(ys)), (
        f"索引长度 {len(tri)}/{len(vai)}/{len(tei)} 与 stratified_split "
        f"{len(yt)}/{len(yv)}/{len(ys)} 不一致"
    )


# ────────────────────────── 生产链推理 ──────────────────────────


def build_features(df, idx: np.ndarray, cleaner, feats: list[str]) -> np.ndarray:
    """复刻生产推理链：cleaner.transform → engineer_features → 按 feature_names 排序。

    对应 predict.py::_predict_physiological_sync（批量版；transform_single 与
    transform 共用同一份 medians/winsor_bounds）。
    """
    cleaned = cleaner.transform(df.iloc[idx])
    engineered = engineer_features(cleaned)
    return engineered[feats].values.astype(np.float32)


def predict_scores(X: np.ndarray, model, scaler) -> np.ndarray:
    scaled = scaler.transform(X)
    return np.asarray(model.predict_proba(scaled)).reshape(-1)


def refit_scaled_scores(X_train: np.ndarray, X: np.ndarray, model) -> np.ndarray:
    """诊断口径：在当前训练集上重新拟合 StandardScaler 后的分数。

    仅用于回答「模型权重本身是否与当前数据匹配」——**不是**生产路径。
    """
    from app.ml.scaler import SimpleStandardScaler

    refit = SimpleStandardScaler().fit(X_train)
    return np.asarray(model.predict_proba(refit.transform(X))).reshape(-1)


# ────────────────────────── 指标与 bootstrap ──────────────────────────


def threshold_metrics(y: np.ndarray, score: np.ndarray, thr: float = THRESHOLD) -> dict:
    pred = (score >= thr).astype(int)
    tp = int(((pred == 1) & (y == 1)).sum())
    fp = int(((pred == 1) & (y == 0)).sum())
    fn = int(((pred == 0) & (y == 1)).sum())
    tn = int(((pred == 0) & (y == 0)).sum())
    n = tp + fp + fn + tn
    acc = (tp + tn) / n
    prec = tp / (tp + fp) if (tp + fp) else 0.0
    rec = tp / (tp + fn) if (tp + fn) else 0.0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) else 0.0
    return {
        "n": n,
        "TP": tp,
        "FP": fp,
        "FN": fn,
        "TN": tn,
        "acc": acc,
        "prec": prec,
        "rec": rec,
        "f1": f1,
    }


def auc_score(y: np.ndarray, score: np.ndarray) -> float:
    """Mann-Whitney U 形式的 ROC AUC（与 sklearn 同值，避免额外依赖）。

    ties 用平均秩处理。全正或全负时返回 nan（bootstrap 抽样可能出现）。
    """
    pos = score[y == 1]
    neg = score[y == 0]
    if len(pos) == 0 or len(neg) == 0:
        return float("nan")
    order = np.argsort(np.concatenate([pos, neg]), kind="mergesort")
    ranks = np.empty(len(order), dtype=np.float64)
    ranks[order] = np.arange(1, len(order) + 1, dtype=np.float64)
    # 平均秩（ties）
    combined = np.concatenate([pos, neg])
    sorted_vals = combined[order]
    i = 0
    while i < len(sorted_vals):
        j = i
        while j + 1 < len(sorted_vals) and sorted_vals[j + 1] == sorted_vals[i]:
            j += 1
        if j > i:
            avg = (ranks[order[i : j + 1]].mean())
            ranks[order[i : j + 1]] = avg
        i = j + 1
    rank_sum_pos = ranks[: len(pos)].sum()
    u = rank_sum_pos - len(pos) * (len(pos) + 1) / 2.0
    return float(u / (len(pos) * len(neg)))


def bootstrap_ci(y: np.ndarray, score: np.ndarray, B: int, seed: int) -> dict:
    """逐指标的非参数 bootstrap 95% CI（分位法），含 AUC。"""
    rng = np.random.RandomState(seed)
    n = len(y)
    keys = ("acc", "prec", "rec", "f1", "roc_auc")
    samples = {k: [] for k in keys}
    for _ in range(B):
        idx = rng.randint(0, n, n)
        ys, ss = y[idx], score[idx]
        m = threshold_metrics(ys, ss)
        for k in ("acc", "prec", "rec", "f1"):
            samples[k].append(m[k])
        a = auc_score(ys, ss)
        if not np.isnan(a):
            samples["roc_auc"].append(a)
    out = {}
    for k in keys:
        arr = np.array(samples[k], dtype=np.float64)
        out[k] = {
            "ci95": [float(np.percentile(arr, 2.5)), float(np.percentile(arr, 97.5))],
            "bootstrap_mean": float(arr.mean()),
            "bootstrap_n": int(len(arr)),
        }
    return out


# ────────────────────────── 产物 I/O ──────────────────────────


def sha256_of(path: Path) -> str:
    h = hashlib.sha256()
    h.update(path.read_bytes())
    return h.hexdigest()


def write_predictions_csv(rows: list[tuple[int, int, float, int, float]]) -> None:
    """列：sample_id,row_index,y_true,y_score,y_pred,y_score_refit_scaler。

    行序按 row_index 升序（确定性）；浮点用 **`.17g`（float64 往返精度）**。

    ROUND_27 修正：ROUND_26 用 `.6f` 舍入，导致 `--report-only` 从 csv 复算
    的 bootstrap CI 端点与全量运行（内存全精度）不一致（Recall 下界
    0.468733 → 0.471698，差 ±0.003）。`.17g` 保证 `float(text) == 原值`
    （float64 往返无损），两种模式由此逐位一致。
    """
    lines = ["sample_id,row_index,y_true,y_score,y_pred,y_score_refit_scaler"]
    for i, (row_index, y_true, y_score, y_pred, y_refit) in enumerate(rows):
        lines.append(
            f"physio_{i:04d},{row_index},{y_true},{y_score:.17g},{y_pred},{y_refit:.17g}"
        )
    text = "\n".join(lines) + "\n"
    PREDICTIONS_CSV.write_text(text, encoding="utf-8", newline="\n")
    digest = sha256_of(PREDICTIONS_CSV)
    PREDICTIONS_SHA.write_text(
        f"{digest}  test_predictions.csv\n", encoding="utf-8", newline="\n"
    )


def read_predictions_csv() -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """读回 csv（--report-only 的唯一数据源）。"""
    lines = PREDICTIONS_CSV.read_text(encoding="utf-8").strip().splitlines()
    header = lines[0].split(",")
    assert header[:5] == ["sample_id", "row_index", "y_true", "y_score", "y_pred"], header
    y, s = [], []
    for ln in lines[1:]:
        parts = ln.split(",")
        y.append(int(parts[2]))
        s.append(float(parts[3]))
    return np.array(y), np.array(s, dtype=np.float64), np.array([ln.split(",")[3] for ln in lines[1:]])


def env_fingerprint() -> dict:
    try:
        import pandas as pd

        pdv = pd.__version__
    except Exception:  # pragma: no cover
        pdv = "n/a"
    try:
        import sklearn

        skv = sklearn.__version__
    except Exception:  # pragma: no cover
        skv = "n/a"
    return {
        "python": platform.python_version(),
        "platform": platform.platform(),
        "numpy": np.__version__,
        "pandas": pdv,
        "scikit_learn": skv,
    }


def artifact_digests() -> dict:
    out = {}
    for name in ("model.json", "scaler.json", "cleaner_stats.json", "feature_names.json"):
        p = ARTIFACTS_DIR / name
        if p.exists():
            out[name] = sha256_of(p)
    return out


# ────────────────────────── 报告 ──────────────────────────


def write_report(metrics: dict, ci: dict, refit_metrics: dict, extra: dict) -> None:
    def fmt_ci(k: str) -> str:
        return f"[{ci[k]['ci95'][0]:.4f}, {ci[k]['ci95'][1]:.4f}]"

    auc_ci = fmt_ci("roc_auc")
    text = f"""# physiological_optimized · 可复跑评估报告

> **样本量先说：n = {metrics['n']}（单一切分、单一随机种子）。**
> 这个量级下 95% CI 的宽度是**结构性**的，不能据此主张高精度；
> 所有区间只能读作「该量级下点估计的波动范围」。

- 评估对象：`backend/models/artifacts/physiological_optimized/`（registry 中以 L1 主模型启用，见 `model_registry.py:142`）
- 数据集：**`datasets/physiological/external/depresjon_processed/depresjon_physiological.csv`（当前版本，1029 行）**
  的确定性切分 test 集（`stratified_split`, 0.7/0.15/0.15, `random_state=42`）
- 推理链：**生产路径**（`DataCleaner.transform` → `engineer_features` → `SimpleStandardScaler.transform` → MLP），
  与 `predict.py::_predict_physiological_sync` 同一套工件
- 判定阈值：`y_score >= {THRESHOLD}`
- 复跑命令：

```bash
cd backend
.venv/Scripts/python.exe scripts/modeling/eval/v1_29/01_reproducible_eval.py
# 只复算（不重建预测、不推理）：加 --report-only —— 会重写 JSON + 本报告，
# 且与全量运行的产物**逐字节一致**（ROUND_27 起 csv 存 float64 往返精度、
# 指标与 CI 按 csv 的行序计算）
```

## 一、与原记录的关系（不可复现，不冒充）

`metrics.json` 记录的测试集是 **n=139（TP=41 / FP=3 / FN=11 / TN=84）**，
本报告**没有**复现它，也不会用它替代它。实测证据（`--verify-original`；以下证据全部取自
**修复前** artifact，已存档为 `*.broken_round29`，ROUND_29 更换——它们解释的是
**旧 139 行测试集为何不可复现**，与当前生产链无关）：

| 检查项 | 实测 | 记录值 | 结论 |
|---|---|---|---|
| 切分输出（`stratified_split`, rs=42, 1029 行 359 阳性/670 阴性） | 719 / 153 / 157 | 719 / 171 / 139 | **不一致**；该函数两个历史版本逐行相同，输出恒定 |
| 修复前 `scaler.json`（存档）的 sleep_quality 均值 | 5.4279 | 5.4279 | 仓内三份数据（depresjon 2.84 / augmented 2.83 / kaggle Mood_Rating≈5.07）**都对不上**，且 5.43 超出 1-5 量表 |
| 修复前 artifact scaler 变换当前数据后的 z 分数 | 多列 abs(mean_z) > 1（sleep_quality -1.00、steps -1.41） | 应 ≈ 0 | **训练数据与当前数据不同版本** |

⇒ 原 139 行测试集**不可复现**：训练脚本从未入库，修复前 artifact 的 scaler 统计量指向
一份不在仓内的数据版本。本报告的数字属于**当前仓内数据版本**（ROUND_29 重训后的
co-consistent 工件），与旧记录**不可比**，任何对外材料不得混用两者。

## 二、指标（生产路径，n = {metrics['n']}）

| 指标 | 点估计 | 95% CI（bootstrap, B={BOOTSTRAP_B}, seed={BOOTSTRAP_SEED}） |
|---|---|---|
| Accuracy | {metrics['acc']:.4f} | {fmt_ci('acc')} |
| Precision | {metrics['prec']:.4f} | {fmt_ci('prec')} |
| Recall | {metrics['rec']:.4f} | {fmt_ci('rec')} |
| F1 | {metrics['f1']:.4f} | {fmt_ci('f1')} |
| ROC AUC | {extra['auc_point']:.4f} | {auc_ci} |

混淆矩阵：TP={metrics['TP']} / FP={metrics['FP']} / FN={metrics['FN']} / TN={metrics['TN']}

> **Recall {metrics['rec']:.4f} 是这份报告最需要被读到的数字**：在阈值 {THRESHOLD} 下，
> 每 10 个真实阳性会漏掉约 {round((1 - metrics['rec']) * 10)} 个。该读数是 ROUND_29
> 修复 D-R26-1（生产 scaler 与模型不配套）**之后**的生产链路实测；修复前在同一测试集上
> 为 0.6000（历史口径，不可比）。修复记录与「这是修标准化缺陷、不是模型变强」的论证见 §三。

## 三、D-R26-1 缺陷披露与 ROUND_29 修复记录（修标准化缺陷，不是模型变强）

**缺陷（修复前，存档口径）**：生产 artifact 的 `scaler.json` 与模型权重、训练数据三者
不同源（§一 第 2、3 行的证据取自修复前工件）。在**同一个** n = {metrics['n']} 测试集上，
修复前生产路径 Recall 仅 0.6000（TP=33 / FP=0 / FN=22 / TN=102，历史口径，不可比）；
只把标准化参数换成「当前训练集重拟合」时 Recall 0.9455 / F1 0.9369 / AUC 0.9841
（旧权重下的诊断读数，仅用于定位缺陷，不得宣称为性能）。

**修复（ROUND_29 · 路径 B 端到端重训）**：
`scripts/modeling/eval/v1_29/04_round29_retrain_physiological.py`——cleaner/scaler 只在
train 719 行上拟合，模型经该 scaler 训练（co-consistent by construction）；超参数沿用
`metrics.json` 记录值（不为迁就测试集调参）；固定 seed 42，同 seed 两跑产物逐字节一致；
修复前工件存档为 `*.broken_round29`，原子替换后生产路径复载校验 max|diff| = 0。
永久防复发闸门：`tests/test_p2_56_round29_scaler_consistency.py`（第一层可复现性：
部署 scaler == train-only 重拟合，实测 max|diff| = 0.000e+00；第二层域合理性；结构层）。

**修复后（本报告主口径，同一测试集、同一阈值 {THRESHOLD}）**：
Recall {metrics['rec']:.4f}（TP={metrics['TP']} / FP={metrics['FP']} / FN={metrics['FN']} /
TN={metrics['TN']}）、F1 {metrics['f1']:.4f}、ROC AUC {extra['auc_point']:.4f}。

| 链路 | F1 | Recall | ROC AUC |
|---|---|---|---|
| 生产路径（部署 artifact，co-consistent by construction） | {metrics['f1']:.4f} | {metrics['rec']:.4f} | {extra['auc_point']:.4f} |
| 诊断对照（train-only 独立重拟合；ROUND_29 后与生产逐位相等） | {refit_metrics['f1']:.4f} | {refit_metrics['rec']:.4f} | {extra['refit_auc']:.4f} |

**为什么这是修缺陷、不是模型变强**：修复后 ROC AUC 由修复前的 0.9884 **下降**到
{extra['auc_point']:.4f}——修复没有提高任何能力读数，它只是把生产链路换回与训练一致的
标准化，使阈值 {THRESHOLD} 重新有意义；修复前的高 AUC 是错配标准化下的读数，与修复后
不可比。另需如实记账：修复后单切分 Recall {metrics['rec']:.4f} **低于**修复前旧权重的
诊断读数 0.9455——本文不追这个数（在测试集上调参即泄漏，见台账 B-05）；新管线的重复
CV（5 折 × 3 次，与 provenance 诊断同折）Recall 为 0.88 ± 0.04，与单切分点估计同量级
（逐折明细见 `docs/P2_56_ROUND29_SCALER_FIX_AUDIT.md`）。

**一致性证明（csv 逐样本列）**：`y_score_refit_scaler`（train-only 独立重拟合过**同一套
生产权重**）与 `y_score` 逐位相等——两列相等即「部署 scaler 就是训练时那一个」的工件级
证据；参数级判据见 p2_56 闸门第一层。修复前那组 0.60 / 0.9455 只在此段作为变更记录出现，
**不得**作为任何性能主张引用。

## 四、可核验性（外部审稿人唯一需要的东西）

逐样本预测已落盘：

```
backend/models/artifacts/physiological_optimized/test_predictions.csv
  sha256 = {extra['csv_sha256']}
backend/models/artifacts/physiological_optimized/test_predictions.csv.sha256
```

列定义：`sample_id, row_index, y_true, y_score, y_pred, y_score_refit_scaler`。
`y_score` 是生产链输出；`y_score_refit_scaler` 是 §三 的一致性证明列——ROUND_29 起部署
scaler 与 train-only 重拟合逐位相等，故该列与 `y_score` **逐位相等**；一旦不相等即
D-R26-1 复发（参数级判据见 `tests/test_p2_56_round29_scaler_consistency.py` 第一层）。

复算全部数字（会重写 JSON + 本报告并重算 CI）：

```bash
cd backend
.venv/Scripts/python.exe scripts/modeling/eval/v1_29/01_reproducible_eval.py --report-only
```

**验收口径**：对已提交的 `test_predictions.csv` 跑上面这条命令，重写出的 JSON 与本报告
必须与仓库里的提交版**逐字节相等**（sha256 相同）。这不是「跑两次自洽」——
比的是「提交产物 vs 单命令产物」。

环境指纹（同机器两次运行产物字节一致；换机器需比对以下版本）：

```json
{json.dumps(extra['env'], ensure_ascii=False, indent=2)}
```

## 五、方法学口径（与旧 json 的统一说明）

- **point 估计 = 全样本统计量**（如 F1 = 2TP/(2TP+FP+FN)），**不是** bootstrap 均值。
  旧 `physio_v2_test_ci.json` 的 `f1.point = 0.8527` 是**bootstrap 均值被误写入 point 位**；
  同一混淆矩阵的名义值是 `0.8541667`（= `metrics.json`），两者差 0.0015 即来源于此。
- **区间 = 非参数 bootstrap 分位**（B={BOOTSTRAP_B}, seed={BOOTSTRAP_SEED}），AUC 同样用 bootstrap——
  旧 json 的 AUC 解析近似已被取代（旧文件保留为历史记录，顶部已标注；取代关系见 `README.md` §1）。
- 小样本（n={metrics['n']}）下 bootstrap 分位区间可能触到 1.0（precision 上界），属正常现象。
"""
    REPORT_MD.write_text(text, encoding="utf-8", newline="\n")


# ────────────────────────── 诊断：能否复现原切分 ──────────────────────────


def verify_original(df, y: np.ndarray) -> dict:
    """穷举仓内可复现的切分候选，回答「139 行测试集能否回来」。"""
    from sklearn.model_selection import train_test_split

    candidates = {}
    tri, vai, tei = split_indices(y)
    candidates["stratified_split(project, 0.7/0.15/0.15, rs=42)"] = [len(tri), len(vai), len(tei)]
    for mid in (0.3, 0.2999):
        for sec in (0.45, 0.5, 0.55):
            Xa, Xb, ya, yb = train_test_split(
                np.arange(len(y)), y, test_size=mid, stratify=y, random_state=42
            )
            Xv, Xs, yv, ys = train_test_split(
                Xb, yb, test_size=sec, stratify=yb, random_state=42
            )
            candidates[f"sklearn 2-stage mid={mid} second={sec}"] = [len(ya), len(yv), len(ys)]

    hit = [k for k, v in candidates.items() if v == [719, 171, 139]]
    return {
        "expected": EXPECTED_SPLIT,
        "recorded_meta": RECORDED_META,
        "candidates": candidates,
        "matched": hit,
        "reproducible": bool(hit),
        "dataset_rows": int(len(y)),
        "class_counts": {str(int(c)): int((y == c).sum()) for c in np.unique(y)},
    }


# ────────────────────────── 产物构造（两模式共用） ──────────────────────────


def dataset_block() -> dict:
    """dataset 元信息（两种模式共用，保证 JSON 逐字段一致）。

    `--report-only` 只从 csv 读**指标输入**；这里的行数/类别/切分尺寸仍来自
    原始数据 + 同一个 `split_indices`（不推理），因此两模式写出的 JSON 相同。
    """
    df = load_depresjon_data()
    y = df["depression_label"].values.astype(np.int64)
    tri, vai, tei = split_indices(y)
    return {
        "name": "depresjon_physiological.csv",
        "rows": int(len(y)),
        "class_counts": {str(int(c)): int((y == c).sum()) for c in np.unique(y)},
        "split": {
            "train": int(len(tri)),
            "val": int(len(vai)),
            "test": int(len(tei)),
            "scheme": "stratified 0.7/0.15/0.15, random_state=42",
        },
    }


def build_payload(
    metrics: dict,
    ci: dict,
    auc_point: float,
    refit_metrics: dict,
    refit_auc: float,
    dataset: dict,
) -> dict:
    """两种模式共用的 JSON 构造：字段、舍入、排序完全一致。"""
    return {
        "_note": (
            "本文件由 backend/scripts/modeling/eval/v1_29/01_reproducible_eval.py 生成；"
            "数据集是仓内 depresjon 当前版本的确定性切分，NOT 原 139 行测试集（不可复现，见 report）。"
            "ROUND_27 起：csv 存 float64 往返精度（.17g），全量运行与 --report-only 的 JSON 逐字段一致。"
            "ROUND_29 起：artifact 已按路径 B 端到端重训（D-R26-1 修复，"
            "04_round29_retrain_physiological.py），部署 scaler == train-only 重拟合"
            "（co-consistent by construction），修复前工件存档为 *.broken_round29"
        ),
        "dataset": dataset,
        "method": "bootstrap over persisted per-sample scores",
        "inference_chain": (
            "DataCleaner.transform -> engineer_features -> SimpleStandardScaler.transform "
            "-> PhysiologicalMLP.predict_proba (production path, predict.py::_predict_physiological_sync)"
        ),
        "threshold": THRESHOLD,
        "acc": {"point": round(metrics["acc"], 6), "ci95": [round(v, 6) for v in ci["acc"]["ci95"]]},
        "prec": {"point": round(metrics["prec"], 6), "ci95": [round(v, 6) for v in ci["prec"]["ci95"]]},
        "rec": {"point": round(metrics["rec"], 6), "ci95": [round(v, 6) for v in ci["rec"]["ci95"]]},
        "f1": {"point": round(metrics["f1"], 6), "ci95": [round(v, 6) for v in ci["f1"]["ci95"]]},
        "roc_auc": {
            "point": round(auc_point, 6),
            "ci95": [round(v, 6) for v in ci["roc_auc"]["ci95"]],
        },
        "meta": {
            "n": metrics["n"],
            "TP": metrics["TP"],
            "FP": metrics["FP"],
            "FN": metrics["FN"],
            "TN": metrics["TN"],
            "bootstrap_B": BOOTSTRAP_B,
            "seed": BOOTSTRAP_SEED,
            "point_estimator": "full-sample statistic (not bootstrap mean)",
        },
        "diagnostic_refit_scaler": {
            "_note": (
                "ROUND_29 起语义变更：不再是缺陷定位列，而是 co-consistency 证明列——"
                "部署 scaler 与 train-only 重拟合逐位相等，故本块读数与主口径相同；"
                "由 csv 列 y_score_refit_scaler 复算（--report-only）。参数级判据见 "
                "tests/test_p2_56_round29_scaler_consistency.py 第一层"
            ),
            "f1": round(refit_metrics["f1"], 6),
            "roc_auc": round(refit_auc, 6),
            "rec": round(refit_metrics["rec"], 6),
        },
        "reproducibility": {
            "predictions_csv_sha256": sha256_of(PREDICTIONS_CSV),
            "artifacts_sha256": artifact_digests(),
            "env": env_fingerprint(),
            "rerun": "cd backend && .venv/Scripts/python.exe scripts/modeling/eval/v1_29/01_reproducible_eval.py",
            "recompute_command": (
                "cd backend && .venv/Scripts/python.exe "
                "scripts/modeling/eval/v1_29/01_reproducible_eval.py --report-only"
            ),
        },
    }


def write_json(payload: dict) -> None:
    EVAL_JSON.parent.mkdir(parents=True, exist_ok=True)
    EVAL_JSON.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
        newline="\n",
    )


# ────────────────────────── main ──────────────────────────


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--verify-original", action="store_true", help="只诊断原切分能否复现")
    ap.add_argument(
        "--report-only",
        action="store_true",
        help="只读 csv 重算并重写 JSON + 报告（不推理）",
    )
    args = ap.parse_args(argv)

    if args.report_only:
        y, score, _raw = read_predictions_csv()
        lines = PREDICTIONS_CSV.read_text(encoding="utf-8").strip().splitlines()[1:]
        refit = np.array([float(ln.split(",")[5]) for ln in lines], dtype=np.float64)

        metrics = threshold_metrics(y, score)
        ci = bootstrap_ci(y, score, BOOTSTRAP_B, BOOTSTRAP_SEED)
        auc_point = auc_score(y, score)
        refit_metrics = threshold_metrics(y, refit)
        refit_auc = auc_score(y, refit)

        payload = build_payload(
            metrics, ci, auc_point, refit_metrics, refit_auc, dataset_block()
        )
        write_json(payload)
        write_report(
            metrics,
            ci,
            refit_metrics,
            {
                "auc_point": auc_point,
                "refit_auc": refit_auc,
                "csv_sha256": sha256_of(PREDICTIONS_CSV),
                "env": env_fingerprint(),
            },
        )
        print(
            f"[report-only] n={metrics['n']} f1={metrics['f1']:.4f} auc={auc_point:.4f} "
            f"rec={metrics['rec']:.4f} -> {EVAL_JSON.name} + {REPORT_MD.name}"
        )
        return 0

    df = load_depresjon_data()
    y = df["depression_label"].values.astype(np.int64)

    if args.verify_original:
        report = verify_original(df, y)
        print(json.dumps(report, ensure_ascii=False, indent=2))
        return 0 if report["reproducible"] else 2

    tri, vai, tei = split_indices(y)
    _assert_split_matches(y, tri, vai, tei)

    cleaner = load_cleaner()
    model = load_model()
    scaler = load_scaler()
    feats = load_feature_names()

    X_train = build_features(df, tri, cleaner, feats)
    X_test = build_features(df, tei, cleaner, feats)
    y_test = y[tei]

    score = predict_scores(X_test, model, scaler)
    score_refit = refit_scaled_scores(X_train, X_test, model)
    pred = (score >= THRESHOLD).astype(int)

    rows = []
    for i, row_index in enumerate(tei):
        rows.append(
            (int(row_index), int(y_test[i]), float(score[i]), int(pred[i]), float(score_refit[i]))
        )
    rows.sort(key=lambda r: r[0])
    write_predictions_csv(rows)

    # ROUND_27 关键修正：指标/CI **必须用与 csv 完全相同的顺序**计算。
    # ROUND_26 用 `tei` 的 shuffle 顺序算 CI，而 csv 按 row_index 升序落盘；
    # `--report-only` 从 csv 读回后是升序 ⇒ bootstrap 的 `rng.randint` 位置索引
    # 映射到不同的 (y, score) 对 ⇒ CI 端点系统性偏移（实测 F1 下界 0.638282 → 0.641026）。
    # 这不是精度问题（point/混淆矩阵对顺序不敏感所以没暴露），
    # 而是「落盘顺序 == 计算顺序」的一致性前提。
    y_eval = np.array([r[1] for r in rows], dtype=np.int64)
    s_eval = np.array([r[2] for r in rows], dtype=np.float64)
    refit_eval = np.array([r[4] for r in rows], dtype=np.float64)

    metrics = threshold_metrics(y_eval, s_eval)
    ci = bootstrap_ci(y_eval, s_eval, BOOTSTRAP_B, BOOTSTRAP_SEED)
    auc_point = auc_score(y_eval, s_eval)
    refit_metrics = threshold_metrics(y_eval, refit_eval)
    refit_auc = auc_score(y_eval, refit_eval)

    payload = build_payload(metrics, ci, auc_point, refit_metrics, refit_auc, dataset_block())
    write_json(payload)
    write_report(
        metrics,
        ci,
        refit_metrics,
        {
            "auc_point": auc_point,
            "refit_auc": refit_auc,
            "csv_sha256": sha256_of(PREDICTIONS_CSV),
            "env": env_fingerprint(),
        },
    )

    print(
        f"[eval] n={metrics['n']} TP={metrics['TP']} FP={metrics['FP']} "
        f"FN={metrics['FN']} TN={metrics['TN']}\n"
        f"  f1={metrics['f1']:.4f} {ci['f1']['ci95']}\n"
        f"  auc={auc_point:.4f} {ci['roc_auc']['ci95']}\n"
        f"  rec={metrics['rec']:.4f} prec={metrics['prec']:.4f} acc={metrics['acc']:.4f}\n"
        f"  refit-scaler diagnostic: f1={refit_metrics['f1']:.4f} auc={refit_auc:.4f}\n"
        f"  csv sha256={sha256_of(PREDICTIONS_CSV)}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
