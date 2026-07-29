"""通过 HTTP 调用 /api/v1/predict/fusion 触发金丝雀流量.

直接生成 admin access token, 通过 HTTP 调用 predict_fusion 端点,
让推理在 uvicorn worker 进程中执行, 验证 Prometheus 指标和 MonitoringLog 是否正确更新.

使用方式:
    docker cp e:\\code\\bysj\\backend\\scripts\\trigger_canary_http.py dws-backend:/tmp/trigger_canary_http.py
    docker exec dws-backend python /tmp/trigger_canary_http.py
    docker exec dws-backend python /tmp/trigger_canary_http.py --requests 20
"""
from __future__ import annotations

import argparse
import asyncio
import json
import os
import sys
import time
import urllib.request

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.core.security import create_access_token
from app.models.user import User


async def generate_admin_token() -> tuple[str, int]:
    """生成 admin 用户的 access token."""
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.role == "admin"))
        admin = result.scalar_one_or_none()
        if not admin:
            raise RuntimeError("未找到 admin 用户")
        # 创建 access token
        token_data = {"sub": str(admin.id), "role": admin.role}
        token = create_access_token(token_data)
        return token, admin.id


def call_predict_fusion(
    token: str,
    user_id: int,
    request_idx: int,
) -> dict:
    """通过 HTTP 调用 /api/v1/predict/fusion."""
    # 构造多样化的输入
    features = {
        "phq9_score": float((request_idx % 27) + 1),
        "gad7_score": float((request_idx % 21) + 1),
        "age": float(20 + (request_idx % 40)),
        "sleep_hours": float(4 + (request_idx % 5)),
    }
    text_options = [
        "最近感觉很糟糕, 总是失眠, 心情低落",
        "工作压力很大, 经常焦虑, 睡眠不好",
        "最近心情不错, 生活比较规律",
        "感到疲惫, 注意力难以集中",
        "和朋友聚会后心情有所好转",
    ]
    text = text_options[request_idx % len(text_options)]
    physiological = {
        "heart_rate": float(60 + (request_idx % 30)),
        "hrv": float(20 + (request_idx % 40)),
        "sleep_duration": float(4 + (request_idx % 5)),
    }

    body = json.dumps({
        "features": features,
        "text": text,
        "physiological": physiological,
    }).encode()

    req = urllib.request.Request(
        "http://localhost:8000/api/v1/model/predict/fusion",
        data=body,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        },
        method="POST",
    )

    start = time.perf_counter()
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        elapsed_ms = (time.perf_counter() - start) * 1000
        body = resp.read().decode()
        data = json.loads(body)
        # 解包 ApiResponse 包装
        result = data.get("data", data) if isinstance(data, dict) else data
        return {
            "request_idx": request_idx,
            "status": resp.status,
            "latency_ms": round(elapsed_ms, 2),
            "canary_routed": result.get("canary_routed", False) if isinstance(result, dict) else False,
            "canary_version": result.get("canary_version") if isinstance(result, dict) else None,
            "model_version": result.get("model_version") if isinstance(result, dict) else None,
            "risk_level": result.get("risk_level") if isinstance(result, dict) else None,
            "risk_score": result.get("risk_score") if isinstance(result, dict) else None,
            "error": None,
        }
    except urllib.error.HTTPError as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        body = e.read().decode()
        return {
            "request_idx": request_idx,
            "status": e.code,
            "latency_ms": round(elapsed_ms, 2),
            "canary_routed": False,
            "error": f"HTTP {e.code}: {body[:200]}",
        }
    except Exception as e:
        elapsed_ms = (time.perf_counter() - start) * 1000
        return {
            "request_idx": request_idx,
            "status": 0,
            "latency_ms": round(elapsed_ms, 2),
            "canary_routed": False,
            "error": f"{type(e).__name__}: {e}",
        }


async def check_monitoring_logs(user_id: int) -> dict:
    """检查 MonitoringLog 表是否有新写入."""
    from sqlalchemy import text
    async with AsyncSessionLocal() as db:
        # 最近 5 分钟内的所有事件
        result = await db.execute(
            text(
                "SELECT event_type, model_version, COUNT(*) as cnt, "
                "MAX(created_at) as last_event "
                "FROM monitoring_logs "
                "WHERE created_at >= NOW() - INTERVAL '5 minutes' "
                "GROUP BY event_type, model_version "
                "ORDER BY last_event DESC"
            )
        )
        rows = result.all()
        return {
            "recent_5min": [
                {
                    "event_type": r.event_type,
                    "model_version": r.model_version,
                    "count": r.cnt,
                    "last_event": str(r.last_event),
                }
                for r in rows
            ]
        }


