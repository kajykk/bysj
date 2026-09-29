"""验证 auto_rollback_service.check_all_canaries() 能正常运行并返回结果."""
import asyncio
import sys
from pathlib import Path

# 添加 backend 到 sys.path 以便容器内执行
sys.path.insert(0, "/app")


async def check():
    from app.core.database import AsyncSessionLocal
    from app.services.auto_rollback_service import auto_rollback_service

    async with AsyncSessionLocal() as db:
        results = await auto_rollback_service.check_all_canaries(db)
        print(f"检查到 {len(results)} 个活跃金丝雀")
        for r in results:
            print(f"  canary_id={r.canary_id}")
            print(f"    should_rollback={r.should_rollback}")
            print(f"    reason={r.reason}")
            print(f"    metrics={r.metrics}")
        await db.rollback()


if __name__ == "__main__":
    asyncio.run(check())
