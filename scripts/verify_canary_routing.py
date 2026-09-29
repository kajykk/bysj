"""验证金丝雀路由在 5% 流量下的行为 (admin hash=19, 不应路由)."""
import json
import os
import urllib.request

API = "http://localhost:8000/api/v1"

# AUDIT-2026-09-28: 口令不得硬编码入库，改从环境变量读取
_pw = os.environ.get("E2E_ADMIN_PASSWORD")
if not _pw:
    raise SystemExit("请设置环境变量 E2E_ADMIN_PASSWORD（禁止在源码中硬编码口令）")
body = json.dumps({"username": "admin", "password": _pw}).encode()
req = urllib.request.Request(
    f"{API}/auth/login",
    data=body,
    headers={"Content-Type": "application/json"},
    method="POST",
)
token = json.loads(urllib.request.urlopen(req, timeout=10).read().decode()).get(
    "data", {}
).get("access_token")

headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
case = {
    "features": {"age": 22, "gender": 1, "study_year": 3, "cgpa": 3.2, "stress_level": 7, "sleep_duration": 5.0, "social_support": 2, "financial_pressure": 3, "family_history": 0, "academic_pressure": 4, "exercise_frequency": 1, "anxiety": 1, "panic_attack": 0, "treatment_seeking": 0},
    "text": "最近总是失眠,什么都提不起兴趣,觉得活着没意思。",
    "physiological": {"heart_rate": 95, "hrv": 25, "steps": 1500, "sleep_efficiency": 0.65, "activity_variance": 0.3},
}

print("5% 流量验证 (admin hash=19, 应 canary=False):")
for i in range(3):
    body = json.dumps(case).encode()
    req = urllib.request.Request(
        f"{API}/model/predict/fusion", data=body, headers=headers, method="POST"
    )
    data = json.loads(urllib.request.urlopen(req, timeout=30).read().decode()).get(
        "data", {}
    )
    canary = data.get("canary_routed", False)
    ver = data.get("canary_version", "-")
    print(f"  [{i+1}] canary={canary} ver={ver}")
