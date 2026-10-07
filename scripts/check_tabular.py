"""Debug tabular prediction - check why model_used and risk_score are None."""
import json
import urllib.request

BASE = "http://localhost:8001/api/v1"
TOKEN_FILE = r"e:\code\bysj\scripts\.admin_token.txt"  # nosec: B105 -- AUDIT-2026-10-07 (P0-4): 非凭据: 值为脚本自身生成的令牌文件路径, 非令牌本身; 真实令牌由 .admin_token.txt 承载且该文件已被 .gitignore 排除

with open(TOKEN_FILE, encoding="utf-8") as f:
    token = f.read().strip()

headers = {
    "Authorization": f"Bearer {token}",
    "Content-Type": "application/json",
}

payload = {"features": {"sleep_hours": 6.5, "appetite": 3, "interest": 2, "energy": 3, "mood": 2}}
data = json.dumps(payload).encode("utf-8")
req = urllib.request.Request(
    f"{BASE}/model/predict/tabular", data=data, headers=headers, method="POST"
)
with urllib.request.urlopen(req, timeout=30) as resp:
    body = resp.read().decode("utf-8")
    print("Tabular full response:")
    print(json.dumps(json.loads(body), indent=2, ensure_ascii=False))
