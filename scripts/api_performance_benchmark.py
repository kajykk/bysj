from __future__ import annotations

import argparse
import asyncio
import json
import os
import statistics
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

import httpx

ROOT = Path(__file__).resolve().parents[1]


@dataclass
class LatencyStats:
    samples_ms: list[float] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)

    def add(self, value: float) -> None:
        self.samples_ms.append(value)

    def percentile(self, pct: float) -> float:
        if not self.samples_ms:
            return 0.0
        ordered = sorted(self.samples_ms)
        index = max(0, min(len(ordered) - 1, round((len(ordered) - 1) * pct)))
        return round(ordered[index], 2)

    def summary(self) -> dict[str, Any]:
        if not self.samples_ms:
            return {"count": 0, "avg_ms": 0.0, "p50_ms": 0.0, "p95_ms": 0.0, "p99_ms": 0.0, "min_ms": 0.0, "max_ms": 0.0, "errors": self.errors}
        return {
            "count": len(self.samples_ms),
            "avg_ms": round(statistics.mean(self.samples_ms), 2),
            "p50_ms": self.percentile(0.50),
            "p95_ms": self.percentile(0.95),
            "p99_ms": self.percentile(0.99),
            "min_ms": round(min(self.samples_ms), 2),
            "max_ms": round(max(self.samples_ms), 2),
            "errors": self.errors,
        }


async def run_concurrent(concurrency: int, iterations: int, factory: Callable[[], Any]) -> LatencyStats:
    stats = LatencyStats()
    sem = asyncio.Semaphore(concurrency)

    async def one() -> None:
        async with sem:
            started = time.perf_counter()
            try:
                await factory()
            except Exception as exc:
                stats.errors.append(str(exc))
            else:
                stats.add((time.perf_counter() - started) * 1000.0)

    await asyncio.gather(*(one() for _ in range(iterations)))
    return stats


async def request_with_retry(client: httpx.AsyncClient, method: str, path: str, json_payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    response = await client.request(method, path, json=json_payload, headers=headers)
    response.raise_for_status()
    return response.json()


async def benchmark_endpoint(base_url: str, token: str, path: str, payload: dict[str, Any], levels: list[int]) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    async with httpx.AsyncClient(base_url=base_url, timeout=120.0) as client:
        results: dict[str, Any] = {}
        for concurrency in levels:
            iterations = max(concurrency, 20)
            stats = await run_concurrent(
                concurrency,
                iterations,
                lambda: request_with_retry(client, "POST", path, payload, headers),
            )
            results[f"c{concurrency}"] = stats.summary()
        return results


async def benchmark_errors(base_url: str, token: str) -> dict[str, Any]:
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    invalid_cases = [
        ("/api/v1/model/predict/tabular", {}),
        ("/api/v1/model/predict/text", {"text": ""}),
        ("/api/v1/model/predict/fusion", {"features": {}, "text": "", "physiological": {}}),
    ]
    out: dict[str, Any] = {}
    async with httpx.AsyncClient(base_url=base_url, timeout=30.0) as client:
        for path, payload in invalid_cases:
            try:
                response = await client.post(path, json=payload, headers=headers)
                out[path] = {"status_code": response.status_code, "body": response.text[:500]}
            except Exception as exc:
                out[path] = {"error": str(exc)}
    return out


async def main_async() -> None:
    parser = argparse.ArgumentParser(description="API benchmark for model prediction endpoints")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--output-dir", default="reports/performance")
    parser.add_argument("--levels", default="1,2,4,8,16,32")
    args = parser.parse_args()

    token = os.environ.get("BENCHMARK_TOKEN", "").strip()
    levels = [int(x) for x in args.levels.split(",") if x.strip()]

    structured_payload = {"features": {"age": 22, "gender": 1, "study_year": 3, "cgpa": 3.5, "stress_level": 3, "sleep_duration": 7, "social_support": 4, "financial_pressure": 2, "family_history": 0, "academic_pressure": 3, "exercise_frequency": 2, "anxiety": 2, "panic_attack": 0, "treatment_seeking": 1}}
    text_payload = {"text": "最近感觉心情不好，对什么都提不起兴趣"}
    fusion_payload = {"features": structured_payload["features"], "text": text_payload["text"], "physiological": {"sleep_hours": 6.5, "sleep_quality": 2, "exercise_minutes": 15, "heart_rate": 90, "systolic_bp": 128, "diastolic_bp": 84, "steps": 3000}}

    result = {
        "environment": {
            "base_url": args.base_url,
            "levels": levels,
            "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        },
        "structured": await benchmark_endpoint(args.base_url, token, "/api/v1/model/predict/tabular", structured_payload, levels),
        "text": await benchmark_endpoint(args.base_url, token, "/api/v1/model/predict/text", text_payload, levels),
        "fusion": await benchmark_endpoint(args.base_url, token, "/api/v1/model/predict/fusion", fusion_payload, levels),
        "error_cases": await benchmark_errors(args.base_url, token),
    }

    output_dir = ROOT / args.output_dir
    output_dir.mkdir(parents=True, exist_ok=True)
    json_path = output_dir / "api_performance_report.json"
    md_path = output_dir / "api_performance_report.md"
    json_path.write_text(json.dumps(result, ensure_ascii=False, indent=2), encoding="utf-8")

    lines: list[str] = ["# API 性能压测报告", "", f"- 生成时间: {result['environment']['timestamp']}", f"- Base URL: {args.base_url}", ""]
    for name in ["structured", "text", "fusion"]:
        lines.append(f"## {name}")
        lines.append("")
        lines.append("```json")
        lines.append(json.dumps(result[name], ensure_ascii=False, indent=2))
        lines.append("```")
        lines.append("")
    lines.append("## 错误处理验证")
    lines.append("")
    lines.append("```json")
    lines.append(json.dumps(result["error_cases"], ensure_ascii=False, indent=2))
    lines.append("```")
    md_path.write_text("\n".join(lines), encoding="utf-8")
    print(json.dumps({"json": str(json_path), "markdown": str(md_path)}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    asyncio.run(main_async())