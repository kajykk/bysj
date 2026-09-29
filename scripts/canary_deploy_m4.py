"""M4 Stacking 金丝雀部署脚本 (阶段三).

通过金丝雀 API 注册 M4 stacking v3 部署, 执行三阶段流量切换:
  5% → 25% → 100%

每阶段需观察 24 小时, 监控指标:
  - fallback_rate < 5%
  - drift_alerts < 10/hour
  - avg_latency < 500ms
  - error_rate < 10%

Usage:
    python scripts/canary_deploy_m4.py            # 注册 5% 初始流量
    python scripts/canary_deploy_m4.py --status   # 查看当前金丝雀状态
    python scripts/canary_deploy_m4.py --promote  # 推进到下一阶段 (25% 或 100%)
    python scripts/canary_deploy_m4.py --rollback # 回滚金丝雀
"""

from __future__ import annotations

import argparse
import json
import logging
import os
import sys
import time
from pathlib import Path

import requests

logging.basicConfig(level=logging.INFO, format="%(asctime)s [Canary] %(message)s")
logger = logging.getLogger("Canary")

# 后端服务地址 (Docker 映射到主机 8001)
BASE_URL = os.getenv("DWS_BACKEND_URL", "http://localhost:8001")
API_BASE = f"{BASE_URL}/api/v1"

# admin 凭据 (从 .env 读取)
ADMIN_USERNAME = os.getenv("E2E_ADMIN_USER", "admin")
ADMIN_PASSWORD = os.getenv("E2E_ADMIN_PASSWORD", "***REMOVED***")

M4_VERSION = "m4_stacking_v3"
DEFAULT_THRESHOLDS = {
    "max_fallback_rate": 0.05,
    "max_drift_alerts_per_hour": 10,
    "max_avg_latency_ms": 500.0,
}


def login() -> str:
    """登录获取 access_token."""
    resp = requests.post(
        f"{API_BASE}/auth/login",
        json={"username": ADMIN_USERNAME, "password": ADMIN_PASSWORD},
        timeout=10,
    )
    if resp.status_code != 200:
        logger.error("登录失败: %d %s", resp.status_code, resp.text[:200])
        sys.exit(1)
    data = resp.json().get("data", {})
    token = data.get("access_token")
    if not token:
        logger.error("未获取到 access_token: %s", data)
        sys.exit(1)
    logger.info("✅ 登录成功 (user=%s)", data.get("user", {}).get("username"))
    return token