async def check_prometheus_metrics() -> dict:
    """检查 /api/v1/metrics 端点的 model_inference_total 指标."""
    token = os.environ.get("METRICS_ACCESS_TOKEN", "")
    req = urllib.request.Request(
        "http://localhost:8000/api/v1/metrics",
        headers={"Authorization": f"Bearer {token}"},
    )
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        content = resp.read().decode()
        lines = content.split("\n")
        # 找 model_inference_total 的实际数据行 (非 HELP/TYPE)
        data_lines = [
            l for l in lines
            if l.startswith("model_inference_total") and "{" in l
        ]
        return {
            "data_lines": data_lines[:20],
            "count": len(data_lines),
        }
    except Exception as e:
        return {"error": f"{type(e).__name__}: {e}"}


async def run_trigger(num_requests: int) -> int:
    """通过 HTTP 触发金丝雀流量."""
    print("=" * 70)
    print(f"HTTP 金丝雀流量触发 @ {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    print("=" * 70)

    # 1. 生成 admin token
    print("\n[1] 生成 admin access token...")
    token, admin_id = await generate_admin_token()
    print(f"  admin user_id: {admin_id}")
    print(f"  token: {token[:30]}...{token[-10:]}")

    # 2. 触发前的状态
    print("\n[2] 触发前状态检查...")
    before_logs = await check_monitoring_logs(admin_id)
    print(f"  MonitoringLog (最近 5min): {before_logs['recent_5min']}")
    before_metrics = await check_prometheus_metrics()
    print(f"  Prometheus model_inference_total: {before_metrics.get('count', 0)} 条数据行")

    # 3. 通过 HTTP 触发推理
    print(f"\n[3] 通过 HTTP 触发 {num_requests} 次推理 (user_id={admin_id}, hash=19 < 25% → CANARY)...")
    results: list[dict] = []
    canary_count = 0
    fail_count = 0

    for i in range(num_requests):
        r = call_predict_fusion(token, admin_id, i)
        results.append(r)
        if r.get("canary_routed"):
            canary_count += 1
            marker = "CANARY"
        elif r.get("error"):
            fail_count += 1
            marker = "FAIL"
        else:
            marker = "STABLE"
        print(f"  [{i+1}/{num_requests}] {marker} status={r['status']} "
              f"latency={r['latency_ms']}ms risk={r.get('risk_level')}")
        if r.get("error"):
            print(f"           error: {r['error']}")
        await asyncio.sleep(0.3)

    # 4. 汇总
    print(f"\n[4] 触发汇总")
    print(f"  总请求数: {num_requests}")
    print(f"  成功: {len(results) - fail_count}")
    print(f"  失败: {fail_count}")
    print(f"  CANARY 路由: {canary_count}")
    if results:
        latencies = [r["latency_ms"] for r in results]
        avg_lat = sum(latencies) / len(latencies)
        max_lat = max(latencies)
        min_lat = min(latencies)
        print(f"  延迟: avg={avg_lat:.2f}ms min={min_lat:.2f}ms max={max_lat:.2f}ms")

    # 5. 触发后的状态
    print(f"\n[5] 等待 3s 后检查指标更新...")
    await asyncio.sleep(3)

    after_logs = await check_monitoring_logs(admin_id)
    print(f"\n  MonitoringLog (最近 5min): {after_logs['recent_5min']}")
    new_logs = [l for l in after_logs["recent_5min"] if l not in before_logs["recent_5min"]]
    if new_logs:
        print(f"  ✅ 新增事件: {new_logs}")
    else:
        print(f"  ⚠️ 无新增 MonitoringLog 事件 (predict_fusion 不写 MonitoringLog)")

    after_metrics = await check_prometheus_metrics()
    print(f"\n  Prometheus model_inference_total: {after_metrics.get('count', 0)} 条数据行")
    if after_metrics.get("data_lines"):
        for line in after_metrics["data_lines"][:10]:
            print(f"    {line}")
    if after_metrics.get("count", 0) > before_metrics.get("count", 0):
        print(f"  ✅ Prometheus 指标已更新 (before={before_metrics.get('count', 0)} → after={after_metrics.get('count', 0)})")
    else:
        print(f"  ⚠️ Prometheus 指标未更新 (可能是多进程 uvicorn 指标隔离)")

    print("\n" + "=" * 70)
    if canary_count > 0:
        print(f"总结: 成功通过 HTTP 触发 {canary_count} 次金丝雀推理")
        return 0
    else:
        print(f"总结: 未触发金丝雀推理, 需排查")
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(description="通过 HTTP 触发金丝雀流量")
    parser.add_argument(
        "--requests", type=int, default=10,
        help="触发请求数 (默认 10)"
    )
    args = parser.parse_args()

    exit_code = asyncio.run(run_trigger(args.requests))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
