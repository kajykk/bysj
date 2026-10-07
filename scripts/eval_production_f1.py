"""生产环境融合 F1 评估脚本.

通过生产 API (http://localhost:8001) 对带标签测试集运行融合推理,
计算实际 F1/Precision/Recall/Accuracy, 验证 Phase 1 关卡条件"融合 F1 +10%".

测试集: models/experiments/depression_multimodal_v1_test.csv (37 样本)
基线: ~0.85 (V4 报告估算, 加权融合)
目标: ≥0.92 (Phase 1 关卡, +10%)

用法:
    python scripts/eval_production_f1.py
    python scripts/eval_production_f1.py --api-url http://localhost:8001
    python scripts/eval_production_f1.py --threshold 50  # risk_score 阈值
"""

from __future__ import annotations

import argparse
import csv
import json
import sys
import time
import urllib.request
import urllib.error
from collections import Counter
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
TEST_CSV = PROJECT_ROOT / "models" / "experiments" / "depression_multimodal_v1_test.csv"
TOKEN_FILE = PROJECT_ROOT / "scripts" / ".admin_token.txt"

# STRUCTURED_FEATURE_SET 中, 测试集提供的字段子集
# 测试集有: text, age, stress_level, sleep_duration, social_support, label
# 其中结构化字段: age, stress_level, sleep_duration, social_support (4/14)
STRUCTURED_FIELDS_FROM_TEST = ["age", "stress_level", "sleep_duration", "social_support"]

# 完整 STRUCTURED_FEATURE_SET (14 字段) - 补全缺失字段的中性默认值
# 用于激活结构化模型 (覆盖率 100% >= 80% 阈值)
# 测试集仅提供 4 个真实字段, 其余 10 个使用中性默认值
STRUCTURED_DEFAULTS = {
    "gender": 1,                # 1=男 (中性)
    "study_year": 2,            # 大二 (中性)
    "cgpa": 3.0,                # 平均 GPA
    "financial_pressure": 2,    # 中等经济压力
    "family_history": 0,        # 无家族史
    "academic_pressure": 2,     # 中等学业压力
    "exercise_frequency": 2,    # 中等运动频率
    "anxiety": 0,               # 无焦虑
    "panic_attack": 0,          # 无恐慌发作
    "treatment_seeking": 0,     # 未寻求治疗
}


