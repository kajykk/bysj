from __future__ import annotations

import argparse
import asyncio
import csv
import json
import math
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
BACKEND_ROOT = ROOT / "backend"
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.core.model_engine import model_engine


@dataclass
class MetricSummary:
    count: int = 0
    avg_ms: float = 0.0
    p50_ms: float = 0.0
    p95_ms: float = 0.0
    p99_ms: float = 0.0
    min_ms: float = 0.0
    max_ms: float = 0.0
    errors: list[str] = field(default_factory=list)


@dataclass
class ClassificationStats:
    total: int = 0
    correct: int = 0
    tp: int = 0
    tn: int = 0
    fp: int = 0
    fn: int = 0
    latencies_ms: list[float] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add(self, y_true: int, y_pred: int, latency_ms: float) -> None:
        self.total += 1
        self.correct += int(y_true == y_pred)
        self.tp += int(y_true == 1 and y_pred == 1)
        self.tn += int(y_true == 0 and y_pred == 0)
        self.fp += int(y_true == 0 and y_pred == 1)
        self.fn += int(y_true == 1 and y_pred == 0)
        self.latencies_ms.append(latency_ms)

    def precision(self) -> float:
        denom = self.tp + self.fp
        return self.tp / denom if denom else 0.0

    def recall(self) -> float:
        denom = self.tp + self.fn
        return self.tp / denom if denom else 0.0

    def f1(self) -> float:
        p = self.precision()
        r = self.recall()
        return (2 * p * r / (p + r)) if (p + r) else 0.0

    def accuracy(self) -> float:
        return self.correct / self.total if self.total else 0.0

    def latency_summary(self) -> MetricSummary:
        return summarize_ms(self.latencies_ms, self.errors)


def summarize_ms(samples: Iterable[float], errors: list[str] | None = None) -> MetricSummary:
    values = list(samples)
    if not values:
        return MetricSummary(errors=list(errors or []))
    ordered = sorted(values)
    return MetricSummary(
        count=len(values),
        avg_ms=round(statistics.mean(values), 2),
        p50_ms=round(percentile(ordered, 0.50), 2),
        p95_ms=round(percentile(ordered, 0.95), 2),
        p99_ms=round(percentile(ordered, 0.99), 2),
        min_ms=round(min(values), 2),
        max_ms=round(max(values), 2),
        errors=list(errors or []),
    )


def percentile(ordered: list[float], value: float) -> float:
    if not ordered:
        return 0.0
    idx = max(0, min(len(ordered) - 1, math.ceil((len(ordered) - 1) * value)))
    return ordered[idx]


def read_csv_rows(path: Path, limit: int | None = None) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8", newline="") as fh:
        reader = csv.DictReader(fh)
        rows: list[dict[str, str]] = []
        for idx, row in enumerate(reader):
            rows.append(row)
            if limit is not None and idx + 1 >= limit:
                break
    return rows


def load_json_samples(path: Path) -> list[dict[str, Any]]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if isinstance(raw, list):
        return [item for item in raw if isinstance(item, dict)]
    if isinstance(raw, dict):
        for key in ("samples", "data", "items"):
            value = raw.get(key)
            if isinstance(value, list):
                return [item for item in value if isinstance(item, dict)]
    raise ValueError(f"Unsupported JSON sample format: {path}")


def load_threshold_info(path_str: str | None) -> dict[str, Any] | None:
    if not path_str:
        return None
    path = ROOT / path_str
    if not path.exists():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    info = raw.get("best_threshold_info") if isinstance(raw, dict) else None
    return info if isinstance(info, dict) else None


def normalize_binary_label(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, (int, float)):
        return int(round(value))
    text = str(value).strip().lower()
    if text in {"1", "true", "yes", "y", "positive", "depressed", "high", "risk"}:
        return 1
    return 0


def safe_float(value: Any, default: float) -> float:
    try:
        if value is None:
            return default
        text = str(value).strip()
        if text in {"", "?", "nan", "none", "null"}:
            return default
        return float(text)
    except (TypeError, ValueError):
        return default


