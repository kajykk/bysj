"""Admin login helper for canary release operations.

L13 修复（ROUND_23）：口令与令牌路径一律从环境变量读取。

修前脚本里硬编码了管理员口令（该口令在 seed 的「公开已知口令」拒绝清单内，
生产不可用），且把真实形态的凭据写进版本库；
令牌还被写到**绝对路径** `e:\\code\\bysj\\scripts\\.admin_token.txt`
（换机器即失效/写到别人的盘上）。

现在：
- `BYSJ_ADMIN_USERNAME` / `BYSJ_ADMIN_PASSWORD` 必须显式提供，缺失即报错退出
  （退出码 2），**不回落任何默认值**——静默使用默认口令正是 L13 要治的病；
- 令牌输出路径默认解析为**仓库根相对**的 `scripts/.admin_token.txt`，
  可由 `BYSJ_ADMIN_TOKEN_PATH` 覆盖；
- `.admin_token.txt` 已被 `.gitignore` 排除（产物不落版本库）。

闸门：`backend/tests/test_p2_49_round23b_secret_scan.py` 会扫描 scripts/ 下
是否重新出现硬编码口令/令牌字面量，变异见证见
`frontend/tests/tools/mutate_round23b.md`。
"""
import json
import os
import sys
import urllib.request
from pathlib import Path

USERNAME = os.environ.get("BYSJ_ADMIN_USERNAME")
PASSWORD = os.environ.get("BYSJ_ADMIN_PASSWORD")

if not USERNAME or not PASSWORD:
    print(
        "ERROR: 缺少环境变量 BYSJ_ADMIN_USERNAME / BYSJ_ADMIN_PASSWORD。\n"
        "本脚本不再内置任何口令（L13 修复）：请显式提供后再运行，例如\n"
        "  export BYSJ_ADMIN_USERNAME=admin\n"
        "  export BYSJ_ADMIN_PASSWORD='<你的口令>'",
        file=sys.stderr,
    )
    sys.exit(2)

# 仓库根 = 本文件所在目录的父目录；可用 BYSJ_ADMIN_TOKEN_PATH 覆盖
_REPO_ROOT = Path(__file__).resolve().parent.parent
_TOKEN_PATH = Path(
    os.environ.get("BYSJ_ADMIN_TOKEN_PATH") or (_REPO_ROOT / "scripts" / ".admin_token.txt")
)

url = "http://localhost:8001/api/v1/auth/login"
payload = {"username": USERNAME, "password": PASSWORD}
data = json.dumps(payload).encode("utf-8")
req = urllib.request.Request(
    url, data=data, headers={"Content-Type": "application/json"}, method="POST"
)
try:
    with urllib.request.urlopen(req, timeout=10) as resp:
        body = resp.read().decode("utf-8")
        print("Login resp:")
        print(body)
        obj = json.loads(body)
        token = obj.get("data", {}).get("access_token")
        if token:
            _TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
            _TOKEN_PATH.write_text(token, encoding="utf-8")
            print(f"Token saved to {_TOKEN_PATH}")
        else:
            print("No access_token in response")
            sys.exit(1)
except urllib.error.HTTPError as e:
    print(f"HTTP Error {e.code}: {e.read().decode('utf-8')}")
    sys.exit(1)
except Exception as e:
    print(f"Error: {e}")
    sys.exit(1)
