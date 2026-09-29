"""D2 增强数据分析: 统计增强倍数分布."""
import pandas as pd

df = pd.read_csv(r"data/external/chinese_depression_corpus_v1.csv")
print("=== 增强数据分布 ===")
print(f"总样本: {len(df)}")
print(f"原始样本 (source_idx=-1): {(df['source_idx'] == -1).sum()}")
print(f"增强样本 (source_idx>=0): {(df['source_idx'] >= 0).sum()}")
print(f"唯一 source_idx (增强): {df[df['source_idx'] >= 0]['source_idx'].nunique()}")

print("\n=== 每个原始样本的增强倍数 ===")
aug_counts = df[df["source_idx"] >= 0].groupby("source_idx").size()
print(f"最大增强倍数: {aug_counts.max()}")
print(f"平均增强倍数: {aug_counts.mean():.1f}")
print(f"增强倍数>3 的源样本数: {(aug_counts > 3).sum()}")
print(f"增强倍数>5 的源样本数: {(aug_counts > 5).sum()}")

print("\n=== 列名 ===")
print(list(df.columns))

print("\n=== 增强样本示例 (source_idx=0) ===")
sample = df[df["source_idx"] == 0][["text", "source_idx", "label"]].head(3)
print(sample.to_string())

print("\n=== 原始样本示例 (source_idx=-1) ===")
orig = df[df["source_idx"] == -1][["text", "source_idx", "label"]].head(3)
print(orig.to_string())
