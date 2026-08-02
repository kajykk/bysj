#!/usr/bin/env python
"""T-P0-02: 金丝雀 100% 阶段观察期满后执行生产切换 (完成金丝雀).

前置条件:
- 存在运行中的金丝雀 (自动查找最新一条 RUNNING), traffic_percent=100
- 100% 阶段观察时长 >= 24h (100% 全量运行期)
- 健康检查通过 (fallback/drift/latency 全部在阈值内, 无回滚)

生产切换动作: 调用 canary_manager.complete_canary 将金丝雀标记为 COMPLETED,
即金丝雀全量流量正式成为生产流量. 切换后可清理旧模型/旧版本金丝雀记录.

使用方式:
    docker exec dws-backend python /app/scripts/complete_production_switch.py
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select, text

from app.core.database import AsyncSessionLocal
from app.models.monitoring import CanaryRecord, CanaryStatus
from app.services.auto_rollback_service import auto_rollback_service
from app.services.canary_manager import canary_manager


MIN_HOURS_OBSERVATION = 24.0


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


async def main() -> None:
    """执行生产切换."""
    async with AsyncSessionLocal() as db_session:
        # 1. 动态定位运行中金丝雀
        canary = await find_running_canary(db_session)
        canary_id = canary.id
        print(f"=== T-P0-02: Production switch for canary {canary_id} ===")
        print()

        # 2. 运行时长 (用 DB 的 NOW() 计算, 避免时区不一致)
        hours_result = await db_session.execute(
            text(
                "SELECT EXTRACT(EPOCH FROM (NOW() - started_at)) / 3600.0 "
                "FROM canary_records WHERE id = :cid"
            ),
            {"cid": canary_id},
        )
        hours_running = float(hours_result.scalar() or 0.0)

        print("[1/3] Preconditions...")
        print(f"  status: {canary.status}")
        print(f"  traffic_percent: {canary.traffic_percent}%")
        print(f"  hours_running: {hours_running:.2f}h (min: {MIN_HOURS_OBSERVATION}h)")

        errors = []
        if canary.status != "running":
            errors.append(f"status={canary.status} (expected: running)")
        if canary.traffic_percent != 100:
            errors.append(f"traffic_percent={canary.traffic_percent} (expected: 100)")
        if hours_running < MIN_HOURS_OBSERVATION:
            errors.append(
                f"hours_running={hours_running:.2f}h < {MIN_HOURS_OBSERVATION}h"
            )
        if canary.rollback_reason:
            errors.append(f"canary was rolled back: {canary.rollback_reason}")

        if errors:
            print("  FAILED:")
            for e in errors:
                print(f"    - {e}")
            print("\n  Aborting production switch. Fix issues before retry.")
            sys.exit(1)
        print("  All preconditions passed.")

        # 3. 健康检查
        print("\n[2/3] Health check...")
        health = await auto_rollback_service.check_canary_health(db_session, canary_id)
        metrics = health.metrics or {}
        print(f"  should_rollback: {health.should_rollback} ({health.reason})")
        print(f"  fallback_rate: {metrics.get('fallback_rate', 0):.2%}")
        print(f"  drift_alerts_per_hour: {metrics.get('drift_alerts_per_hour', 0)}")
        print(f"  avg_latency_ms: {metrics.get('avg_latency_ms', 0):.2f}")
        if health.should_rollback:
            print("\n  Aborting production switch: 健康检查未通过.")
            sys.exit(1)

        # 4. 执行生产切换
        print(f"\n[3/3] Completing canary {canary_id} (production switch)...")
        completed = await canary_manager.complete_canary(db_session, canary_id)
        await db_session.commit()

        print(f"  SUCCESS: canary {completed.id} status={completed.status}")
        print(f"  ended_at: {completed.ended_at}")
        print()
        print("=== Production switch complete. Canary traffic is now production traffic. ===")
        print("=== Old model artifacts can be cleaned up. ===")


if __name__ == "__main__":
    asyncio.run(main())
