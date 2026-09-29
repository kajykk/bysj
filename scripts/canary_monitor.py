"""Canary 5% phase continuous monitor - run periodically to collect metrics.

Usage:
    python scripts/canary_monitor.py [--once] [--interval 300]

Default: runs every 5 minutes, logs metrics to scripts/canary_monitor.log
--once: runs once and exits
--interval N: runs every N seconds
"""
import argparse
import json
import statistics
import sys
import time
from datetime import datetime, timezone
import urllib.request

BASE = "http://localhost:8001/api/v1"
TOKEN_FILE = r"e:\code\bysj\scripts\.admin_token.txt"
LOG_FILE = r"e:\code\bysj\scripts\canary_monitor.log"
CANARY_ID = 3
CANARY_START = datetime(2026, 7, 22, 4, 24, 35, tzinfo=timezone.utc)


def log(msg: str) -> None:
    """Log message with timestamp to both console and log file."""
    ts = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    line = f"[{ts}] {msg}"
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def get_token() -> str:
    with open(TOKEN_FILE, encoding="utf-8") as f:
        return f.read().strip()


def call_api(path, payload=None, method="GET"):
    token = get_token()
    headers = {"Authorization": f"Bearer {token}"}
    if payload is not None:
        headers["Content-Type"] = "application/json"
    data = json.dumps(payload).encode("utf-8") if payload is not None else None
    req = urllib.request.Request(f"{BASE}{path}", data=data, headers=headers, method=method)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return resp.status, resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8")
    except Exception as e:
        return -1, str(e)


def check_canary_status() -> dict:
    """Check canary deployment status."""
    status, body = call_api(f"/canary/deployments/{CANARY_ID}")
    if status != 200:
        return {"error": f"HTTP {status}"}
    try:
        return json.loads(body).get("data", {})
    except Exception:
        return {"error": "parse error"}


def check_drift_alerts() -> int:
    """Check recent drift alerts count."""
    status, body = call_api("/monitoring/drift-alerts?limit=100")
    if status != 200:
        return -1
    try:
        data = json.loads(body).get("data", {})
        return len(data.get("alerts", []))
    except Exception:
        return -1


def generate_light_traffic() -> dict:
    """Generate light traffic (6 requests) to collect latency metrics."""
    token = get_token()
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json",
    }

    payloads = [
        ("/model/predict/tabular", {"features": {"age": 20, "gender": 1, "study_year": 2, "cgpa": 3.5, "stress_level": 3, "sleep_duration": 6.0, "social_support": 2, "financial_pressure": 3, "family_history": 0, "academic_pressure": 3, "exercise_frequency": 2, "anxiety": 1, "panic_attack": 0, "treatment_seeking": 0}}),
        ("/model/predict/text", {"text": "最近总是睡不好，感觉很累"}),
        ("/model/predict/physiological", {"physiological": {"heart_rate": 80, "hrv": 35, "steps": 3000, "sleep_hours": 6.5, "sleep_quality": 3, "exercise_minutes": 20, "systolic_bp": 120, "diastolic_bp": 80}}),
        ("/model/predict/fusion", {
            "features": {"age": 20, "gender": 1, "study_year": 2, "cgpa": 3.5, "stress_level": 3, "sleep_duration": 6.0, "social_support": 2, "financial_pressure": 3, "family_history": 0, "academic_pressure": 3, "exercise_frequency": 2, "anxiety": 1, "panic_attack": 0, "treatment_seeking": 0},
            "text": "感觉很疲惫",
            "physiological": {"heart_rate": 80, "hrv": 35, "steps": 3000, "sleep_hours": 6.5, "sleep_quality": 3, "exercise_minutes": 20, "systolic_bp": 120, "diastolic_bp": 80},
        }),
        ("/model/predict/text", {"text": "今天心情不错"}),
        ("/model/predict/tabular", {"features": {"age": 22, "gender": 0, "study_year": 4, "cgpa": 3.8, "stress_level": 4, "sleep_duration": 5.0, "social_support": 1, "financial_pressure": 4, "family_history": 1, "academic_pressure": 4, "exercise_frequency": 1, "anxiety": 1, "panic_attack": 1, "treatment_seeking": 0}}),
    ]

    latencies = []
    errors = 0
    for path, payload in payloads:
        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            f"{BASE}{path}", data=data, headers=headers, method="POST"
        )
        t0 = time.perf_counter()
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                resp.read()
                lat = (time.perf_counter() - t0) * 1000
                latencies.append(lat)
        except urllib.error.HTTPError as e:
            e.read()
            lat = (time.perf_counter() - t0) * 1000
            latencies.append(lat)
            errors += 1
        except Exception:
            lat = (time.perf_counter() - t0) * 1000
            latencies.append(lat)
            errors += 1

    return {
        "total": len(payloads),
        "errors": errors,
        "avg_latency_ms": round(statistics.mean(latencies), 1) if latencies else 0,
        "p99_latency_ms": round(max(latencies), 1) if latencies else 0,
        "error_rate_pct": round(errors / len(payloads) * 100, 2) if payloads else 0,
    }


