"""v1.27 E2E API test script."""
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))

BASE = "http://localhost:8000"
results = []

def test(name, method, path, body=None, expected_status=200):
    url = f"{BASE}{path}"
    data = json.dumps(body).encode() if body else None
    try:
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", "application/json")
        r = urllib.request.urlopen(req, timeout=10)
        resp = json.loads(r.read())
        ok = r.status == expected_status
        results.append((name, ok, r.status, resp if ok else str(resp)[:200]))
        print(f"  {'PASS' if ok else 'FAIL'} {name} (status={r.status})")
        return resp
    except urllib.error.HTTPError as e:
        ok = e.code == expected_status
        results.append((name, ok, e.code, str(e)[:200]))
        print(f"  {'PASS' if ok else 'FAIL'} {name} (status={e.code})")
        return None
    except Exception as e:
        results.append((name, False, 0, str(e)[:200]))
        print(f"  FAIL {name}: {e}")
        return None

print("=== v1.27 E2E Test Suite ===\n")

# T-E2E-001: Health Check & Engine Snapshot
print("--- T-E2E-001: Backend Service ---")
test("health_check", "GET", "/health")
snap = test("engine_snapshot", "GET", "/api/v1/monitoring/engine-snapshot")

# T-E2E-002: 6 Route Tests
print("\n--- T-E2E-002: 6 Routing Paths ---")

# 1. Structured
resp1 = test("route_structured", "POST", "/api/v1/model/predict/tabular", {
    "features": {
        "age": 21, "gender": 1, "cgpa": 3.2, "study_year": 3,
        "stress_level": 7, "sleep_duration": 5.5,
        "social_support": 2, "financial_pressure": 4,
        "family_history": 1, "academic_pressure": 6,
        "exercise_frequency": 2, "anxiety": 3, "panic_attack": 1,
        "treatment_seeking": 0, "phq9_score": 8, "gad7_score": 6,
        "text": "最近压力很大，睡不好觉"
    }
})

# 2. Lite (GAD-7 + text only)
resp2 = test("route_lite", "POST", "/api/v1/model/predict/tabular", {
    "features": {
        "gad7_score": 12,
        "text": "最近总是很焦虑，担心很多事情，晚上也睡不着"
    }
})

# 3. Anxiety only
resp3 = test("route_anxiety_only", "POST", "/api/v1/model/predict/tabular", {
    "features": {
        "gad7_score": 15
    }
})

# 4. Insufficient
resp4 = test("route_insufficient", "POST", "/api/v1/model/predict/tabular", {
    "features": {}
})

# 5. Crisis
resp5 = test("route_crisis", "POST", "/api/v1/model/predict/tabular", {
    "features": {
        "gad7_score": 10,
        "text": "我想死，真的活不下去了"
    }
})

# 6. Invalid input (should not crash)
resp6 = test("route_invalid", "POST", "/api/v1/model/predict/tabular", {
    "features": {"unknown_field": 999}
})

# Summary
print("\n=== Summary ===")
passed = sum(1 for _, ok, _, _ in results if ok)
total = len(results)
print(f"Passed: {passed}/{total}")
for name, ok, status, detail in results:
    marker = "PASS" if ok else "FAIL"
    print(f"  [{marker}] {name} (status={status})")

# Save results
out_path = Path(__file__).resolve().parent / "e2e_results.json"
json.dump([{"name": n, "ok": o, "status": s, "detail": str(d)} for n, o, s, d in results], open(out_path, "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print(f"\nResults saved to {out_path}")
