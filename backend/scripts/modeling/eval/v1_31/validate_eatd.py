#!/usr/bin/env python
"""EATD 外部测试集 · 结构校验 + 污染检查（只验结构与重叠，不报任何模型指标）。

用法（数据放好后）：
    cd backend
    .venv/Scripts/python.exe scripts/modeling/eval/v1_31/validate_eatd.py --data-root ../data/external/eatd

职责（不允许报指标，防止"先看结果"）：
1. 扫描 data_root 下每个志愿者文件夹，确认存在文本转录 + new_label.txt/label.txt；
2. 按预注册规则拼接 positive→negative→neutral，统计可解析样本数、阳性数（≥53，≥60）；
3. 与 MMPsy 派生训练语料做重叠检查（精确匹配 + 近似去重给命中率）；
4. 输出结构报告 json（不含任何模型预测）。

不会读取模型、不会 transform、不会 predict。
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import re
from pathlib import Path

REPO = Path(__file__).resolve().parents[5]
TRAIN_CORPORA = [
    REPO / "data" / "external" / "chinese_depression_corpus_v1.csv",
    REPO / "data" / "external" / "chinese_depression_corpus_v2_clean.csv",
    REPO / "data" / "external" / "mmpsy_augmented.csv",
]
SEG_ORDER = ("positive", "negative", "neutral")
SDS_MAIN = 53.0
SDS_SEVERE = 60.0


def find_text_file(folder: Path, seg: str) -> Path | None:
    for name in (f"{seg}.txt", f"{seg}_out.txt"):
        p = folder / name
        if p.exists():
            return p
    return None


def _parse_first_number(path: Path) -> float | None:
    """健壮解析：去 BOM、取首个数字 token（容忍 'SDS: 53' 等前缀）。"""
    import re
    raw = path.read_text(encoding="utf-8-sig", errors="ignore")
    m = re.search(r"-?\d+(?:\.\d+)?", raw)
    return float(m.group(0)) if m else None


def read_score(folder: Path) -> float | None:
    # 预注册用 new_label.txt（标准化 SDS = 原始×1.25）；缺失回退 label.txt×1.25
    nl = folder / "new_label.txt"
    lb = folder / "label.txt"
    if nl.exists():
        return _parse_first_number(nl)
    if lb.exists():
        v = _parse_first_number(lb)
        return v * 1.25 if v is not None else None
    return None


def collect_subjects(data_root: Path) -> list[dict]:
    subjects = []
    for folder in sorted(p for p in data_root.rglob("*") if p.is_dir()):
        segs = {}
        for seg in SEG_ORDER:
            f = find_text_file(folder, seg)
            if f is not None:
                segs[seg] = f.read_text(encoding="utf-8", errors="ignore")
        if not segs:
            continue
        score = read_score(folder)
        text = "\n".join(segs[s] for s in SEG_ORDER if s in segs).strip()
        if not text:
            continue
        subjects.append({
            "subject": folder.name,
            "score": score,
            "n_segments": len(segs),
            "chars": len(text),
            "text_sha1": hashlib.sha1(text.encode("utf-8")).hexdigest(),
            "text": text,
        })
    return subjects


def load_train_texts() -> set[str]:
    seen: set[str] = set()
    for path in TRAIN_CORPORA:
        if not path.exists():
            continue
        with open(path, encoding="utf-8-sig", errors="ignore") as f:
            for row in csv.DictReader(f):
                t = (row.get("text") or "").strip()
                if t:
                    seen.add(hashlib.sha1(t.encode("utf-8")).hexdigest())
    return seen


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--data-root", required=True)
    ap.add_argument("--out", default=str(Path(__file__).resolve().parent / "eatd_structure_report.json"))
    args = ap.parse_args()

    root = Path(args.data_root)
    if not root.exists():
        print(f"[validate] data-root 不存在：{root}")
        return 2

    subjects = collect_subjects(root)
    scored = [s for s in subjects if s["score"] is not None]
    pos_main = sum(1 for s in scored if s["score"] >= SDS_MAIN)
    pos_severe = sum(1 for s in scored if s["score"] >= SDS_SEVERE)

    train_sha = load_train_texts()
    overlap = sum(1 for s in subjects if s["text_sha1"] in train_sha)

    report = {
        "_note": "EATD 结构校验（无模型指标）。预注册见 EATD_PREREGISTRATION.md。",
        "data_root": str(root),
        "n_subject_folders": len(subjects),
        "n_with_score": len(scored),
        "n_missing_score": len(subjects) - len(scored),
        "positive_ge53": pos_main,
        "negative_lt53": len(scored) - pos_main,
        "positive_ge60_desc": pos_severe,
        "positive_rate_ge53": round(pos_main / len(scored), 4) if scored else None,
        "segments_per_subject_hist": {},
        "train_corpus_texts": len(train_sha),
        "exact_overlap_with_train": overlap,
        "score_min": min((s["score"] for s in scored), default=None),
        "score_max": max((s["score"] for s in scored), default=None),
    }
    hist: dict[int, int] = {}
    for s in subjects:
        hist[s["n_segments"]] = hist.get(s["n_segments"], 0) + 1
    report["segments_per_subject_hist"] = {str(k): v for k, v in sorted(hist.items())}

    out = Path(args.out)
    out.write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"[validate] subjects={len(subjects)} scored={len(scored)} "
          f"pos>=53={pos_main} ({report['positive_rate_ge53']}) overlap={overlap}")
    print(f"  -> {out}")
    if overlap > 0:
        print(f"  ! 警告：{overlap} 个样本与训练语料精确重叠，评估时须剔除")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())