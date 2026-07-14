"""WF-0 运行期性能基线探测（locust 缺失时的 httpx 替代方案）。

对关键端点做并发压测，输出 P50/P95/P99 延迟与 QPS。
用法: python load_tests/httpx_baseline.py
"""
from __future__ import annotations

import json
import statistics
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

import httpx

BASE = "http://127.0.0.1:8010"

# (name, path, 期望状态码) —— 覆盖轻量探针/就绪聚合/大 payload/鉴权中间件开销
TARGETS = [
    ("health_live", "/health/live", 200),
    ("health_ready", "/health/ready", 200),
    ("health_startup", "/health/startup", 200),
    ("openapi_json", "/openapi.json", 200),
    ("reviews_authwall", "/api/v1/reviews", 401),
]

REQUESTS_PER_TARGET = 300
CONCURRENCY = 20


def percentile(data: list[float], pct: float) -> float:
    if not data:
        return 0.0
    data = sorted(data)
    k = (len(data) - 1) * (pct / 100)
    f = int(k)
    c = min(f + 1, len(data) - 1)
    if f == c:
        return data[f]
    return data[f] + (data[c] - data[f]) * (k - f)


def bench(client: httpx.Client, name: str, path: str, expect: int) -> dict:
    latencies: list[float] = []
    errors = 0
    status_mismatch = 0

    def one_call() -> tuple[float, bool, bool]:
        t0 = time.perf_counter()
        try:
            r = client.get(path)
            dt = (time.perf_counter() - t0) * 1000  # ms
            return dt, r.status_code != expect, False
        except Exception:
            return (time.perf_counter() - t0) * 1000, False, True

    wall_start = time.perf_counter()
    with ThreadPoolExecutor(max_workers=CONCURRENCY) as ex:
        futures = [ex.submit(one_call) for _ in range(REQUESTS_PER_TARGET)]
        for fut in as_completed(futures):
            dt, mism, err = fut.result()
            if err:
                errors += 1
            else:
                latencies.append(dt)
                if mism:
                    status_mismatch += 1
    wall = time.perf_counter() - wall_start
    qps = REQUESTS_PER_TARGET / wall if wall > 0 else 0.0

    return {
        "endpoint": path,
        "requests": REQUESTS_PER_TARGET,
        "concurrency": CONCURRENCY,
        "errors": errors,
        "status_mismatch": status_mismatch,
        "p50_ms": round(percentile(latencies, 50), 2),
        "p95_ms": round(percentile(latencies, 95), 2),
        "p99_ms": round(percentile(latencies, 99), 2),
        "max_ms": round(max(latencies), 2) if latencies else 0.0,
        "mean_ms": round(statistics.mean(latencies), 2) if latencies else 0.0,
        "qps": round(qps, 1),
    }


def main() -> None:
    results: dict[str, dict] = {}
    with httpx.Client(base_url=BASE, timeout=30.0) as client:
        # 预热
        for _ in range(30):
            try:
                client.get("/health/live")
            except Exception:
                pass
        for name, path, expect in TARGETS:
            print(f"[bench] {name} {path} ...", flush=True)
            results[name] = bench(client, name, path, expect)
            r = results[name]
            print(
                f"    p50={r['p50_ms']}ms p95={r['p95_ms']}ms "
                f"p99={r['p99_ms']}ms qps={r['qps']} err={r['errors']}",
                flush=True,
            )

    out = {
        "measured_at": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "tool": "httpx ThreadPoolExecutor (locust unavailable)",
        "base_url": BASE,
        "env": "APP_ENV=test sqlite+aiosqlite (single uvicorn worker)",
        "note": "本地单 worker 测试环境数字，非生产容量；用于 WF-0 相对基线",
        "targets": results,
    }
    out_path = Path(__file__).parent / "httpx_baseline_result.json"
    out_path.write_text(json.dumps(out, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"\n[done] written -> {out_path}")


if __name__ == "__main__":
    main()
