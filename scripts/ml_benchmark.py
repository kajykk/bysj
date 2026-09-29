from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT / "backend") not in sys.path:
    sys.path.insert(0, str(ROOT / "backend"))


@dataclass
class RunStats:
    samples_ms: list[float] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add(self, elapsed_ms: float) -> None:
        self.samples_ms.append(elapsed_ms)

    def percentile(self, value: float) -> float:
        if not self.samples_ms:
            return 0.0
        ordered = sorted(self.samples_ms)
        index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * value)))
        return round(ordered[index], 2)

    def summary(self) -> dict[str, Any]:
        if not self.samples_ms:
            return {"count": 0, "avg_ms": 0.0, "p50_ms": 0.0, "p95_ms": 0.0, "min_ms": 0.0, "max_ms": 0.0, "errors": self.errors}
        return {
            "count": len(self.samples_ms),
            "avg_ms": round(statistics.mean(self.samples_ms), 2),
            "p50_ms": self.percentile(0.50),
            "p95_ms": self.percentile(0.95),
            "min_ms": round(min(self.samples_ms), 2),
            "max_ms": round(max(self.samples_ms), 2),
            "errors": self.errors,
        }


async def _run_many(concurrency: int, iterations: int, factory: Callable[[], Any]) -> RunStats:
    stats = RunStats()
    sem = asyncio.Semaphore(concurrency)

    async def _one() -> None:
        async with sem:
            started = time.perf_counter()
            try:
                await factory()
            except Exception as exc:
                stats.errors.append(str(exc))
            else:
                stats.add((time.perf_counter() - started) * 1000.0)

    await asyncio.gather(*(_one() for _ in range(iterations)))
    return stats