def structured_features_from_row(row: dict[str, str]) -> tuple[dict[str, Any], int]:
    features: dict[str, Any] = {
        "age": safe_float(row.get("Age"), 20),
        "gender": 1 if str(row.get("Gender", "Male")).strip().lower() == "male" else 0,
        "study_year": 3,
        "cgpa": safe_float(row.get("CGPA"), 0),
        "stress_level": safe_float(row.get("Academic Pressure"), 2),
        "sleep_duration": 7.0,
        "social_support": 3,
        "financial_pressure": safe_float(row.get("Financial Stress"), 2),
        "family_history": 1 if str(row.get("Family History of Mental Illness", "No")).strip().lower() == "yes" else 0,
        "academic_pressure": safe_float(row.get("Academic Pressure"), 2),
        "exercise_frequency": 2,
        "anxiety": 2,
        "panic_attack": 1 if str(row.get("Have you ever had suicidal thoughts ?", "No")).strip().lower() == "yes" else 0,
        "treatment_seeking": 0,
    }
    label = normalize_binary_label(row.get("Depression", 0))
    return features, label


def text_sample_from_row(row: dict[str, str]) -> tuple[str, int]:
    text = row.get("clean_text") or row.get("text") or row.get("content") or row.get("post") or row.get("sentence") or row.get("comment") or ""
    label = normalize_binary_label(row.get("is_depression", row.get("label", row.get("target", row.get("Depression", 0)))))
    return text, label


async def timed_call(coro_factory: Any) -> tuple[Any, float, str | None]:
    started = time.perf_counter()
    try:
        result = await coro_factory()
        return result, (time.perf_counter() - started) * 1000.0, None
    except asyncio.CancelledError as exc:
        return None, (time.perf_counter() - started) * 1000.0, f"cancelled: {exc}"
    except Exception as exc:
        return None, (time.perf_counter() - started) * 1000.0, str(exc)


async def eval_structured(dataset_path: Path, limit: int | None = None) -> dict[str, Any]:
    rows = read_csv_rows(dataset_path, limit=limit)
    stats = ClassificationStats()
    sample_results: list[dict[str, Any]] = []
    for row in rows:
        try:
            features, label = structured_features_from_row(row)
            result, latency_ms, error = await timed_call(lambda: model_engine.predict_structured(features))
            if error:
                stats.errors.append(error)
                continue
            pred = int(result["prediction"])
            stats.add(label, pred, latency_ms)
            if len(sample_results) < 5:
                sample_results.append({"y_true": label, "y_pred": pred, "latency_ms": round(latency_ms, 2), "risk_score": result.get("risk_score")})
        except Exception as exc:
            stats.errors.append(str(exc))
            continue
    latency = stats.latency_summary()
    return {
        "dataset": str(dataset_path),
        "samples": stats.total,
        "accuracy": round(stats.accuracy(), 4),
        "precision": round(stats.precision(), 4),
        "recall": round(stats.recall(), 4),
        "f1": round(stats.f1(), 4),
        "confusion_matrix": [[stats.tn, stats.fp], [stats.fn, stats.tp]],
        "latency_ms": latency.__dict__,
        "examples": sample_results,
        "errors": stats.errors[:20],
    }


async def eval_text(dataset_path: Path, limit: int | None = None) -> dict[str, Any]:
    rows = read_csv_rows(dataset_path, limit=limit)
    stats = ClassificationStats()
    sample_results: list[dict[str, Any]] = []
    for row in rows:
        try:
            text, label = text_sample_from_row(row)
            if not text.strip():
                continue
            result, latency_ms, error = await timed_call(lambda: model_engine.predict_text(text))
            if error:
                stats.errors.append(error)
                continue
            pred = int(result["prediction"])
            stats.add(label, pred, latency_ms)
            if len(sample_results) < 5:
                sample_results.append({"y_true": label, "y_pred": pred, "latency_ms": round(latency_ms, 2), "probability": result.get("probability")})
        except Exception as exc:
            stats.errors.append(str(exc))
            continue
    latency = stats.latency_summary()
    return {
        "dataset": str(dataset_path),
        "samples": stats.total,
        "accuracy": round(stats.accuracy(), 4),
        "precision": round(stats.precision(), 4),
        "recall": round(stats.recall(), 4),
        "f1": round(stats.f1(), 4),
        "confusion_matrix": [[stats.tn, stats.fp], [stats.fn, stats.tp]],
        "latency_ms": latency.__dict__,
        "examples": sample_results,
        "errors": stats.errors[:20],
    }


