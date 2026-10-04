"""P2-2: 用 DeepSeek 做「低置信灰区第二意见」的离线评估。

合规硬约束（2026-10-04 已定: 只传脱敏后的结构化特征）
--------------------------------------------------------
**自由文本一律不出境**，且**金标准字段也不得出境**。原因:
  金标准是 PHQ-9 量表分级(phq9_binary)。若把 phq9_score/level 发给 LLM, 它基本能
  复算出分级 -> kappa 会虚高, 但那是「LLM 复算量表」, 没有临床增量价值, 等于拿答案考自己。
  因此发给 LLM 的字段必须**排除 phq9_***, 只保留:
    - 模型侧判断(预测概率/置信度/风险等级) —— 这才是要被复核的对象
    - GAD-7 焦虑量表(gad7_*) —— 不同构念, 允许
    - 其他结构化量(audio_count 等)
  本脚本用 `assert_no_leakage()` 在发送前做防御性断言, 违规直接抛错。

用法:
    cd backend
    $env:DEEPSEEK_API_KEY="<你的 key>"        # 只走环境变量, 绝不写进代码或仓库
    .venv/Scripts/python.exe ../scripts/llm_judge_evaluate.py --limit 100
    .venv/Scripts/python.exe ../scripts/llm_judge_evaluate.py --dry-run   # 只看 payload

依赖: requests(已在 requirements.txt); 不引入新 SDK。
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import sys
import time
from pathlib import Path

import numpy as np
import pandas as pd

REPO_ROOT = Path(__file__).resolve().parents[1]
BACKEND = REPO_ROOT / "backend"
sys.path.insert(0, str(BACKEND))

CORPUS = REPO_ROOT / "data" / "external" / "chinese_depression_corpus_v1.csv"
TEMPLATE = REPO_ROOT / "docs" / "planning" / "llm_judge_eval_template.csv"
OUT_CSV = REPO_ROOT / "docs" / "planning" / "llm_judge_results.csv"
OUT_JSON = REPO_ROOT / "docs" / "planning" / "llm_judge_eval_report.json"

API_BASE = "https://api.deepseek.com"
# 2026-10-05 按官方定价页更新: 现役为 V4 系列; legacy 名 deepseek-chat 也会由
# V4.1-Flash 服务并按 Flash 价计费。默认用 flash（便宜 4 倍，本任务不需要 Pro 的推理深度）。
DEFAULT_MODEL = "deepseek-flash"
KAPPA_GATE = 0.6
COST_GATE_PER_CALL = 0.01       # 元
COST_GATE_MONTHLY = 50.0        # 元

#: DeepSeek 官方定价（美元 / 1M tokens，缓存未命中；命中价见文档，本任务基本不会命中）
#: 来源: https://api-docs.deepseek.com/quick_start/pricing （价格会调整，用前请复核）
PRICE_USD_PER_1M = {
    "flash": {"input": 0.15, "output": 0.6},
    "pro": {"input": 0.66, "output": 1.98},
}
#: Off-peak = 半价。Peak: UTC 01:00-04:00 与 06:00-10:00（周一至周五，中国节假日除外）
PEAK_UTC_HOURS = {1, 2, 3, 6, 7, 8, 9}
DEFAULT_USD_CNY = 7.2           # 汇率假设，可用 --usd-cny 覆盖

#: 绝不发给 LLM 的列（金标准 + 自由文本）
FORBIDDEN_PREFIXES = ("phq9_", "text", "audio_transcript")
FORBIDDEN_KEYS = {"gold_phq9_binary", "sample_id", "notes", "human_review"}


def build_model_predictions(df_sample: pd.DataFrame) -> pd.DataFrame:
    """用现役生产文本模型(bilingual_v2)对样本跑预测, 得到要被复核的「模型侧判断」。

    这是 P2-2 的对象: 模型低置信的预测。灰区由 confidence.py 的 LLM_REVIEW_ZONE 定义。
    """
    import joblib

    from app.core.confidence import in_llm_review_zone

    tfidf = joblib.load(BACKEND / "models" / "text" / "improved_bilingual_tfidf.pkl")
    clf = joblib.load(BACKEND / "models" / "text" / "improved_bilingual_model.pkl")
    texts = df_sample["text"].fillna("").astype(str).tolist()
    X = tfidf.transform(texts)
    prob = clf.predict_proba(X)[:, 1]
    out = df_sample.copy()
    out["model_prob"] = np.round(prob, 4)
    out["model_pred"] = (prob >= 0.3).astype(int)          # 生产固定阈值 0.3
    # 置信度: 距决策边界越远越自信(0.5~1.0), 用于筛灰区
    out["model_confidence"] = np.round(1.0 - np.abs(prob - 0.5) * 2, 4)
    out["in_review_zone"] = out["model_confidence"].map(in_llm_review_zone)
    return out


def make_payload(row: pd.Series) -> dict:
    """构造发给 LLM 的结构化字段（不含金标准、不含文本）。"""
    return {
        "model_predicted_risk": int(row["model_pred"]),
        "model_probability": float(row["model_prob"]),
        "model_confidence": float(row["model_confidence"]),
        "gad7_score": int(row["ref_gad7_score"]) if pd.notna(row.get("ref_gad7_score")) else None,
        "gad7_binary": int(row["ref_gad7_binary"]) if pd.notna(row.get("ref_gad7_binary")) else None,
        "audio_count": int(row["audio_count"]) if pd.notna(row.get("audio_count")) else 0,
    }


def assert_no_leakage(payload: dict) -> None:
    """防御性断言: 任何金标准字段/自由文本出现在 payload 里就抛错。"""
    for k in payload:
        low = k.lower()
        if low in {x.lower() for x in FORBIDDEN_KEYS} or any(
            low.startswith(p.lower()) for p in FORBIDDEN_PREFIXES
        ):
            raise AssertionError(f"合规违规: payload 含禁止字段 '{k}'")
    blob = json.dumps(payload, ensure_ascii=False)
    # 自由文本不会是纯数字/短串; 这里再兜底查一次超长字符串
    for v in payload.values():
        if isinstance(v, str) and len(v) > 50:
            raise AssertionError(f"合规违规: payload 字段 '{k}' 疑似含长文本")


PROMPT_TMPL = """你是精神科辅助评估的复核者。以下是某心理评估系统的**结构化摘要**（无原文文本）。

