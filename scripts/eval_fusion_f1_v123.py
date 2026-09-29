"""生产环境融合 F1 评估脚本 v2 (使用 v1.23 真实验证数据).

使用 data/processed/v1_23_external/validation.csv (4318 真实样本, 12/14 结构化特征)
通过生产 API 调用融合推理, 计算实际 F1, 验证 Phase 1 关卡条件"融合 F1 +10%".

数据集特点:
- 4318 真实样本 (4181 kaggle + 137 mendeley PHQ-9)
- 12 个结构化特征 (覆盖率 85.7% >= 80% 阈值, 激活结构化模型)
- depression_binary 标签 (0=健康, 1=抑郁)
- 标签与特征临床相关 (stress/anxiety 高 → 抑郁)

评估方式:
- 抽样 60 样本 (30 抑郁 + 30 健康)
- 调用 POST /api/v1/model/predict/fusion (structured + neutral text)
- 计算 F1/Precision/Recall/Accuracy
- 对比基线 ~0.85, 目标 ≥0.92

用法:
    python scripts/eval_fusion_f1_v123.py
    python scripts/eval_fusion_f1_v123.py --n-samples 100
    python scripts/eval_fusion_f1_v123.py --threshold 50
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import random
import sys
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VALIDATION_CSV = PROJECT_ROOT / "data" / "processed" / "v1_23_external" / "validation.csv"
TOKEN_FILE = PROJECT_ROOT / "scripts" / ".admin_token.txt"

# v1.23 数据集的 12 个结构化特征 (12/14 = 85.7% 覆盖率 >= 80% 阈值)
V123_FEATURES = [
    "age", "gender", "cgpa", "stress_level", "sleep_duration",
    "social_support", "financial_pressure", "family_history",
    "academic_pressure", "exercise_frequency", "anxiety", "panic_attack",
]

# 中性文本 (让结构化模型主导融合, 文本模型给中性分数)
NEUTRAL_TEXT = "今天状态一般，没有特别的感觉"

# 缺失的 2 个字段 (study_year, treatment_seeking) 使用默认值
MISSING_DEFAULTS = {
    "study_year": 2,
    "treatment_seeking": 0,
}


def load_validation_data(n_samples: int = 60) -> list[dict]:
    """加载 v1.23 验证集, 均衡抽样."""
    if not VALIDATION_CSV.exists():
        raise FileNotFoundError(f"验证集不存在: {VALIDATION_CSV}")
    rows: list[dict] = []
    with open(VALIDATION_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)

    # 按标签分组
    label_0 = [r for r in rows if r["depression_binary"] == "0"]
    label_1 = [r for r in rows if r["depression_binary"] == "1"]

    n_per_class = n_samples // 2
    random.seed(42)  # 可复现
    sampled = random.sample(label_0, min(n_per_class, len(label_0))) + \
              random.sample(label_1, min(n_per_class, len(label_1)))
    random.shuffle(sampled)
    return sampled


def get_token(api_url: str) -> str:
    """获取 admin JWT token."""
    if TOKEN_FILE.exists():
        token = TOKEN_FILE.read_text(encoding="utf-8").strip()
        if token:
            return token
    url = api_url.rstrip("/") + "/api/v1/auth/login"
    # AUDIT-2026-09-28: 口令不得硬编码入库，改从环境变量读取
    _pw = os.environ.get("E2E_ADMIN_PASSWORD")
    if not _pw:
        raise SystemExit("请设置环境变量 E2E_ADMIN_PASSWORD（禁止在源码中硬编码口令）")
    payload = {"username": "admin", "password": _pw}
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode("utf-8")
        obj = json.loads(body)
        token = obj.get("data", {}).get("access_token")
        if not token:
            raise RuntimeError(f"登录失败: {body}")
        TOKEN_FILE.write_text(token, encoding="utf-8")
        return token


def call_fusion_api(
    api_url: str, token: str, features: dict, text: str, max_retries: int = 3
) -> dict:
    """调用融合推理 API (含 429 重试)."""
    url = api_url.rstrip("/") + "/api/v1/model/predict/fusion"
    payload = {"features": features, "text": text, "physiological": None}
    data = json.dumps(payload).encode("utf-8")

    last_exc: Exception | None = None
    for attempt in range(max_retries):
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8")
                obj = json.loads(body)
                if obj.get("code") != 200:
                    raise RuntimeError(f"API 业务错误: code={obj.get('code')}, msg={obj.get('message')}")
                return obj["data"]
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_retries - 1:
                time.sleep(3.5)
                last_exc = e
                continue
            raise
        except Exception as e:
            last_exc = e
            if attempt < max_retries - 1:
                time.sleep(1.0)
                continue
            raise
    if last_exc:
        raise last_exc
    raise RuntimeError("未知错误")


def compute_metrics(y_true: list[int], y_pred: list[int]) -> dict:
    """计算二分类指标."""
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)
    tn = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 0)
    accuracy = (tp + tn) / len(y_true) if y_true else 0.0
    precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
    recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) > 0 else 0.0
    return {
        "n": len(y_true), "tp": tp, "fp": fp, "fn": fn, "tn": tn,
        "accuracy": round(accuracy, 4), "precision": round(precision, 4),
        "recall": round(recall, 4), "f1": round(f1, 4),
        "label_dist": dict(Counter(y_true)), "pred_dist": dict(Counter(y_pred)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="生产环境融合 F1 评估 (v1.23 真实数据)")
    parser.add_argument("--api-url", default="http://localhost:8001")
    parser.add_argument("--n-samples", type=int, default=60, help="抽样总数 (每类一半)")
    parser.add_argument("--threshold", type=float, default=50.0, help="risk_score 二分类阈值")
    parser.add_argument("--use-risk-level", action="store_true", help="使用 risk_level>=2")
    args = parser.parse_args()

    print("=" * 70)
    print("生产环境融合 F1 评估 (v1.23 真实数据)")
    print("=" * 70)
    print(f"API: {args.api_url}")
    print(f"验证集: {VALIDATION_CSV}")
    print(f"抽样: {args.n_samples} 样本 (每类 {args.n_samples // 2})")
    print(f"判定: {'risk_level>=2' if args.use_risk_level else f'risk_score>={args.threshold}'}")
    print(f"基线: ~0.85 | 目标: ≥0.92 (+10%)")
    print()

    rows = load_validation_data(args.n_samples)
    print(f"加载: {len(rows)} 样本")
    print(f"标签分布: {dict(Counter(int(r['depression_binary']) for r in rows))}")
    print()

    print("获取 admin token...")
    token = get_token(args.api_url)
    print(f"token: {token[:20]}...")
    print()

    print(f"开始融合推理 ({len(rows)} 样本, 中性文本='{NEUTRAL_TEXT}')...")
    y_true: list[int] = []
    y_pred: list[int] = []
    risk_scores: list[float] = []
    risk_levels: list[int] = []
    errors: list[str] = []
    latencies: list[float] = []

    for i, row in enumerate(rows, 1):
        # 构造 14 个结构化特征 (12 真实 + 2 默认)
        features: dict = dict(MISSING_DEFAULTS)
        for field in V123_FEATURES:
            val = row.get(field)
            if val is not None and val != "":
                try:
                    features[field] = float(val)
                except ValueError:
                    features[field] = val

        label = int(row["depression_binary"])
        y_true.append(label)

        try:
            t0 = time.perf_counter()
            result = call_fusion_api(args.api_url, token, features, NEUTRAL_TEXT)
            latency_ms = (time.perf_counter() - t0) * 1000
            latencies.append(latency_ms)

            risk_score = float(result.get("risk_score", 0))
            risk_level = int(result.get("risk_level", 0))
            risk_scores.append(risk_score)
            risk_levels.append(risk_level)

            if args.use_risk_level:
                pred = 1 if risk_level >= 2 else 0
            else:
                pred = 1 if risk_score >= args.threshold else 0
            y_pred.append(pred)

            model_used = result.get("model_used", [])
            if isinstance(model_used, list):
                model_str = "+".join(model_used) if model_used else "none"
            else:
                model_str = str(model_used)

            print(
                f"  [{i:2d}/{len(rows)}] label={label} pred={pred} "
                f"risk_score={risk_score:6.2f} risk_level={risk_level} "
                f"stress={features.get('stress_level', '?'):4.1f} "
                f"anxiety={features.get('anxiety', '?'):4.1f} "
                f"latency={latency_ms:6.1f}ms models={model_str}"
            )
        except Exception as e:
            errors.append(f"样本 {i}: {e}")
            y_pred.append(0)
            risk_scores.append(0.0)
            risk_levels.append(0)
            latencies.append(0.0)
            print(f"  [{i:2d}/{len(rows)}] ERROR: {e}")

        if i < len(rows):
            time.sleep(3.5)

    print()
    metrics = compute_metrics(y_true, y_pred)
    print("=" * 70)
    print("融合 F1 评估结果 (v1.23 真实数据)")
    print("=" * 70)
    print(f"样本数: {metrics['n']}")
    print(f"混淆矩阵: TP={metrics['tp']} FP={metrics['fp']} FN={metrics['fn']} TN={metrics['tn']}")
    print(f"标签分布: {metrics['label_dist']}")
    print(f"预测分布: {metrics['pred_dist']}")
    print()
    print(f"Accuracy:  {metrics['accuracy']:.4f}")
    print(f"Precision: {metrics['precision']:.4f}")
    print(f"Recall:    {metrics['recall']:.4f}")
    print(f"F1:        {metrics['f1']:.4f}")
    print()
    print(f"基线: ~0.85 | 目标: ≥0.92 (+10%)")
    improvement = (metrics['f1'] - 0.85) / 0.85 * 100
    print(f"实际提升: {improvement:+.2f}%")
    if metrics['f1'] >= 0.92:
        print("✅ Phase 1 关卡条件 '融合 F1 +10%' 已达标")
    elif metrics['f1'] >= 0.85:
        print("⚠️ F1 高于基线但未达 +10% 目标")
    else:
        print("❌ F1 低于基线, 需调查")
    print()

    if latencies:
        valid_lat = sorted([l for l in latencies if l > 0])
        if valid_lat:
            p50 = valid_lat[len(valid_lat) // 2]
            p99 = valid_lat[int(len(valid_lat) * 0.99)] if len(valid_lat) > 1 else valid_lat[0]
            avg = sum(valid_lat) / len(valid_lat)
            print(f"延迟: avg={avg:.1f}ms  P50={p50:.1f}ms  P99={p99:.1f}ms")
            print()

    if risk_scores:
        dep_scores = [s for s, l in zip(risk_scores, y_true) if l == 1]
        heal_scores = [s for s, l in zip(risk_scores, y_true) if l == 0]
        if dep_scores:
            print(f"抑郁组 (n={len(dep_scores)}): avg={sum(dep_scores)/len(dep_scores):.2f} "
                  f"min={min(dep_scores):.2f} max={max(dep_scores):.2f}")
        if heal_scores:
            print(f"健康组 (n={len(heal_scores)}): avg={sum(heal_scores)/len(heal_scores):.2f} "
                  f"min={min(heal_scores):.2f} max={max(heal_scores):.2f}")
        print()

    if errors:
        print(f"错误 ({len(errors)}):")
        for e in errors:
            print(f"  - {e}")
        print()

    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "api_url": args.api_url,
        "test_set": str(VALIDATION_CSV),
        "n_samples": metrics["n"],
        "threshold_mode": "risk_level>=2" if args.use_risk_level else f"risk_score>={args.threshold}",
        "baseline_f1": 0.85,
        "target_f1": 0.92,
        "metrics": metrics,
        "latency_ms": {
            "avg": round(sum(latencies) / len(latencies), 1) if latencies else 0,
            "p50": round(sorted(latencies)[len(latencies) // 2], 1) if latencies else 0,
            "p99": round(sorted(latencies)[int(len(latencies) * 0.99) - 1], 1) if len(latencies) > 1 else 0,
        },
        "errors": errors,
    }
    summary_path = PROJECT_ROOT / "scripts" / ".production_f1_v123_result.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"摘要已写入: {summary_path}")
    return 0 if metrics["f1"] >= 0.92 else 1


if __name__ == "__main__":
    sys.exit(main())