async def eval_physiological(path: Path, limit: int | None = None) -> dict[str, Any]:
    samples = load_json_samples(path)[:limit] if limit is not None else load_json_samples(path)
    stats = ClassificationStats()
    sample_results: list[dict[str, Any]] = []
    for sample in samples:
        try:
            label = normalize_binary_label(sample.get("label", sample.get("risk_label", sample.get("target", 0))))
            payload = sample.get("features", sample)
            result, latency_ms, error = await timed_call(lambda: model_engine._predict_physiological(payload))
            if error:
                stats.errors.append(error)
                continue
            pred = 1 if float(result) >= 50 else 0
            stats.add(label, pred, latency_ms)
            if len(sample_results) < 5:
                sample_results.append({"y_true": label, "y_pred": pred, "latency_ms": round(latency_ms, 2), "score": result})
        except Exception as exc:
            stats.errors.append(str(exc))
            continue
    latency = stats.latency_summary()
    return {
        "dataset": str(path),
        "samples": stats.total,
        "accuracy": round(stats.accuracy(), 4),
        "precision": round(stats.precision(), 4),
        "recall": round(stats.recall(), 4),
        "f1": round(stats.f1(), 4),
        "confusion_matrix": [[stats.tn, stats.fp], [stats.fn, stats.tp]],
        "latency_ms": latency.__dict__,
        "examples": sample_results,
        "errors": stats.errors[:20],
    }


async def eval_fusion(path: Path, limit: int | None = None) -> dict[str, Any]:
    samples = load_json_samples(path)[:limit] if limit is not None else load_json_samples(path)
    results: list[dict[str, Any]] = []
    latencies: list[float] = []
    errors: list[str] = []
    preds: list[int] = []
    labels: list[int] = []
    for sample in samples:
        started = time.perf_counter()
        try:
            payload = sample.get("payload", sample)
            result = await model_engine.predict_fusion(
                features=payload.get("features"),
                text=payload.get("text"),
                physiological=payload.get("physiological"),
            )
            elapsed = (time.perf_counter() - started) * 1000.0
            latencies.append(elapsed)
            pred = 1 if float(result.get("risk_score", 0)) >= 50 else 0
            label = normalize_binary_label(sample.get("label", 0))
            preds.append(pred)
            labels.append(label)
            results.append({
                "scenario": sample.get("scenario", sample.get("name", f"case_{len(results)+1}")),
                "label": label,
                "prediction": pred,
                "risk_score": result.get("risk_score"),
                "risk_level": result.get("risk_level"),
                "severity": result.get("severity"),
                "latency_ms": round(elapsed, 2),
            })
        except Exception as exc:
            errors.append(str(exc))
    if results:
        tp = sum(int(y == 1 and p == 1) for y, p in zip(labels, preds))
        tn = sum(int(y == 0 and p == 0) for y, p in zip(labels, preds))
        fp = sum(int(y == 0 and p == 1) for y, p in zip(labels, preds))
        fn = sum(int(y == 1 and p == 0) for y, p in zip(labels, preds))
        precision = tp / (tp + fp) if (tp + fp) else 0.0
        recall = tp / (tp + fn) if (tp + fn) else 0.0
        f1 = (2 * precision * recall / (precision + recall)) if (precision + recall) else 0.0
        accuracy = (tp + tn) / len(results)
    else:
        tp = tn = fp = fn = 0
        precision = recall = f1 = accuracy = 0.0
    latency = summarize_ms(latencies, errors)
    return {
        "dataset": str(path),
        "samples": len(results),
        "accuracy": round(accuracy, 4),
        "precision": round(precision, 4),
        "recall": round(recall, 4),
        "f1": round(f1, 4),
        "confusion_matrix": [[tn, fp], [fn, tp]],
        "latency_ms": latency.__dict__,
        "examples": results,
        "errors": errors[:20],
    }


async def evaluate_all(args: argparse.Namespace) -> dict[str, Any]:
    structured_path = ROOT / args.structured
    text_path = ROOT / args.text
    physio_path = ROOT / args.physiological
    fusion_path = ROOT / args.fusion

    model_engine.preload()

    structured_result = await eval_structured(structured_path, args.limit)
    threshold_info = load_threshold_info(args.threshold_metrics)
    if threshold_info:
        structured_result["best_threshold_info"] = threshold_info

    return {
        "environment": {
            "os": os.name,
            "python": sys.version,
            "mode": "offline",
        },
        "benchmarks": {
            "structured_f1_min": 0.85,
            "text_f1_min": 0.90,
            "fusion_latency_ms_max": 200.0,
            "memory_mb_max": 2048.0,
        },
        "results": {
            "structured": structured_result,
            "text": await eval_text(text_path, args.limit),
            "physiological": await eval_physiological(physio_path, args.limit),
            "fusion": await eval_fusion(fusion_path, args.limit),
        },
        "model_metrics_snapshot": model_engine.get_metrics_snapshot(),
    }