{fields}

请判断该个案是否达到「中度及以上抑郁」。只输出 JSON: {{"judgement": 0 或 1, "reason": "一句话理由"}}
不要输出其他内容。"""


def call_deepseek(payloads: list[dict], api_key: str, model: str,
                  dry_run: bool = False) -> list[dict]:
    import requests

    results = []
    for p in payloads:
        assert_no_leakage(p)
        fields = "\n".join(f"- {k}: {v}" for k, v in p.items())
        prompt = PROMPT_TMPL.format(fields=fields)
        if dry_run:
            results.append({"raw": "[dry-run]", "judgement": None, "reason": None,
                            "usage": {}, "prompt": prompt})
            continue
        r = requests.post(
            f"{API_BASE}/chat/completions",
            headers={"Authorization": f"Bearer {api_key}",
                     "Content-Type": "application/json"},
            json={"model": model, "messages": [{"role": "user", "content": prompt}],
                  "temperature": 0, "max_tokens": 200},
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        content = data["choices"][0]["message"]["content"]
        try:
            parsed = json.loads(content[content.find("{"): content.rfind("}") + 1])
        except Exception:
            parsed = {"judgement": None, "reason": content[:80]}
        results.append({
            "raw": content, "judgement": parsed.get("judgement"),
            "reason": parsed.get("reason"), "usage": data.get("usage", {}),
        })
        time.sleep(0.3)   # 温和限速
    return results


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=100, help="评估样本数")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--dry-run", action="store_true", help="只打印 payload, 不调用 API")
    ap.add_argument("--grey-zone-only", action="store_true",
                    help="只评估落在低置信灰区(0.3<=conf<0.6)的样本")
    ap.add_argument("--usd-cny", type=float, default=DEFAULT_USD_CNY,
                    help="美元兑人民币汇率假设（成本换算用，默认 7.2）")
    args = ap.parse_args()

    api_key = os.environ.get("DEEPSEEK_API_KEY", "")
    if not api_key and not args.dry_run:
        print("错误: 未设置环境变量 DEEPSEEK_API_KEY。")
        print("  PowerShell: $env:DEEPSEEK_API_KEY=\"<key>\"  (不要写进代码或仓库)")
        sys.exit(2)

    corpus = pd.read_csv(CORPUS)
    corpus["text"] = corpus["text"].fillna("").astype(str)
    tpl = pd.read_csv(TEMPLATE)
    # 用 group_id 回取完整文本(仅本地用于生成模型预测, 不发送)
    merged = tpl.merge(
        corpus[["source_idx", "text"]].rename(columns={"source_idx": "group_id"}),
        on="group_id", how="left",
    )
    merged = merged[merged["text"].notna()].head(args.limit)
    print(f"样本: {len(merged)} 条")

    scored = build_model_predictions(merged)
    if args.grey_zone_only:
        scored = scored[scored["in_review_zone"]]
        print(f"灰区子集(conf 0.3~0.6): {len(scored)} 条")

    payloads = [make_payload(r) for _, r in scored.iterrows()]
    if args.dry_run:
        print("\n=== 示例 payload（将发给 DeepSeek，注意不含 phq9_* 与文本） ===")
        print(json.dumps(payloads[0], ensure_ascii=False, indent=2))
        out = call_deepseek(payloads[:1], "", args.model, dry_run=True)
        print("\n=== 示例 prompt ===")
        print(out[0]["prompt"])
        return

    t0 = time.time()
    results = call_deepseek(payloads, api_key, args.model)
    elapsed = time.time() - t0

    scored = scored.copy()
    scored["llm_judgement"] = [r["judgement"] for r in results]
    scored["llm_reason"] = [r.get("reason") for r in results]

    # ---- 评估: 一致率 与 Cohen's kappa ----
    from sklearn.metrics import cohen_kappa_score

    valid = scored[scored["llm_judgement"].isin([0, 1])]
    if len(valid) == 0:
        print("没有有效判断，无法评估。")
        sys.exit(1)
    gold = valid["gold_phq9_binary"].astype(int).tolist()
    pred = valid["llm_judgement"].astype(int).tolist()
    acc = sum(int(a == b) for a, b in zip(gold, pred)) / len(gold)
    kappa = float(cohen_kappa_score(gold, pred))

    # ---- 成本（按 DeepSeek 官方定价 + peak/off-peak） ----
    from datetime import datetime, timezone

    tin = sum(r["usage"].get("prompt_tokens", 0) for r in results)
    tout = sum(r["usage"].get("completion_tokens", 0) for r in results)
    now = datetime.now(timezone.utc)
    is_peak = (now.hour in PEAK_UTC_HOURS) and now.weekday() < 5
    tier = "pro" if "pro" in args.model else "flash"
    mult = 1.0 if is_peak else 0.5          # off-peak 半价
    cost_usd = (tin * PRICE_USD_PER_1M[tier]["input"]
                + tout * PRICE_USD_PER_1M[tier]["output"]) / 1_000_000 * mult
    cost = cost_usd * args.usd_cny
    per_call = cost / max(len(results), 1)

    report = {
        "vendor": "deepseek", "model": args.model,
        "n_samples": int(len(results)), "n_valid": int(len(valid)),
        "gold": "phq9_binary (PHQ-9 量表分级)",
        "sent_fields": sorted(payloads[0].keys()),
        "excluded_fields": "phq9_* (金标准) 与 text/audio_transcript (自由文本, 合规)",
        "accuracy": round(acc, 4), "cohen_kappa": round(kappa, 4),
        "kappa_gate": KAPPA_GATE,
        "metrics": {
            "prompt_tokens": tin, "completion_tokens": tout,
            "total_cost_cny": round(cost, 6), "cost_per_call_cny": round(per_call, 6),
            "elapsed_seconds": round(elapsed, 1),
            "pricing": {
                "tier": tier, "is_peak_hour": is_peak, "multiplier": mult,
                "usd_per_1m": PRICE_USD_PER_1M[tier], "usd_cny_assumption": args.usd_cny,
                "source": "https://api-docs.deepseek.com/quick_start/pricing",
            },
        },
        "gates": {
            "kappa": "PASS" if kappa >= KAPPA_GATE else "FAIL",
            "cost_per_call": "PASS" if per_call <= COST_GATE_PER_CALL else "FAIL",
        },
    }
    report["verdict"] = (
        f"可做（kappa {kappa:.3f} >= {KAPPA_GATE} 且成本达标）"
        if kappa >= KAPPA_GATE and per_call <= COST_GATE_PER_CALL
        else f"不做（kappa {kappa:.3f} < {KAPPA_GATE} 或成本超门槛）—— 结论是放弃，不放宽传原文"
    )

    OUT_CSV.parent.mkdir(parents=True, exist_ok=True)
    scored.to_csv(OUT_CSV, index=False, encoding="utf-8-sig")
    OUT_JSON.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")

    print("\n" + "=" * 60)
    print(f"一致率 = {acc:.4f} | Cohen's kappa = {kappa:.4f} (门槛 {KAPPA_GATE})")
    print(f"tokens: in={tin} out={tout} | 总成本 ¥{cost:.4f} | 单次 ¥{per_call:.6f}")
    print(f"耗时 {elapsed:.1f}s")
    print(f"结论: {report['verdict']}")
    print(f"明细: {OUT_CSV}\n报告: {OUT_JSON}")


if __name__ == "__main__":
    main()
