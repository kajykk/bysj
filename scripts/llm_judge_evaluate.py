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
    """构造发给 LLM 的结构化字段（不含金标准、不含文本）。

    2026-10-05 修正: 初版把 `model_predicted_risk=1` 与 `model_confidence=0.48`
    并列给出, LLM 读到后判为「证据不足」而全判 0 —— 两个字段看起来自相矛盾
    (模型说有风险 vs 模型没把握)。故改为给出**可解释的原始量**并把判定阈值
    写进字段名, 让 LLM 自己做阈值判断, 而不是被一个现成结论带偏。
    """
    return {
        "model_risk_probability": float(row["model_prob"]),
        "model_decision_threshold": 0.3,
        "model_own_uncertainty_0_to_1": float(row["model_confidence"]),
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


PROMPT_TMPL = """你是精神科辅助评估的复核者。以下是某心理评估系统的**结构化摘要**（不含原文文本）。

{fields}

字段含义:
- model_risk_probability: 该系统判定「有中度及以上抑郁风险」的估计概率(0~1)
- model_decision_threshold: 该系统实际使用的判定阈值（概率 >= 阈值即判为高风险）
- model_own_uncertainty_0_to_1: 系统自评的不确定度(0=非常确定, 1=非常不确定)
- gad7_score / gad7_binary: 焦虑量表 GAD-7 的分数与是否达阈值（与抑郁是不同构念）

请综合这些信息判断该个案是否达到「中度及以上抑郁」。只输出 JSON: {{"judgement": 0 或 1, "reason": "一句话理由"}}
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
            json={"model": model,
                  "messages": [{"role": "user", "content": prompt}],
                  # DeepSeek V4 系列**默认开 thinking 模式**（effort=high），此时
                  # 最终答案在 content、思维链在 reasoning_content, 且若模型 thinking
                  # 未结束 content 会是空串 -> 解析不到 judgement。
                  # 本任务只要结构化判断，不需要思维链，故显式关闭（也更省 token）。
                  "thinking": {"type": "disabled"},
                  "temperature": 0, "max_tokens": 200},
            timeout=60,
        )
        r.raise_for_status()
        data = r.json()
        msg = data["choices"][0]["message"]
        # 双保险: 正常走 content, 空则回退 reasoning_content
        content = (msg.get("content") or msg.get("reasoning_content") or "").strip()
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


def load_api_key() -> str:
    """按优先级取 API key: 环境变量 > backend/.env（后者已 gitignored）。

    两种放法（都不会入库）:
      1) 临时, 仅当前终端:  $env:DEEPSEEK_API_KEY="sk-xxx"        (PowerShell)
      2) 持久, 项目本地:    写入 E:\\code\\bysj\\backend\\.env 一行
                            DEEPSEEK_API_KEY=sk-xxx
                            该文件已被 .gitignore 覆盖, 但**备份/分享仓库时要记得剔除**。
    绝对不要: 写进代码、写进提交、贴在聊天里。
    """
    key = os.environ.get("DEEPSEEK_API_KEY", "")
    if key:
        return key
    env_file = BACKEND / ".env"
    if env_file.exists():
        try:
            from dotenv import load_dotenv

            load_dotenv(env_file)   # 默认不覆盖已存在的环境变量
            key = os.environ.get("DEEPSEEK_API_KEY", "")
            if key:
                print(f"已从 {env_file.name} 读取 DEEPSEEK_API_KEY")
        except ImportError:
            print("提示: 未安装 python-dotenv, 只能用环境变量传 key")
    return key


def run_ablation(texts_df: pd.DataFrame, api_key: str, model: str, batch_pause: float = 0.3) -> dict:
    """三臂消融: 回答「LLM 是有独立判断, 还是只会复述模型?」

    只看单一 kappa 会误导: 若把模型的概率和阈值一起给 LLM, 它只需比两个数字,
    kappa 会很高 —— 但那衡量的是「LLM 是否忠实复述模型」, 不是「LLM 有临床增量」。

    A: 完整字段(含模型判断)      -> 预期很高, 接近复述
    B: 中性字段(**不含模型判断**) -> 关键臂: LLM 能否独立达到 kappa 门槛
    C: 模型自身判断(不经 LLM)     -> 基线: 现有模型 vs 金标准
    判读: B >= C 才说明 LLM 有独立增量价值; 若 B << C, 引入 LLM 只是多花一遍钱复述。
    """
    from sklearn.metrics import cohen_kappa_score

    def _score(gold: list[int], pred: list[int]) -> tuple[float, float]:
        if not gold:
            return 0.0, 0.0
        acc = sum(int(a == b) for a, b in zip(gold, pred)) / len(gold)
        return acc, float(cohen_kappa_score(gold, pred))

    gold_all = texts_df["gold_phq9_binary"].astype(int).tolist()

    # ---- C: 模型自身(阈值 0.3), 不经 LLM ----
    c_pred = texts_df["model_pred"].astype(int).tolist()
    c_acc, c_kappa = _score(gold_all, c_pred)

    # ---- A: 完整字段 ----
    a_res = call_deepseek([make_payload(r) for _, r in texts_df.iterrows()], api_key, model)
    a_valid = [(g, r["judgement"]) for g, r in zip(gold_all, a_res) if r["judgement"] in (0, 1)]
    a_acc, a_kappa = _score([x[0] for x in a_valid], [x[1] for x in a_valid])

    # ---- B: 中性字段(不含任何模型判断) ----
    def neutral_payload(row: pd.Series) -> dict:
        return {
            "gad7_score": int(row["ref_gad7_score"]) if pd.notna(row.get("ref_gad7_score")) else None,
            "gad7_binary": int(row["ref_gad7_binary"]) if pd.notna(row.get("ref_gad7_binary")) else None,
            "audio_count": int(row["audio_count"]) if pd.notna(row.get("audio_count")) else 0,
        }

    b_res = call_deepseek([neutral_payload(r) for _, r in texts_df.iterrows()], api_key, model)
    b_valid = [(g, r["judgement"]) for g, r in zip(gold_all, b_res) if r["judgement"] in (0, 1)]
    b_acc, b_kappa = _score([x[0] for x in b_valid], [x[1] for x in b_valid])

    tokens = {"A": _usage(a_res), "B": _usage(b_res)}
    out = {
        "A_full_fields": {"n": len(a_valid), "accuracy": round(a_acc, 4), "kappa": round(a_kappa, 4)},
        "B_neutral_no_model": {"n": len(b_valid), "accuracy": round(b_acc, 4), "kappa": round(b_kappa, 4)},
        "C_model_itself": {"n": len(gold_all), "accuracy": round(c_acc, 4), "kappa": round(c_kappa, 4)},
        "kappa_gate": KAPPA_GATE,
    }
    # 判读
    if b_kappa < KAPPA_GATE:
        verdict = (f"不做：抽掉模型判断后 LLM 的 kappa={b_kappa:.3f} < {KAPPA_GATE}，"
                   "说明它本来就没在独立判断，只是复述模型 —— 引入它只是多花一遍钱。")
    elif b_kappa >= c_kappa:
        verdict = (f"可做：中性字段下 kappa={b_kappa:.3f} ≥ 模型自身 {c_kappa:.3f}，"
                   "LLM 提供了独立增量。")
    else:
        verdict = (f"需谨慎：中性字段 kappa={b_kappa:.3f} 低于模型自身 {c_kappa:.3f}，"
                   "说明模型比 LLM 更准，LLM 只在模型低置信时才可能有用（应只在灰区调用）。")
    out["verdict"] = verdict
    out["usage_tokens"] = tokens
    return out


def _usage(results: list[dict]) -> dict:
    return {
        "prompt_tokens": sum(r["usage"].get("prompt_tokens", 0) for r in results),
        "completion_tokens": sum(r["usage"].get("completion_tokens", 0) for r in results),
    }


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--limit", type=int, default=100, help="评估样本数")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--dry-run", action="store_true", help="只打印 payload, 不调用 API")
    ap.add_argument("--grey-zone-only", action="store_true",
                    help="只评估落在低置信灰区(0.3<=conf<0.6)的样本")
    ap.add_argument("--usd-cny", type=float, default=DEFAULT_USD_CNY,
                    help="美元兑人民币汇率假设（成本换算用，默认 7.2）")
    ap.add_argument("--ablation", action="store_true",
                    help="跑三臂消融（A 含模型判断 / B 中性字段 / C 模型自身），"
                         "用于判断 LLM 是独立判断还是只会复述模型")
    args = ap.parse_args()

    api_key = load_api_key()
    if not api_key and not args.dry_run:
        print("错误: 未找到 DEEPSEEK_API_KEY。任选一种方式:")
        print('  1) 当前终端临时:  $env:DEEPSEEK_API_KEY="sk-xxx"')
        print('  2) 写入 backend/.env 一行:  DEEPSEEK_API_KEY=sk-xxx   (该文件已 gitignored)')
        print("  不要写进代码或提交。")
        sys.exit(2)

    corpus = pd.read_csv(CORPUS)
    corpus["text"] = corpus["text"].fillna("").astype(str)
    # ⚠️ 必须按 source_idx 去重: 同一 group 有「原文 + 若干增强变体」多行, 直接按
    # group_id merge 会把每个样本复制成多份（实测 --limit 5 全是 J0001）。
    # 2026-10-05 实测坑: 语料 8,379 行只有 1,244 个唯一 group。
    corpus = corpus.sort_values("source_idx", kind="stable").drop_duplicates(
        subset="source_idx", keep="first"
    )
    tpl = pd.read_csv(TEMPLATE)
    merged = tpl.merge(
        corpus[["source_idx", "text"]].rename(columns={"source_idx": "group_id"}),
        on="group_id", how="left",
    )
    merged = merged[merged["text"].notna()].drop_duplicates(subset="sample_id", keep="first")
    merged = merged.head(args.limit)
    print(f"样本: {len(merged)} 条（语料去重后 {len(corpus):,} 个 group）")

    scored = build_model_predictions(merged)
    if args.grey_zone_only:
        scored = scored[scored["in_review_zone"]]
        print(f"灰区子集(conf 0.3~0.6): {len(scored)} 条")

    if args.ablation:
        t0 = time.time()
        out = run_ablation(scored, api_key, args.model)
        out["elapsed_seconds"] = round(time.time() - t0, 1)
        usage = out.pop("usage_tokens", {})
        tin = sum(v["prompt_tokens"] for v in usage.values())
        tout = sum(v["completion_tokens"] for v in usage.values())
        out["cost"] = {
            "prompt_tokens": tin, "completion_tokens": tout,
            "total_cny": round((tin * 0.15 + tout * 0.6) / 1e6 * 0.5 * args.usd_cny, 6),
            "note": "A+B 两臂合计, 按 flash off-peak 价估算",
        }
        p = OUT_JSON.with_name("llm_judge_ablation.json")
        p.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
        print("\n" + "=" * 66)
        print(f"A 含模型判断 : kappa={out['A_full_fields']['kappa']:.4f} "
              f"(acc {out['A_full_fields']['accuracy']:.4f})")
        print(f"B 中性字段   : kappa={out['B_neutral_no_model']['kappa']:.4f} "
              f"(acc {out['B_neutral_no_model']['accuracy']:.4f})")
        print(f"C 模型自身   : kappa={out['C_model_itself']['kappa']:.4f} "
              f"(acc {out['C_model_itself']['accuracy']:.4f})")
        print(f"\n判读: {out['verdict']}")
        print(f"成本: {out['cost']}")
        print(f"报告: {p}")
        return

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
