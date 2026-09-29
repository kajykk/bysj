"""Check canary deployment status and monitoring metrics."""
import json
import sys
import urllib.request

BASE = "http://localhost:8001/api/v1"
TOKEN_FILE = r"e:\code\bysj\scripts\.admin_token.txt"

with open(TOKEN_FILE, encoding="utf-8") as f:
    token = f.read().strip()

headers = {"Authorization": f"Bearer {token}"}


def get(path):
    req = urllib.request.Request(f"{BASE}{path}", headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}", "body": e.read().decode("utf-8")}


def get_raw(path):
    req = urllib.request.Request(f"{BASE}{path}", headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            return resp.read().decode("utf-8")
    except urllib.error.HTTPError as e:
        return f"HTTP {e.code}: {e.read().decode('utf-8')}"


# 1. List all canary deployments
print("=" * 70)
print("[1] List all canary deployments")
print("=" * 70)
result = get("/canary/deployments")
print(json.dumps(result, indent=2, ensure_ascii=False)[:3000])

# 2. Get specific canary id=3 detail
print()
print("=" * 70)
print("[2] Canary id=3 detail")
print("=" * 70)
result = get("/canary/deployments/3")
print(json.dumps(result, indent=2, ensure_ascii=False)[:3000])

# 3. Try monitoring endpoints
print()
print("=" * 70)
print("[3] Canary metrics for id=3")
print("=" * 70)
print(get_raw("/canary/deployments/3/metrics")[:2000])

# 4. Check monitoring logs
print()
print("=" * 70)
print("[4] Canary monitoring logs for id=3")
print("=" * 70)
print(get_raw("/canary/deployments/3/logs?limit=10")[:2000])

# 5. Check drift alerts
print()
print("=" * 70)
print("[5] Drift alerts (recent)")
print("=" * 70)
print(get_raw("/monitoring/drift-alerts?limit=5")[:1500])

# 6. Check overall system metrics endpoint
print()
print("=" * 70)
print("[6] System metrics")
print("=" * 70)
print(get_raw("/monitoring/metrics")[:1500])
