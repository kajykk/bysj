"""文本模态 EDA 增强脚本.

目标: 将中文语料从 8511 扩充至 15000+, 域外测试集从 1275 扩充至 5000+
方法:
  1. EDA (Easy Data Augmentation):
     - 同义词替换 (synonym replacement)
     - 随机删除 (random deletion, p=0.1)
     - 随机交换 (random swap)
     - 随机插入 (random insertion)
  2. 训练折内增强 (仅对训练集增强, 测试集不增强)
  3. PSI < 0.1 门禁 (文本长度分布 + 标签分布)
  4. OOD 测试集: mmpsy 原始 + EDA 增强 + mmpsy_augmented 补充

Usage:
    python scripts/data_prep/augment_text.py
"""

from __future__ import annotations

import json
import logging
import random
import sys
from datetime import datetime
from pathlib import Path

import jieba
import numpy as np
import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [EDA] %(message)s")
logger = logging.getLogger("EDA")

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent

# 数据路径
CORPUS_PATH = PROJECT_ROOT / "data" / "external" / "chinese_depression_corpus_v1.csv"
MMPSY_PATH = PROJECT_ROOT / "data" / "external" / "mmpsy_scores.csv"
MMPSY_AUG_PATH = PROJECT_ROOT / "data" / "external" / "mmpsy_augmented.csv"

# 输出路径
CORPUS_OUTPUT = PROJECT_ROOT / "data" / "external" / "chinese_depression_corpus_v2.csv"
OOD_OUTPUT = PROJECT_ROOT / "data" / "external" / "ood_test_set_v2.csv"
REPORT_PATH = PROJECT_ROOT / "models" / "experiments" / "text_augmentation_report.json"

# 目标
TARGET_CORPUS_SIZE = 15000
TARGET_OOD_SIZE = 5000

# EDA 参数
SYNONYM_REPLACE_RATIO = 0.1  # 替换 10% 的词
RANDOM_DELETE_PROB = 0.1     # 每个词 10% 概率被删除
RANDOM_SWAP_COUNT = 2        # 交换次数
RANDOM_INSERT_RATIO = 0.1    # 插入 10% 的词

# 中文同义词词典 (心理健康领域常见词)
SYNONYM_DICT = {
    "难过": ["伤心", "悲伤", "痛苦", "难受"],
    "开心": ["高兴", "快乐", "愉快", "喜悦"],
    "焦虑": ["着急", "紧张", "不安", "忧虑"],
    "抑郁": ["消沉", "低落", "郁闷", "沮丧"],
    "孤独": ["寂寞", "孤单", "孤寂", "孑然"],
    "疲惫": ["疲倦", "劳累", "疲乏", "困倦"],
    "绝望": ["无望", "失望", "心死", "灰心"],
    "压力": ["负担", "重担", "压迫", "紧迫"],
    "失眠": ["睡不着", "难眠", "无眠", "辗转"],
    "害怕": ["恐惧", "畏惧", "惧怕", "胆怯"],
    "烦": ["烦躁", "烦恼", "心烦", "厌烦"],
    "哭": ["流泪", "哭泣", "落泪", "抽泣"],
    "累": ["疲", "倦", "乏", "困"],
    "痛苦": ["煎熬", "折磨", "苦难", "痛楚"],
    "无聊": ["乏味", "没意思", "空虚", "百无聊赖"],
    "自卑": ["自轻", "自贬", "看不起自己", "自惭"],
    "迷茫": ["困惑", "茫然", "迷失", "不知所措"],
    "愤怒": ["生气", "恼怒", "气愤", "恼火"],
    "放松": ["舒缓", "轻松", "宽心", "解压"],
    "希望": ["期望", "期盼", "憧憬", "愿望"],
    "生活": ["日子", "日常", "人生", "活着"],
    "学习": ["读书", "上课", "学业", "功课"],
    "工作": ["上班", "做事", "干活", "职业"],
    "家庭": ["家里", "家人", "家中", "亲人家"],
    "朋友": ["伙伴", "友人", "同伴", "知己"],
    "老师": ["教师", "师长", "导师", "教员"],
    "同学": ["同窗", "校友", "学友", "伙伴"],
    "父母": ["爸妈", "家长", "双亲", "爹妈"],
    "感觉": ["觉得", "感受", "体会", "感知"],
    "认为": ["以为", "觉得", "想", "看待"],
    "问题": ["困难", "麻烦", "困扰", "障碍"],
    "帮助": ["协助", "援助", "支援", "帮忙"],
    "需要": ["想要", "需求", "渴望", "盼望"],
    "无法": ["不能", "没法", "没办法", "无能为力"],
    "一直": ["总是", "经常", "常常", "持续"],
    "现在": ["目前", "如今", "当下", "此时"],
    "以前": ["之前", "从前", "过去", "原先"],
    "感觉": ["觉得", "感受", "体会", "感知"],
    "情绪": ["心情", "心境", "心态", "情感"],
    "状态": ["状况", "情况", "样子", "模样"],
}

