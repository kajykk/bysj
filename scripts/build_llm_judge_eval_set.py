"""P2-2: 生成 LLM-as-judge 离线评估的**标注模板**（不生成金标准）。

设计立场（为什么不直接产出「金标准」）:
    金标准的唯一合法来源是**人工标注**（临床/心理背景的标注者）。用规则、
    现有模型或本脚本的抽样逻辑「生成」金标准，等于把待验证的判断当成基准，
    会让后续 kappa 失去意义。故本脚本只负责:
      1. 分层抽样（保证正负例与文本长度分布可用）;
      2. 导出**待标注** CSV（含参考信息与留空列）;
      3. 打印标注指引（样本量依据、kappa 门槛、注意事项）。

用法:
    cd backend
    .venv/Scripts/python.exe ../scripts/build_llm_judge_eval_set.py
    .venv/Scripts/python.exe ../scripts/build_llm_judge_eval_set.py --n 120 --out ../docs/planning/llm_judge_eval_template.csv
"""

from __future__ import annotations

import argparse
from pathlib import Path

import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
CORPUS = REPO_ROOT / "data" / "external" / "chinese_depression_corpus_v1.csv"
SEED = 42

#: kappa 门槛（P2-2 文档定义）: >= 0.6 才考虑接入; < 0.6 直接否决
KAPPA_GATE = 0.6
#: 样本量依据: 期望一致率 0.8、95% CI 半宽 <= 0.10 -> n >= 64; 取 100 留余量
DEFAULT_N = 100

GUIDE = """\
## 标注指引（随模板一起给标注者）

### 金标准不需要你从零标 —— 语料自带临床量表
`ref_phq9_score` / `ref_phq9_binary`（以及 GAD-7 两列）来自 **PHQ-9 / GAD-7 临床量表实测**，
不是模型输出，因此**直接作为金标准**。你的工作是**校验**，不是从零标注：

- 认可：`human_review` 留空（默认采纳量表标签）
- 不认可：在 `human_review` 填你的判断（0/1），并在 `notes` 写一句原因

### ⚠️ 合规约束（2026-10-04 已定：只传脱敏后的结构化特征）
`text_excerpt` 列**只给你（标注者）看，绝不发给 LLM**。发给 LLM 的只有结构化字段
（量表分数、风险等级、置信度、模态可用性等聚合量）。
若将来实验证明「只有结构化字段」达不到 kappa 门槛，结论是**不做**，而不是放宽到传原文。

### 为什么要标两列
- `human_review`：你对金标准的校验（留空=认可量表标签）
- `llm_judgement`：稍后由 LLM 复核填入（留空）
两列都填完后才能算一致性 / Cohen's kappa。**校验前不要看 LLM 的答案**（避免锚定）。

### 边界与易错点
1. 量表是自评分数，文本是访谈转录 —— 两者天然有偏差，这个偏差正是要测的对象。
   所以"文本看起来不像"不等于金标准错了，请在 notes 里写清楚你的判断依据。
2. 否定/反讽（如「我当然开心啊（笑）」）按真实含义判。
3. 截断文本（超过 max_chars）按可见部分判。
4. 拿不准就在 `human_review` 留空并在 notes 写「不确定」——留空样本会在 kappa 计算时
   被排除，比错标更有价值。

### 完成后算什么
- 一致率 accuracy(LLM == 金标准) 与 Cohen's kappa（后者处理偶然一致，比准确率更严）
- 门槛 **kappa >= 0.6**；成本门槛 单次 <= ¥0.01、月度 <= ¥50
"""


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--n", type=int, default=DEFAULT_N, help=f"样本量（建议 >= 80, 默认 {DEFAULT_N}）")
    ap.add_argument("--out", type=str, default=str(REPO_ROOT / "docs" / "planning" / "llm_judge_eval_template.csv"))
    ap.add_argument("--max-chars", type=int, default=300, help="正文截断长度")
    args = ap.parse_args()

    df = pd.read_csv(CORPUS)
    df = df[df["phq9_binary"].notna()].copy()
    df["text"] = df["text"].fillna("").astype(str)
    df = df[df["text"].str.len() > 0]
    # 同一 source_idx 的样本属同一 group，只取每组一条，避免抽样集内自我泄露
    df = df.sort_values("source_idx", kind="stable").drop_duplicates(subset="source_idx", keep="first")

    # 分层: 正负例各半; 组内按文本长度排序后等距取样 -> 覆盖各长度层, 分布不偏
    parts = []
    per_label = max(1, args.n // 2)
    for _label, sub in df.groupby("phq9_binary"):
        sub = sub.sort_values("text", key=lambda s: s.str.len())
        take = min(per_label, len(sub))
        step = max(1, len(sub) // take)
        parts.append(sub.iloc[::step][:take])
    out_df = pd.concat(parts).sample(frac=1.0, random_state=SEED).reset_index(drop=True)
    out_df = out_df.head(args.n)

    template = pd.DataFrame({
        "sample_id": [f"J{i + 1:04d}" for i in range(len(out_df))],
        "group_id": out_df["source_idx"].astype("Int64").astype(str).replace("<NA>", ""),
        # ↓ 以下两列【只给标注者看】; 合规约束: 自由文本不发给 LLM
        "text_excerpt_NOT_FOR_LLM": out_df["text"].str.slice(0, args.max_chars),
        "text_len": out_df["text"].str.len(),
        # ↓ 以下为【结构化特征】, 是可发给 LLM 的全部字段
        "ref_phq9_score": out_df["phq9_score"],
        "gold_phq9_binary": out_df["phq9_binary"].astype(int),   # 金标准(量表实测)
        "ref_gad7_score": out_df["gad7_score"],
        "ref_gad7_binary": out_df["gad7_binary"].astype(int),
        "model_confidence": "",      # 待填: 现有模型置信度（筛灰区用）
        "llm_judgement": "",         # 待填: LLM 复核结论（0/1）
        "llm_reason": "",            # 待填: LLM 理由
        "human_review": "",          # 待填: 校验金标准（留空=认可量表标签）
        "notes": "",                 # 待填: 与金标准不符的原因 / 「不确定」
    })

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    template.to_csv(args.out, index=False, encoding="utf-8-sig")

    print(f"语料: {len(df):,} 组可用（已按 source_idx 去重）")
    print(f"标注模板: {args.out}")
    print(f"样本数: {len(template)} | 正例 {int(template['gold_phq9_binary'].sum())} / "
          f"负例 {int((1 - template['gold_phq9_binary']).sum())} (金标准=PHQ-9 量表分级)")
    print(f"正文截断: {args.max_chars} 字 | kappa 门槛: {KAPPA_GATE}")
    print("\n" + "=" * 62)
    print(GUIDE)


if __name__ == "__main__":
    main()
