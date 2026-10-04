#!/usr/bin/env python3
"""金丝雀发布脚本 (S-01~S-05 V4.1 优化项).

三级推进流程: 5% → 25% → 100%, 每级 ≥24h 观察.

用法:
    # 1. 启动金丝雀 (5% 流量)
    python scripts/canary_release.py start --api-url https://localhost --admin-user admin --admin-password 'xxx'

    # 2. 查看当前状态
    python scripts/canary_release.py status --api-url https://localhost --token 'jwt_token'

    # 3. 推进到下一级 (5→25 或 25→100)
    python scripts/canary_release.py promote --canary-id 1 --traffic 25 --api-url https://localhost --token 'jwt_token'

    # 4. 自动回滚 (如指标超阈值)
    python scripts/canary_release.py rollback --canary-id 1 --reason 'fallback rate >5%' --api-url https://localhost --token 'jwt_token'

    # 5. 完成金丝雀 (100% 稳定后)
    python scripts/canary_release.py complete --canary-id 1 --api-url https://localhost --token 'jwt_token'

环境变量 (优先级高于参数):
    DWS_API_URL: API base URL
    DWS_ADMIN_TOKEN: admin JWT token (登录后获取)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

# 金丝雀发布版本 (S-01~S-05 合并为 v4.1)
CANARY_VERSION = "v4.1-s01-s05"

# 三级推进阈值
TRAFFIC_STAGES = [5, 25, 100]

# 自动回滚阈值 (来自 STATE.md / 优化项验证标准)
AUTO_ROLLBACK_THRESHOLDS = {
    "fallback_rate_threshold": 5.0,      # fallback 率 <5%
    "drift_alert_threshold": 10.0,        # 漂移告警 <10 次/小时
    "avg_latency_threshold": 500.0,       # 平均延迟 <500ms
    "error_rate_threshold": 10.0,         # 错误率 <10%
}

# 每级最小观察时间 (秒)
STAGE_MIN_OBSERVATION_SECONDS = 24 * 3600  # 24 小时


def make_request(url: str, method: str = "GET", data: dict | None = None,
                 token: str | None = None, timeout: int = 30) -> dict:
    """发起 HTTP 请求并返回 JSON 响应."""
    headers = {"Content-Type": "application/json", "Accept": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    body = json.dumps(data).encode("utf-8") if data else None
    req = Request(url, data=body, headers=headers, method=method)

    try:
        with urlopen(req, timeout=timeout) as resp:
            return json.loads(resp.read().decode("utf-8"))
    except HTTPError as e:
        err_body = e.read().decode("utf-8", errors="replace")
        print(f"[HTTP {e.code}] {e.reason}: {err_body}", file=sys.stderr)
        sys.exit(1)
    except URLError as e:
        print(f"[URL Error] {e.reason}", file=sys.stderr)
        sys.exit(1)


def login(api_url: str, username: str, password: str) -> str:
    """登录获取 JWT token."""
    url = f"{api_url}/api/v1/auth/login"
    data = {"username": username, "password": password}
    resp = make_request(url, method="POST", data=data)
    token = resp.get("data", {}).get("access_token") or resp.get("access_token")
    if not token:
        print(f"[ERROR] 登录响应缺少 access_token: {resp}", file=sys.stderr)
        sys.exit(1)
    return token


def start_canary(api_url: str, token: str, traffic_percent: int = 5,
                 route_prefix: str | None = None) -> dict:
    """启动金丝雀部署."""
    url = f"{api_url}/api/v1/canary/deployments"
    data = {
        "version": CANARY_VERSION,
        "traffic_percent": traffic_percent,
        "thresholds": AUTO_ROLLBACK_THRESHOLDS,
    }
    if route_prefix:
        data["route_prefix"] = route_prefix

    print(f"[INFO] 启动金丝雀 v={CANARY_VERSION} traffic={traffic_percent}%")
    resp = make_request(url, method="POST", data=data, token=token)
    canary = resp.get("data", resp)
    print(f"[OK] 金丝雀已创建: id={canary.get('id')} status={canary.get('status')}")
    print(f"     下一步: 等待 {STAGE_MIN_OBSERVATION_SECONDS//3600}h 后执行 promote")
    return canary


def list_canaries(api_url: str, token: str) -> dict:
    """列出所有金丝雀部署."""
    url = f"{api_url}/api/v1/canary/deployments"
    return make_request(url, method="GET", token=token)


def get_canary(api_url: str, token: str, canary_id: int) -> dict:
    """获取金丝雀详情."""
    url = f"{api_url}/api/v1/canary/deployments/{canary_id}"
    return make_request(url, method="GET", token=token)


def update_traffic(api_url: str, token: str, canary_id: int,
                   traffic_percent: int) -> dict:
    """更新金丝雀流量百分比."""
    url = f"{api_url}/api/v1/canary/deployments/{canary_id}/traffic"
    data = {"traffic_percent": traffic_percent}
    print(f"[INFO] 推进金丝雀 id={canary_id} traffic={traffic_percent}%")
    resp = make_request(url, method="PATCH", data=data, token=token)
    canary = resp.get("data", resp)
    print(f"[OK] 流量已更新: status={canary.get('status')} traffic={canary.get('traffic_percent')}%")
    return canary


def rollback_canary(api_url: str, token: str, canary_id: int, reason: str) -> dict:
    """回滚金丝雀."""
    url = f"{api_url}/api/v1/canary/deployments/{canary_id}/rollback"
    data = {"reason": reason}
    print(f"[WARN] 回滚金丝雀 id={canary_id} reason={reason}")
    resp = make_request(url, method="POST", data=data, token=token)
    canary = resp.get("data", resp)
    print(f"[OK] 已回滚: status={canary.get('status')}")
    return canary


def complete_canary(api_url: str, token: str, canary_id: int) -> dict:
    """完成金丝雀发布."""
    url = f"{api_url}/api/v1/canary/deployments/{canary_id}/complete"
    print(f"[INFO] 完成金丝雀 id={canary_id}")
    resp = make_request(url, method="POST", token=token)
    canary = resp.get("data", resp)
    print(f"[OK] 已完成: status={canary.get('status')}")
    return canary


def check_health(api_url: str) -> dict:
    """检查后端健康状态."""
    url = f"{api_url}/health"
    return make_request(url, method="GET", timeout=10)


def check_metrics(api_url: str, token: str) -> str:
    """获取 Prometheus 指标文本."""
    url = f"{api_url}/api/v1/metrics"
    req = Request(url, headers={"Authorization": f"Bearer {token}"})
    try:
        with urlopen(req, timeout=30) as resp:
            return resp.read().decode("utf-8")
    except HTTPError as e:
        print(f"[ERROR] 获取指标失败: {e}", file=sys.stderr)
        return ""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="金丝雀发布脚本 (S-01~S-05 V4.1)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # start
    p_start = sub.add_parser("start", help="启动金丝雀 (5%% 流量)")
    p_start.add_argument("--api-url", default=os.environ.get("DWS_API_URL", "https://localhost"))
    p_start.add_argument("--admin-user", default="admin")
    p_start.add_argument("--admin-password", required=True)
    p_start.add_argument("--traffic", type=int, default=5, help="初始流量百分比 (默认 5)")
    p_start.add_argument("--route-prefix", default=None, help="路由前缀 (None=全局)")

    # status
    p_status = sub.add_parser("status", help="查看金丝雀状态")
    p_status.add_argument("--api-url", default=os.environ.get("DWS_API_URL", "https://localhost"))
    p_status.add_argument("--token", default=os.environ.get("DWS_ADMIN_TOKEN"))
    p_status.add_argument("--canary-id", type=int, default=None)

    # promote
    p_promote = sub.add_parser("promote", help="推进金丝雀流量")
    p_promote.add_argument("--api-url", default=os.environ.get("DWS_API_URL", "https://localhost"))
    p_promote.add_argument("--token", default=os.environ.get("DWS_ADMIN_TOKEN"))
    p_promote.add_argument("--canary-id", type=int, required=True)
    p_promote.add_argument("--traffic", type=int, required=True,
                           help="目标流量百分比 (25 或 100)")

    # rollback
    p_rollback = sub.add_parser("rollback", help="回滚金丝雀")
    p_rollback.add_argument("--api-url", default=os.environ.get("DWS_API_URL", "https://localhost"))
    p_rollback.add_argument("--token", default=os.environ.get("DWS_ADMIN_TOKEN"))
    p_rollback.add_argument("--canary-id", type=int, required=True)
    p_rollback.add_argument("--reason", required=True)

    # complete
    p_complete = sub.add_parser("complete", help="完成金丝雀发布")
    p_complete.add_argument("--api-url", default=os.environ.get("DWS_API_URL", "https://localhost"))
    p_complete.add_argument("--token", default=os.environ.get("DWS_ADMIN_TOKEN"))
    p_complete.add_argument("--canary-id", type=int, required=True)

    # health
    p_health = sub.add_parser("health", help="检查后端健康状态")
    p_health.add_argument("--api-url", default=os.environ.get("DWS_API_URL", "https://localhost"))

    return parser.parse_args()


def main() -> None:
    args = parse_args()

    if args.command == "health":
        resp = check_health(args.api_url)
        print(json.dumps(resp, indent=2, ensure_ascii=False))
        return

    # 获取 token
    token = getattr(args, "token", None)
    if not token and hasattr(args, "admin_password"):
        token = login(args.api_url, args.admin_user, args.admin_password)
        print(f"[INFO] 登录成功, token: {token[:20]}...")
    elif not token:
        print("[ERROR] 需要 --token 或 --admin-password", file=sys.stderr)
        sys.exit(1)

    if args.command == "start":
        start_canary(args.api_url, token, args.traffic, args.route_prefix)
    elif args.command == "status":
        if args.canary_id:
            resp = get_canary(args.api_url, token, args.canary_id)
        else:
            resp = list_canaries(args.api_url, token)
        print(json.dumps(resp, indent=2, ensure_ascii=False))
    elif args.command == "promote":
        if args.traffic not in TRAFFIC_STAGES:
            print(f"[ERROR] 流量百分比必须是 {TRAFFIC_STAGES} 之一", file=sys.stderr)
            sys.exit(1)
        update_traffic(args.api_url, token, args.canary_id, args.traffic)
    elif args.command == "rollback":
        rollback_canary(args.api_url, token, args.canary_id, args.reason)
    elif args.command == "complete":
        complete_canary(args.api_url, token, args.canary_id)


if __name__ == "__main__":
    main()
