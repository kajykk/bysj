#!/usr/bin/env python
"""金丝雀监控值守脚本: 检查所有 running 金丝雀的健康指标与回滚触发条件.

检查项:
  1. 金丝雀基础信息 (id/version/status/traffic_percent/运行时长)
  2. 四个回滚触发条件:
     - fallback_rate < 5%
     - drift_alerts_per_hour < 10
     - avg_latency_ms < 500ms
     - error_rate < 10% (MonitoringLog 中 ERROR 级别占比)
  3. DriftAlert 持久化情况 (按 modality 分组统计)
  4. auto_rollback_service.check_all_canaries() 实时输出
  5. celery_beat 双任务最近调度时间

使用方式:
    docker exec dws-backend python /app/scripts/check_canary_health.py
    docker exec dws-backend python /app/scripts/check_canary_health.py --canary-id 1
"""
from __future__ import annotations

import argparse
import asyncio
import sys
from datetime import datetime, timezone

from sqlalchemy import select, text

from app.core.database import AsyncSessionLocal
from app.models.monitoring import CanaryRecord, CanaryStatus
from app.services.auto_rollback_service import auto_rollback_service


def _fmt_pct(v: float) -> str:
    return f"{v * 100:.2f}%"


def _fmt_ms(v: float) -> str:
    return f"{v:.1f}ms"


def _hr(char: str = "=", n: int = 70) -> str:
    return char * n


async def check_canary_record(db_session, canary_id: int | None) -> list[CanaryRecord]:
    """返回目标金丝雀列表 (canary_id 为 None 时返回所有 running)."""
    if canary_id is not None:
        result = await db_session.execute(
            select(CanaryRecord).where(CanaryRecord.id == canary_id)
        )
        canaries = result.scalars().all()
    else:
        result = await db_session.execute(
            select(CanaryRecord)
            .where(CanaryRecord.status == CanaryStatus.RUNNING)
            .order_by(CanaryRecord.started_at.desc())
        )
        canaries = result.scalars().all()
    return list(canaries)


async def check_canary_health(
    db_session, canary: CanaryRecord
) -> dict:
    """检查单只金丝雀的健康指标 (复用 auto_rollback_service 的检查逻辑)."""
    # 调用 auto_rollback_service.check_canary_health (在 savepoint 中, 不触发回滚)
    async with db_session.begin_nested():
        result = await auto_rollback_service.check_canary_health(
            db_session, canary.id
        )
    return {
        "should_rollback": result.should_rollback,
        "reason": result.reason,
        "metrics": result.metrics,
    }


async def check_drift_alerts(db_session, canary_version: str) -> dict:
    """检查 DriftAlert 持久化情况 (按 modality 分组).

    model_version 字段存金丝雀版本, modality 归属在 details->>'modality'.
    """
    # 按模态分组统计 (modality 从 details JSON 中取)
    stmt = text(
        "SELECT COALESCE(details->>'modality', 'unknown') AS modality, "
        "       severity, COUNT(*) AS cnt "
        "FROM drift_alerts "
        "GROUP BY COALESCE(details->>'modality', 'unknown'), severity "
        "ORDER BY modality, severity"
    )
    result = await db_session.execute(stmt)
    rows = result.all()

    by_modality: dict[str, dict[str, int]] = {}
    for row in rows:
        mod = row.model_version or "unknown"
        sev = row.severity or "unknown"
        by_modality.setdefault(mod, {})
        by_modality[mod][sev] = row.cnt

    # 最近 1h 未解决的漂移告警数 (按金丝雀版本匹配)
    one_hour_ago_sql = text(
        "SELECT COUNT(*) FROM drift_alerts "
        "WHERE resolved_at IS NULL "
        "AND created_at >= NOW() - INTERVAL '1 hour' "
        "AND model_version = :version"
    )
    recent_result = await db_session.execute(
        one_hour_ago_sql, {"version": canary_version}
    )
    recent_unresolved = recent_result.scalar() or 0

    # 最近 24h 漂移告警总数
    last_24h_sql = text(
        "SELECT COUNT(*) FROM drift_alerts "
        "WHERE created_at >= NOW() - INTERVAL '24 hours'"
    )
    last_24h_result = await db_session.execute(last_24h_sql)
    last_24h = last_24h_result.scalar() or 0

    return {
        "by_modality": by_modality,
        "recent_unresolved_1h": recent_unresolved,
        "total_last_24h": last_24h,
    }


