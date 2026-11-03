#!/usr/bin/env python3
"""NHANES 数据接入（ingest）：xpt -> 项目生理模型的 7 列基 schema。

为什么是 NHANES（补 TRANSFER_MATRIX.md §4 的「真·生理外部集」缺口）：
  仓内 6 份数据里，生理模型只有 depresjon（训练/评估同源）+ Kaggle（13 特征仅 3 列可映射，
  AUC 0.512）。NHANES 提供 **实测** 血压/脉搏/睡眠时长/活动量 + **完整 PHQ-9**，
  且为美国联邦政府作品（公有领域），许可证据明确，是唯一能直接产出可对外数字的候选。

输入（data/external/nhanes/，.gitignore 排除）：
  DEMO_J.xpt 人口学；DPQ_J.xpt PHQ-9；BPX_J.xpt 血压；SLQ_J.xpt 睡眠；PAQ_J.xpt 体力活动
  均为 NHANES 2017-2018 周期，CDC 公开文件。

输出（同目录）：
  nhanes_physiological.csv  一行 = 一名被试，含 7 列基 schema + 标签 + 分层辅助列
  nhanes_manifest.json      实测统计 + 源/产物 sha256 + 映射口径 + 已知缺口

═══ 两个必须知道的坑（实测踩过，勿"优化"回去）═══

1. **SAS xport 的 0 值在 pandas.read_sas 里读成 denormal 5.397605e-79，不是缺失值。**
   判据：与官方 codebook 逐值对拍——DPQ010 的 denormal 计数 3792 恰等于 codebook 里
   「0 = Not at all」的 3792。若误当缺失清洗，会删掉全部无症状样本，
   只剩 36 行高分组，得到 100% 阳性率（本轮实测确实先踩了这个坑）。
2. **DPQ 的 7（Refused）/9（Don't know）不是症状频率，必须置缺失**，否则总分虚高到 72。

标签口径：depression_label = PHQ-9 total >= 10（与本项目结构化模型一致）。
⚠️ 与 Depresjon 的 depression_label **定义不同**（后者为数据集自带的诊断标签），
   两者不可直接比较，见 manifest.label_caveat。

用法：
    python fetch_external_datasets.py --dataset nhanes   # 先取数
    python ingest_nhanes.py                              # 再接入
    python ingest_nhanes.py --check                      # 只打印 manifest
"""
from __future__ import annotations

import argparse
import hashlib
import json
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

REPO = Path(__file__).resolve().parents[2]
DATA_DIR = REPO / "data/external/nhanes"
OUT_CSV = DATA_DIR / "nhanes_physiological.csv"
OUT_MANIFEST = DATA_DIR / "nhanes_manifest.json"

# SAS xport 把 0 写成的最小 denormal（见 docstring 坑 1）
SAS_ZERO_DENORMAL = 5.397605346934028e-79
ABSENT_THRESHOLD = 1e-60

PHQ9_ITEMS = [f"DPQ{code:03d}" for code in range(10, 100, 10)]
ACTIVITY_COLS = ["PAD615", "PAD630", "PAD645", "PAD660", "PAD675"]

# 映射到 depresjon_physiological.csv 的 7 列基 schema
SCHEMA_MAP = {
    "sleep_hours": "SLD012（派生：工作日入睡/起床时刻差，四舍五入到 0.5h）",
    "sleep_quality": "SLQ050（1=否 2=是「是否曾因睡眠问题就医」）——**序数代理，非 1-4 睡眠质量量表**",
    "exercise_minutes": "PAD615+630+645+660+675（GPAQ 各项每日分钟和）",
    "heart_rate": "BPXPLS（60 秒脉搏，护士实测）",
    "systolic_bp": "BPXSY1（第 1 次读数，水银/听诊，mm Hg）",
    "diastolic_bp": "BPXDI1（第 1 次读数，mm Hg）",
    "steps": "**无对应列**——NHANES 2017-2018 公开文件不含加速度计步数（2013-2014 后有 MIMS 但非步数）",
}

SCHEMA_GAP = ["steps（无对应列，保持缺失，不以 0 或均值填充）"]

