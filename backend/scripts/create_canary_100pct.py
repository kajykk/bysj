#!/usr/bin/env python
"""T-P0-02: 直接创建 100% 金丝雀记录 (基于之前 29h 无回滚证据).

背景:
- 金丝雀 id=4 (5%) + id=5 (25%) 累计运行 29h 无回滚
- Docker 数据丢失后重建, 金丝雀记录丢失
- 基于之前 29h 无回滚的证据, 直接创建 100% 金丝雀
- 100% 阶段观察 24h 后完成生产切换

使用方式:
    docker exec dws-backend python /app/scripts/create_canary_100pct.py
"""
from __future__ import annotations

import asyncio
import sys

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.monitoring import CanaryRecord, CanaryStatus
from app.services.canary_manager import canary_manager


CANARY_VERSION = "m4_stacking_v3"
TRAFFIC_PERCENT = 100


async def main():
    """直接创建 100% 金丝雀."""
    print("=== T-P0-02: Create canary at 100% (based on 29h no-rollback evidence) ===")
    print()

    async with AsyncSessionLocal() as db_session:
        # 1. 检查是否已有运行中的金丝雀
        print("[1/2] Checking existing canaries...")
        existing = (
            await db_session.execute(
                select(CanaryRecord).where(CanaryRecord.status == CanaryStatus.RUNNING)
            )
        ).scalar_one_or_none()

        if existing:
            print(f"  Found running canary: id={existing.id} version={existing.version} traffic={existing.traffic_percent}%")
            if existing.traffic_percent >= TRAFFIC_PERCENT:
                print(f"  Already at {TRAFFIC_PERCENT}%, no action needed.")
                return
            print(f"  Updating to {TRAFFIC_PERCENT}%...")
            canary = await canary_manager.update_traffic_percent(
                db_session, existing.id, TRAFFIC_PERCENT
            )
            await db_session.commit()
            print(f"  SUCCESS: canary {canary.id} traffic={canary.traffic_percent}%")
            return

        print("  No running canary found. Creating new 100% canary.")

        # 2. 创建 100% 金丝雀
        print(f"\n[2/2] Creating canary: version={CANARY_VERSION} traffic={TRAFFIC_PERCENT}%...")
        canary = await canary_manager.start_canary(
            db_session,
            version=CANARY_VERSION,
            traffic_percent=TRAFFIC_PERCENT,
            # Docker 数据丢失重建后 users 表为空 (ENABLE_SEED=false),
            # triggered_by 为 FK -> users(id), 设为 NULL 避免外键约束失败.
            # 金丝雀记录的 triggered_by 仅用于审计, 不影响流量分流逻辑.
            triggered_by=None,
        )
        await db_session.commit()

        print(f"  SUCCESS: canary {canary.id} created")
        print(f"  version: {canary.version}")
        print(f"  traffic_percent: {canary.traffic_percent}%")
        print(f"  status: {canary.status}")
        print(f"  started_at: {canary.started_at}")
        print()
        print("=== Canary at 100% created. Monitor for 24h before production switch. ===")
        print("=== After 24h observation without rollback, run complete_production_switch.py ===")

if __name__ == "__main__":
    asyncio.run(main())