async def check_celery_beat_schedule(db_session) -> dict:
    """检查 celery_beat 双任务最近调度时间."""
    schedule: dict[str, str] = {}

    # 从 monitoring_logs 中查找最近的 canary-auto-rollback-check / drift-monitoring-check
    # 这些任务通过 observability 记录, 失败/成功都会写入日志
    sql = text(
        "SELECT event_type, MAX(created_at) as last_run, COUNT(*) as cnt "
        "FROM monitoring_logs "
        "WHERE created_at >= NOW() - INTERVAL '2 hours' "
        "GROUP BY event_type "
        "ORDER BY last_run DESC"
    )
    result = await db_session.execute(sql)
    rows = result.all()
    schedule["recent_events_2h"] = [
        {"event_type": r.event_type, "last_run": str(r.last_run), "count": r.cnt}
        for r in rows
    ]

    return schedule


async def check_error_rate(db_session, canary_version: str) -> dict:
    """检查错误率 (MonitoringLog 中 ERROR 级别 / 总推理数)."""
    one_hour_ago_sql = text(
        "SELECT "
        "  COUNT(*) FILTER (WHERE event_type = 'INFERENCE') AS inference_total, "
        "  COUNT(*) FILTER (WHERE event_type = 'INFERENCE' AND latency_ms IS NULL) AS inference_with_error, "
        "  COUNT(*) FILTER (WHERE event_type = 'FALLBACK') AS fallback_total "
        "FROM monitoring_logs "
        "WHERE created_at >= NOW() - INTERVAL '1 hour' "
        "AND model_version = :version"
    )
    result = await db_session.execute(one_hour_ago_sql, {"version": canary_version})
    row = result.one()

    inference_total = row.inference_total or 0
    fallback_total = row.fallback_total or 0
    # error_rate 简化定义: fallback / (inference + fallback)
    total = inference_total + fallback_total
    error_rate = (fallback_total / total) if total > 0 else 0.0

    return {
        "inference_total_1h": inference_total,
        "fallback_total_1h": fallback_total,
        "error_rate": error_rate,
        "error_rate_ok": error_rate < 0.10,
    }


