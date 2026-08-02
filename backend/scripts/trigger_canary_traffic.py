#!/usr/bin/env python
"""主动触发金丝雀流量验证脚本.

通过直接调用 ModelPredictService.predict_fusion, 传入会路由到金丝雀的 user_id,
生成 m4_stacking_v3 推理事件, 用于验证金丝雀健康指标.

前置条件:
- 存在运行中的金丝雀 (自动查找最新一条 RUNNING, 流量 >= 1%)
- 至少有一个 user_id 的 hash < traffic_percent (会被路由到金丝雀)

使用方式:
    docker cp e:\\code\\bysj\\backend\\scripts\\trigger_canary_traffic.py dws-backend:/tmp/trigger_canary_traffic.py
    docker exec dws-backend python /tmp/trigger_canary_traffic.py
    docker exec dws-backend python /tmp/trigger_canary_traffic.py --requests 20
"""
from __future__ import annotations

import argparse
import asyncio
import hashlib
import sys
import time
from dataclasses import dataclass

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.models.user import User
from app.services.canary_manager import canary_manager
from app.services.model_predict_service import ModelPredictService


@dataclass
class CanaryUserInfo:
    """会路由到金丝雀的用户信息."""

    user_id: int
    username: str
    hash_value: int


def find_canary_users(users: list[User], traffic_percent: int) -> list[CanaryUserInfo]:
    """找出会路由到金丝雀的用户 (hash < traffic_percent)."""
    canary_users: list[CanaryUserInfo] = []
    for u in users:
        digest = hashlib.sha256(str(u.id).encode()).hexdigest()[:8]
        h = int(digest, 16) % 100
        if h < traffic_percent:
            canary_users.append(
                CanaryUserInfo(user_id=u.id, username=u.username, hash_value=h)
            )
    return canary_users


def find_canary_user_id_by_scan(
    start: int, end: int, traffic_percent: int
) -> list[int]:
    """扫描数字 ID 范围, 找出会路由到金丝雀的 ID (用于无真实用户时)."""
    result: list[int] = []
    for uid in range(start, end):
        digest = hashlib.sha256(str(uid).encode()).hexdigest()[:8]
        h = int(digest, 16) % 100
        if h < traffic_percent:
            result.append(uid)
    return result


async def get_active_canary_traffic_percent() -> int | None:
    """获取当前活跃金丝雀的流量百分比."""
    async with AsyncSessionLocal() as db:
        canary = await canary_manager.get_active_canary(db)
        return canary.traffic_percent if canary else None


async def trigger_single_inference(
    service: ModelPredictService,
    user_id: int,
    request_idx: int,
) -> dict:
    """触发单次融合推理 (会路由到金丝雀)."""
    # 构造多样化的输入, 避免缓存命中 (虽然金丝雀不走缓存)
    # 简化的真实输入特征 (基于 PHQ-9 / GAD-7 量表范围)
    features = {
        "phq9_score": float((request_idx % 27) + 1),  # 1-27
        "gad7_score": float((request_idx % 21) + 1),  # 1-21
        "age": float(20 + (request_idx % 40)),  # 20-59
        "sleep_hours": float(4 + (request_idx % 5)),  # 4-8
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
        "heart_rate": float(60 + (request_idx % 30)),  # 60-89
        "hrv": float(20 + (request_idx % 40)),  # 20-59
        "sleep_duration": float(4 + (request_idx % 5)),  # 4-8
    }

    start = time.perf_counter()
    result = await service.predict_fusion(
        features=features,
        text=text,
        physiological=physiological,
        user_id=user_id,
    )
    latency_ms = (time.perf_counter() - start) * 1000

    return {
        "request_idx": request_idx,
        "user_id": user_id,
        "latency_ms": round(latency_ms, 2),
        "canary_routed": result.get("canary_routed", False),
        "canary_version": result.get("canary_version"),
        "model_version": result.get("model_version"),
        "risk_level": result.get("risk_level"),
        "risk_score": result.get("risk_score"),
    }


