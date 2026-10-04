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
## 标注指引（贴在 CSV 旁边，随模板一起给标注者）

### 你要标的到底是什么
对每条 `text_excerpt`，判断**该段文本所描述的心理状态**是否达到「中度及以上抑郁」——
即与 `phq9_binary == 1` 的语义一致。**不要**参考 `model_confidence` 列，它本轮不参与判断。

### 为什么要标两份
- `human_label`：你的人工判断（金标准）
- `llm_judgement`：稍后由 LLM 复核填入（留空）
两列填完后才能算一致性与 Cohen's kappa。**标完之前不要看 LLM 的答案**（避免锚定）。

### 边界与易错点
1. `phq9_binary` 只是**参考**，不是答案。文本与量表可能不一致（这正是要测的）——
   若你觉得文本明显不符，允许与参考列不同，请在 `notes` 写一句原因。
2. 表达强度按**文本自身**判断，不按你的推测。文「我有点累」≠ 抑郁表述；
   「我什么都做不下去了」才是。
3. 否定/反讽：「我当然开心啊（笑）」这类按真实含义判，并在 notes 标注。
4. 截断的文本（超过 `max_chars`）按可见部分判。
5. 拿不准的**不要瞎猜**，把 `human_label` 留空并在 notes 写「不确定」——
   留空样本会在 kappa 计算时被排除，比错标更有价值。

### 完成后算什么
- 一致率 accuracy(LLM == human)
- Cohen's kappa（处理「偶然一致」，比准确率更严）
- 门槛 **kappa >= 0.6**（见 app/core/confidence.py 的 KAPPA_GATE 注释处的文档约定）
- 若通过，再算成本：单次调用成本 x 灰区日流量
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
        "text_excerpt": out_df["text"].str.slice(0, args.max_chars),
        "text_len": out_df["text"].str.len(),
        "ref_phq9_score": out_df["phq9_score"],
        "ref_phq9_binary": out_df["phq9_binary"].astype(int),
        "model_confidence": "",      # 待填: 现有模型对该样本的置信度（灰区筛选用）
        "llm_judgement": "",         # 待填: LLM 复核结论（0/1）
        "llm_reason": "",            # 待填: LLM 给出的理由（评估可解释性）
        "human_label": "",           # 待填: 人工金标准（0/1）
        "notes": "",                 # 待填: 不确定 / 与参考不符的原因
    })

    Path(args.out).parent.mkdir(parents=True, exist_ok=True)
    template.to_csv(args.out, index=False, encoding="utf-8-sig")

    print(f"语料: {len(df):,} 组可用（已按 source_idx 去重）")
    print(f"标注模板: {args.out}")
    print(f"样本数: {len(template)} | 正例 {int(template['ref_phq9_binary'].sum())} / "
          f"负例 {int((1 - template['ref_phq9_binary']).sum())}")
    print(f"正文截断: {args.max_chars} 字 | kappa 门槛: {KAPPA_GATE}")
    print("\n" + "=" * 62)
    print(GUIDE)


if __name__ == "__main__":
    main()