async def print_canary_report(canary_id: int | None) -> int:
    """打印金丝雀健康报告, 返回退出码 (0=健康, 1=有警告, 2=有回滚风险)."""
    print(_hr())
    print(f"金丝雀健康报告 @ {datetime.now(timezone.utc).isoformat()}")
    print(_hr())

    exit_code = 0

    async with AsyncSessionLocal() as db_session:
        # 1. 金丝雀基础信息
        canaries = await check_canary_record(db_session, canary_id)
        if not canaries:
            print(f"\n[!] 未找到金丝雀 (canary_id={canary_id})")
            return 2

        print(f"\n[1] 金丝雀基础信息 (共 {len(canaries)} 只)")
        for c in canaries:
            # 用 DB NOW() 计算运行时长, 避免时区不一致
            hours_sql = text(
                "SELECT EXTRACT(EPOCH FROM (NOW() - started_at)) / 3600.0 "
                "FROM canary_records WHERE id = :cid"
            )
            hours_result = await db_session.execute(hours_sql, {"cid": c.id})
            hours_running = float(hours_result.scalar() or 0.0)

            print(f"  - id={c.id} version={c.version}")
            print(f"    status={c.status} traffic={c.traffic_percent}%")
            print(f"    started_at={c.started_at} (运行 {hours_running:.2f}h)")
            thresholds = c.auto_rollback_thresholds or {}
            print(f"    thresholds: {thresholds}")
            if c.rollback_reason:
                print(f"    [!] rollback_reason: {c.rollback_reason}")
                exit_code = max(exit_code, 2)

        # 2. 每只金丝雀的健康检查
        print(f"\n[2] auto_rollback_service 健康检查")
        all_results = await auto_rollback_service.check_all_canaries(db_session)
        if not all_results:
            print("  (无 running 金丝雀, check_all_canaries 返回空)")
        for r in all_results:
            print(f"  - canary_id={r.canary_id}")
            print(f"    should_rollback={r.should_rollback}")
            print(f"    reason: {r.reason}")
            print(f"    metrics: {r.metrics}")
            if r.should_rollback:
                exit_code = max(exit_code, 2)

        # 3. 四个回滚触发条件 (针对第一只金丝雀, 通常只有一只 running)
        target = canaries[0]
        print(f"\n[3] 四个回滚触发条件 (canary id={target.id}, version={target.version})")

        health = await check_canary_health(db_session, target)
        metrics = health["metrics"]
        thresholds = target.auto_rollback_thresholds or {}

        fb_rate = metrics.get("fallback_rate", 0.0)
        fb_thresh = thresholds.get("max_fallback_rate", 0.05)
        fb_ok = fb_rate < fb_thresh
        print(f"  [3.1] fallback_rate: {_fmt_pct(fb_rate)} (阈值 <{_fmt_pct(fb_thresh)}) "
              f"{'OK' if fb_ok else 'FAIL'}")
        print(f"        fallback_count={metrics.get('fallback_count', 0)} "
              f"inference_count={metrics.get('inference_count', 0)}")

        drift_1h = metrics.get("drift_alerts_per_hour", 0)
        drift_thresh = thresholds.get("max_drift_alerts_per_hour", 10)
        drift_ok = drift_1h < drift_thresh
        print(f"  [3.2] drift_alerts_per_hour: {drift_1h} (阈值 <{drift_thresh}) "
              f"{'OK' if drift_ok else 'FAIL'}")

        latency = metrics.get("avg_latency_ms", 0.0)
        latency_thresh = thresholds.get("max_avg_latency_ms", 500.0)
        latency_ok = latency < latency_thresh
        print(f"  [3.3] avg_latency_ms: {_fmt_ms(latency)} (阈值 <{_fmt_ms(latency_thresh)}) "
              f"{'OK' if latency_ok else 'FAIL'}")

        # 3.4 error_rate (独立检查, 不在 auto_rollback_service 中)
        err = await check_error_rate(db_session, target.version)
        print(f"  [3.4] error_rate: {_fmt_pct(err['error_rate'])} (阈值 <10.00%) "
              f"{'OK' if err['error_rate_ok'] else 'FAIL'}")
        print(f"        inference_total_1h={err['inference_total_1h']} "
              f"fallback_total_1h={err['fallback_total_1h']}")

        if not (fb_ok and drift_ok and latency_ok and err["error_rate_ok"]):
            exit_code = max(exit_code, 2)

        # 4. DriftAlert 持久化情况
        print(f"\n[4] DriftAlert 持久化情况")
        drift_info = await check_drift_alerts(db_session, target.version)
        print(f"  最近1h未解决(匹配 version={target.version}): "
              f"{drift_info['recent_unresolved_1h']}")
        print(f"  最近24h总数: {drift_info['total_last_24h']}")
        print(f"  按模态分组:")
        for mod, sev_counts in drift_info["by_modality"].items():
            total = sum(sev_counts.values())
            sev_str = ", ".join(f"{k}={v}" for k, v in sev_counts.items())
            print(f"    - {mod}: total={total} ({sev_str})")

        # 5. celery_beat 调度情况
        print(f"\n[5] 最近 2h monitoring_logs 事件分布")
        sched = await check_celery_beat_schedule(db_session)
        events = sched.get("recent_events_2h", [])
        if not events:
            print("  (无事件, celery_beat 可能未正常运行)")
            exit_code = max(exit_code, 1)
        else:
            for ev in events[:10]:
                print(f"  - {ev['event_type']}: count={ev['count']} last={ev['last_run']}")

    # 6. 总结
    print(f"\n{_hr('-')}")
    if exit_code == 0:
        print("总结: 全部健康, 金丝雀可继续观察或推进下一阶段")
    elif exit_code == 1:
        print("总结: 有警告, 需关注但未触发回滚")
    else:
        print("总结: 存在回滚风险或已回滚, 立即处理")
    print(_hr('-'))

    return exit_code


def main() -> None:
    parser = argparse.ArgumentParser(description="金丝雀监控值守脚本")
    parser.add_argument(
        "--canary-id", type=int, default=None, help="指定金丝雀 ID (默认检查所有 running)"
    )
    args = parser.parse_args()

    exit_code = asyncio.run(print_canary_report(args.canary_id))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