def auth_headers(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def list_canaries(token: str) -> list[dict]:
    """列出现有金丝雀部署."""
    resp = requests.get(
        f"{API_BASE}/canary/deployments",
        headers=auth_headers(token),
        params={"limit": 20},
        timeout=10,
    )
    if resp.status_code != 200:
        logger.error("查询金丝雀列表失败: %d %s", resp.status_code, resp.text[:200])
        return []
    body = resp.json().get("data", {})
    items = body.get("items", [])
    return items


def find_active_m4(token: str) -> dict | None:
    """查找活跃的 M4 金丝雀."""
    items = list_canaries(token)
    for item in items:
        if item.get("version") == M4_VERSION and item.get("status") == "running":
            return item
    return None


def create_canary(token: str, traffic_percent: int) -> dict:
    """创建金丝雀部署."""
    resp = requests.post(
        f"{API_BASE}/canary/deployments",
        headers=auth_headers(token),
        json={
            "version": M4_VERSION,
            "traffic_percent": traffic_percent,
            "thresholds": DEFAULT_THRESHOLDS,
        },
        timeout=10,
    )
    if resp.status_code not in (200, 201):
        logger.error("创建金丝雀失败: %d %s", resp.status_code, resp.text[:300])
        sys.exit(1)
    data = resp.json().get("data", {})
    return data


def update_traffic(token: str, canary_id: int, new_percent: int) -> dict:
    """更新金丝雀流量百分比."""
    resp = requests.patch(
        f"{API_BASE}/canary/deployments/{canary_id}/traffic",
        headers=auth_headers(token),
        json={"traffic_percent": new_percent},
        timeout=10,
    )
    if resp.status_code != 200:
        logger.error("更新流量失败: %d %s", resp.status_code, resp.text[:300])
        sys.exit(1)
    return resp.json().get("data", {})


def rollback_canary(token: str, canary_id: int, reason: str) -> dict:
    """回滚金丝雀部署."""
    resp = requests.post(
        f"{API_BASE}/canary/deployments/{canary_id}/rollback",
        headers=auth_headers(token),
        json={"reason": reason},
        timeout=10,
    )
    if resp.status_code != 200:
        logger.error("回滚失败: %d %s", resp.status_code, resp.text[:300])
        sys.exit(1)
    return resp.json().get("data", {})


def show_status(token: str) -> None:
    """显示金丝雀状态."""
    items = list_canaries(token)
    if not items:
        logger.info("当前无金丝雀部署记录")
        return
    logger.info("=" * 60)
    logger.info("金丝雀部署列表 (%d 条):", len(items))
    logger.info("=" * 60)
    for item in items:
        logger.info(
            "  id=%s version=%s traffic=%s%% status=%s started=%s",
            item.get("id"),
            item.get("version"),
            item.get("traffic_percent"),
            item.get("status"),
            item.get("started_at"),
        )
    active = find_active_m4(token)
    if active:
        logger.info("-" * 60)
        logger.info("✅ M4 活跃金丝雀: id=%s traffic=%s%%",
                     active.get("id"), active.get("traffic_percent"))


def cmd_deploy(token: str) -> None:
    """注册 5% 初始金丝雀."""
    active = find_active_m4(token)
    if active:
        logger.info("M4 金丝雀已存在 (id=%s traffic=%s%%), 跳过创建",
                     active.get("id"), active.get("traffic_percent"))
        return

    logger.info("注册 M4 金丝雀部署: version=%s traffic=5%%", M4_VERSION)
    data = create_canary(token, traffic_percent=5)
    logger.info("✅ 金丝雀创建成功:")
    logger.info("  id=%s version=%s traffic=%s%% status=%s",
                data.get("id"), data.get("version"),
                data.get("traffic_percent"), data.get("status"))
    logger.info("  started_at=%s", data.get("started_at"))
    logger.info("")
    logger.info("阶段 1 (5%%) 已启动, 需观察 24 小时:")
    logger.info("  - fallback_rate < 5%%")
    logger.info("  - drift_alerts < 10/hour")
    logger.info("  - avg_latency < 500ms")
    logger.info("  - error_rate < 10%%")
    logger.info("观察期结束后运行: python scripts/canary_deploy_m4.py --promote")


def cmd_promote(token: str) -> None:
    """推进金丝雀到下一阶段."""
    active = find_active_m4(token)
    if not active:
        logger.error("无活跃的 M4 金丝雀, 请先运行: python scripts/canary_deploy_m4.py")
        sys.exit(1)

    canary_id = active["id"]
    current = active["traffic_percent"]
    logger.info("当前 M4 金丝雀: id=%s traffic=%s%%", canary_id, current)

    if current < 25:
        next_percent = 25
        stage = 2
    elif current < 100:
        next_percent = 100
        stage = 3
    else:
        logger.info("已达 100%% 流量, 无需推进")
        return

    logger.info("推进到阶段 %d: %s%% → %s%%", stage, current, next_percent)
    data = update_traffic(token, canary_id, next_percent)
    logger.info("✅ 流量更新成功: id=%s traffic=%s%% status=%s",
                data.get("id"), data.get("traffic_percent"), data.get("status"))
    if next_percent < 100:
        logger.info("阶段 %d (%s%%) 已启动, 需观察 24 小时", stage, next_percent)
    else:
        logger.info("阶段 %d (100%%) 已启动, 金丝雀发布完成!", stage)


def cmd_rollback(token: str) -> None:
    """回滚金丝雀."""
    active = find_active_m4(token)
    if not active:
        logger.error("无活跃的 M4 金丝雀可回滚")
        sys.exit(1)
    canary_id = active["id"]
    logger.info("回滚 M4 金丝雀: id=%s", canary_id)
    data = rollback_canary(token, canary_id, reason="manual_rollback_phase3")
    logger.info("✅ 回滚成功: id=%s status=%s", data.get("id"), data.get("status"))


def check_health() -> bool:
    """检查后端服务健康状态."""
    try:
        resp = requests.get(f"{BASE_URL}/health", timeout=5)
        return resp.status_code == 200
    except Exception:
        return False


def main() -> None:
    parser = argparse.ArgumentParser(description="M4 金丝雀部署管理")
    parser.add_argument("--status", action="store_true", help="查看金丝雀状态")
    parser.add_argument("--promote", action="store_true", help="推进到下一阶段")
    parser.add_argument("--rollback", action="store_true", help="回滚金丝雀")
    args = parser.parse_args()

    logger.info("=" * 60)
    logger.info("M4 Stacking 金丝雀部署管理 (阶段三)")
    logger.info("=" * 60)

    if not check_health():
        logger.error("后端服务不可用: %s", BASE_URL)
        logger.error("请启动 Docker 环境: docker compose up -d")
        sys.exit(1)
    logger.info("✅ 后端服务健康: %s", BASE_URL)

    token = login()

    if args.status:
        show_status(token)
    elif args.promote:
        cmd_promote(token)
    elif args.rollback:
        cmd_rollback(token)
    else:
        cmd_deploy(token)
        show_status(token)


if __name__ == "__main__":
    main()