def status_for(metric: float, benchmark: float, higher_is_better: bool = True) -> str:
    if higher_is_better:
        return "pass" if metric >= benchmark else "fail"
    return "pass" if metric <= benchmark else "fail"


def build_report(result: dict[str, Any]) -> str:
    benchmarks = result["benchmarks"]
    structured = result["results"]["structured"]
    text = result["results"]["text"]
    physio = result["results"]["physiological"]
    fusion = result["results"]["fusion"]
    lines: list[str] = []
    lines.append("# 模型性能评估报告")
    lines.append("")
    lines.append(f"- 生成时间: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- 环境: {result['environment']['python'].split()[0]} / {result['environment']['os']} / offline")
    lines.append("")
    lines.append("## 预设基准")
    lines.append("")
    lines.append(f"- 结构化模型 F1 >= {benchmarks['structured_f1_min']:.2f}")
    lines.append(f"- 文本模型 F1 >= {benchmarks['text_f1_min']:.2f}")
    lines.append(f"- 融合延迟 <= {benchmarks['fusion_latency_ms_max']:.0f} ms")
    lines.append(f"- 内存 <= {benchmarks['memory_mb_max']:.0f} MB")
    lines.append("")

    def section(title: str, payload: dict[str, Any], f1_benchmark: float | None = None) -> None:
        lines.append(f"## {title}")
        lines.append("")
        if f1_benchmark is not None:
            f1 = float(payload.get("f1", 0.0))
            lines.append(f"- F1: {f1:.4f} ({status_for(f1, f1_benchmark)})")
        if "accuracy" in payload:
            lines.append(f"- Accuracy: {float(payload.get('accuracy', 0.0)):.4f}")
        if "precision" in payload:
            lines.append(f"- Precision: {float(payload.get('precision', 0.0)):.4f}")
        if "recall" in payload:
            lines.append(f"- Recall: {float(payload.get('recall', 0.0)):.4f}")
        latency = payload.get("latency_ms", {})
        if latency:
            lines.append(f"- Latency avg/p95/max: {latency.get('avg_ms', 0.0):.2f} / {latency.get('p95_ms', 0.0):.2f} / {latency.get('max_ms', 0.0):.2f} ms")
        if payload.get("errors"):
            lines.append(f"- Errors: {len(payload.get('errors', []))}")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(payload, ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")

    section("结构化模型", structured, benchmarks["structured_f1_min"])
    section("文本模型", text, benchmarks["text_f1_min"])
    section("生理数据模型", physio)
    section("多模态融合引擎", fusion)

    lines.append("## 总结与建议")
    lines.append("")
    lines.append("- 结构化与文本模型按 F1 基准自动判定是否达标。")
    lines.append("- 融合引擎重点关注端到端延迟是否低于 200ms。")
    lines.append("- 若并发压测结果在高并发下 p95 显著抬升，优先检查模型加载、序列化和线程池开销。")
    lines.append("- 若内存峰值接近或超过 2GB，建议减少热加载模型数量并优化预加载策略。")
    lines.append("")
    return "\n".join(lines)


async def main_async() -> None:
    parser = argparse.ArgumentParser(description="Offline model performance evaluation")
    parser.add_argument("--structured", default="datasets/structured/student_depression_dataset.csv")
    parser.add_argument("--text", default="datasets/text/depression_dataset_reddit_cleaned.csv")
    parser.add_argument("--physiological", default="datasets/physiological/samples.json")
    parser.add_argument("--fusion", default="datasets/fusion/test_scenarios.json")
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--output-dir", default="reports/performance")
    parser.add_argument("--threshold-metrics", default="models/artifacts/depression_tabular/metrics.json")
    args = parser.parse_args()

    output_dir = ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)

    result = await evaluate_all(args)
    json_path = output_dir / "model_performance_report.json"
    md_path = output_dir / "model_performance_report.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")
    md_path.write_text(build_report(result), encoding="utf-8")
    print(json.dumps({"json": str(json_path), "markdown": str(md_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main_async())