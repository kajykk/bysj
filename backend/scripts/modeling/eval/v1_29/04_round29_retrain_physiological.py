#!/usr/bin/env python
"""ROUND_29 (T2 · 路径 B)：physiological_optimized 端到端重训 —— 修复 D-R26-1 (P0)。

缺陷与判定（T1 结论；证据见 03_round29_scaler_provenance.py 与
docs/P2_56_ROUND29_SCALER_FIX_AUDIT.md）
--------------------------------------------------
- artifact `scaler.json` 与仓内任何数据版本都不匹配（sleep_quality 均值 5.43
  超出 1-5 量表；overall_activity 错配约 5 倍）⇒ 生产路径 test recall 仅
  **0.6000**（阈值 0.5 下每 10 个阳性漏约 4 个）。
- T1 重复 CV（5 折 × 3 次重抽，非 test 872 行）证明：即便每折重拟合 scaler，
  旧权重的 recall 仍只有 0.8729 ± 0.0342（min 0.8333），且 train/val/test
  表现强烈依赖具体切分 ⇒ 旧权重与当前数据**不稳健兼容**，只换 scaler
  （路径 A）不够 ⇒ **路径 B（端到端重训）**。

纪律（ROUND_29 提示词 §一 T2 路径 B / §二 铁律）
-----------------------------------------------
1. **train-only**：DataCleaner 与 SimpleStandardScaler 都只在训练切分（719 行）
   上拟合；val/test 只做评估推理，绝不参与任何 fit。
2. **co-consistent by construction**：cleaner(train) → engineer_features →
   scaler.fit(X_train) → 模型在「经该 scaler 变换后的 X_train」上训练；
   推理链加载的就是同一套 cleaner/scaler/model。
3. **固定 seed=42**：权重初始化（PhysiologicalMLP.random_state）与 batch
   shuffling（train_model.random_state）都钉死。`--check-determinism`
   验证同 seed 两跑逐字节一致（4 个 inference 工件全等；metrics.json 除
   training_timestamp 外全等）。
4. **超参来自旧 metrics.json**（原训练的存档记录，不是新调参）：
   epochs 120 / batch 32 / lr 0.001 / weight_decay 0.005 / patience 15 /
   hidden [128,64,32,16] / dropout 0.2 / BatchNorm。
   **严禁为追指标调参**——让 test 好看的调参即作弊（提示词铁律）。
5. **旧工件存档**：scaler/model/cleaner_stats/metrics 四个旧文件复制为
   `*.broken_round29`；存档前用各自的 `.sha256` 侧车证明字节未被篡改。
   load_* 只认固定文件名，存档不会被生产加载路径拾取。
6. **如实报告**：before（旧工件、同一 test 行）与 after（新工件）全部打印；
   after 若低于修复前诊断口径 0.9455，如实记录，不追数、不调参。
7. **熔断线（不是目标线）**：after 的 test recall < 0.5 或 f1 < 0.5 ⇒ 判定
   训练崩坏，拒绝写入生产工件（只落 staging），退出码非 0。该线低于修复前
   生产口径 0.60，只防"训练坏了"，不构成调参压力。
8. **原子替换**：新工件先写同卷 staging 目录，再从 staging `os.replace`
   原子换入生产目录；替换后清工件缓存并从生产路径重新加载，断言复现的
   test 分数与训练管线逐点相等（atol=1e-12）。

用法
----
    cd backend
    # 正式重训：存档旧工件 → 训练 → 原子替换 → before/after 报告
    .venv/Scripts/python.exe scripts/modeling/eval/v1_29/04_round29_retrain_physiological.py

    # 演习：同样训练+评估，但只写临时目录，不碰生产工件
    .venv/Scripts/python.exe scripts/modeling/eval/v1_29/04_round29_retrain_physiological.py --dry-run

    # 同 seed 两跑逐字节一致性验证（两个临时目录）
    .venv/Scripts/python.exe scripts/modeling/eval/v1_29/04_round29_retrain_physiological.py --check-determinism

边界：本脚本**不写** test_predictions.csv / physio_v2_current_data_eval.json /
评估报告——那是 01_reproducible_eval.py 的职责（T4 在本脚本成功后重跑 01）。
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

BACKEND = Path(__file__).resolve().parents[4]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

from app.ml.data_cleaner import DataCleaner  # noqa: E402
from app.ml.data_loader import load_depresjon_data  # noqa: E402
from app.ml.model import PhysiologicalMLP  # noqa: E402
from app.ml.model_loader import (  # noqa: E402
    clear_artifact_cache,
    load_cleaner,
    load_feature_names,
    load_model,
    load_scaler,
)
from app.ml.scaler import SimpleStandardScaler, save_feature_names  # noqa: E402
from app.ml.trainer import train_model  # noqa: E402
from app.utils.checksum import _compute_sha256, write_sha256_sidecar  # noqa: E402

EVAL01_PATH = Path(__file__).resolve().parent / "01_reproducible_eval.py"
ARTIFACTS_DIR = BACKEND / "models" / "artifacts" / "physiological_optimized"
PREDICTIONS_CSV = ARTIFACTS_DIR / "test_predictions.csv"
EVAL_JSON = BACKEND.parent / "docs" / "model-evaluation" / "physio_v2_current_data_eval.json"

RANDOM_STATE = 42
ARCHIVE_SUFFIX = ".broken_round29"
ARCHIVE_TARGETS = ("scaler.json", "model.json", "cleaner_stats.json", "metrics.json")
PROMOTE_FILES = ("cleaner_stats.json", "scaler.json", "feature_names.json", "model.json", "metrics.json")
BYTE_COMPARE_FILES = ("model.json", "scaler.json", "cleaner_stats.json", "feature_names.json")

# 原训练的存档超参（旧 metrics.json hyperparameters 块）——只允许照抄，不允许新调
EXPECTED_HP = {
    "epochs": 120,
    "batch_size": 32,
    "learning_rate": 0.001,
    "weight_decay": 0.005,
    "patience": 15,
    "hidden_dims": [128, 64, 32, 16],
    "dropout_rate": 0.2,
    "use_batch_norm": True,
    "input_dim": 13,
}

# 熔断线（见 docstring 纪律 7）：低于修复前生产口径 0.60 的"训练崩坏"判定
FLOOR_RECALL = 0.5
FLOOR_F1 = 0.5


def _load_eval01():
    """把评估壳 01 当模块导入（其 main 有 __main__ 保护，无副作用）。"""
    import importlib.util

    spec = importlib.util.spec_from_file_location("eval01_round29_t2", EVAL01_PATH)
    assert spec and spec.loader
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _sha256(path: Path) -> str:
    return _compute_sha256(path)


def _sidecar_path(path: Path) -> Path:
    return path.with_suffix(path.suffix + ".sha256")


def auprc_score(y: np.ndarray, score: np.ndarray) -> float:
    """AUPRC（precision-recall 曲线下面积，阶梯型）。

    与 sklearn.metrics.average_precision_score 同值：按 score 降序在
    「score 变化处」取阈值点，step 积分 sum(diff(recall) * precision[:-1])。
    """
    pos_total = int((y == 1).sum())
    if pos_total == 0:
        return float("nan")
    order = np.argsort(-score, kind="mergesort")
    y_sorted = y[order].astype(np.int64)
    s_sorted = score[order]
    distinct = np.where(np.diff(s_sorted))[0]
    idx = np.r_[distinct, len(y_sorted) - 1]
    tp = np.cumsum(y_sorted)[idx]
    fp = np.cumsum(1 - y_sorted)[idx]
    precision = tp / (tp + fp)
    recall = tp / pos_total
    recall = np.r_[0.0, recall]
    precision = np.r_[1.0, precision]
    return float(np.sum(np.diff(recall) * precision[:-1]))


def _align(scores: np.ndarray, tei: np.ndarray) -> np.ndarray:
    """把 tei 顺序的分数重排为 row_index 升序（与 csv 落盘序一致）。"""
    pairs = sorted(zip((int(i) for i in tei), scores), key=lambda p: p[0])
    return np.array([p[1] for p in pairs], dtype=np.float64)


def _read_csv_production_column() -> tuple[np.ndarray, np.ndarray]:
    """读已提交 csv 的 (row_index 升序 y_true, y_score)。"""
    lines = PREDICTIONS_CSV.read_text(encoding="utf-8").strip().splitlines()[1:]
    rows = sorted(
        ((int(ln.split(",")[1]), int(ln.split(",")[2]), float(ln.split(",")[3])) for ln in lines),
        key=lambda r: r[0],
    )
    return (
        np.array([r[0] for r in rows], dtype=np.int64),
        np.array([r[1] for r in rows], dtype=np.int64),
        np.array([r[2] for r in rows], dtype=np.float64),
    )


def _load_hyperparameters() -> dict:
    """超参只从（旧）metrics.json 读，并对照 EXPECTED_HP 防漂移。"""
    path = ARTIFACTS_DIR / "metrics.json"
    assert path.exists(), f"缺少 {path}——无法确认原训练超参，拒绝开训"
    hp = json.loads(path.read_text(encoding="utf-8"))["hyperparameters"]
    for key, want in EXPECTED_HP.items():
        got = hp.get(key)
        assert got == want, (
            f"metrics.json 超参 {key}={got} 与存档预期 {want} 不符——"
            "请人工核对来源后再跑（严禁借机调参）"
        )
    return hp


def _quantize_to_artifact_dtype(model: PhysiologicalMLP) -> None:
    """把训练后的权重量化回 float32——artifact 的交付形态。

    `train_model` 的反向传播含 Python 标量（如 BN 的 1.0/N），梯度与权重更新
    会提升到 float64；而 artifact 格式是 float32（`PhysiologicalMLP.load` /
    `model_loader._load_model_cached` 都 `np.array(..., dtype=np.float32)`）。
    不量化的话，落盘前内存里的 float64 权重与生产加载的 float32 权重有
    ~1e-7 的量化差（实测 score maxdiff 7.96e-08）——「训练管线分数 == 生产
    工件分数」的逐位断言就不成立。量化后两者逐位相等，且不改变训练本身
    （train_model 内部已 restore_best_weights，量化在其返回之后）。
    """
    for layer in model.layers:
        for key in ("W", "b", "bn_gamma", "bn_beta", "bn_running_mean", "bn_running_var"):
            if key in layer:
                layer[key] = np.asarray(layer[key], dtype=np.float32)


def _train_pipeline(e01, df, y, tri, vai, tei, feats, hp) -> dict:
    """一次完整的 train-only 训练。返回全部中间量与工件对象（纯内存）。

    tei 可为 None（CV 模式不建 test 特征）。
    """
    # 纪律 1+2：cleaner/scaler 只在训练侧拟合；模型经该 scaler 训练
    cleaner = DataCleaner()
    cleaner.fit(df.iloc[tri])
    X_train = e01.build_features(df, tri, cleaner, feats)
    X_val = e01.build_features(df, vai, cleaner, feats)
    X_test = e01.build_features(df, tei, cleaner, feats) if tei is not None else None

    scaler = SimpleStandardScaler().fit(X_train)

    model = PhysiologicalMLP(
        input_dim=hp["input_dim"],
        hidden_dims=list(hp["hidden_dims"]),
        dropout_rate=hp["dropout_rate"],
        use_batch_norm=hp["use_batch_norm"],
        random_state=RANDOM_STATE,
    )
    # 仓内惯例（tests/test_trainer.py / hyperparameter_tuning.py）：y 为 (n,1) float32
    history = train_model(
        model,
        scaler.transform(X_train),
        y[tri].astype(np.float32).reshape(-1, 1),
        scaler.transform(X_val),
        y[vai].astype(np.float32).reshape(-1, 1),
        epochs=hp["epochs"],
        batch_size=hp["batch_size"],
        learning_rate=hp["learning_rate"],
        weight_decay=hp["weight_decay"],
        patience=hp["patience"],
        random_state=RANDOM_STATE,
    )
    # artifact 交付形态即 float32；量化后「训练管线 == 生产工件」逐位相等
    _quantize_to_artifact_dtype(model)
    return {
        "cleaner": cleaner,
        "scaler": scaler,
        "model": model,
        "history": history,
        "X_train": X_train,
        "X_val": X_val,
        "X_test": X_test,
        "y_train": y[tri],
        "y_val": y[vai],
        "y_test": y[tei],
    }


def _load_pre_fix_artifacts() -> tuple[DataCleaner, PhysiologicalMLP, SimpleStandardScaler]:
    """修复前口径的工件：优先从 `*.broken_round29` 存档读。

    重跑时磁盘上部署的已是新工件，若从活动路径读，「修复前」会悄悄变成
    「上一轮的新工件」——before/after 对照就失去意义。存档存在时一律读存档
    （首轮存档尚未生成时退回活动路径，即当时部署的旧工件）。
    """
    def pick(name: str) -> Path:
        archive = ARTIFACTS_DIR / (name + ARCHIVE_SUFFIX)
        return archive if archive.exists() else ARTIFACTS_DIR / name

    cleaner = DataCleaner().load(pick("cleaner_stats.json"))
    model = PhysiologicalMLP.load(pick("model.json"))
    scaler = SimpleStandardScaler.from_dict(
        json.loads(pick("scaler.json").read_text(encoding="utf-8"))
    )
    return cleaner, model, scaler


def _metrics_block(m: dict, auc: float, auprc: float) -> dict:
    return {
        "accuracy": m["acc"],
        "precision": m["prec"],
        "recall": m["rec"],
        "f1": m["f1"],
        "roc_auc": auc,
        "auprc": auprc,
    }


def _build_metrics(pipe: dict, feats, hp, m_after, auc_after, auprc_after, before_after) -> dict:
    return {
        "best_epoch": int(pipe["history"]["best_epoch"]),
        "best_val_f1": float(pipe["history"]["best_val_f1"]),
        "test_metrics": _metrics_block(m_after, auc_after, auprc_after),
        "data_leakage_fixed": True,
        "cleaner_stats_saved": True,
        "hyperparameters": {k: (list(v) if isinstance(v, list) else v) for k, v in hp.items()},
        "random_state": RANDOM_STATE,
        "data_split": {
            "train_ratio": 0.7,
            "val_ratio": 0.15,
            "test_ratio": 0.15,
            "train_samples": int(len(pipe["y_train"])),
            "val_samples": int(len(pipe["y_val"])),
            "test_samples": int(len(pipe["y_test"])),
            "scheme": "stratified 0.7/0.15/0.15, random_state=42 (app.ml.data_split.stratified_split)",
        },
        "feature_engineering": {
            "version": "v1",
            "feature_count": len(feats),
            "feature_names": list(feats),
        },
        "training_timestamp": datetime.now(timezone.utc).isoformat(),
        "model_parameters": int(pipe["model"].count_parameters()),
        "_audit_note_round29": {
            "date": datetime.now(timezone.utc).date().isoformat(),
            "defect": "D-R26-1 (P0): artifact scaler 与数据版本不配套，生产路径 test recall 0.6000",
            "provenance_verdict": (
                "路径 B（端到端重训）。T1 重复 CV（5 折 x 3 次，非 test 872 行）显示旧权重在"
                "重拟合 scaler 下 recall 仅 0.8729+/-0.0342（min 0.8333），且 train/val/test "
                "表现强烈依赖切分 ⇒ 旧权重与当前数据不稳健兼容，只换 scaler 不够。"
            ),
            "retrain_script": "backend/scripts/modeling/eval/v1_29/04_round29_retrain_physiological.py",
            "co_consistency": (
                "cleaner/scaler 只在 train 719 行拟合；模型在经该 scaler 变换的训练数据上训练"
                "（co-consistent by construction）"
            ),
            "archived_broken_artifacts": [name + ARCHIVE_SUFFIX for name in ARCHIVE_TARGETS],
            "data_split_correction": (
                "旧 metrics.json 记录 719/171/139 不可复现（ROUND_26 三重证据）；"
                "本文件记录真实切分 719/153/157"
            ),
            "not_a_model_upgrade": (
                "这不是'模型变强'：修复前 0.60 是标准化缺陷（叠加权重不兼容）的产物；"
                "修复后数字是 co-consistent 管线在同一数据上的诚实表现"
            ),
        },
        "round29_before_after": before_after,
        "scaler_provenance": {
            "fit_on": "train split only (719 rows, depresjon_physiological.csv current version)",
            "fit_never_on_val_or_test": True,
            "co_consistent_with_model": True,
        },
    }


def _write_artifacts(out: Path, pipe: dict, feats, hp, m_after, auc_after, auprc_after, before_after) -> None:
    """把训练产物写入 out（含 .sha256 侧车）。"""
    out.mkdir(parents=True, exist_ok=True)
    pipe["cleaner"].save(out / "cleaner_stats.json")
    pipe["scaler"].save(out / "scaler.json")
    save_feature_names(list(feats), out / "feature_names.json")
    pipe["model"].save(out / "model.json")
    metrics = _build_metrics(pipe, feats, hp, m_after, auc_after, auprc_after, before_after)
    mpath = out / "metrics.json"
    mpath.write_text(
        json.dumps(metrics, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n"
    )
    write_sha256_sidecar(mpath)


def _archive_originals() -> list[str]:
    """把四个旧工件存档为 *.broken_round29；存档前用侧车证明字节未被篡改。

    已存在存档则跳过（上一轮已存档过；重跑时磁盘上的"旧"文件其实是上一轮的新文件，
    不能覆盖存档）。
    """
    archived = []
    for name in ARCHIVE_TARGETS:
        src = ARTIFACTS_DIR / name
        dst = ARTIFACTS_DIR / (name + ARCHIVE_SUFFIX)
        assert src.exists(), f"缺少待存档工件 {src}"
        if dst.exists():
            print(f"  存档已存在，跳过：{dst.name}")
            continue
        sidecar = _sidecar_path(src)
        if sidecar.exists():
            recorded = sidecar.read_text(encoding="utf-8").strip().split()[0]
            actual = _sha256(src)
            assert actual == recorded, (
                f"{name} 与 {sidecar.name} 记录的哈希不符（{actual[:16]} vs {recorded[:16]}）"
                "——磁盘工件已被篡改，拒绝存档"
            )
            print(f"  侧车校验通过：{name} sha256={actual[:16]}...")
        else:
            print(f"  警告：{name} 无侧车，无法证明字节未被篡改，仍按原样存档")
        shutil.copy2(src, dst)
        archived.append(name)
    return archived


def _promote(staging: Path) -> list[str]:
    """从 staging 原子替换生产工件（同卷 os.replace）。"""
    moved = []
    for name in PROMOTE_FILES:
        src = staging / name
        dst = ARTIFACTS_DIR / name
        assert src.exists(), f"staging 缺少 {name}"
        os.replace(src, dst)
        moved.append(name)
        side = _sidecar_path(src)
        if side.exists():
            os.replace(side, _sidecar_path(dst))
            moved.append(side.name)
    return moved


def stratified_folds(y: np.ndarray, idx: np.ndarray, k: int, seed: int) -> list[np.ndarray]:
    """确定性分层 k 折：正/负各自 shuffle 后轮询分配；返回每折的验证侧索引。

    与 03_round29_scaler_provenance.py 逐行相同（同种子同折划分）⇒
    新管线的 CV 与 T1 旧权重的 CV 在同一组折上，可直接对比。
    """
    rng = np.random.RandomState(seed)
    folds: list[list[int]] = [[] for _ in range(k)]
    for cls in np.unique(y):
        cls_idx = idx[y[idx] == cls]
        cls_idx = cls_idx.copy()
        rng.shuffle(cls_idx)
        for j, sample in enumerate(cls_idx):
            folds[j % k].append(int(sample))
    return [np.array(sorted(f), dtype=np.int64) for f in folds]


def _cross_validate(e01, df, y, tri, vai, feats, hp, repeats: int = 3, k: int = 5) -> int:
    """新管线的重复 CV：每折重新 fit cleaner/scaler 并重训模型（co-consistent）。

    - 折划分与 T1 完全相同（非 test 872 行，5 折 × 3 次，seed=100/101/102）；
    - 与 T1 的协议差异：T1 固定生产 cleaner、只重拟合 scaler、用旧权重推理
      （回答"旧权重是否兼容"）；本模式每折完整重训（回答"新管线的泛化期望"）。
    - 只读评估，不写任何文件、不碰生产工件。
    """
    non_test = np.concatenate([tri, vai])
    rows = []
    for rep in range(repeats):
        folds = stratified_folds(y, non_test, k=k, seed=100 + rep)
        assert sorted(int(i) for f in folds for i in f) == sorted(int(i) for i in non_test), (
            "折划分没有恰好覆盖非 test 集——CV 前提被破坏"
        )
        for fi, val_idx in enumerate(folds, 1):
            tr_idx = np.array(
                sorted(set(int(i) for i in non_test) - set(int(i) for i in val_idx)),
                dtype=np.int64,
            )
            pipe = _train_pipeline(e01, df, y, tr_idx, val_idx, None, feats, hp)
            s = e01.predict_scores(pipe["X_val"], pipe["model"], pipe["scaler"])
            m = e01.threshold_metrics(y[val_idx], s)
            rows.append({
                "repeat": rep, "fold": fi, "n_val": len(val_idx),
                "rec": m["rec"], "f1": m["f1"],
                "auc": e01.auc_score(y[val_idx], s),
                "best_epoch": pipe["history"]["best_epoch"],
            })
            print(f"  rep{rep} fold{fi} (n={len(val_idx):3d}): "
                  f"rec={m['rec']:.4f} f1={m['f1']:.4f} auc={rows[-1]['auc']:.4f} "
                  f"(best_epoch={rows[-1]['best_epoch']})")

    rec = np.array([r["rec"] for r in rows])
    f1 = np.array([r["f1"] for r in rows])
    auc = np.array([r["auc"] for r in rows])
    print("-" * 78)
    print(f"新管线重复 CV（{k} 折 x {repeats} 次，非 test 872 行，每折完整重训）：")
    print(f"  recall mean={rec.mean():.4f} std={rec.std(ddof=1):.4f} "
          f"min={rec.min():.4f} max={rec.max():.4f}")
    print(f"  f1     mean={f1.mean():.4f} std={f1.std(ddof=1):.4f} "
          f"min={f1.min():.4f} max={f1.max():.4f}")
    print(f"  auc    mean={auc.mean():.4f} std={auc.std(ddof=1):.4f}")
    print("=" * 78)
    return 0


def _check_determinism(e01, df, y, tri, vai, tei, feats, hp) -> int:
    """同 seed 两跑：4 个 inference 工件逐字节一致；metrics.json 除时间戳全等。"""
    print("=" * 78)
    print("同 seed 两跑一致性验证（两个独立临时目录）")
    print("=" * 78)
    runs = []
    for i in range(2):
        out = Path(tempfile.mkdtemp(prefix=f"round29_det{i}_"))
        pipe = _train_pipeline(e01, df, y, tri, vai, tei, feats, hp)
        s_test = e01.predict_scores(pipe["X_test"], pipe["model"], pipe["scaler"])
        m = e01.threshold_metrics(pipe["y_test"], s_test)
        _write_artifacts(
            out, pipe, feats, hp, m, e01.auc_score(pipe["y_test"], s_test),
            auprc_score(pipe["y_test"], s_test), {"_note": "determinism check run"},
        )
        runs.append(out)
        print(f"  第 {i + 1} 跑完成：{out}")

    ok = True
    print("-" * 78)
    for name in BYTE_COMPARE_FILES:
        ha, hb = _sha256(runs[0] / name), _sha256(runs[1] / name)
        same = ha == hb
        ok &= same
        print(f"  {name:22s} {'一致' if same else '不一致!'}  sha256={ha[:24]}...")
        if not same:
            print(f"      run1={ha}\n      run2={hb}")
    m0 = json.loads((runs[0] / "metrics.json").read_text(encoding="utf-8"))
    m1 = json.loads((runs[1] / "metrics.json").read_text(encoding="utf-8"))
    ts0 = m0.pop("training_timestamp")
    ts1 = m1.pop("training_timestamp")
    same = m0 == m1
    ok &= same
    print(f"  {'metrics.json（除时间戳）':22s} {'一致' if same else '不一致!'}")
    print(f"      两跑时间戳（预期不同）：{ts0} / {ts1}")
    # 侧车自洽：每个工件与其 .sha256 相符
    for out in runs:
        for name in (*BYTE_COMPARE_FILES, "metrics.json"):
            side = _sidecar_path(out / name)
            assert side.exists(), f"{out}/{name} 缺侧车"
            recorded = side.read_text(encoding="utf-8").strip().split()[0]
            assert recorded == _sha256(out / name), f"{out}/{name} 侧车与文件不符"
    print("  侧车自洽：两跑全部工件与各自 .sha256 相符")
    for out in runs:
        shutil.rmtree(out, ignore_errors=True)
    print("=" * 78)
    print("判定：同 seed 两跑" + ("**逐字节一致**" if ok else "**不一致——训练管线存在不确定性，禁止上线**"))
    print("=" * 78)
    return 0 if ok else 1


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--check-determinism", action="store_true", help="同 seed 两跑逐字节一致性验证")
    ap.add_argument("--cross-validate", action="store_true",
                    help="新管线重复 CV（5 折 x 3 次，每折完整重训；只读评估，不写文件）")
    ap.add_argument("--dry-run", action="store_true", help="只训练+评估+写临时目录，不碰生产工件")
    args = ap.parse_args(argv)

    e01 = _load_eval01()
    df = load_depresjon_data()
    y = df["depression_label"].values.astype(np.int64)
    tri, vai, tei = e01.split_indices(y)
    assert (len(tri), len(vai), len(tei)) == (719, 153, 157), (
        f"切分尺寸异常：{len(tri)}/{len(vai)}/{len(tei)}"
    )
    e01._assert_split_matches(y, tri, vai, tei)
    feats = load_feature_names()
    assert len(feats) == EXPECTED_HP["input_dim"], f"特征数异常：{len(feats)}"
    hp = _load_hyperparameters()

    if args.check_determinism:
        return _check_determinism(e01, df, y, tri, vai, tei, feats, hp)

    if args.cross_validate:
        print("=" * 78)
        print("ROUND_29 T2 · 新管线重复 CV（每折完整重训，co-consistent；只读评估）")
        print("=" * 78)
        return _cross_validate(e01, df, y, tri, vai, feats, hp)

    print("=" * 78)
    print("ROUND_29 T2 · 路径 B 端到端重训（修复 D-R26-1 P0）")
    print("=" * 78)
    print(f"数据：depresjon_physiological.csv（{len(y)} 行，"
          f"{int((y == 1).sum())} 阳性 / {int((y == 0).sum())} 阴性）")
    print(f"切分：stratified 0.7/0.15/0.15, random_state=42 → "
          f"train {len(tri)} / val {len(vai)} / test {len(tei)}")
    print(f"超参（来自旧 metrics.json，非新调参）：epochs={hp['epochs']} batch={hp['batch_size']} "
          f"lr={hp['learning_rate']} wd={hp['weight_decay']} patience={hp['patience']} "
          f"hidden={hp['hidden_dims']} dropout={hp['dropout_rate']} BN={hp['use_batch_norm']}")

    # ── 修复前口径：存档的旧工件（生产链）在同一 test 行上的表现 ──
    old_cleaner, old_model, old_scaler = _load_pre_fix_artifacts()
    X_test_old = e01.build_features(df, tei, old_cleaner, feats)
    s_before = e01.predict_scores(X_test_old, old_model, old_scaler)
    m_before = e01.threshold_metrics(y[tei], s_before)
    auc_before = e01.auc_score(y[tei], s_before)
    auprc_before = auprc_score(y[tei], s_before)

    # 连续性：修复前分数必须等于已提交 csv 的生产列（证明「修复前 0.60」可复算）。
    # 逐行口径：csv 按 row_index 升序落盘 ⇒ 两边都按 row_index 对齐后比
    # （曾误写成 csv_y == np.sort(y[tei])——那是「标签值序」对「行号序」，恒不等）。
    if PREDICTIONS_CSV.exists():
        _ri, csv_y, csv_score = _read_csv_production_column()
        labels_ok = np.array_equal(csv_y, y[np.sort(tei)])
        before_ok = labels_ok and np.allclose(_align(s_before, tei), csv_score, rtol=0, atol=1e-12)
        if before_ok:
            print("连续性：修复前分数 == 已提交 test_predictions.csv 生产列（逐行 atol=1e-12）")
            if EVAL_JSON.exists():
                payload = json.loads(EVAL_JSON.read_text(encoding="utf-8"))
                assert abs(float(payload["rec"]["point"]) - m_before["rec"]) < 1e-6, (
                    f"修复前 recall {m_before['rec']} 与已提交 json 的 rec point 不符"
                )
                print(f"连续性：修复前 recall == 已提交 json rec point（{payload['rec']['point']}，1e-6）")
        else:
            print("注意：csv 与修复前口径不符（可能 01 已重跑为修复后口径，或 csv 被替换）")

    print()
    print("── 修复前（存档旧工件，生产链口径，同一 test 157 行）──")
    print(f"  recall={m_before['rec']:.4f} f1={m_before['f1']:.4f} acc={m_before['acc']:.4f} "
          f"prec={m_before['prec']:.4f} auc={auc_before:.4f} auprc={auprc_before:.4f}")
    print(f"  CM: TP={m_before['TP']} FP={m_before['FP']} FN={m_before['FN']} TN={m_before['TN']}")

    # ── 训练 ──
    print()
    print("── 训练（train-only；早停于 val F1）──")
    pipe = _train_pipeline(e01, df, y, tri, vai, tei, feats, hp)
    hist = pipe["history"]
    print(f"  best_epoch={hist['best_epoch']} best_val_f1={hist['best_val_f1']:.4f} "
          f"（共训 {len(hist['train_loss'])} 个 epoch，patience={hp['patience']}）")
    s_tr = e01.predict_scores(pipe["X_train"], pipe["model"], pipe["scaler"])
    s_va = e01.predict_scores(pipe["X_val"], pipe["model"], pipe["scaler"])
    m_tr = e01.threshold_metrics(pipe["y_train"], s_tr)
    m_va = e01.threshold_metrics(pipe["y_val"], s_va)
    print(f"  train(719): rec={m_tr['rec']:.4f} f1={m_tr['f1']:.4f} acc={m_tr['acc']:.4f}")
    print(f"  val  (153): rec={m_va['rec']:.4f} f1={m_va['f1']:.4f} acc={m_va['acc']:.4f}")

    # ── 修复后口径：新工件（生产链）在同一 test 行上的表现 ──
    s_after = e01.predict_scores(pipe["X_test"], pipe["model"], pipe["scaler"])
    m_after = e01.threshold_metrics(pipe["y_test"], s_after)
    auc_after = e01.auc_score(pipe["y_test"], s_after)
    auprc_after = auprc_score(pipe["y_test"], s_after)

    print()
    print("── 修复后（新工件，生产链口径，同一 test 157 行）──")
    print(f"  recall={m_after['rec']:.4f} f1={m_after['f1']:.4f} acc={m_after['acc']:.4f} "
          f"prec={m_after['prec']:.4f} auc={auc_after:.4f} auprc={auprc_after:.4f}")
    print(f"  CM: TP={m_after['TP']} FP={m_after['FP']} FN={m_after['FN']} TN={m_after['TN']}")
    print(f"  vs 修复前生产口径 recall={m_before['rec']:.4f}：{m_after['rec'] - m_before['rec']:+.4f}")
    print(f"  vs 修复前诊断口径 recall=0.9455（旧权重+重拟合 scaler，单切分）："
          f"{m_after['rec'] - 0.9455:+.4f}"
          + ("  ← 低于诊断口径，如实记录（提示词纪律：不追数、不调参）" if m_after["rec"] < 0.9455 else ""))

    # ── co-consistency 自检 ──
    refit = SimpleStandardScaler().fit(pipe["X_train"])
    assert np.allclose(pipe["scaler"].mean_, refit.mean_, rtol=1e-3, atol=1e-4), "scaler mean 漂移"
    assert np.allclose(pipe["scaler"].scale_, refit.scale_, rtol=1e-3, atol=1e-4), "scaler scale 漂移"
    print()
    print("── co-consistency 自检 ──")
    print("  生产 scaler == X_train 上独立重拟合的 scaler（rtol=1e-3, atol=1e-4）：True")
    print("  新 scaler 参数（按 feature_names.json 顺序；括号内为修复前存档值）：")
    old_scaler_data = json.loads(
        (ARTIFACTS_DIR / ("scaler.json" + ARCHIVE_SUFFIX)).read_text(encoding="utf-8")
    ) if (ARTIFACTS_DIR / ("scaler.json" + ARCHIVE_SUFFIX)).exists() else None
    for i, name in enumerate(feats):
        old_mean = old_scaler_data["mean"][i] if old_scaler_data else float("nan")
        old_scale = old_scaler_data["scale"][i] if old_scaler_data else float("nan")
        print(f"    {name:24s} mean={pipe['scaler'].mean_[i]:14.6f}（旧 {old_mean:14.6f}）  "
              f"scale={pipe['scaler'].scale_[i]:14.6f}（旧 {old_scale:14.6f}）")

    before_after = {
        "_note": (
            "同一 test 157 行。before=存档的旧工件（生产链修复前口径）；"
            "after=本 metrics.json 对应的新工件。均为推理评估，无任何 fit 涉及 test。"
        ),
        "test_rows": int(len(pipe["y_test"])),
        "before": {
            **_metrics_block(m_before, auc_before, auprc_before),
            "confusion_matrix": {"TP": m_before["TP"], "FP": m_before["FP"],
                                 "FN": m_before["FN"], "TN": m_before["TN"]},
        },
        "after": {
            **_metrics_block(m_after, auc_after, auprc_after),
            "confusion_matrix": {"TP": m_after["TP"], "FP": m_after["FP"],
                                 "FN": m_after["FN"], "TN": m_after["TN"]},
        },
    }

    # ── 熔断线（纪律 7）──
    if m_after["rec"] < FLOOR_RECALL or m_after["f1"] < FLOOR_F1:
        print()
        print("!" * 78)
        print(f"熔断：修复后 test recall={m_after['rec']:.4f} / f1={m_after['f1']:.4f} "
              f"低于熔断线（recall>={FLOOR_RECALL}, f1>={FLOOR_F1}）——判定训练崩坏，")
        print("      拒绝写入生产工件。请人工研判后重跑（不得为过线调参）。")
        print("!" * 78)
        return 2

    # ── 落盘：staging → 原子替换 → 生产路径复载校验 ──
    if args.dry_run:
        staging = Path(tempfile.mkdtemp(prefix="round29_dryrun_"))
        _write_artifacts(staging, pipe, feats, hp, m_after, auc_after, auprc_after, before_after)
        print()
        print(f"[dry-run] 工件已写临时目录（未触碰生产工件）：{staging}")
        print(f"[dry-run] model.json sha256={_sha256(staging / 'model.json')[:24]}...")
        return 0

    print()
    print("── 存档与落盘 ──")
    archived = _archive_originals()
    print(f"  本轮存档（*.broken_round29）：{archived if archived else '（无新存档）'}")

    staging = ARTIFACTS_DIR.parent / "physiological_optimized.staging_round29"
    if staging.exists():
        shutil.rmtree(staging)
    try:
        _write_artifacts(staging, pipe, feats, hp, m_after, auc_after, auprc_after, before_after)
        moved = _promote(staging)
        print(f"  原子替换进生产目录：{moved}")
    finally:
        if staging.exists():
            shutil.rmtree(staging, ignore_errors=True)

    # 缓存失效后从生产路径重新加载，断言复现训练管线（防序列化漂移）
    clear_artifact_cache()
    p_model = load_model()
    p_scaler = load_scaler()
    p_cleaner = load_cleaner()
    X_test_prod = e01.build_features(df, tei, p_cleaner, feats)
    s_prod = e01.predict_scores(X_test_prod, p_model, p_scaler)
    maxdiff = float(np.max(np.abs(s_prod - s_after)))
    assert maxdiff <= 1e-12, f"生产工件复现的分数与训练管线不一致（maxdiff={maxdiff}）"
    print(f"  生产路径复载校验：test 分数与训练管线逐点相等（maxdiff={maxdiff:.1e}）")

    print()
    print("── 工件 sha256（生产目录）──")
    for name in PROMOTE_FILES:
        print(f"  {name:22s} {_sha256(ARTIFACTS_DIR / name)}")
    print()
    print("=" * 78)
    print("完成：生产工件已替换为 co-consistent 重训产物。")
    print("下一步（T4）：重跑 01_reproducible_eval.py 生成新 csv/json/报告，再回填论文数字。")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