def _write_markdown_report(report: dict[str, Any], output_path: Path) -> None:
    lines: list[str] = []
    lines.append("# ML Benchmark Report")
    lines.append("")
    lines.append(f"- Generated: {time.strftime('%Y-%m-%d %H:%M:%S')}")
    lines.append(f"- Mode: {report.get('mode', 'unknown')}")
    lines.append("")

    def section(title: str, payload: Any) -> None:
        lines.append(f"## {title}")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(payload, ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")

    if report.get("service") is not None:
        section("Service Layer", report["service"])
    if report.get("api") is not None:
        section("API Layer", report["api"])
    if report.get("shap_slow_path") is not None:
        section("SHAP Slow Path", report["shap_slow_path"])

    output_path.with_suffix(".md").write_text("\n".join(lines), encoding="utf-8")


async def _bench_service_layer() -> dict[str, Any]:
    from app.core.model_engine import model_engine

    structured_features = {
        "age": 22,
        "gender": 1,
        "study_year": 3,
        "cgpa": 3.5,
        "stress_level": 3,
        "sleep_duration": 7,
        "social_support": 4,
        "financial_pressure": 2,
        "family_history": 0,
        "academic_pressure": 3,
        "exercise_frequency": 2,
        "anxiety": 2,
        "panic_attack": 0,
        "treatment_seeking": 1,
    }
    text = "最近感觉心情不好，对什么都提不起兴趣"
    physio = {"sleep_hours": 6.5, "sleep_quality": 2, "exercise_minutes": 15, "heart_rate": 90, "systolic_bp": 128, "diastolic_bp": 84, "steps": 3000}

    async def structured() -> Any:
        return await model_engine.predict_structured(structured_features)

    async def text_call() -> Any:
        return await model_engine.predict_text(text)

    async def fusion() -> Any:
        return await model_engine.predict_fusion(features=structured_features, text=text, physiological=physio)

    start = time.perf_counter()
    model_engine.preload()
    cold_start_ms = round((time.perf_counter() - start) * 1000.0, 2)

    return {
        "cold_start_ms": cold_start_ms,
        "structured": {
            "single": (await _run_many(1, 1, structured)).summary(),
            "concurrency_10": (await _run_many(10, 20, structured)).summary(),
            "concurrency_50": (await _run_many(50, 50, structured)).summary(),
            "concurrency_100": (await _run_many(100, 100, structured)).summary(),
        },
        "text": {
            "single": (await _run_many(1, 1, text_call)).summary(),
            "concurrency_10": (await _run_many(10, 20, text_call)).summary(),
            "concurrency_50": (await _run_many(50, 50, text_call)).summary(),
            "concurrency_100": (await _run_many(100, 100, text_call)).summary(),
        },
        "fusion": {
            "single": (await _run_many(1, 1, fusion)).summary(),
            "concurrency_10": (await _run_many(10, 20, fusion)).summary(),
            "concurrency_50": (await _run_many(50, 50, fusion)).summary(),
            "concurrency_100": (await _run_many(100, 100, fusion)).summary(),
        },
        "metrics_snapshot": model_engine.get_metrics_snapshot(),
    }


async def _bench_api_layer(base_url: str) -> dict[str, Any]:
    import httpx

    structured_payload = {"features": {"age": 22, "gender": 1, "study_year": 3, "cgpa": 3.5, "stress_level": 3, "sleep_duration": 7, "social_support": 4, "financial_pressure": 2, "family_history": 0, "academic_pressure": 3, "exercise_frequency": 2, "anxiety": 2, "panic_attack": 0, "treatment_seeking": 1}}
    text_payload = {"text": "最近感觉心情不好，对什么都提不起兴趣"}
    fusion_payload = {"features": structured_payload["features"], "text": text_payload["text"], "physiological": {"sleep_hours": 6.5, "sleep_quality": 2, "exercise_minutes": 15, "heart_rate": 90, "systolic_bp": 128, "diastolic_bp": 84, "steps": 3000}}

    token = os.environ.get("BENCHMARK_TOKEN", "").strip()
    if not token:
        raise RuntimeError("BENCHMARK_TOKEN is not set")

    async def call(path: str, payload: dict[str, Any]) -> Any:
        async with httpx.AsyncClient(base_url=base_url, timeout=60.0) as client:
            r = await client.post(path, json=payload, headers={"Authorization": f"Bearer {token}"})
            r.raise_for_status()
            return r.json()

    return {
        "structured": {
            "single": (await _run_many(1, 1, lambda: call("/api/v1/model/predict/tabular", structured_payload))).summary(),
            "concurrency_10": (await _run_many(10, 20, lambda: call("/api/v1/model/predict/tabular", structured_payload))).summary(),
            "concurrency_50": (await _run_many(50, 50, lambda: call("/api/v1/model/predict/tabular", structured_payload))).summary(),
            "concurrency_100": (await _run_many(100, 100, lambda: call("/api/v1/model/predict/tabular", structured_payload))).summary(),
        },
        "text": {
            "single": (await _run_many(1, 1, lambda: call("/api/v1/model/predict/text", text_payload))).summary(),
            "concurrency_10": (await _run_many(10, 20, lambda: call("/api/v1/model/predict/text", text_payload))).summary(),
            "concurrency_50": (await _run_many(50, 50, lambda: call("/api/v1/model/predict/text", text_payload))).summary(),
            "concurrency_100": (await _run_many(100, 100, lambda: call("/api/v1/model/predict/text", text_payload))).summary(),
        },
        "fusion": {
            "single": (await _run_many(1, 1, lambda: call("/api/v1/model/predict/fusion", fusion_payload))).summary(),
            "concurrency_10": (await _run_many(10, 20, lambda: call("/api/v1/model/predict/fusion", fusion_payload))).summary(),
            "concurrency_50": (await _run_many(50, 50, lambda: call("/api/v1/model/predict/fusion", fusion_payload))).summary(),
            "concurrency_100": (await _run_many(100, 100, lambda: call("/api/v1/model/predict/fusion", fusion_payload))).summary(),
        },
    }


async def _run_shap_slow_path() -> dict[str, Any]:
    from app.core.model_engine import model_engine

    features = {
        "age": 22,
        "gender": 1,
        "study_year": 3,
        "cgpa": 3.5,
        "stress_level": 3,
        "sleep_duration": 7,
        "social_support": 4,
        "financial_pressure": 2,
        "family_history": 0,
        "academic_pressure": 3,
        "exercise_frequency": 2,
        "anxiety": 2,
        "panic_attack": 0,
        "treatment_seeking": 1,
    }
    started = time.perf_counter()
    try:
        result = await model_engine.explain_prediction(features, "structured_logistic_regression_quick")
        return {"elapsed_ms": round((time.perf_counter() - started) * 1000.0, 2), "items": result}
    except Exception as exc:
        return {"elapsed_ms": round((time.perf_counter() - started) * 1000.0, 2), "error": str(exc)}


async def main_async() -> dict[str, Any]:
    parser = argparse.ArgumentParser(description="Benchmark model prediction performance")
    parser.add_argument("--mode", choices=["service", "api", "both"], default="both")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output", default=str(ROOT / "benchmark-results.json"))
    args = parser.parse_args()

    report: dict[str, Any] = {"mode": args.mode, "service": None, "api": None, "shap_slow_path": None}
    if args.mode in {"service", "both"}:
        report["service"] = await _bench_service_layer()
    if args.mode in {"api", "both"}:
        report["api"] = await _bench_api_layer(args.base_url)
    report["shap_slow_path"] = await _run_shap_slow_path()

    output_path = Path(args.output)
    output_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    _write_markdown_report(report, output_path)
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report


if __name__ == "__main__":
    asyncio.run(main_async())
