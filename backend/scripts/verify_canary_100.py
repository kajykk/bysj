"""验证金丝雀 100% 阶段状态."""
import asyncio
from app.core.database import AsyncSessionLocal
from app.services.auto_rollback_service import auto_rollback_service
from app.models.monitoring import CanaryRecord
from sqlalchemy import select


async def verify():
    async with AsyncSessionLocal() as db:
        # 1. 确认 100% 状态
        result = await db.execute(select(CanaryRecord).where(CanaryRecord.id == 5))
        c = result.scalar_one()
        print("=== Canary Status ===")
        print(f"  id={c.id}, version={c.version}, traffic={c.traffic_percent}%, status={c.status}")
        print(f"  started_at={c.started_at}")

        # 2. 健康检查
        print("\n=== Health Check ===")
        health = await auto_rollback_service.check_canary_health(db, 5)
        # RollbackCheckResult 对象, 用属性访问
        print(f"  inference_count: {getattr(health, 'inference_count', 0)}")
        print(f"  fallback_count: {getattr(health, 'fallback_count', 0)}")
        print(f"  fallback_rate: {getattr(health, 'fallback_rate', 0):.2%}")
        print(f"  avg_latency_ms: {getattr(health, 'avg_latency_ms', 0):.2f}")
        print(f"  error_rate: {getattr(health, 'error_rate', 0):.2%}")
        print(f"  drift_alerts_per_hour: {getattr(health, 'drift_alerts_per_hour', 0)}")
        print(f"  should_rollback: {getattr(health, 'should_rollback', False)}")
        print(f"  reason: {getattr(health, 'reason', 'unknown')}")

        # 3. 回滚阈值
        print("\n=== Rollback Thresholds ===")
        thresholds = c.auto_rollback_thresholds or {}
        for k, v in thresholds.items():
            print(f"  {k}: {v}")


asyncio.run(verify())