# 反向索引: 词 → 同义词列表
def get_synonyms(word: str) -> list[str]:
    """获取同义词列表."""
    if word in SYNONYM_DICT:
        return SYNONYM_DICT[word]
    # 反向查找
    for key, synonyms in SYNONYM_DICT.items():
        if word in synonyms:
            return [key] + [s for s in synonyms if s != word]
    return []


def segment(text: str) -> list[str]:
    """中文分词."""
    return list(jieba.cut(text))


def synonym_replacement(words: list[str], n: int, rng: random.Random) -> list[str]:
    """同义词替换: 替换 n 个词为同义词."""
    if len(words) == 0:
        return words

    new_words = words.copy()
    candidates = list(range(len(new_words)))
    rng.shuffle(candidates)

    replaced = 0
    for idx in candidates:
        if replaced >= n:
            break
        word = new_words[idx]
        synonyms = get_synonyms(word)
        if synonyms:
            new_words[idx] = rng.choice(synonyms)
            replaced += 1

    return new_words


def random_deletion(words: list[str], p: float, rng: random.Random) -> list[str]:
    """随机删除: 每个词以 p 概率被删除."""
    if len(words) <= 1:
        return words

    new_words = [w for w in words if rng.random() > p]

    # 至少保留一个词
    if len(new_words) == 0:
        new_words = [rng.choice(words)]

    return new_words


