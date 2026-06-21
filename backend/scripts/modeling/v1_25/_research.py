"""Research script: analyze mmpsy raw data for v1.25 planning."""
import pandas as pd
import numpy as np

mmpsy = pd.read_csv(r"e:\code\bysj\data\external\mmpsy_scores.csv")

print("=== 数据集基本信息 ===")
print(f"行数: {len(mmpsy)}")
print(f"列数: {len(mmpsy.columns)}")
print()

print("=== 所有列名 ===")
for c in mmpsy.columns:
    nulls = mmpsy[c].isnull().sum()
    nunique = mmpsy[c].nunique()
    dtype = str(mmpsy[c].dtype)
    print(f"  {c}: dtype={dtype}, nulls={nulls}, unique={nunique}")
print()

print("=== 标签相关列详情 ===")
label_cols = [c for c in mmpsy.columns if any(k in c.lower() for k in ["depress", "binary", "phq", "label", "risk", "diag"])]
for c in label_cols:
    vals = mmpsy[c].dropna()
    vc = vals.value_counts().head(10)
    print(f"  {c}: values={sorted(vc.index.tolist())[:20]}, counts={dict(vc)}")
print()

print("=== PHQ-9 条目 ===")
phq_items = [c for c in mmpsy.columns if "phq" in c.lower() and c != "phq9_score"]
for c in phq_items:
    vals = mmpsy[c].dropna()
    if len(vals) > 0:
        print(f"  {c}: range=[{vals.min()}, {vals.max()}], nulls={mmpsy[c].isnull().sum()}/{len(mmpsy)}")
print()

print("=== GAD-7 条目 ===")
gad_items = [c for c in mmpsy.columns if "gad" in c.lower() and c != "gad7_score"]
for c in gad_items:
    vals = mmpsy[c].dropna()
    if len(vals) > 0:
        print(f"  {c}: range=[{vals.min()}, {vals.max()}], nulls={mmpsy[c].isnull().sum()}/{len(mmpsy)}")
print()

print("=== 文本相关列 ===")
text_cols = [c for c in mmpsy.columns if any(k in c.lower() for k in ["text", "transcript", "audio", "content", "note"])]
for c in text_cols:
    vals = mmpsy[c].dropna()
    if mmpsy[c].dtype == object:
        lengths = vals.str.len()
        n_empty = int((vals == "").sum())
        print(f"  {c}: count={len(vals)}/{len(mmpsy)}, len_range=[{lengths.min()}, {lengths.max()}], mean_len={lengths.mean():.0f}, empty={n_empty}")
    else:
        print(f"  {c}: values={sorted(vals.unique())[:10]}")
print()

print("=== 缺失值全局 ===")
missing = mmpsy.isnull().sum()
missing_pct = (missing / len(mmpsy) * 100).round(1)
for c in mmpsy.columns:
    if missing[c] > 0:
        print(f"  {c}: {missing[c]} missing ({missing_pct[c]}%)")
print()

print("=== PHQ-9 vs depression_binary 关系 ===")
if "phq9_score" in mmpsy.columns and "depression_binary" in mmpsy.columns:
    valid = mmpsy[["phq9_score", "depression_binary"]].dropna()
    print(f"PHQ-9 cutoff analysis ({len(valid)} samples):")
    for cutoff in [5, 10, 15, 20]:
        pred = (valid["phq9_score"] >= cutoff).astype(int)
        agreement = (pred == valid["depression_binary"]).mean()
        print(f"  cutoff={cutoff}: agreement with depression_binary = {agreement:.1%}")

print()
print("=== 已有结构化特征文件中 demographic 字段的缺失模式 ===")
try:
    feats = pd.read_csv(r"e:\code\bysj\data\processed\mmpsy_structured_features.csv")
    demo_cols = ["age", "gender", "cgpa"]
    for c in demo_cols:
        if c in feats.columns:
            nulls = feats[c].isnull().sum()
            pct = nulls / len(feats) * 100
            print(f"  {c}: {nulls}/{len(feats)} missing ({pct:.1f}%)")
    
    src_cols = [c for c in feats.columns if c.endswith("_source")]
    for c in src_cols:
        base = c.replace("_source", "")
        if base in feats.columns:
            derived = (feats[c] == "derived").sum()
            collected = (feats[c] == "collected").sum()
            missing_src = (feats[c] == "missing").sum()
            n_nan = feats[base].isnull().sum()
            print(f"  {base}: derived={derived}, collected={collected}, missing_src={missing_src}, NaN_values={n_nan}/{len(feats)}")
except Exception as e:
    print(f"  Error reading features: {e}")