LABEL_CAVEAT = {
    "this_dataset": "PHQ-9 total >= 10（9 项均答妥才算，不做缺失填补）",
    "depresjon": "数据集自带的 depression_label（原始队列诊断标签，非 PHQ-9 派生）",
    "comparable": False,
    "why": "两者定义不同源，跨数据集比较 F1/AUC 时必须标注口径差异，不可宣称『同一标签』",
}

# 已知域偏移（写进 manifest，避免下游忘记）
DOMAIN_OFFSET = [
    "人群为美国 18+ 成年人（含大量中老年），本项目目标人群为高校学生 ⇒ 年龄/文化域偏移",
    "睡眠质量列是二值『是否就医』代理，与 Depresjon 的 1-4 序数量表不同分布",
    "活动量为自我报告（GPAQ），非设备步数；与 steps 不可互相替代",
    "NHANES 采用复杂抽样，未加权统计仅作描述；正式发表需用 WTMEC2YR 权重",
]


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def _fix_sas(series: pd.Series) -> pd.Series:
    """SAS xport 数值列清洗：denormal -> 0，保留真实 0。

    只有 |x| < 1e-60 且 x != 0 的才是 denormal 编码的 0。
    """
    s = pd.to_numeric(series, errors="coerce")
    return s.mask((s != 0) & (s.abs() < ABSENT_THRESHOLD), 0.0)


def _read(name: str, cols: list[str] | None = None) -> pd.DataFrame:
    path = DATA_DIR / f"{name}.xpt"
    if not path.exists():
        raise FileNotFoundError(
            f"缺少 {path}；先运行 python scripts/data_acquisition/fetch_external_datasets.py "
            f"--dataset nhanes"
        )
    df = pd.read_sas(path, format="xport")
    if cols is not None:
        df = df[["SEQN"] + [c for c in cols if c in df.columns]]
    for c in df.columns:
        if c != "SEQN":
            df[c] = _fix_sas(df[c])
    return df