async def run_trigger(num_requests: int) -> int:
    """触发金丝雀流量, 返回退出码 (0=成功, 1=部分失败, 2=无法触发)."""
    print("=" * 70)
    print(f"金丝雀流量触发 @ {time.strftime('%Y-%m-%d %H:%M:%S UTC', time.gmtime())}")
    print("=" * 70)

    # 1. 检查当前金丝雀状态
    print("\n[1] 检查金丝雀状态...")
    traffic_percent = await get_active_canary_traffic_percent()
    if traffic_percent is None:
        print("  [!] 无活跃金丝雀, 退出")
        return 2
    print(f"  当前金丝雀流量: {traffic_percent}%")

    # 2. 找出会路由到金丝雀的用户
    print("\n[2] 查找会路由到金丝雀的用户...")
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).order_by(User.id))
        all_users = list(result.scalars().all())

    canary_users = find_canary_users(all_users, traffic_percent)
    if canary_users:
        print(f"  找到 {len(canary_users)} 个真实金丝雀用户:")
        for cu in canary_users[:5]:
            print(f"    - user_id={cu.user_id} username={cu.username} hash={cu.hash_value}")
        target_user_id = canary_users[0].user_id
    else:
        # 无真实用户落到金丝雀范围, 扫描数字 ID 找一个
        print(f"  数据库 {len(all_users)} 个用户均未路由到金丝雀")
        print(f"  扫描 ID 1-1000 找出会路由到金丝雀的虚拟 ID...")
        virtual_ids = find_canary_user_id_by_scan(1, 1000, traffic_percent)
        if not virtual_ids:
            print("  [!] 未找到会路由到金丝雀的 ID, 退出")
            return 2
        target_user_id = virtual_ids[0]
        print(f"  使用虚拟 ID: {target_user_id} (hash 计算 < {traffic_percent}%)")
        print(f"  共 {len(virtual_ids)} 个 ID 可路由到金丝雀, 前 5: {virtual_ids[:5]}")
        # 显示 admin 用户的 hash
        for u in all_users:
            digest = hashlib.sha256(str(u.id).encode()).hexdigest()[:8]
            h = int(digest, 16) % 100
            print(f"  - user_id={u.id} ({u.username}) hash={h} "
                  f"({'CANARY' if h < traffic_percent else 'STABLE'})")

    # 3. 触发推理
    print(f"\n[3] 触发 {num_requests} 次金丝雀推理 (user_id={target_user_id})...")
    service = ModelPredictService()
    results: list[dict] = []
    canary_count = 0
    stable_count = 0
    fail_count = 0

    for i in range(num_requests):
        try:
            r = await trigger_single_inference(service, target_user_id, i)
            results.append(r)
            if r["canary_routed"]:
                canary_count += 1
                marker = "CANARY"
            else:
                stable_count += 1
                marker = "STABLE"
            print(f"  [{i+1}/{num_requests}] {marker} latency={r['latency_ms']}ms "
                  f"risk_level={r['risk_level']} score={r['risk_score']}")
        except Exception as exc:
            fail_count += 1
            print(f"  [{i+1}/{num_requests}] FAIL: {type(exc).__name__}: {exc}")

        # 短暂间隔, 避免压垮服务
        await asyncio.sleep(0.2)

    # 4. 汇总
    print(f"\n[4] 触发汇总")
    print(f"  总请求数: {num_requests}")
    print(f"  成功: {len(results)}")
    print(f"  失败: {fail_count}")
    print(f"  CANARY 路由: {canary_count}")
    print(f"  STABLE 路由: {stable_count}")
    if results:
        latencies = [r["latency_ms"] for r in results]
        avg_lat = sum(latencies) / len(latencies)
        max_lat = max(latencies)
        min_lat = min(latencies)
        print(f"  延迟: avg={avg_lat:.2f}ms min={min_lat:.2f}ms max={max_lat:.2f}ms")

    # 5. 验证指标已写入
    print(f"\n[5] 等待 5s 让 metrics flush...")
    await asyncio.sleep(5)
    print(f"  完成. 请运行 check_canary_health.py 查看更新后的 metrics.")

    print("\n" + "=" * 70)
    if canary_count > 0:
        print(f"总结: 成功触发 {canary_count} 次金丝雀推理, metrics 已生成")
        return 0
    elif fail_count > 0:
        print(f"总结: 全部失败, 需排查")
        return 1
    else:
        print(f"总结: 推理成功但未路由到金丝雀, 检查 user_id hash")
        return 1


def main() -> None:
    parser = argparse.ArgumentParser(description="主动触发金丝雀流量")
    parser.add_argument(
        "--requests", type=int, default=10,
        help="触发请求数 (默认 10)"
    )
    args = parser.parse_args()

    exit_code = asyncio.run(run_trigger(args.requests))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()
