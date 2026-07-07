#!/usr/bin/env python3
"""
DWS 仓库 Topics 配置脚本
使用前请先创建 Personal Access Token:
1. https://github.com/settings/tokens
2. Generate new token (Fine-grained)
3. 勾选: Repository permissions -> Administration: Read and write
4. 复制 token 到此脚本输入

注意: 设置 topics 需要 Administration 权限 (经典 token 勾选 repo 即可)
"""
import urllib.request
import urllib.error
import json
import sys
import getpass

REPO = "kajykk/bysj"
TOPICS = [
    "vue",
    "fastapi",
    "docker",
    "ai",
    "fullstack",
    "mental-health",
    "ml",
    "typescript",
    "python",
    "websocket",
    "celery",
    "prometheus",
    "postgresql",
    "redis",
    "machine-learning",
    "real-time",
    "monitoring",
    "pwa",
    "element-plus",
    "tailwindcss",
]

def main():
    print("=" * 60)
    print("  DWS 仓库 Topics 配置")
    print("=" * 60)
    print()
    print("需要 Personal Access Token (勾选 repo / Administration: write)")
    print("获取: https://github.com/settings/tokens\n")

    token = getpass.getpass("请输入 GitHub Token (输入隐藏): ").strip()
    if not token:
        print("❌ Token 为空，已退出")
        sys.exit(1)

    url = f"https://api.github.com/repos/{REPO}/topics"
    headers = {
        "Authorization": f"token {token}",
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    body = json.dumps({"names": TOPICS}).encode("utf-8")

    req = urllib.request.Request(url, data=body, headers=headers, method="PUT")
    try:
        with urllib.request.urlopen(req) as resp:
            data = json.loads(resp.read())
            print(f"\n✅ 成功设置 {len(data.get('names', []))} 个 Topics:")
            for t in data.get("names", []):
                print(f"   - {t}")
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", errors="ignore")
        print(f"\n❌ HTTP {e.code}: {body[:200]}")
        if e.code == 401:
            print("   原因: Token 无效或权限不足")
        elif e.code == 404:
            print("   原因: 仓库不存在或 token 缺少 repo 权限")
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f"\n❌ 网络错误: {e.reason}")
        sys.exit(1)

    print(f"\n🌐 验证: https://github.com/{REPO}")
    input("\n按 Enter 退出...")

if __name__ == "__main__":
    main()
