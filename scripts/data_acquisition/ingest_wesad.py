#!/usr/bin/env python3
"""WESAD 数据接入（ingest）：原始窗口 parquet -> 项目生理特征表。

输入：datasets/physiological/external/wesad/wesad_4_3_120.parquet
      （HF 镜像 LouisSimon/wesad-parquet；原始数据集 Schmidt et al., ICMI 2018，
       UCI DOI 10.24432/C57K5T。4s 窗 / 3s 步长；手腕 E4 + 胸部 RespiBAN。）

输出（同目录，.gitignore 排除）：
  - wesad_window_features.csv   逐窗口特征（一行 = 一个 4s 窗）
  - wesad_subject_features.csv  逐被试聚合（一行 = 一个被试 × 一个条件）
  - wesad_manifest.json         实测统计 + 源/产物 sha256 + 提取参数

特征口径（与 depresjon_physiological.csv 的可映射子集对齐，缺口如实记录）：
  heart_rate(hr_bpm) / mean_activity / std_activity / peak_activity /
  autocorrelation(lag-1)  <- 可映射
  eda_* / temp_* / hrv_* / chest_*            <- WESAD 独有（depresjon 无对应列）
  sleep_* / *_bp / phq9_score                 <- WESAD 不存在，不造列（见 manifest.schema_gap）

本脚本只做特征提取与聚合，不训练、不评估、不挑优；外部验证（G2）另行立项。
依赖：pyarrow / numpy / scipy / pandas（见 requirements-ml.txt）。

用法：
    python ingest_wesad.py                     # 窗口特征 + 被试聚合 + manifest
    python ingest_wesad.py --check             # 只打印 manifest，不重算
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import numpy as np
import pyarrow.parquet as pq

REPO = Path(__file__).resolve().parents[2]
DATA_DIR = REPO / "datasets/physiological/external/wesad"
SRC = DATA_DIR / "wesad_4_3_120.parquet"
OUT_WINDOW = DATA_DIR / "wesad_window_features.csv"
OUT_SUBJECT = DATA_DIR / "wesad_subject_features.csv"
OUT_MANIFEST = DATA_DIR / "wesad_manifest.json"

# 采样率（窗口 4s；与 parquet 各列长度实测一致：wrist acc 128@32Hz / bvp 256@64Hz /
# eda,temp 16@4Hz；chest 全 512@128Hz）
FS = {"wrist_acc": 32.0, "wrist_bvp": 64.0, "wrist_eda": 4.0, "wrist_temp": 4.0,
      "chest": 128.0}

# WESAD 原始标签 -> 二分类（应激 vs 非应激）。冥想(4) 在原镜像中不出现。
LABEL_MAP = {1: 0, 2: 1, 3: 0}  # 1=baseline, 2=stress, 3=amusement
LABEL_NAMES = {1: "baseline", 2: "stress", 3: "amusement"}

WINDOW_FEATURES = [
    "hr_bpm_wrist", "ibi_mean_s_wrist", "rmssd_ms_wrist",
    "eda_mean_wrist", "eda_std_wrist", "eda_slope_wrist",
    "temp_mean_wrist", "temp_slope_wrist",
    "acc_mag_mean_wrist", "acc_mag_std_wrist", "acc_mag_max_wrist",
    "acc_autocorr_lag1_wrist",
    "acc_mag_mean_chest", "acc_mag_std_chest", "acc_mag_max_chest",
    "acc_autocorr_lag1_chest",
    "eda_mean_chest", "temp_mean_chest",
]

# 与 depresjon_physiological.csv 的口径映射（G2 外部验证时使用）
SCHEMA_MAP = {
    "heart_rate": "hr_bpm_wrist",
    "mean_activity": "acc_mag_mean_wrist",
    "std_activity": "acc_mag_std_wrist",
    "peak_activity": "acc_mag_max_wrist",
    "autocorrelation": "acc_autocorr_lag1_wrist",
}
SCHEMA_GAP = ["sleep_hours", "sleep_quality", "exercise_minutes", "systolic_bp",
              "diastolic_bp", "phq9_score"]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _peaks_hr(sig: np.ndarray, fs: float) -> tuple[float, float]:
    """BVP 峰值计数估计心率与 RMSSD。返回 (hr_bpm, rmssd_ms)；峰值不足返回 nan。

     prominence 判据（对干净 PPG 鲁棒）；IBI 生理域过滤 0.3~2.0s（30~200bpm）；
    4s 窗口至少需要 3 个合规峰间期。实测：手腕 BVP 为干净 PPG（64Hz）；
    胸部 ctxt_bvp 通道在该镜像中为高频噪声（128Hz 下周期 6~10 样本），不可用于心率，
    故心率只取手腕（见 manifest.notes）。
    """
    from scipy.signal import find_peaks

    if sig.size < 8 or not np.all(np.isfinite(sig)):
        return float("nan"), float("nan")
    sig = sig - sig.mean()
    std = sig.std()
    if std <= 0:
        return float("nan"), float("nan")
    peaks, props = find_peaks(sig, prominence=0.5 * std,
                              distance=max(1, int(0.3 * fs)))
    if peaks.size < 4:
        return float("nan"), float("nan")
    ibi = np.diff(peaks) / fs  # 秒
    ibi = ibi[(ibi > 0.3) & (ibi < 2.0)]  # 30~200 bpm 生理合理域
    if ibi.size < 3:
        return float("nan"), float("nan")
    hr = 60.0 / float(np.median(ibi))
    # RMSSD 对峰列不规则度敏感：IBI 变异系数 > 0.25 视为峰列不可信（4s 短窗双峰/漏峰），不报 RMSSD
    cv = float(ibi.std() / ibi.mean()) if ibi.size >= 4 and ibi.mean() > 0 else float("inf")
    rmssd = float(np.sqrt(np.mean(np.diff(ibi) ** 2)) * 1000.0) if cv <= 0.25 else float("nan")
    return hr, rmssd


def _acc_features(x: np.ndarray, y: np.ndarray, z: np.ndarray) -> dict[str, float]:
    mag = np.sqrt(x ** 2 + y ** 2 + z ** 2)
    mean, std = float(mag.mean()), float(mag.std())
    if std > 0 and mag.size > 1:
        ac1 = float(np.corrcoef(mag[:-1], mag[1:])[0, 1])
    else:
        ac1 = float("nan")
    return {"mean": mean, "std": std, "max": float(mag.max()), "autocorr_lag1": ac1}


def _slope(sig: np.ndarray, fs: float) -> float:
    if sig.size < 2:
        return float("nan")
    t = np.arange(sig.size) / fs
    return float(np.polyfit(t, sig, 1)[0])


def extract_window(row: dict) -> dict[str, float]:
    out: dict[str, float] = {}
    bvp_w = np.asarray(row["bvp"], dtype=float)
    hr_w, rmssd_w = _peaks_hr(bvp_w, FS["wrist_bvp"])
    out["hr_bpm_wrist"], out["rmssd_ms_wrist"] = hr_w, rmssd_w
    if np.isfinite(hr_w):
        out["ibi_mean_s_wrist"] = 60.0 / hr_w
    else:
        out["ibi_mean_s_wrist"] = float("nan")

    eda_w = np.asarray(row["eda"], dtype=float)
    out["eda_mean_wrist"] = float(eda_w.mean())
    out["eda_std_wrist"] = float(eda_w.std())
    out["eda_slope_wrist"] = _slope(eda_w, FS["wrist_eda"])
    temp_w = np.asarray(row["temp"], dtype=float)
    out["temp_mean_wrist"] = float(temp_w.mean())
    out["temp_slope_wrist"] = _slope(temp_w, FS["wrist_temp"])

    for dev, pre in (("wrist", ("acc_x", "acc_y", "acc_z")), ("chest", ("ctxt_acc_x", "ctxt_acc_y", "ctxt_acc_z"))):
        feats = _acc_features(*(np.asarray(row[c], dtype=float) for c in pre))
        out[f"acc_mag_mean_{dev}"] = feats["mean"]
        out[f"acc_mag_std_{dev}"] = feats["std"]
        out[f"acc_mag_max_{dev}"] = feats["max"]
        out[f"acc_autocorr_lag1_{dev}"] = feats["autocorr_lag1"]

    out["eda_mean_chest"] = float(np.asarray(row["ctxt_eda"], dtype=float).mean())
    out["temp_mean_chest"] = float(np.asarray(row["ctxt_temp"], dtype=float).mean())
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description="WESAD ingest")
    ap.add_argument("--check", action="store_true", help="只打印已有 manifest")
    args = ap.parse_args()

    if args.check:
        if OUT_MANIFEST.exists():
            print(OUT_MANIFEST.read_text(encoding="utf-8"))
            return 0
        print("manifest 不存在，先跑一次全量。")
        return 1

    if not SRC.exists():
        print(f"缺少源文件 {SRC}；先运行 scripts/data_acquisition/fetch_external_datasets.py --dataset wesad")
        return 1

    table = pq.read_table(SRC)
    rows = table.to_pylist()
    print(f"读取 {len(rows)} 个窗口（源 sha256 {sha256_file(SRC)[:16]}…）")

    records = []
    for idx, row in enumerate(rows):
        rec: dict = {
            "user": str(row["user"]),
            "window_idx": idx,
            "label_orig": int(row["stress"]),
            "condition": LABEL_NAMES.get(int(row["stress"]), "unknown"),
            "label_stress": LABEL_MAP.get(int(row["stress"]), -1),
        }
        rec.update(extract_window(row))
        records.append(rec)

    import pandas as pd

    df = pd.DataFrame.from_records(records)
    cols = ["user", "window_idx", "label_orig", "condition", "label_stress"] + WINDOW_FEATURES
    df = df[cols]
    df.to_csv(OUT_WINDOW, index=False, encoding="utf-8")
    print(f"写出 {OUT_WINDOW.name}: {len(df)} 行 × {len(df.columns)} 列")

    subj = (df.groupby(["user", "condition", "label_orig", "label_stress"], as_index=False)
              .agg(n_windows=("window_idx", "count"), **{f: (f, "mean") for f in WINDOW_FEATURES}))
    subj.to_csv(OUT_SUBJECT, index=False, encoding="utf-8")
    print(f"写出 {OUT_SUBJECT.name}: {len(subj)} 行")

    n_nan = {f: int(df[f].isna().sum()) for f in WINDOW_FEATURES}
    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": "scripts/data_acquisition/ingest_wesad.py",
        "source": {
            "file": str(SRC),
            "sha256": sha256_file(SRC),
            "mirror": "https://hf-mirror.com/datasets/LouisSimon/wesad-parquet",
            "original": "Schmidt et al., ICMI 2018; UCI DOI 10.24432/C57K5T",
            "license": "科研非商业使用需署名（uni-siegen 条款）",
        },
        "measured": {
            "n_windows": int(len(df)),
            "n_subjects": int(df["user"].nunique()),
            "subjects": sorted(df["user"].unique(), key=lambda s: int(s)),
            "label_orig_counts": {str(k): int(v) for k, v in df["label_orig"].value_counts().sort_index().items()},
            "label_stress_counts": {str(k): int(v) for k, v in df["label_stress"].value_counts().sort_index().items()},
            "nan_per_feature": n_nan,
        },
        "extraction": {
            "window_seconds": 4.0,
            "stride_seconds": 3.0,
            "sampling_rates_hz": FS,
            "hr_method": "BVP 峰值计数（find_peaks, height=0.5σ, distance=0.25s）；HR=60/median(IBI)",
            "label_map": {str(k): v for k, v in LABEL_MAP.items()},
        },
        "schema_map_to_depresjon": SCHEMA_MAP,
        "schema_gap": SCHEMA_GAP,
        "outputs": {
            "window_csv": {"path": str(OUT_WINDOW), "sha256": sha256_file(OUT_WINDOW)},
            "subject_csv": {"path": str(OUT_SUBJECT), "sha256": sha256_file(OUT_SUBJECT)},
        },
        "notes": [
            "信号为上游镜像的标准化值（非原始物理单位）；HR/RMSSD 由手腕 BVP 波形重新估计，单位有效。",
            "胸部 ctxt_bvp 通道在该镜像中为高频噪声（128Hz 下周期 6~10 样本，自相关/FFT 互相矛盾），"
            "不取胸部心率；胸部仅保留 ACC/EDA/TEMP 的慢变统计量。",
            "胸部信号采样率 128Hz 为原 700Hz 的重采样（镜像处理），特征仅取稳健统计量。",
            "本数据集不含 depresjon 的睡眠/血压/PHQ-9 列；G2 外部验证只能使用可映射子集，缺口见 schema_gap。",
        ],
    }
    OUT_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写出 {OUT_MANIFEST.name}")
    print(json.dumps(manifest["measured"], ensure_ascii=False, indent=2)[:800])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
