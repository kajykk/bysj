#!/usr/bin/env python
"""T-P0-02: 推进当前运行中金丝雀从 5% -> 25% (第二阶段).

前置条件:
- 存在运行中的金丝雀 (自动查找最新一条 RUNNING), traffic_percent=5
- 运行时长 >= 24h
- 无回滚触发 (canary-auto-rollback-check 每 30s 检查, 未回滚)
- 无新增 CRITICAL/HIGH 漂移告警 (守卫逻辑修复生效)

使用方式:
    docker exec dws-backend python /app/scripts/promote_canary_25pct.py
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select, text

from app.core.database import AsyncSessionLocal
from app.models.monitoring import CanaryRecord, CanaryStatus
from app.services.canary_manager import canary_manager


OLD_PERCENT = 5
NEW_PERCENT = 25
MIN_HOURS_RUNNING = 24.0


async def find_running_canary(db_session) -> CanaryRecord:
    """查找当前运行中的金丝雀 (取最新一条)."""
    result = await db_session.execute(
        select(CanaryRecord)
        .where(CanaryRecord.status == CanaryStatus.RUNNING)
        .order_by(CanaryRecord.started_at.desc())
        .limit(1)
    )
    canary = result.scalar_one_or_none()
    if not canary:
        raise RuntimeError("当前无 RUNNING 金丝雀")
    return canary


async def check_canary_health(db_session, canary_id: int) -> dict:
    """检查金丝雀健康指标 (回滚率/漂移告警/延迟/错误率)."""
    health = {}

    # 1. 金丝雀运行时长 (用 DB 的 NOW() 计算, 避免时区不一致)
    result = await db_session.execute(
        select(CanaryRecord).where(CanaryRecord.id == canary_id)
    )
    canary = result.scalar_one_or_none()
    if not canary:
        raise RuntimeError(f"Canary {canary_id} not found")

    hours_result = await db_session.execute(
        text(
            "SELECT EXTRACT(EPOCH FROM (NOW() - started_at)) / 3600.0 "
            "FROM canary_records WHERE id = :cid"
        ),
        {"cid": canary_id},
    )
    hours_running = float(hours_result.scalar())
    health["hours_running"] = round(hours_running, 2)
    health["min_hours_met"] = hours_running >= MIN_HOURS_RUNNING
    health["status"] = canary.status
    health["current_percent"] = canary.traffic_percent

    # 2. 漂移告警数 (最近 1h, 未解决, prediction_drift)
    drift_count_result = await db_session.execute(
        text(
            "SELECT COUNT(*) FROM drift_alerts "
            "WHERE drift_type = 'prediction_drift' "
            "AND resolved_at IS NULL "
            "AND created_at >= NOW() - INTERVAL '1 hour'"
        )
    )
    health["drift_alerts_last_1h"] = drift_count_result.scalar()
    health["drift_alerts_ok"] = health["drift_alerts_last_1h"] < 10

    # 3. 金丝雀是否曾被回滚 (不应有 rollback_reason)
    health["was_rolled_back"] = canary.rollback_reason is not None

    return health


async def main():
    """推进金丝雀 5% -> 25%."""
    async with AsyncSessionLocal() as db_session:
        # 0. 动态定位运行中金丝雀
        canary = await find_running_canary(db_session)
        canary_id = canary.id
        print(f"=== T-P0-02: Promote canary {canary_id} {OLD_PERCENT}% -> {NEW_PERCENT}% ===")
        print()

        # 1. 健康检查
        print("[1/3] Health check...")
        health = await check_canary_health(db_session, canary_id)
        print(f"  status: {health['status']}")
        print(f"  current_percent: {health['current_percent']}%")
        print(f"  hours_running: {health['hours_running']}h (min: {MIN_HOURS_RUNNING}h)")
        print(f"  min_hours_met: {health['min_hours_met']}")
        print(f"  drift_alerts_last_1h: {health['drift_alerts_last_1h']} (< 10: {health['drift_alerts_ok']})")
        print(f"  was_rolled_back: {health['was_rolled_back']}")

        # 2. 验证前置条件
        print("\n[2/3] Validating preconditions...")
        errors = []
        if health["status"] != "running":
            errors.append(f"status={health['status']} (expected: running)")
        if health["current_percent"] != OLD_PERCENT:
            errors.append(f"current_percent={health['current_percent']} (expected: {OLD_PERCENT})")
        if not health["min_hours_met"]:
            errors.append(f"hours_running={health['hours_running']} < {MIN_HOURS_RUNNING}")
        if not health["drift_alerts_ok"]:
            errors.append(f"drift_alerts_last_1h={health['drift_alerts_last_1h']} >= 10")
        if health["was_rolled_back"]:
            errors.append(f"canary was rolled back: {health.get('rollback_reason')}")

        if errors:
            print("  FAILED:")
            for e in errors:
                print(f"    - {e}")
            print("\n  Aborting promotion. Fix issues before retry.")
            sys.exit(1)

        print("  All preconditions passed.")

        # 3. 推进流量
        print(f"\n[3/3] Promoting canary {canary_id}: {OLD_PERCENT}% -> {NEW_PERCENT}%...")
        canary = await canary_manager.update_traffic_percent(
            db_session, canary_id, NEW_PERCENT
        )
        await db_session.commit()

        print(f"  SUCCESS: canary {canary.id} traffic={canary.traffic_percent}%")
        print(f"  status: {canary.status}")
        print(f"  Next stage: 25% -> 100% after another 24h observation")
        print()
        print("=== Promotion complete. Monitor for 24h before advancing to 100%. ===")


if __name__ == "__main__":
    asyncio.run(main())