def run_check() -> dict:
    """Run one check cycle."""
    now = datetime.now(timezone.utc)
    elapsed = now - CANARY_START
    elapsed_hours = elapsed.total_seconds() / 3600
    remaining_hours = max(0, 24 - elapsed_hours)

    canary = check_canary_status()
    drift_count = check_drift_alerts()
    traffic = generate_light_traffic()

    result = {
        "timestamp": now.isoformat(),
        "canary_elapsed_hours": round(elapsed_hours, 2),
        "canary_remaining_hours_24h": round(remaining_hours, 2),
        "canary_status": canary.get("status"),
        "canary_traffic_percent": canary.get("traffic_percent"),
        "drift_alerts_count": drift_count,
        "traffic_check": traffic,
        "thresholds": {
            "error_rate_lt_10pct": traffic["error_rate_pct"] < 10,
            "avg_latency_lt_500ms": traffic["avg_latency_ms"] < 500,
            "p99_latency_lt_500ms": traffic["p99_latency_ms"] < 500,
            "drift_alerts_lt_10": drift_count < 10 if drift_count >= 0 else False,
        },
    }
    all_met = all(result["thresholds"].values())
    result["all_thresholds_met"] = all_met
    return result


def main():
    parser = argparse.ArgumentParser(description="Canary 5% phase monitor")
    parser.add_argument("--once", action="store_true", help="Run once and exit")
    parser.add_argument("--interval", type=int, default=300, help="Run interval in seconds (default: 300)")
    args = parser.parse_args()

    log("=" * 70)
    log(f"Canary Monitor started (interval={args.interval}s, once={args.once})")
    log(f"Canary ID: {CANARY_ID}, Started: {CANARY_START.isoformat()}")
    log("=" * 70)

    while True:
        try:
            result = run_check()
            log(f"Check: elapsed={result['canary_elapsed_hours']}h / 24h, "
                f"remaining={result['canary_remaining_hours_24h']}h, "
                f"status={result['canary_status']}, "
                f"traffic={result['canary_traffic_percent']}%, "
                f"drift_alerts={result['drift_alerts_count']}, "
                f"traffic_check: errors={result['traffic_check']['errors']}/{result['traffic_check']['total']} "
                f"avg_lat={result['traffic_check']['avg_latency_ms']}ms "
                f"p99_lat={result['traffic_check']['p99_latency_ms']}ms, "
                f"all_thresholds_met={result['all_thresholds_met']}")

            if not result["all_thresholds_met"]:
                failed = [k for k, v in result["thresholds"].items() if not v]
                log(f"WARNING: Threshold violations: {failed}")

            if result["canary_remaining_hours_24h"] <= 0:
                log("INFO: 24h observation period complete. Ready to promote to 25%.")
                log("Run: python scripts/promote_canary.py 25")

        except Exception as e:
            log(f"ERROR in check cycle: {e}")

        if args.once:
            break
        time.sleep(args.interval)


if __name__ == "__main__":
    main()
