"""Check model versions returned by inference APIs to verify canary routing."""
import json
import urllib.request

BASE = "http://localhost:8001/api/v1"
TOKEN_FILE = r"e:\code\bysj\scripts\.admin_token.txt"

with open(TOKEN_FILE, encoding="utf-8") as f:
    token = f.read().strip()

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
}


def call_api(path, payload):
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        f"{BASE}{path}", data=data, headers=headers, method="POST"
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        return {"error": f"HTTP {e.code}", "body": e.read().decode("utf-8")}


print("=" * 70)
print("Model version check - verify canary routing")
print("=" * 70)

# Tabular
r = call_api("/model/predict/tabular", {"features": {"sleep_hours": 6.5, "appetite": 3, "interest": 2, "energy": 3, "mood": 2}})
if r.get("code") == 200:
    data = r["data"]
    print(f"Tabular: model_used={data.get('model_used')}, model_version={data.get('model_version')}, risk_score={data.get('risk_score')}")
else:
    print(f"Tabular error: {r}")

# Text
r = call_api("/model/predict/text", {"text": "最近总是睡不好，感觉很累"})
if r.get("code") == 200:
    data = r["data"]
    print(f"Text: model_used={data.get('model_used')}, model_version={data.get('model_version')}, prediction={data.get('prediction')}, prob={data.get('probability')}")
else:
    print(f"Text error: {r}")

# Physiological
r = call_api("/model/predict/physiological", {"physiological": {"heart_rate": 80, "hrv": 35, "steps": 3000}})
if r.get("code") == 200:
    data = r["data"]
    print(f"Physiological: model_used={data.get('model_used')}, model_version={data.get('model_version')}, risk_score={data.get('risk_score')}")
else:
    print(f"Physiological error: {r}")

# Fusion
r = call_api("/model/predict/fusion", {
    "features": {"sleep_hours": 6.0, "appetite": 3, "interest": 2, "energy": 3, "mood": 2},
    "text": "感觉很疲惫，没什么动力",
    "physiological": {"heart_rate": 80, "hrv": 35, "steps": 3000},
})
if r.get("code") == 200:
    data = r["data"]
    print(f"Fusion: model_used={data.get('model_used')}, model_version={data.get('model_version')}, risk_score={data.get('risk_score')}, risk_level={data.get('risk_level')}")
    # Print full data for inspection
    print(f"  Full data keys: {list(data.keys())}")
    print(f"  Full data: {json.dumps(data, indent=2, ensure_ascii=False)[:1500]}")
else:
    print(f"Fusion error: {r}")

# Check current canary version expectation
print()
print("Expected canary version: v4.1-s01-s05")
print("Canary traffic_percent: 5%")
print("Note: Canary routing is user_id-based. Admin user_id=1 may always route to baseline.")
print("      To verify canary routing, would need multiple user_ids.")
