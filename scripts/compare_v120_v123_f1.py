"""对比 v1.20 (生产 default) vs v1.23 (experimental) 在真实验证集上的 F1.

通过 tabular 端点同时获取两个模型的预测:
- v1.20: 主路径 risk_score (structured_logistic_regression_quick)
- v1.23: experimental_external_score 字段 (structured_v1.23_external_lr)

目标: 判断切换默认结构化模型到 v1.23 是否能提升 F1.
"""
from __future__ import annotations

import csv
import json
import os
import random
import time
import urllib.error
import urllib.request
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
VALIDATION_CSV = PROJECT_ROOT / "data" / "processed" / "v1_23_external" / "validation.csv"
TOKEN_FILE = PROJECT_ROOT / "scripts" / ".admin_token.txt"

V123_FEATURES = [
    "age", "gender", "cgpa", "stress_level", "sleep_duration",
    "social_support", "financial_pressure", "family_history",
    "academic_pressure", "exercise_frequency", "anxiety", "panic_attack",
]
MISSING_DEFAULTS = {"study_year": 2, "treatment_seeking": 0}


def load_validation_data(n_samples: int = 60) -> list[dict]:
    rows: list[dict] = []
    with open(VALIDATION_CSV, "r", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            rows.append(row)
    label_0 = [r for r in rows if r["depression_binary"] == "0"]
    label_1 = [r for r in rows if r["depression_binary"] == "1"]
    n_per = n_samples // 2
    random.seed(42)
    sampled = random.sample(label_0, min(n_per, len(label_0))) + \
              random.sample(label_1, min(n_per, len(label_1)))
    random.shuffle(sampled)
    return sampled


def get_token(api_url: str) -> str:
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
        obj = json.loads(resp.read().decode("utf-8"))
        token = obj.get("data", {}).get("access_token")
        if not token:
            raise RuntimeError("登录失败")
        TOKEN_FILE.write_text(token, encoding="utf-8")
        return token


def call_tabular(api_url: str, token: str, features: dict, max_retries: int = 3) -> dict:
    url = api_url.rstrip("/") + "/api/v1/model/predict/tabular"
    payload = {"features": features}
    data = json.dumps(payload).encode("utf-8")
    for attempt in range(max_retries):
        req = urllib.request.Request(
            url, data=data,
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {token}"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                obj = json.loads(resp.read().decode("utf-8"))
                if obj.get("code") != 200:
                    raise RuntimeError(f"API code={obj.get('code')}")
                return obj["data"]
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_retries - 1:
                time.sleep(3.5)
                continue
            raise
        except Exception as e:
            if attempt < max_retries - 1:
                time.sleep(1.0)
                continue
            raise
    raise RuntimeError("max retries exceeded")


def compute_metrics(y_true, y_pred) -> dict:
    tp = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 1)
    fp = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 1)
    fn = sum(1 for t, p in zip(y_true, y_pred) if t == 1 and p == 0)
    tn = sum(1 for t, p in zip(y_true, y_pred) if t == 0 and p == 0)
    acc = (tp + tn) / len(y_true) if y_true else 0
    prec = tp / (tp + fp) if (tp + fp) > 0 else 0
    rec = tp / (tp + fn) if (tp + fn) > 0 else 0
    f1 = 2 * prec * rec / (prec + rec) if (prec + rec) > 0 else 0
    return {"tp": tp, "fp": fp, "fn": fn, "tn": tn,
            "accuracy": round(acc, 4), "precision": round(prec, 4),
            "recall": round(rec, 4), "f1": round(f1, 4)}


