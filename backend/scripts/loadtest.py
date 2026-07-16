#!/usr/bin/env python3
"""ISS-05 压测基线采集脚本 (零外部依赖, 仅标准库).

对运行态后端做并发压测, 输出真实 QPS / 延迟分位数 (p50/p90/p95/p99) /
错误率 / 状态码分布, 将"静态基线"升级为"实测基线"。

设计要点:
- 纯标准库 (urllib + threading), 无需 pip 安装 k6 / locust, 跨平台可跑。
- 闭环负载: 每个 worker 线程持续发请求直到 duration 到期 (开环可另配)。
- 记录每次请求墙钟延迟与状态码; 汇总时算分位数与吞吐。
- 支持 GET (默认) 与带 JSON body 的 POST (--method POST --json '{...}')。
- 支持 Bearer Token (--token) 以压测鉴权端点。

前置条件 (本机当前缺 redis, docker daemon 未运行, 故无法就地实跑):
  1. 起 redis:   docker run -d --name redis -p 6379:6379 redis:7-alpine
                 (或本机 redis-server)
  2. 起后端:     cd backend && python -m uvicorn app.main:app --host 127.0.0.1 --port 8000
                 (读取 backend/.env 的 DATABASE_URL / REDIS_URL)
  3. 跑压测:     python scripts/loadtest.py --url http://127.0.0.1:8000/health \
                     --concurrency 50 --duration 30 --out iss05_baseline.json

示例 (只读健康检查, 50 并发压 30s):
  python scripts/loadtest.py --url http://127.0.0.1:8000/health -c 50 -d 30
"""
from __future__ import annotations

import argparse
import json
import statistics
import threading
import time
import urllib.error
import urllib.request
from collections import Counter


def _percentile(sorted_vals: list[float], pct: float) -> float:
    """线性插值分位数 (sorted_vals 需已升序, 单位 ms)。"""
    if not sorted_vals:
        return 0.0
    if len(sorted_vals) == 1:
        return sorted_vals[0]
    k = (len(sorted_vals) - 1) * (pct / 100.0)
    lo = int(k)
    hi = min(lo + 1, len(sorted_vals) - 1)
    frac = k - lo
    return sorted_vals[lo] + (sorted_vals[hi] - sorted_vals[lo]) * frac


def _worker(args, deadline, latencies, statuses, errors, lock):
    body = args.json.encode("utf-8") if args.json else None
    headers = {"Content-Type": "application/json"}
    if args.token:
        headers["Authorization"] = f"Bearer {args.token}"
    local_lat: list[float] = []
    local_status: list[int] = []
    local_err = 0
    while time.monotonic() < deadline:
        req = urllib.request.Request(
            args.url, data=body, headers=headers, method=args.method
        )
        t0 = time.monotonic()
        try:
            with urllib.request.urlopen(req, timeout=args.timeout) as resp:
                resp.read()
                code = resp.status
            local_status.append(code)
        except urllib.error.HTTPError as e:
            local_status.append(e.code)  # 4xx/5xx 仍是"有响应", 计入状态分布
        except Exception:
            local_err += 1
        finally:
            local_lat.append((time.monotonic() - t0) * 1000.0)
    with lock:
        latencies.extend(local_lat)
        statuses.extend(local_status)
        errors[0] += local_err


def main() -> None:
    p = argparse.ArgumentParser(description="ISS-05 零依赖压测基线采集")
    p.add_argument("--url", required=True, help="目标 URL")
    p.add_argument("-c", "--concurrency", type=int, default=50, help="并发线程数")
    p.add_argument("-d", "--duration", type=float, default=30.0, help="压测秒数")
    p.add_argument("--method", default="GET", help="HTTP 方法")
    p.add_argument("--json", default="", help="POST JSON body")
    p.add_argument("--token", default="", help="Bearer Token")
    p.add_argument("--timeout", type=float, default=10.0, help="单请求超时(s)")
    p.add_argument("--out", default="", help="结果 JSON 输出路径")
    args = p.parse_args()

    latencies: list[float] = []
    statuses: list[int] = []
    errors = [0]
    lock = threading.Lock()
    deadline = time.monotonic() + args.duration

    print(
        f"[loadtest] {args.method} {args.url} | concurrency={args.concurrency} "
        f"duration={args.duration}s"
    )
    wall0 = time.monotonic()
    threads = [
        threading.Thread(
            target=_worker,
            args=(args, deadline, latencies, statuses, errors, lock),
            daemon=True,
        )
        for _ in range(args.concurrency)
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    wall = time.monotonic() - wall0

    total = len(latencies)
    ok = sum(1 for s in statuses if 200 <= s < 400)
    http_err = sum(1 for s in statuses if s >= 400)
    conn_err = errors[0]
    completed = total  # latencies 记录了每次尝试(含 HTTPError), conn_err 未计延迟
    qps = completed / wall if wall > 0 else 0.0
    lat_sorted = sorted(latencies)
    result = {
        "url": args.url,
        "method": args.method,
        "concurrency": args.concurrency,
        "duration_s": round(wall, 2),
        "requests_total": completed + conn_err,
        "requests_ok_2xx3xx": ok,
        "requests_http_err_4xx5xx": http_err,
        "connection_errors": conn_err,
        "error_rate_pct": round(
            (http_err + conn_err) / (completed + conn_err) * 100.0, 3
        )
        if (completed + conn_err)
        else 0.0,
        "qps": round(qps, 1),
        "latency_ms": {
            "min": round(min(lat_sorted), 2) if lat_sorted else 0.0,
            "p50": round(_percentile(lat_sorted, 50), 2),
            "p90": round(_percentile(lat_sorted, 90), 2),
            "p95": round(_percentile(lat_sorted, 95), 2),
            "p99": round(_percentile(lat_sorted, 99), 2),
            "max": round(max(lat_sorted), 2) if lat_sorted else 0.0,
            "mean": round(statistics.fmean(lat_sorted), 2) if lat_sorted else 0.0,
        },
        "status_distribution": dict(Counter(statuses)),
    }

    print(json.dumps(result, indent=2, ensure_ascii=False))
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)
        print(f"[loadtest] written -> {args.out}")


if __name__ == "__main__":
    main()