def build() -> tuple[pd.DataFrame, dict]:
    demo = _read("DEMO_J", ["RIDAGEYR", "RIAGENDR", "INDFMPIR", "WTMEC2YR"])
    dpq = _read("DPQ_J", PHQ9_ITEMS)
    bpx = _read("BPX_J", ["BPXSY1", "BPXDI1", "BPXPLS"])
    slq = _read("SLQ_J", ["SLD012", "SLQ050"])
    paq = _read("PAQ_J", ACTIVITY_COLS)

    # PHQ-9：7/9 置缺失；仅 9 项全答妥才计总分（不填补）
    raw_items = dpq[PHQ9_ITEMS].copy()
    items = raw_items.replace({7: pd.NA, 9: pd.NA})
    complete = items.notna().all(axis=1)
    phq9_total = items.sum(axis=1, min_count=len(PHQ9_ITEMS))  # 缺项时为 NA
    # 注意：不能写 (total >= 10) & complete —— NA & False 会得到 False，
    # 把「未答完」静默标成阴性，稀释阳性率。必须在完整样本上取布尔，其余置 NA。
    label = pd.Series(pd.NA, index=dpq.index, dtype="Int64")
    label[complete] = (phq9_total[complete] >= 10).astype("int64")
    phq9 = pd.DataFrame({
        "SEQN": dpq["SEQN"],
        "phq9_total": phq9_total,
        "depression_label": label,
    })

    paq = paq.copy()
    paq["exercise_minutes"] = paq[ACTIVITY_COLS].sum(axis=1, min_count=1)
    # 24h 上限校验：超一天的自我报告视为不可信
    paq["exercise_minutes"] = paq["exercise_minutes"].where(paq["exercise_minutes"] <= 1440)

    merged = (demo
              .merge(phq9, on="SEQN", how="inner")
              .merge(bpx, on="SEQN", how="inner")
              .merge(slq, on="SEQN", how="inner")
              .merge(paq[["SEQN", "exercise_minutes"]], on="SEQN", how="inner"))

    out = pd.DataFrame({
        "sleep_hours": merged["SLD012"],
        "sleep_quality": merged["SLQ050"],
        "exercise_minutes": merged["exercise_minutes"],
        "heart_rate": merged["BPXPLS"],
        "systolic_bp": merged["BPXSY1"],
        "diastolic_bp": merged["BPXDI1"],
        "steps": pd.NA,
        "phq9_total": merged["phq9_total"],
        "depression_label": merged["depression_label"],
        "age": merged["RIDAGEYR"],
        "gender": merged["RIAGENDR"],
        "poverty_index": merged["INDFMPIR"],
        "wtmec2yr": merged["WTMEC2YR"],
    })

    base_cols = ["sleep_hours", "sleep_quality", "exercise_minutes", "heart_rate",
                 "systolic_bp", "diastolic_bp", "steps"]
    labelled = out["depression_label"].notna()
    y = out.loc[labelled, "depression_label"].astype(int)
    nonnull_base = out.loc[labelled, base_cols].notna().sum(axis=1)

    meta = {
        "measured": {
            "n_rows_merged": int(len(out)),
            "n_labelled": int(labelled.sum()),
            "positives": int(y.sum()),
            "pos_rate": round(float(y.mean()), 4),
            "phq9_total_range": [float(pd.to_numeric(out["phq9_total"], errors="coerce").min()),
                                 float(pd.to_numeric(out["phq9_total"], errors="coerce").max())],
            "age_range": [int(out["age"].min()), int(out["age"].max())],
            "age_median": float(out["age"].median()),
            "missing_per_base_feature": {
                c: int(out.loc[labelled, c].isna().sum()) for c in base_cols
            },
            "n_with_all_6_available": int((nonnull_base == 6).sum()),
            "n_with_4plus_available": int((nonnull_base >= 4).sum()),
            "phq9_items_complete_rate": round(float(phq9["phq9_total"].notna().mean()), 4),
            "dpq_raw_counts_DPQ010": {str(k): int(v) for k, v in
                                      raw_items["DPQ010"].value_counts(dropna=False).head(10).items()},
        },
        "schema_map": SCHEMA_MAP,
        "schema_gap": SCHEMA_GAP,
        "label": {
            "column": "depression_label",
            "rule": "PHQ-9 total >= 10",
            "caveat": LABEL_CAVEAT,
        },
        "domain_offset": DOMAIN_OFFSET,
        "source": {
            "cycle": "NHANES 2017-2018",
            "files": {
                n: {"path": str(DATA_DIR / f"{n}.xpt"),
                    "sha256": sha256_file(DATA_DIR / f"{n}.xpt")}
                for n in ("DEMO_J", "DPQ_J", "BPX_J", "SLQ_J", "PAQ_J")
                if (DATA_DIR / f"{n}.xpt").exists()
            },
            "url": "https://wwwn.cdc.gov/Nchs/Data/Nhanes/Public/2017/DataFiles/",
            "license": "美国联邦政府作品，公有领域（CDC/NCHS 公开数据，无需 DUA）；"
                       "引用建议：CDC/NCHS, National Health and Nutrition Examination Survey, 2017-2018",
        },
        "notes": [
            "SAS xport 的 0 值在 pandas.read_sas 中读为 denormal 5.397605e-79；"
            "已按 codebook 逐值对拍确认为 0（非缺失），见脚本 docstring 坑 1。",
            "DPQ 7/9（拒答/不知道）置缺失，未做任何缺失填补。",
            "steps 列全为缺失：NHANES 2017-2018 公开文件无步数，不以 0 或均值伪造。",
            "本脚本只做接入与清洗，不训练、不评估、不挑优；外部验证（G2）另行立项。",
        ],
    }
    return out, meta


def main() -> int:
    ap = argparse.ArgumentParser(description="NHANES ingest")
    ap.add_argument("--check", action="store_true", help="只打印已有 manifest")
    args = ap.parse_args()

    if args.check:
        if OUT_MANIFEST.exists():
            print(OUT_MANIFEST.read_text(encoding="utf-8"))
            return 0
        print("manifest 不存在，先跑一次全量。")
        return 1

    df, meta = build()
    df.to_csv(OUT_CSV, index=False, encoding="utf-8")
    print(f"写出 {OUT_CSV.name}: {len(df)} 行 × {len(df.columns)} 列")

    manifest = {
        "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "generator": "scripts/data_acquisition/ingest_nhanes.py",
        **meta,
        "outputs": {"physiological_csv": {"path": str(OUT_CSV),
                                          "sha256": sha256_file(OUT_CSV)}},
    }
    OUT_MANIFEST.write_text(json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"写出 {OUT_MANIFEST.name}")
    print(json.dumps(manifest["measured"], ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