def main():
    api_url = "http://localhost:8001"
    n_samples = 60

    print("=" * 70)
    print("v1.20 vs v1.23 F1 对比评估 (tabular 端点, 真实数据)")
    print("=" * 70)

    rows = load_validation_data(n_samples)
    print(f"加载: {len(rows)} 样本, 标签: {dict(Counter(int(r['depression_binary']) for r in rows))}")

    token = get_token(api_url)

    y_true = []
    v120_scores = []  # 主路径 risk_score (v1.20)
    v123_scores = []  # experimental_external_score (v1.23)

    print(f"\n开始推理 ({len(rows)} 样本)...")
    for i, row in enumerate(rows, 1):
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
            result = call_tabular(api_url, token, features)
            v120_score = float(result.get("risk_score", 0))
            v123_score_raw = result.get("experimental_external_score")
            v123_available = result.get("experimental_external_available", False)

            if v123_score_raw is not None and v123_available:
                v123_score = float(v123_score_raw)
            else:
                v123_score = -1  # 不可用

            v120_scores.append(v120_score)
            v123_scores.append(v123_score)

            print(f"  [{i:2d}/{len(rows)}] label={label} "
                  f"v1.20={v120_score:6.2f} v1.23={v123_score:6.2f} "
                  f"stress={features.get('stress_level', '?'):4.1f} "
                  f"anxiety={features.get('anxiety', '?'):4.1f}")
        except Exception as e:
            print(f"  [{i:2d}/{len(rows)}] ERROR: {e}")
            v120_scores.append(0)
            v123_scores.append(-1)

        if i < len(rows):
            time.sleep(3.5)

    # 评估多个阈值的 F1
    print("\n" + "=" * 70)
    print("F1 对比 (多个阈值)")
    print("=" * 70)
    print(f"{'阈值':<8} {'v1.20 F1':<12} {'v1.23 F1':<12} {'v1.20 Prec':<12} {'v1.23 Prec':<12} {'v1.20 Rec':<12} {'v1.23 Rec':<12}")
    for threshold in [30, 40, 50, 60, 70]:
        v120_pred = [1 if s >= threshold else 0 for s in v120_scores]
        v123_pred = [1 if (s >= 0 and s >= threshold) else 0 for s in v123_scores]
        m120 = compute_metrics(y_true, v120_pred)
        m123 = compute_metrics(y_true, v123_pred)
        print(f"{threshold:<8} {m120['f1']:<12} {m123['f1']:<12} "
              f"{m120['precision']:<12} {m123['precision']:<12} "
              f"{m120['recall']:<12} {m123['recall']:<12}")

    # v1.23 专属阈值 (v1.23 输出 0-1 概率, 乘以 100 得到 0-100 分数)
    print("\nv1.23 专属阈值 (probability * 100):")
    for threshold in [0.3, 0.4, 0.5, 0.6, 0.7]:
        v123_pred = [1 if (s >= 0 and s / 100 >= threshold) else 0 for s in v123_scores]
        m123 = compute_metrics(y_true, v123_pred)
        print(f"  prob>={threshold}: F1={m123['f1']} Prec={m123['precision']} Rec={m123['recall']} "
              f"TP={m123['tp']} FP={m123['fp']} FN={m123['fn']} TN={m123['tn']}")

    # 输出 v1.23 分数分布
    print("\nv1.23 分数分布:")
    dep_v123 = [s for s, l in zip(v123_scores, y_true) if l == 1 and s >= 0]
    heal_v123 = [s for s, l in zip(v123_scores, y_true) if l == 0 and s >= 0]
    if dep_v123:
        print(f"  抑郁组 (n={len(dep_v123)}): avg={sum(dep_v123)/len(dep_v123):.2f} "
              f"min={min(dep_v123):.2f} max={max(dep_v123):.2f}")
    if heal_v123:
        print(f"  健康组 (n={len(heal_v123)}): avg={sum(heal_v123)/len(heal_v123):.2f} "
              f"min={min(heal_v123):.2f} max={max(heal_v123):.2f}")
    v123_unavailable = sum(1 for s in v123_scores if s < 0)
    print(f"  v1.23 不可用: {v123_unavailable}/{len(v123_scores)}")

    summary = {
        "v120_scores": v120_scores,
        "v123_scores": v123_scores,
        "y_true": y_true,
    }
    summary_path = PROJECT_ROOT / "scripts" / ".v120_v123_comparison.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n摘要已写入: {summary_path}")


if __name__ == "__main__":
    main()
