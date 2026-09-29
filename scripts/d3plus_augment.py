"""D3+ 中文语料数据增强.

策略:
    1. 同义词替换 (jieba + 预定义字典) → 1,275 条
    2. 回译增强 (transformers 翻译模型, 中→英→中) → 1,275 条
    3. 原始数据保留 → 1,275 条
    总计 ~3,825 条 (需 LLM 生成补足到 5,000)

输出:
    data/external/mmpsy_augmented.csv (增强数据,不含原始)
    data/external/chinese_depression_corpus_v1.csv (汇总: 原始 + 增强)

Usage:
    python scripts/d3plus_augment.py --strategy synonym          # 仅同义词替换
    python scripts/d3plus_augment.py --strategy backtranslation   # 仅回译
    python scripts/d3plus_augment.py --strategy all               # 全部
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import re
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Any

import pandas as pd

logging.basicConfig(level=logging.INFO, format="%(asctime)s [D3+] %(message)s")
logger = logging.getLogger("D3+")

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MMPSY_DATA_PATH = PROJECT_ROOT / "data" / "external" / "mmpsy_scores.csv"
AUGMENTED_OUTPUT = PROJECT_ROOT / "data" / "external" / "mmpsy_augmented.csv"
CORPUS_OUTPUT = PROJECT_ROOT / "data" / "external" / "chinese_depression_corpus_v1.csv"
SUMMARY_OUTPUT = PROJECT_ROOT / "model_assessment" / "d3plus_augment_summary.json"

# 同义词替换字典(非抑郁核心词,替换不影响语义)
SYNONYM_DICT = {
    # 时间词
    "今天": ["今天", "今日", "这天"],
    "昨天": ["昨天", "昨日", "昨天"],
    "明天": ["明天", "明日", "明天"],
    "最近": ["最近", "近来", "近期"],
    "现在": ["现在", "目前", "当下"],
    "以前": ["以前", "之前", "从前"],
    "有时候": ["有时候", "有时", "偶尔"],
    # 感受词(保留语义,微调表达)
    "感觉": ["感觉", "觉得", "感到"],
    "觉得": ["觉得", "感觉", "感到"],
    "认为": ["认为", "觉得", "以为"],
    "想法": ["想法", "念头", "心思"],
    # 学习/工作
    "学习": ["学习", "念书", "读书"],
    "上课": ["上课", "听课", "上堂"],
    "作业": ["作业", "功课", "习题"],
    "考试": ["考试", "测验", "测试"],
    "老师": ["老师", "教师", "师长"],
    "同学": ["同学", "同窗", "学友"],
    "学校": ["学校", "校园", "学堂"],
    "宿舍": ["宿舍", "寝室", "舍房"],
    # 日常活动
    "吃饭": ["吃饭", "用餐", "进餐"],
    "睡觉": ["睡觉", "休息", "睡眠"],
    "打游戏": ["打游戏", "玩游戏", "游戏"],
    "看电视": ["看电视", "看剧", "追剧"],
    "运动": ["运动", "锻炼", "活动"],
    # 程度副词
    "很": ["很", "挺", "蛮"],
    "非常": ["非常", "特别", "十分"],
    "比较": ["比较", "相对", "略微"],
    "一直": ["一直", "始终", "总是"],
    "总是": ["总是", "老是", "一直"],
    "经常": ["经常", "常常", "时常"],
    # 人称
    "父母": ["父母", "爸妈", "双亲"],
    "朋友": ["朋友", "友人", "伙伴"],
    "家里": ["家里", "家中", "家庭"],
    # 连接词
    "但是": ["但是", "不过", "然而"],
    "因为": ["因为", "由于", "因"],
    "所以": ["所以", "因此", "故"],
    "虽然": ["虽然", "尽管", "固然"],
}

# 抑郁核心词(不替换,保留语义)
DEPRESSION_CORE_WORDS = {
    "抑郁", "沮丧", "绝望", "痛苦", "焦虑", "压力", "孤独", "寂寞",
    "悲伤", "难过", "崩溃", "无力", "疲惫", "疲倦", "失眠", "嗜睡",
    "自杀", "自残", "死亡", "活着", "意义", "逃避", "承受", "撑不下去",
    "开心", "快乐", "兴趣", "喜欢", "讨厌", "恶心", "食欲", "体重",
}


def load_mmpsy_data() -> pd.DataFrame:
    """加载 mmpsy 数据,合并多段对话文本."""
    logger.info("加载 mmpsy 数据: %s", MMPSY_DATA_PATH)
    df = pd.read_csv(MMPSY_DATA_PATH)

    # 合并多段对话文本
    df["text"] = df["audio_transcript"].astype(str).str.split("|").apply(
        lambda parts: " ".join(p.strip() for p in parts)
    )
    df = df[df["text"].str.len() >= 5].reset_index(drop=True)

    logger.info(
        "加载完成: %d 样本, 阳性率=%.2f%%, 平均文本长度=%.0f 字符",
        len(df), df["phq9_binary"].mean() * 100, df["text"].str.len().mean(),
    )
    return df


def synonym_replace(text: str, replace_rate: float = 0.15) -> str:
    """同义词替换(保留抑郁核心词).

    Args:
        text: 原始文本
        replace_rate: 替换率(0-1)

    Returns:
        替换后的文本
    """
    import jieba

    words = list(jieba.cut(text))
    n_replaceable = 0
    n_replaced = 0
    new_words = []

    for word in words:
        word_stripped = word.strip()
        if (word_stripped in SYNONYM_DICT
            and word_stripped not in DEPRESSION_CORE_WORDS
            and len(word_stripped) >= 2):

            n_replaceable += 1
            # 按替换率决定是否替换
            if random.random() < replace_rate:
                synonyms = SYNONYM_DICT[word_stripped]
                # 随机选择一个同义词(避免选回原词)
                candidates = [s for s in synonyms if s != word_stripped]
                if candidates:
                    new_word = random.choice(candidates)
                    new_words.append(new_word)
                    n_replaced += 1
                    continue

        new_words.append(word)

    return "".join(new_words)


def augment_with_synonyms(
    df: pd.DataFrame,
    seed: int = 42,
    replace_rate: float = 0.15,
    tag: str = "synonym_replace",
) -> pd.DataFrame:
    """同义词替换增强(保留抑郁核心词).

    Args:
        df: 原始数据
        seed: 随机种子
        replace_rate: 替换率(0-1)
        tag: 增强标记名称

    Returns:
        增强后的 DataFrame
    """
    logger.info("同义词替换增强 (seed=%d, replace_rate=%.2f)...", seed, replace_rate)

    random.seed(seed)
    augmented = []

    for idx, row in df.iterrows():
        original_text = str(row["text"])
        augmented_text = synonym_replace(original_text, replace_rate=replace_rate)

        # 跳过无变化的样本(替换率太低)
        if augmented_text == original_text:
            continue

        augmented.append({
            "user_id": f"aug_{tag}_{seed}_{idx}",
            "phq9_score": row.get("phq9_score", 0),
            "phq9_level": row.get("phq9_level", "Unknown"),
            "phq9_binary": int(row["phq9_binary"]),
            "gad7_score": row.get("gad7_score", 0),
            "gad7_level": row.get("gad7_level", "Unknown"),
            "gad7_binary": int(row.get("gad7_binary", 0)),
            "audio_count": 0,
            "audio_transcript": augmented_text,
            "text": augmented_text,
            "augmentation": tag,
            "source_idx": int(idx),
        })

    aug_df = pd.DataFrame(augmented)
    logger.info("同义词替换完成 (seed=%d): %d 条增强样本", seed, len(aug_df))
    return aug_df


def augment_with_multi_synonym(df: pd.DataFrame) -> pd.DataFrame:
    """多轮同义词替换(3 种子 × 2 替换率 = 6 轮,最大化数据多样性).

    种子: 42 / 2024 / 2025
    替换率: 0.20 / 0.30
    """
    logger.info("多轮同义词替换 (3 种子 × 2 替换率 = 6 轮)...")

    configs = [
        (42, 0.20, "syn_v1"),
        (42, 0.30, "syn_v2"),
        (2024, 0.20, "syn_v3"),
        (2024, 0.30, "syn_v4"),
        (2025, 0.20, "syn_v5"),
        (2025, 0.30, "syn_v6"),
    ]

    all_parts = []
    for seed, rate, tag in configs:
        aug = augment_with_synonyms(df, seed=seed, replace_rate=rate, tag=tag)
        if len(aug) > 0:
            all_parts.append(aug)

    combined = pd.concat(all_parts, ignore_index=True) if all_parts else pd.DataFrame()

    # 内部去重(不同种子可能产出相同替换结果)
    if len(combined) > 0:
        import hashlib as _hashlib

        def _text_hash(text):
            norm = re.sub(r"\s+", "", str(text).lower().strip())
            return _hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]

        combined["_text_hash"] = combined["text"].apply(_text_hash)
        before = len(combined)
        combined = combined.drop_duplicates(subset=["_text_hash"], keep="first").reset_index(drop=True)
        after = len(combined)
        combined = combined.drop(columns=["_text_hash"])
        logger.info("多轮同义词替换内部去重: %d → %d (剔除 %d)", before, after, before - after)

    logger.info("多轮同义词替换完成: %d 条增强样本", len(combined))
    return combined


def backtranslate(text: str, zh_en_translator, en_zh_translator) -> str | None:
    """回译: 中文 → 英文 → 中文.

    对多段对话(用 | 分隔)分段回译.
    """
    # 分段处理(保留 | 分隔结构)
    segments = str(text).split("|")
    translated_segments = []

    for seg in segments:
        seg = seg.strip()
        if not seg or len(seg) < 2:
            translated_segments.append(seg)
            continue

        try:
            # 中 → 英
            en_result = zh_en_translator(seg, max_length=512)
            en_text = en_result[0]["translation_text"] if en_result else seg

            # 英 → 中
            zh_result = en_zh_translator(en_text, max_length=512)
            zh_text = zh_result[0]["translation_text"] if zh_result else seg

            translated_segments.append(zh_text)
        except Exception as e:
            logger.warning("回译失败: %s, 使用原文", e)
            translated_segments.append(seg)

    return " ".join(translated_segments)


def augment_with_backtranslation(df: pd.DataFrame, batch_size: int = 16) -> pd.DataFrame:
    """回译增强.

    使用 Helsinki-NLP/opus-mt 模型进行中→英→中回译.
    """
    logger.info("回译增强 (Helsinki-NLP/opus-mt-zh-en + opus-mt-en-zh)...")
    logger.info("(首次运行需下载翻译模型 ~600MB)")

    try:
        from transformers import pipeline
        import torch

        device = "cuda" if torch.cuda.is_available() else "cpu"
        logger.info("设备: %s", device)

        # 加载翻译模型
        logger.info("加载中→英翻译模型...")
        zh_en_translator = pipeline(
            "translation",
            model="Helsinki-NLP/opus-mt-zh-en",
            device=device,
        )

        logger.info("加载英→中翻译模型...")
        en_zh_translator = pipeline(
            "translation",
            model="Helsinki-NLP/opus-mt-en-zh",
            device=device,
        )

    except Exception as e:
        logger.error("翻译模型加载失败: %s", e)
        logger.error("跳过回译增强,请检查网络连接或手动下载模型")
        return pd.DataFrame()

    augmented = []
    n_total = len(df)
    start_time = time.time()

    for idx, row in df.iterrows():
        original_text = str(row["text"])
        bt_text = backtranslate(original_text, zh_en_translator, en_zh_translator)

        if bt_text and bt_text != original_text:
            augmented.append({
                "user_id": f"aug_bt_{idx}",
                "phq9_score": row.get("phq9_score", 0),
                "phq9_level": row.get("phq9_level", "Unknown"),
                "phq9_binary": int(row["phq9_binary"]),
                "gad7_score": row.get("gad7_score", 0),
                "gad7_level": row.get("gad7_level", "Unknown"),
                "gad7_binary": int(row.get("gad7_binary", 0)),
                "audio_count": 0,
                "audio_transcript": bt_text,
                "text": bt_text,
                "augmentation": "backtranslation",
                "source_idx": int(idx),
            })

        # 进度日志
        if (idx + 1) % 50 == 0:
            elapsed = time.time() - start_time
            eta = elapsed / (idx + 1) * (n_total - idx - 1)
            logger.info("回译进度: %d/%d (%.0f%%), 用时 %.0fs, ETA %.0fs",
                        idx + 1, n_total, (idx + 1) / n_total * 100,
                        elapsed, eta)

    aug_df = pd.DataFrame(augmented)
    elapsed = time.time() - start_time
    logger.info("回译完成: %d 条增强样本, 用时 %.0fs", len(aug_df), elapsed)
    return aug_df


def merge_and_dedup(original_df: pd.DataFrame, augmented_df: pd.DataFrame) -> pd.DataFrame:
    """合并原始和增强数据,去重."""
    logger.info("合并原始 + 增强数据...")

    # 统一列结构
    original_cols = ["user_id", "phq9_score", "phq9_level", "phq9_binary",
                     "gad7_score", "gad7_level", "gad7_binary",
                     "audio_count", "audio_transcript", "text"]

    # 原始数据添加 augmentation 标记
    original_df_clean = original_df.copy()
    original_df_clean["augmentation"] = "original"
    original_df_clean["source_idx"] = -1

    # 确保列一致
    for col in original_cols + ["augmentation", "source_idx"]:
        if col not in original_df_clean.columns:
            original_df_clean[col] = None
        if col not in augmented_df.columns:
            augmented_df[col] = None

    merged = pd.concat([
        original_df_clean[original_cols + ["augmentation", "source_idx"]],
        augmented_df[original_cols + ["augmentation", "source_idx"]],
    ], ignore_index=True)

    # 精确去重(基于文本规范化哈希)
    import hashlib

    def text_hash(text):
        norm = re.sub(r"\s+", "", str(text).lower().strip())
        return hashlib.sha256(norm.encode("utf-8")).hexdigest()[:16]

    merged["_text_hash"] = merged["text"].apply(text_hash)
    before = len(merged)
    merged = merged.drop_duplicates(subset=["_text_hash"], keep="first").reset_index(drop=True)
    after = len(merged)
    merged = merged.drop(columns=["_text_hash"])

    logger.info("去重: %d → %d (剔除 %d 重复)", before, after, before - after)

    return merged


def main() -> None:
    parser = argparse.ArgumentParser(description="D3+ 中文语料数据增强")
    parser.add_argument("--strategy",
                        choices=["synonym", "multi_synonym", "backtranslation", "all"],
                        default="all", help="增强策略")
    parser.add_argument("--seed", type=int, default=42, help="同义词替换随机种子(仅 synonym 策略)")
    parser.add_argument("--replace-rate", type=float, default=0.15,
                        help="同义词替换率(仅 synonym 策略)")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("D3+ 中文语料数据增强")
    logger.info("策略: %s", args.strategy)
    logger.info("=" * 60)

    # 加载原始数据
    df = load_mmpsy_data()

    augmented_parts = []

    # 策略 1: 单次同义词替换(向后兼容)
    if args.strategy == "synonym":
        syn_aug = augment_with_synonyms(df, seed=args.seed, replace_rate=args.replace_rate)
        if len(syn_aug) > 0:
            augmented_parts.append(syn_aug)

    # 策略 1.5: 多轮同义词替换(6 轮,最大化多样性)
    if args.strategy == "multi_synonym":
        multi_aug = augment_with_multi_synonym(df)
        if len(multi_aug) > 0:
            augmented_parts.append(multi_aug)

    # 策略 2: 回译
    if args.strategy in ("backtranslation", "all"):
        bt_aug = augment_with_backtranslation(df)
        if len(bt_aug) > 0:
            augmented_parts.append(bt_aug)

    # 策略 3: 全部 = 多轮同义词 + 回译
    if args.strategy == "all":
        multi_aug = augment_with_multi_synonym(df)
        if len(multi_aug) > 0:
            augmented_parts.append(multi_aug)

    if not augmented_parts:
        logger.warning("无增强数据生成")
        return

    # 合并本次增强数据
    new_augmented = pd.concat(augmented_parts, ignore_index=True)
    logger.info("本次新增增强: %d 条", len(new_augmented))

    # 追加模式:如果已有增强文件,合并历史增强数据(避免覆盖)
    if AUGMENTED_OUTPUT.exists():
        try:
            existing_aug = pd.read_csv(AUGMENTED_OUTPUT)
            logger.info("发现历史增强文件: %d 条, 将合并", len(existing_aug))
            # 排除本次相同策略的旧数据(避免重复)
            new_tags = set(new_augmented["augmentation"].unique()) if "augmentation" in new_augmented.columns else set()
            if new_tags:
                existing_aug = existing_aug[~existing_aug["augmentation"].isin(new_tags)] if "augmentation" in existing_aug.columns else existing_aug
                logger.info("排除同策略旧数据后历史增强: %d 条", len(existing_aug))
            all_augmented = pd.concat([existing_aug, new_augmented], ignore_index=True)
        except Exception as e:
            logger.warning("读取历史增强文件失败: %s, 使用本次数据", e)
            all_augmented = new_augmented
    else:
        all_augmented = new_augmented

    logger.info("增强数据总计: %d 条", len(all_augmented))

    # 保存增强数据(不含原始)
    all_augmented.to_csv(AUGMENTED_OUTPUT, index=False, encoding="utf-8")
    logger.info("增强数据已保存: %s", AUGMENTED_OUTPUT)

    # 合并原始 + 增强
    corpus = merge_and_dedup(df, all_augmented)
    corpus.to_csv(CORPUS_OUTPUT, index=False, encoding="utf-8")
    logger.info("汇总语料已保存: %s", CORPUS_OUTPUT)

    # 生成摘要
    summary = {
        "augmented_at": datetime.now().isoformat(timespec="seconds"),
        "strategy": args.strategy,
        "original_samples": int(len(df)),
        "augmented_samples": int(len(all_augmented)),
        "total_after_dedup": int(len(corpus)),
        "augmentation_breakdown": all_augmented["augmentation"].value_counts().to_dict() if len(all_augmented) > 0 else {},
        "label_distribution_original": df["phq9_binary"].value_counts().to_dict(),
        "label_distribution_corpus": corpus["phq9_binary"].value_counts().to_dict() if "phq9_binary" in corpus.columns else {},
        "positive_rate_original": float(df["phq9_binary"].mean()),
        "positive_rate_corpus": float(corpus["phq9_binary"].mean()) if "phq9_binary" in corpus.columns else 0.0,
        "target_5000_met": len(corpus) >= 5000,
        "gap_to_5000": max(0, 5000 - len(corpus)),
    }

    SUMMARY_OUTPUT.parent.mkdir(parents=True, exist_ok=True)
    with open(SUMMARY_OUTPUT, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    logger.info("=" * 60)
    logger.info("D3+ 增强完成")
    logger.info("=" * 60)
    logger.info("原始: %d 条", summary["original_samples"])
    logger.info("增强: %d 条", summary["augmented_samples"])
    logger.info("去重后总计: %d 条", summary["total_after_dedup"])
    logger.info("目标 5000: %s (差距 %d)",
                "✓ 达标" if summary["target_5000_met"] else "✗ 未达标",
                summary["gap_to_5000"])
    logger.info("标签分布(原始): %s", summary["label_distribution_original"])
    logger.info("标签分布(语料): %s", summary["label_distribution_corpus"])
    logger.info("阳性率: %.2f%% → %.2f%%",
                summary["positive_rate_original"] * 100,
                summary["positive_rate_corpus"] * 100)


if __name__ == "__main__":
    main()
