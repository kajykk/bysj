"""阶段三续: 检查 M4 金丝雀 5% 阶段健康指标 (容器内执行).

验证 5% 流量阶段是否满足推进到 25% 的条件:
- fallback_rate < 5%
- drift_alerts < 10/hour
- avg_latency < 500ms
- error_rate < 10%
"""
import asyncio
import sys
from datetime import datetime, timedelta, timezone


async def main() -> int:
    from app.core.database import AsyncSessionLocal
    from sqlalchemy import text

    print("=" * 60)
    print("M4 金丝雀 5% 阶段健康指标检查")
    print("=" * 60)

    async with AsyncSessionLocal() as db:
        # 1. 查询金丝雀记录
        r = await db.execute(
            text(
                "SELECT id, version, traffic_percent, status, started_at, ended_at, rollback_reason "
                "FROM canary_records WHERE id=4"
            )
        )
        row = r.fetchone()
        if not row:
            print("ERROR: 金丝雀 id=4 不存在")
            return 1

        canary_id, version, traffic, status, started_at, ended_at, rollback_reason = row
        print(f"\n金丝雀记录:")
        print(f"  id={canary_id} version={version} traffic={traffic}% status={status}")
        print(f"  started_at={started_at} ended_at={ended_at}")
        if rollback_reason:
            print(f"  rollback_reason={rollback_reason}")

        if status != "running":
            print(f"\nWARN: 金丝雀状态为 {status}, 非 running")
            return 1

        # 2. 计算观察时长
        now = datetime.utcnow()
        if started_at:
            if started_at.tzinfo:
                started_at = started_at.replace(tzinfo=None)
            elapsed = now - started_at
            print(f"\n  观察时长: {elapsed} ({elapsed.total_seconds()/3600:.2f}h)")
            print(f"  目标时长: 24h (5% 阶段)")
            if elapsed < timedelta(hours=24):
                remaining = timedelta(hours=24) - elapsed
                print(f"  剩余时间: {remaining} ({remaining.total_seconds()/3600:.2f}h)")
            else:
                print(f"  ✅ 已达 24h 观察期")

        # 3. 检查 fallback_rate (从 model_engine metrics snapshot)
        try:
            from app.core.model_engine import model_engine

            snapshot = model_engine.get_metrics_snapshot()
            monitoring = snapshot.get("monitoring", {})
            fallback_ratio = monitoring.get("fallback_ratio", 0)
            total_preds = monitoring.get("total_predictions", 0)
            fallback_count = monitoring.get("fallback_count", 0)
            print(f"\n指标 1: fallback_rate")
            print(f"  fallback_ratio={fallback_ratio:.4f} ({fallback_ratio*100:.2f}%)")
            print(f"  total_predictions={total_preds} fallback_count={fallback_count}")
            print(f"  阈值: < 5%")
            print(f"  状态: {'✅ PASS' if fallback_ratio < 0.05 else '❌ FAIL'}")
        except Exception as exc:
            print(f"\n指标 1: fallback_rate — ERROR: {exc}")

        # 4. 检查 drift_alerts (过去 1 小时)
        try:
            one_hour_ago = now - timedelta(hours=1)
            r = await db.execute(
                text(
                    "SELECT COUNT(*) FROM drift_alerts WHERE created_at >= :t"
                ),
                {"t": one_hour_ago},
            )
            drift_count = r.scalar() or 0
            print(f"\n指标 2: drift_alerts (过去 1h)")
            print(f"  count={drift_count}")
            print(f"  阈值: < 10/hour")
            print(f"  状态: {'✅ PASS' if drift_count < 10 else '❌ FAIL'}")
        except Exception as exc:
            print(f"\n指标 2: drift_alerts — ERROR: {exc}")

        # 5. 检查 avg_latency (从 model_inference 指标)
        try:
            from app.core.metrics import model_inference_duration_seconds

            entries = model_inference_duration_seconds.collect()
            total_sum = 0.0
            total_count = 0.0
            for labels, entry in entries:
                if isinstance(entry, dict):
                    total_sum += entry.get("_sum", 0)
                    total_count += entry.get("_count", 0)
            avg_latency = total_sum / total_count if total_count > 0 else 0
            print(f"\n指标 3: avg_latency")
            print(f"  total_sum={total_sum:.4f}s total_count={total_count}")
            print(f"  avg_latency={avg_latency*1000:.2f}ms")
            print(f"  阈值: < 500ms")
            print(f"  状态: {'✅ PASS' if avg_latency < 0.5 else '❌ FAIL'}")
        except Exception as exc:
            print(f"\n指标 3: avg_latency — ERROR: {exc}")

        # 6. 检查 error_rate (从 model_inference_total)
        try:
            from app.core.metrics import model_inference_total

            entries = model_inference_total.collect()
            success_count = 0
            error_count = 0
            for labels, value in entries:
                status_label = labels.get("status", "")
                if status_label == "success":
                    success_count += value
                else:
                    error_count += value
            total = success_count + error_count
            error_rate = error_count / total if total > 0 else 0
            print(f"\n指标 4: error_rate")
            print(f"  success={success_count} error={error_count} total={total}")
            print(f"  error_rate={error_rate*100:.2f}%")
            print(f"  阈值: < 10%")
            print(f"  状态: {'✅ PASS' if error_rate < 0.1 else '❌ FAIL'}")
        except Exception as exc:
            print(f"\n指标 4: error_rate — ERROR: {exc}")

    print("\n" + "=" * 60)
    return 0


if __name__ == "__main__":
    sys.exit(asyncio.run(main()))
