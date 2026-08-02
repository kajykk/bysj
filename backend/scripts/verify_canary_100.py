"""验证金丝雀 100% 阶段状态."""
import asyncio
from app.core.database import AsyncSessionLocal
from app.services.auto_rollback_service import auto_rollback_service
from app.models.monitoring import CanaryRecord, CanaryStatus
from sqlalchemy import select


async def verify():
    async with AsyncSessionLocal() as db:
        # 1. 找到当前运行中的金丝雀 (状态小写 'running', 取最新一条)
        result = await db.execute(
            select(CanaryRecord)
            .where(CanaryRecord.status == CanaryStatus.RUNNING)
            .order_by(CanaryRecord.started_at.desc())
            .limit(1)
        )
        c = result.scalar_one_or_none()
        if c is None:
            print("=== Canary Status ===")
            print("  [!] 当前无运行中的金丝雀")
            return
        cid = c.id
        print("=== Canary Status ===")
        print(f"  id={cid}, version={c.version}, traffic={c.traffic_percent}%, status={c.status}")
        print(f"  started_at={c.started_at}")

        # 2. 健康检查
        print("\n=== Health Check ===")
        health = await auto_rollback_service.check_canary_health(db, cid)
        # RollbackCheckResult 指标全部在 health.metrics dict 中, 非实例属性
        metrics = health.metrics or {}
        print(f"  inference_count: {metrics.get('inference_count', 0)}")
        print(f"  fallback_count: {metrics.get('fallback_count', 0)}")
        print(f"  fallback_rate: {metrics.get('fallback_rate', 0):.2%}")
        print(f"  avg_latency_ms: {metrics.get('avg_latency_ms', 0):.2f}")
        print(f"  error_rate: {metrics.get('error_rate', 0):.2%}")
        print(f"  drift_alerts_per_hour: {metrics.get('drift_alerts_per_hour', 0)}")
        print(f"  should_rollback: {health.should_rollback}")
        print(f"  reason: {health.reason}")

        # 3. 回滚阈值
        print("\n=== Rollback Thresholds ===")
        thresholds = c.auto_rollback_thresholds or {}
        for k, v in thresholds.items():
            print(f"  {k}: {v}")


asyncio.run(verify())
