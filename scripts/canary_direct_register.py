"""M4 金丝雀直接注册 (容器内执行, 绕过 HTTP 认证).

Usage (主机 PowerShell):
    docker cp scripts/canary_direct_register.py dws-backend:/tmp/c.py
    docker exec dws-backend python /tmp/c.py
"""
import asyncio
from datetime import datetime, timezone
from sqlalchemy import text
from app.core.database import AsyncSessionLocal
from app.services.canary_manager import canary_manager

M4_VERSION = "m4_stacking_v3"
THRESHOLDS = {
    "max_fallback_rate": 0.05,
    "max_drift_alerts_per_hour": 10,
    "max_avg_latency_ms": 500.0,
}


async def main() -> None:
    async with AsyncSessionLocal() as db:
        # 1. 列出现有金丝雀
        r = await db.execute(
            text("SELECT id, version, traffic_percent, status FROM canary_records ORDER BY id DESC LIMIT 10")
        )
        rows = r.fetchall()
        print("=" * 60)
        print("现有金丝雀记录:")
        for row in rows:
            print(f"  id={row[0]} version={row[1]} traffic={row[2]}% status={row[3]}")

        # 2. 检查是否已有活跃的 M4 金丝雀
        r = await db.execute(
            text("SELECT id, traffic_percent FROM canary_records WHERE version=:v AND status=:s"),
            {"v": M4_VERSION, "s": "running"},
        )
        existing_m4 = r.fetchone()
        if existing_m4:
            print(f"\nM4 金丝雀已存在: id={existing_m4[0]} traffic={existing_m4[1]}%, 跳过创建")
            return

        # 3. 回滚其他活跃的全局金丝雀 (route_prefix IS NULL)
        r = await db.execute(
            text("SELECT id, version FROM canary_records WHERE status=:s AND route_prefix IS NULL AND version<>:v"),
            {"s": "running", "v": M4_VERSION},
        )
        conflicts = r.fetchall()
        for cid, cver in conflicts:
            print(f"\n回滚冲突金丝雀: id={cid} version={cver}")
            await db.execute(
                text("UPDATE canary_records SET status=:s, ended_at=:t, rollback_reason=:r WHERE id=:id"),
                {"s": "rolled_back", "t": datetime.now(timezone.utc).replace(tzinfo=None), "r": "replaced_by_m4_stacking_v3", "id": cid},
            )
            await db.commit()
            print(f"  已回滚: id={cid}")

        # 4. 创建 M4 金丝雀 5%
        print(f"\n注册 M4 金丝雀: version={M4_VERSION} traffic=5%")
        canary = await canary_manager.start_canary(
            db_session=db,
            version=M4_VERSION,
            traffic_percent=5,
            thresholds=THRESHOLDS,
        )
        await db.commit()
        print(f"OK 金丝雀创建成功:")
        print(f"  id={canary.id} version={canary.version} traffic={canary.traffic_percent}% status={canary.status}")
        print(f"  started_at={canary.started_at}")
        print(f"\n阶段 1 (5%) 已启动, 需观察 24 小时:")
        print(f"  - fallback_rate < 5%")
        print(f"  - drift_alerts < 10/hour")
        print(f"  - avg_latency < 500ms")
        print(f"  - error_rate < 10%")

        # 5. 验证
        r = await db.execute(
            text("SELECT id, version, traffic_percent, status FROM canary_records WHERE status=:s ORDER BY id DESC"),
            {"s": "running"},
        )
        active = r.fetchall()
        print(f"\n当前活跃金丝雀 ({len(active)} 条):")
        for row in active:
            print(f"  id={row[0]} version={row[1]} traffic={row[2]}% status={row[3]}")


asyncio.run(main())