def load_test_data() -> list[dict]:
    """加载带标签测试集."""
    if not TEST_CSV.exists():
        raise FileNotFoundError(f"测试集不存在: {TEST_CSV}")
    rows: list[dict] = []
    with open(TEST_CSV, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            rows.append(row)
    return rows


def get_token(api_url: str) -> str:
    """获取 admin JWT token —— 运行时登录, 不使用硬编码字面量。

    AUDIT-2026-10-07 (S-3): 原实现直接 return 一个预生成的 JWT 字面量, 且该值
    已进入 git 历史。三个加重问题:
      1. 凭据入库后即使删除也仍在历史中, 且曾出现「清除后被写回」;
      2. 函数签名收了 api_url 却完全不用, 调用方 main():186 传入后被静默丢弃,
         结构上暗示「本该动态获取」实为写死, 误导后续维护者;
      3. 同项目 trigger_canary_traffic.py 的 login() 已是正确范式, 此处未对齐。
    故改为真实登录; 口令从环境变量读取, 缺失即 fail-fast。
    """
    import os

    password = os.environ.get("ADMIN_PASSWORD", "").strip()
    if not password:
        raise RuntimeError(
            "ADMIN_PASSWORD 未设置。该脚本需要 admin 账号口令以登录取token, "
            "拒绝使用硬编码凭据。请设置环境变量后重试。"
        )
    body = json.dumps({"username": "admin", "password": password}).encode()
    req = urllib.request.Request(
        api_url.rstrip("/") + "/api/v1/auth/login",
        data=body,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        payload = json.loads(resp.read().decode())
    return payload["data"]["access_token"]


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
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {token}",
            },
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                body = resp.read().decode("utf-8")
                obj = json.loads(body)
                # API 成功返回 code=200 (HTTP 风格), 非 200 为业务错误
                if obj.get("code") != 200:
                    raise RuntimeError(f"API 业务错误: code={obj.get('code')}, msg={obj.get('message')}")
                return obj["data"]
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < max_retries - 1:
                # 限流: 等待 3.5s 后重试 (端点限流 20/minute)
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
    f1 = (
        2 * precision * recall / (precision + recall)
        if (precision + recall) > 0
        else 0.0
    )

    return {
        "n": len(y_true),
        "tp": tp,
        "fp": fp,
        "fn": fn,
        "tn": tn,
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "label_dist": dict(Counter(y_true)),
        "pred_dist": dict(Counter(y_pred)),
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="生产环境融合 F1 评估")
    parser.add_argument(
        "--api-url", default="http://localhost:8001", help="API base URL"
    )
    parser.add_argument(
        "--threshold",
        type=float,
        default=50.0,
        help="risk_score 二分类阈值 (默认 50, >=50 视为抑郁=1)",
    )
    parser.add_argument(
        "--use-risk-level",
        action="store_true",
        help="使用 risk_level>=2 作为抑郁判定 (替代 risk_score 阈值)",
    )
    args = parser.parse_args()

    print(f"=" * 70)
    print(f"生产环境融合 F1 评估")
    print(f"=" * 70)
    print(f"API: {args.api_url}")
    print(f"测试集: {TEST_CSV}")
    print(f"判定方式: {'risk_level>=2' if args.use_risk_level else f'risk_score>={args.threshold}'}")
    print(f"基线: ~0.85 (V4 报告估算)")
    print(f"目标: ≥0.92 (Phase 1 关卡, +10%)")
    print()

    # 加载测试数据
    rows = load_test_data()
    print(f"加载测试集: {len(rows)} 样本")
    print(f"标签分布: {dict(Counter(int(r['label']) for r in rows))}")
    print()

    # 获取 token
    print("获取 admin token...")
    token = get_token(args.api_url)
    print(f"token: {token[:20]}...")
    print()

    # 运行推理
    print(f"开始融合推理 ({len(rows)} 样本)...")
    y_true: list[int] = []
    y_pred: list[int] = []
    risk_scores: list[float] = []
    risk_levels: list[int] = []
    errors: list[str] = []
    latencies: list[float] = []
    # AUDIT-2026-10-07 (S-3): 与 risk_scores 同步 append 的 label 配对列表,
    # 避免失败样本剔除后 zip(risk_scores, y_true) 长度不一致导致分组错配。
    eval_labels: list[int] = []

    for i, row in enumerate(rows, 1):
        text = row.get("text", "").strip()
        if not text:
            errors.append(f"样本 {i}: 文本为空, 跳过")
            continue

        # 构造结构化特征: 4 个真实字段 (来自测试集) + 10 个中性默认值 = 14/14 覆盖率
        # 激活结构化模型 (覆盖率 100% >= 80% 阈值), 使融合引擎组合 structured+text
        features: dict = dict(STRUCTURED_DEFAULTS)  # 先填入 10 个默认值
        for field in STRUCTURED_FIELDS_FROM_TEST:
            val = row.get(field)
            if val is not None and val != "":
                try:
                    features[field] = float(val)
                except ValueError:
                    features[field] = val

        label = int(row["label"])
        y_true.append(label)

        try:
            t0 = time.perf_counter()
            result = call_fusion_api(args.api_url, token, features, text)
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
            # AUDIT-2026-10-07 (S-3): 与 risk_scores 同步记录 label, 供分组统计
            # 配对使用(见下方 risk_score 分布段)。
            eval_labels.append(label)

            model_used = result.get("model_used", [])
            if isinstance(model_used, list):
                model_str = "+".join(model_used) if model_used else "none"
            else:
                model_str = str(model_used)

            print(
                f"  [{i:2d}/{len(rows)}] label={label} pred={pred} "
                f"risk_score={risk_score:6.2f} risk_level={risk_level} "
                f"latency={latency_ms:6.1f}ms models={model_str}"
            )
        except Exception as e:
            errors.append(f"样本 {i} (text='{text[:20]}...'): {e}")
            # AUDIT-2026-10-07 (S-3): 原为 y_pred.append(0) +保留 y_true,
            # 等于把「调用失败(401/429/超时)」计为「预测健康」并送进混淆矩阵。
            # 失败不是预测结果, 必须成对剔除, 否则 F1 被系统性拉低且结论失真
            # ——而本脚本结论被当作 Phase 1 关卡证据引用。
            y_true.pop()  # 回滚 L240 已append 的 label, 与 y_pred 保持对齐
            print(f"  [{i:2d}/{len(rows)}] ERROR (已剔除该样本): {e}")

        # 限流规避: 端点 20/minute, 请求间隔 3.5s 确保不触发 429
        if i < len(rows):
            time.sleep(3.5)

    print()

    # 计算指标
    metrics = compute_metrics(y_true, y_pred)
    print(f"=" * 70)
    print(f"融合 F1 评估结果")
    print(f"=" * 70)
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
    print(f"基线: ~0.85")
    print(f"目标: ≥0.92 (+10%)")
    improvement = (metrics['f1'] - 0.85) / 0.85 * 100
    print(f"实际提升: {improvement:+.2f}%")
    if metrics['f1'] >= 0.92:
        print(f"✅ Phase 1 关卡条件 '融合 F1 +10%' 已达标")
    elif metrics['f1'] >= 0.85:
        print(f"⚠️ F1 高于基线但未达 +10% 目标, 需进一步分析")
    else:
        print(f"❌ F1 低于基线, 需调查")
    print()

    # 延迟统计
    if latencies:
        valid_lat = [l for l in latencies if l > 0]
        if valid_lat:
            valid_lat.sort()
            p50 = valid_lat[len(valid_lat) // 2]
            p99 = valid_lat[int(len(valid_lat) * 0.99)] if len(valid_lat) > 1 else valid_lat[0]
            avg = sum(valid_lat) / len(valid_lat)
            print(f"延迟统计 (n={len(valid_lat)}):")
            print(f"  avg={avg:.1f}ms  P50={p50:.1f}ms  P99={p99:.1f}ms")
            print()

    # risk_score 分布
    if risk_scores:
        print(f"risk_score 分布:")
        print(f"  min={min(risk_scores):.2f}  max={max(risk_scores):.2f}  "
              f"avg={sum(risk_scores)/len(risk_scores):.2f}")
        # 按 label 分组
        # AUDIT-2026-10-07 (S-3): 原用 zip(risk_scores, y_true)。失败样本已从
        # y_true 剔除, 但 risk_scores 只在成功时 append, 两者长度不一致,
        # zip 会静默错配(取较短者) —— 分组均值随之失真。
        # 改为维护显式配对列表, 保证 (score, label) 严格对应。
        paired = list(zip(risk_scores, eval_labels))
        depressed_scores = [s for s, l in paired if l == 1]
        healthy_scores = [s for s, l in paired if l == 0]
        if depressed_scores:
            print(f"  抑郁组 (label=1, n={len(depressed_scores)}): "
                  f"avg={sum(depressed_scores)/len(depressed_scores):.2f}")
        if healthy_scores:
            print(f"  健康组 (label=0, n={len(healthy_scores)}): "
                  f"avg={sum(healthy_scores)/len(healthy_scores):.2f}")
        print()

    if errors:
        print(f"错误 ({len(errors)}):")
        for e in errors:
            print(f"  - {e}")
        print()

    # 输出 JSON 摘要 (供 STATE.md 引用)
    summary = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "api_url": args.api_url,
        "test_set": str(TEST_CSV),
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
        # AUDIT-2026-10-07 (S-3): 显式记录剔除数, 让引用方(STATE.md)能看到
        # F1 是在多少有效样本上得出的 —— 样本被大量剔除时 F1 再高也不可信。
        "n_errors": len(errors),
        "n_excluded": len(errors),
        "valid": not errors,
    }
    summary_path = PROJECT_ROOT / "scripts" / ".production_f1_result.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"摘要已写入: {summary_path}")

    # AUDIT-2026-10-07 (S-3): 有失败样本时一律判为不达标。原实现只看 F1,
    # 会出现「大量请求失败 + 剩余样本 F1 达标 => exit 0 报告通过」,
    # 把失败包装成了达标证据。正确的 F1 比没有 F1 更危险。
    if errors:
        print(f"[不达标] 存在 {len(errors)} 个失败样本, F1 结论不可信 (已从混淆矩阵剔除)")
        return 1
    return 0 if metrics["f1"] >= 0.92 else 1


if __name__ == "__main__":
    sys.exit(main())