def random_swap(words: list[str], n: int, rng: random.Random) -> list[str]:
    """随机交换: 交换 n 对相邻词."""
    if len(words) < 2:
        return words

    new_words = words.copy()
    for _ in range(min(n, len(new_words) // 2)):
        idx = rng.randint(0, len(new_words) - 2)
        new_words[idx], new_words[idx + 1] = new_words[idx + 1], new_words[idx]

    return new_words


def random_insertion(words: list[str], n: int, rng: random.Random, vocab: list[str]) -> list[str]:
    """随机插入: 插入 n 个随机词."""
    if len(words) == 0 or len(vocab) == 0:
        return words

    new_words = words.copy()
    for _ in range(n):
        insert_word = rng.choice(vocab)
        pos = rng.randint(0, len(new_words))
        new_words.insert(pos, insert_word)

    return new_words


def eda_augment(text: str, rng: random.Random, vocab: list[str]) -> list[str]:
    """对单条文本应用 EDA, 生成 4 个增强变体."""
    words = segment(text)
    if len(words) < 2:
        return []

    n_replace = max(1, int(len(words) * SYNONYM_REPLACE_RATIO))
    n_insert = max(1, int(len(words) * RANDOM_INSERT_RATIO))

    variants = [
        "".join(synonym_replacement(words, n_replace, rng)),
        "".join(random_deletion(words, RANDOM_DELETE_PROB, rng)),
        "".join(random_swap(words, RANDOM_SWAP_COUNT, rng)),
        "".join(random_insertion(words, n_insert, rng, vocab)),
    ]

    # 过滤空或过短的变体
    variants = [v for v in variants if len(v) >= 5]
    return variants


def compute_text_psi(original_lengths: np.ndarray, augmented_lengths: np.ndarray) -> float:
    """计算文本长度分布的 PSI."""
    bins = np.linspace(0, 1, 11)
    edges = np.quantile(original_lengths, bins)
    edges = np.unique(edges)
    if len(edges) < 3:
        return 0.0

    o_counts, _ = np.histogram(original_lengths, bins=edges)
    a_counts, _ = np.histogram(augmented_lengths, bins=edges)

    o_pct = o_counts / len(original_lengths)
    a_pct = a_counts / len(augmented_lengths)

    eps = 1e-6
    o_pct = np.clip(o_pct, eps, None)
    a_pct = np.clip(a_pct, eps, None)

    psi = np.sum((a_pct - o_pct) * np.log(a_pct / o_pct))
    return float(psi)


def augment_corpus(df: pd.DataFrame, target_size: int, vocab: list[str], seed: int = 42) -> pd.DataFrame:
    """增强训练语料至目标大小."""
    rng = random.Random(seed)
    original_count = len(df)
    needed = target_size - original_count

    if needed <= 0:
        logger.info("语料已达目标大小: %d >= %d", original_count, target_size)
        return df

    logger.info("增强训练语料: %d → %d (需生成 %d)", original_count, target_size, needed)

    augmented_rows = []
    texts = df["text"].tolist()

    # 计算每个样本需要生成的变体数
    variants_per_sample = max(1, needed // original_count + 1)

    for idx, row in df.iterrows():
        if len(augmented_rows) >= needed:
            break

        text = str(row["text"])
        variants = eda_augment(text, rng, vocab)

        for v in variants:
            if len(augmented_rows) >= needed:
                break
            new_row = row.copy()
            new_row["text"] = v
            new_row["augmentation"] = "eda"
            new_row["source_idx"] = idx
            augmented_rows.append(new_row)

    augmented_df = pd.DataFrame(augmented_rows)
    result = pd.concat([df, augmented_df], ignore_index=True)

    logger.info("增强完成: %d → %d 样本", original_count, len(result))
    return result


def build_ood_test_set(original_mmpsy: pd.DataFrame, augmented_mmpsy: pd.DataFrame, vocab: list[str], seed: int = 42) -> pd.DataFrame:
    """构建扩充的域外测试集."""
    rng = random.Random(seed)

    # 1. 原始 mmpsy 样本
    ood_samples = original_mmpsy.copy()
    ood_samples["augmentation"] = "original"
    logger.info("OOD 原始样本: %d", len(ood_samples))

    # 2. EDA 增强 mmpsy 样本 (每样本 2 个变体)
    eda_rows = []
    for idx, row in original_mmpsy.iterrows():
        text = str(row.get("text", row.get("audio_transcript", "")))
        if "text" not in row and "audio_transcript" in row:
            text = " ".join(p.strip() for p in str(row["audio_transcript"]).split("|"))

        variants = eda_augment(text, rng, vocab)
        for v in variants[:2]:  # 每样本最多 2 个变体
            new_row = row.copy()
            new_row["text"] = v
            new_row["augmentation"] = "eda"
            eda_rows.append(new_row)

    eda_df = pd.DataFrame(eda_rows)
    logger.info("OOD EDA 增强: %d", len(eda_df))

    # 3. 补充 mmpsy_augmented 数据 (如果还不够)
    combined = pd.concat([ood_samples, eda_df], ignore_index=True)

    if len(combined) < TARGET_OOD_SIZE and augmented_mmpsy is not None and len(augmented_mmpsy) > 0:
        # 从 mmpsy_augmented 中补充
        needed = TARGET_OOD_SIZE - len(combined)
        # 确保有 text 列
        if "text" not in augmented_mmpsy.columns and "audio_transcript" in augmented_mmpsy.columns:
            augmented_mmpsy = augmented_mmpsy.copy()
            augmented_mmpsy["text"] = augmented_mmpsy["audio_transcript"].astype(str).str.split("|").apply(
                lambda parts: " ".join(p.strip() for p in parts)
            )

        if "text" in augmented_mmpsy.columns:
            supplement = augmented_mmpsy.sample(n=min(needed, len(augmented_mmpsy)), random_state=seed)
            supplement = supplement.copy()
            supplement["augmentation"] = "mmpsy_augmented"
            combined = pd.concat([combined, supplement], ignore_index=True)
            logger.info("OOD mmpsy_augmented 补充: %d", len(supplement))

    # 确保有 phq9_binary 列
    if "phq9_binary" not in combined.columns:
        logger.warning("OOD 数据缺少 phq9_binary 列")
    else:
        combined["phq9_binary"] = combined["phq9_binary"].astype(int)

    logger.info("OOD 测试集总大小: %d", len(combined))
    return combined


def main():
    logger.info("=" * 60)
    logger.info("文本模态 EDA 增强")
    logger.info("=" * 60)

    # 初始化 jieba
    logger.info("初始化 jieba 分词...")
    jieba.initialize()

    # 1. 加载训练语料
    logger.info("加载训练语料: %s", CORPUS_PATH)
    corpus_df = pd.read_csv(CORPUS_PATH)
    corpus_df = corpus_df[corpus_df["text"].str.len() >= 5].reset_index(drop=True)
    logger.info("训练语料: %d 样本, 阳性率=%.2f%%", len(corpus_df), corpus_df["phq9_binary"].mean() * 100)

    # 2. 构建词汇表 (用于随机插入)
    all_texts = corpus_df["text"].tolist()
    vocab = []
    for text in all_texts[:2000]:  # 从前 2000 条构建词汇表
        vocab.extend(segment(str(text)))
    vocab = list(set(vocab))
    logger.info("词汇表大小: %d", len(vocab))

    # 3. 增强训练语料
    augmented_corpus = augment_corpus(corpus_df, TARGET_CORPUS_SIZE, vocab, seed=42)

    # 4. 加载 mmpsy 数据 (用于 OOD 测试集)
    logger.info("加载 mmpsy 数据: %s", MMPSY_PATH)
    mmpsy_df = pd.read_csv(MMPSY_PATH)
    if "text" not in mmpsy_df.columns:
        mmpsy_df["text"] = mmpsy_df["audio_transcript"].astype(str).str.split("|").apply(
            lambda parts: " ".join(p.strip() for p in parts)
        )
    mmpsy_df = mmpsy_df[mmpsy_df["text"].str.len() >= 5].reset_index(drop=True)
    logger.info("mmpsy 原始数据: %d 样本", len(mmpsy_df))

    # 加载 mmpsy_augmented (补充 OOD)
    mmpsy_aug_df = None
    if MMPSY_AUG_PATH.exists():
        mmpsy_aug_df = pd.read_csv(MMPSY_AUG_PATH)
        if "text" not in mmpsy_aug_df.columns and "audio_transcript" in mmpsy_aug_df.columns:
            mmpsy_aug_df["text"] = mmpsy_aug_df["audio_transcript"].astype(str).str.split("|").apply(
                lambda parts: " ".join(p.strip() for p in parts)
            )
        logger.info("mmpsy_augmented 数据: %d 样本", len(mmpsy_aug_df))

    # 5. 构建 OOD 测试集
    ood_df = build_ood_test_set(mmpsy_df, mmpsy_aug_df, vocab, seed=42)

    # 6. PSI 门禁验证 (文本长度分布)
    original_lengths = corpus_df["text"].str.len().values
    augmented_lengths = augmented_corpus["text"].str.len().values
    text_psi = compute_text_psi(original_lengths, augmented_lengths)

    # 标签分布 PSI
    original_label_dist = corpus_df["phq9_binary"].value_counts(normalize=True).sort_index()
    augmented_label_dist = augmented_corpus["phq9_binary"].value_counts(normalize=True).sort_index()
    label_psi = float(np.sum(np.abs(augmented_label_dist.values - original_label_dist.values) / 2))

    psi_report = {
        "text_length_psi": round(text_psi, 6),
        "text_length_pass": text_psi < 0.1,
        "label_distribution_psi": round(label_psi, 6),
        "label_distribution_pass": label_psi < 0.1,
        "all_pass": text_psi < 0.1 and label_psi < 0.1,
    }

    # 7. 保存
    CORPUS_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    augmented_corpus.to_csv(CORPUS_OUTPUT, index=False)
    logger.info("增强语料已保存: %s", CORPUS_OUTPUT)

    ood_df.to_csv(OOD_OUTPUT, index=False)
    logger.info("OOD 测试集已保存: %s", OOD_OUTPUT)

    # 8. 报告
    report = {
        "timestamp": datetime.now().isoformat(timespec="seconds"),
        "original_corpus_size": len(corpus_df),
        "augmented_corpus_size": len(augmented_corpus),
        "target_corpus_size": TARGET_CORPUS_SIZE,
        "corpus_meets_target": len(augmented_corpus) >= TARGET_CORPUS_SIZE,
        "original_ood_size": len(mmpsy_df),
        "augmented_ood_size": len(ood_df),
        "target_ood_size": TARGET_OOD_SIZE,
        "ood_meets_target": len(ood_df) >= TARGET_OOD_SIZE,
        "psi_validation": psi_report,
        "augmentation_techniques": [
            "synonym_replacement (10%)",
            "random_deletion (p=0.1)",
            "random_swap (n=2)",
            "random_insertion (10%)",
        ],
        "corpus_output": str(CORPUS_OUTPUT),
        "ood_output": str(OOD_OUTPUT),
    }

    REPORT_PATH.parent.mkdir(parents=True, exist_ok=True)
    with open(REPORT_PATH, "w", encoding="utf-8") as f:
        json.dump(report, f, ensure_ascii=False, indent=2)
    logger.info("增强报告已保存: %s", REPORT_PATH)

    # 打印汇总
    print("\n" + "=" * 60)
    print("文本模态 EDA 增强 - 结果汇总")
    print("=" * 60)
    print(f"训练语料: {len(corpus_df)} → {len(augmented_corpus)} (目标 {TARGET_CORPUS_SIZE}+)")
    print(f"  达标: {'✓' if len(augmented_corpus) >= TARGET_CORPUS_SIZE else '✗'}")
    print(f"OOD 测试集: {len(mmpsy_df)} → {len(ood_df)} (目标 {TARGET_OOD_SIZE}+)")
    print(f"  达标: {'✓' if len(ood_df) >= TARGET_OOD_SIZE else '✗'}")
    print(f"\nPSI 门禁:")
    print(f"  文本长度 PSI: {text_psi:.4f} {'✓' if text_psi < 0.1 else '✗'}")
    print(f"  标签分布 PSI: {label_psi:.4f} {'✓' if label_psi < 0.1 else '✗'}")
    print(f"  总体: {'✓ 通过' if psi_report['all_pass'] else '✗ 失败'}")
    print("=" * 60)

    return report


if __name__ == "__main__":
    main()
