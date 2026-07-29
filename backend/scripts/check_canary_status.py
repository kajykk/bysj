"""Quick canary status check via raw SQL (avoiding ORM column mismatch)."""
import sys
import asyncio
sys.path.insert(0, ".")

from datetime import datetime, timezone
from sqlalchemy import text

from app.core.database import AsyncSessionLocal


def _fmt_pct(v: float) -> str:
    return f"{v * 100:.2f}%"


def _fmt_ms(v: float) -> str:
    return f"{v:.1f}ms"


def _hr(char: str = "=", n: int = 70) -> str:
    return char * n


async def main():
    print(_hr())
    print(f"金丝雀状态检查 @ {datetime.now(timezone.utc).isoformat()}")
    print(_hr())

    async with AsyncSessionLocal() as db:
        # 1. 全部金丝雀
        sql = text(
            "SELECT id, version, traffic_percent, status, auto_rollback_thresholds, "
            "triggered_by, started_at, ended_at, rollback_reason, created_at "
            "FROM canary_records ORDER BY started_at DESC LIMIT 5"
        )
        rows = (await db.execute(sql)).all()
        if not rows:
            print("\n[!] 数据库无金丝雀记录")
            return

        print(f"\n[1] 最近 5 只金丝雀（共 {len(rows)}）")
        for r in rows:
            hours_sql = text(
                "SELECT EXTRACT(EPOCH FROM (NOW() - started_at)) / 3600.0 "
                "FROM canary_records WHERE id = :cid"
            )
            hours = float((await db.execute(hours_sql, {"cid": r.id})).scalar() or 0.0)
            print(f"  - id={r.id} version={r.version}")
            print(f"    status={r.status} traffic={r.traffic_percent}%")
            print(f"    started_at={r.started_at} (运行 {hours:.2f}h)")
            print(f"    thresholds: {r.auto_rollback_thresholds}")
            if r.rollback_reason:
                print(f"    [!] rollback_reason: {r.rollback_reason}")
            if r.ended_at:
                print(f"    ended_at={r.ended_at}")
            print()

        # 2. running 的金丝雀
        running_sql = text(
            "SELECT id, version, traffic_percent, started_at, auto_rollback_thresholds "
            "FROM canary_records WHERE status = 'RUNNING' ORDER BY started_at DESC LIMIT 1"
        )
        running = (await db.execute(running_sql)).first()
        if not running:
            print("[!] 当前无 RUNNING 金丝雀")
            return

        cid = running.id
        version = running.version
        print(f"\n[2] 当前 RUNNING 金丝雀")
        print(f"  id={cid} version={version} traffic={running.traffic_percent}%")

        # 3. 推理事件统计（最近 1h）
        inf_sql = text(
            "SELECT "
            "  COUNT(*) FILTER (WHERE event_type = 'INFERENCE') AS inf_total, "
            "  COUNT(*) FILTER (WHERE event_type = 'FALLBACK') AS fb_total, "
            "  AVG(latency_ms) FILTER (WHERE event_type = 'INFERENCE') AS avg_lat "
            "FROM monitoring_logs "
            "WHERE created_at >= NOW() - INTERVAL '1 hour' "
            "AND model_version = :version"
        )
        inf_row = (await db.execute(inf_sql, {"version": version})).one()
        inf_total = inf_row.inf_total or 0
        fb_total = inf_row.fb_total or 0
        avg_lat = inf_row.avg_lat or 0
        total = inf_total + fb_total
        fb_rate = (fb_total / total) if total > 0 else 0
        err_rate = (fb_total / total) if total > 0 else 0
        print(f"\n[3] 最近 1h 推理事件 (model_version={version})")
        print(f"  inference_count = {inf_total}")
        print(f"  fallback_count  = {fb_total}")
        print(f"  avg_latency_ms  = {avg_lat:.1f}ms")
        print(f"  fallback_rate   = {_fmt_pct(fb_rate)} (阈值 <5.00%)")
        print(f"  error_rate      = {_fmt_pct(err_rate)} (阈值 <10.00%)")

        # 4. 漂移告警（最近 1h）
        drift_sql = text(
            "SELECT COUNT(*) FROM drift_alerts "
            "WHERE resolved_at IS NULL "
            "AND created_at >= NOW() - INTERVAL '1 hour' "
            "AND model_version = :version"
        )
        drift_1h = (await db.execute(drift_sql, {"version": version})).scalar() or 0
        print(f"\n[4] 最近 1h 漂移告警（未解决, version={version}）")
        print(f"  drift_alerts_per_hour = {drift_1h} (阈值 <10)")

        # 5. DriftAlert 按模态
        mod_sql = text(
            "SELECT model_version, severity, COUNT(*) as cnt "
            "FROM drift_alerts GROUP BY model_version, severity"
        )
        mod_rows = (await db.execute(mod_sql)).all()
        print(f"\n[5] DriftAlert 全部按模态分组")
        if not mod_rows:
            print("  (无记录)")
        for r in mod_rows:
            print(f"  - {r.model_version}/{r.severity}: {r.cnt}")

        # 6. monitoring_logs 事件分布
        ev_sql = text(
            "SELECT event_type, COUNT(*) as cnt, MAX(created_at) as last_run "
            "FROM monitoring_logs "
            "WHERE created_at >= NOW() - INTERVAL '2 hours' "
            "GROUP BY event_type ORDER BY cnt DESC LIMIT 10"
        )
        ev_rows = (await db.execute(ev_sql)).all()
        print(f"\n[6] 最近 2h monitoring_logs 事件分布")
        if not ev_rows:
            print("  (无事件, celery_beat 可能未正常运行)")
        for r in ev_rows:
            print(f"  - {r.event_type}: count={r.cnt} last={r.last_run}")

        # 总结
        thresholds = running.auto_rollback_thresholds or {}
        fb_thresh = thresholds.get("max_fallback_rate", 0.05)
        drift_thresh = thresholds.get("max_drift_alerts_per_hour", 10)
        lat_thresh = thresholds.get("max_avg_latency_ms", 500)

        all_ok = (
            fb_rate < fb_thresh
            and drift_1h < drift_thresh
            and avg_lat < lat_thresh
            and err_rate < 0.10
        )

        print(f"\n{_hr('-')}")
        if all_ok:
            print("✅ 总结: 全部健康, 金丝雀可继续观察或推进下一阶段")
        else:
            print("⚠️ 总结: 存在告警/回滚风险, 需立即处理")
        print(_hr('-'))


if __name__ == "__main__":
    asyncio.run(main())
