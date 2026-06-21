"""v1.36 T3.1: 告警可观测性 - 端到端测试.

TC-INT-001:
- test_e2e_alert_to_channel_stats:
  触发告警 → webhook → notifier 写 OperationLog → channel-stats API 查到
- test_e2e_silence_to_am_sync:
  创建静默 → am_sync 写 OperationLog → am-sync API 查到
- test_e2e_lock_fallback_to_stats:
  锁降级 → flush 任务 → lock-stats API 查到

测试架构:
- 使用 conftest.py 的 db_session/client/as_role 真实 fixture
- mock 外部服务 (webhook/AM/Redis) 但写入真实 DB
- 验证 API 端点能查回到我们刚写入的数据
"""
from __future__ import annotations

import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from sqlalchemy import select

from app.models.admin import OperationLog
from app.monitoring import dedup_lock as dedup_lock_mod
from app.monitoring.dedup_lock import flush_lock_stats, reset_stats, try_acquire_lock
from app.monitoring.notifier import AlertPayload, CompositeNotifier


# ===== test_e2e_alert_to_channel_stats =====


async def test_e2e_alert_to_channel_stats(
    db_session, client, as_role
) -> None:
    """v1.36 T3.1: 触发告警 → webhook 通道发送 → OperationLog 写入 → channel-stats API 查到."""
    # 1. 设为 admin 角色, 调 API 时可鉴权通过
    as_role("admin", 3)

    # 2. 准备 payload
    payload = AlertPayload(
        rule="HighErrorRate",
        severity="P0",
        status="firing",
        message="5xx error rate exceeded 5%",
        labels={"service": "backend", "env": "prod"},
        fingerprint="fp-e2e-channel-1",
    )

    # 3. mock requests.post 让 webhook 通道发送成功
    with patch("app.monitoring.notifier.requests.post") as mock_post, \
         patch("app.monitoring.notifier.time.sleep"):  # 跳过指数退避
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp

        # 4. 用真实 db_session 触发发送, 这样会写入 OperationLog
        notifier = CompositeNotifier(
            notifiers=[
                # 仅启用 webhook, 避免 slack/dingtalk/email 请求真实网络
                _make_webhook_notifier("https://example.com/hook"),
            ]
        )
        results = await notifier.send(payload, db=db_session)
        await db_session.commit()

    # 5. 验证发送结果
    assert results["webhook"] is True

    # 6. 验证 DB 中存在 alert_channel_sent OperationLog
    log_stmt = select(OperationLog).where(
        OperationLog.action_type == "alert_channel_sent",
        OperationLog.target_type == "alert_channel",
    )
    logs = (await db_session.execute(log_stmt)).scalars().all()
    assert len(logs) == 1
    log = logs[0]
    detail = json.loads(log.detail)
    assert detail["channel"] == "webhook"
    assert detail["rule"] == "HighErrorRate"
    assert detail["severity"] == "P0"
    assert detail["fingerprint"] == "fp-e2e-channel-1"
    assert "duration_ms" in detail

    # 7. 调 channel-stats API 验证能查回
    resp = client.get("/api/v1/alerts/observability/channel-stats")
    assert resp.status_code == 200, f"channel-stats failed: {resp.text}"
    body = resp.json()
    assert "data" in body
    assert "webhook" in body["data"]["channels"]
    ch = body["data"]["channels"]["webhook"]
    assert ch["sent"] == 1
    assert ch["failed"] == 0
    assert ch["total"] == 1
    assert ch["success_rate"] == 1.0
    # 整体统计
    assert body["data"]["total_sent"] == 1
    assert body["data"]["overall_success_rate"] == 1.0


async def test_e2e_alert_channel_failure_to_channel_stats(
    db_session, client, as_role
) -> None:
    """v1.36 T3.1: webhook 失败 → alert_channel_failed → channel-stats success_rate < 1."""
    as_role("admin", 3)

    payload = AlertPayload(
        rule="HighLatency",
        severity="P1",
        status="firing",
        message="p99 latency > 1s",
        fingerprint="fp-e2e-channel-2",
    )

    # 使用一个会直接 raise 的 notifier, 绕过 WebhookNotifier 内部的 try/except
    # 让 CompositeNotifier._dispatch 的 except 捕获 error_msg
    notifier = CompositeNotifier(notifiers=[_RaisingWebhookNotifier()])
    results = await notifier.send(payload, db=db_session)
    await db_session.commit()

    assert results["webhook"] is False

    # 验证 DB 写入 alert_channel_failed
    log_stmt = select(OperationLog).where(
        OperationLog.action_type == "alert_channel_failed"
    )
    logs = (await db_session.execute(log_stmt)).scalars().all()
    assert len(logs) == 1
    detail = json.loads(logs[0].detail)
    assert "error" in detail
    assert "connection refused" in detail["error"]
    assert detail["channel"] == "webhook"
    assert detail["fingerprint"] == "fp-e2e-channel-2"

    # 调 API 验证
    resp = client.get("/api/v1/alerts/observability/channel-stats?channel=webhook")
    assert resp.status_code == 200
    body = resp.json()
    ch = body["data"]["channels"]["webhook"]
    assert ch["sent"] == 0
    assert ch["failed"] == 1
    assert ch["success_rate"] == 0.0


# ===== test_e2e_silence_to_am_sync =====


async def test_e2e_silence_to_am_sync(
    db_session, client, as_role
) -> None:
    """v1.36 T3.1: 推送静默到 AM → am_sync 写 OperationLog → am-sync API 查到."""
    from app.monitoring.am_sync import push_silence

    as_role("admin", 3)

    silence = {
        "matchers": [{"name": "alertname", "value": "DiskSpaceLow", "isRegex": False}],
        "startsAt": "2026-06-03T00:00:00Z",
        "endsAt": "2026-06-04T00:00:00Z",
        "createdBy": "admin",
        "comment": "E2E test silence",
    }

    # mock AM 端点, 返回 200 + silenceID
    with patch("app.monitoring.am_sync._get_am_url", return_value="http://am:9093"), \
         patch("app.monitoring.am_sync.requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_resp.json.return_value = {"silenceID": "am-uuid-e2e-1"}
        mock_post.return_value = mock_resp

        result = await push_silence(silence, db=db_session)
        await db_session.commit()

    # 验证 push 返回值
    assert result is not None
    assert result["silenceID"] == "am-uuid-e2e-1"

    # 验证 DB 写入 am_sync_success
    log_stmt = select(OperationLog).where(
        OperationLog.action_type == "am_sync_success",
        OperationLog.target_type == "alert_silence",
    )
    logs = (await db_session.execute(log_stmt)).scalars().all()
    assert len(logs) == 1
    log = logs[0]
    detail = json.loads(log.detail)
    assert detail["operation"] == "push_silence"
    assert detail["am_silence_id"] == "am-uuid-e2e-1"
    assert "duration_ms" in detail

    # 调 am-sync API 验证
    resp = client.get("/api/v1/alerts/observability/am-sync")
    assert resp.status_code == 200, f"am-sync failed: {resp.text}"
    body = resp.json()
    data = body["data"]
    assert data["total_success"] == 1
    assert data["total_failed"] == 0
    assert data["success_rate"] == 1.0
    # by_operation
    op_map = {op["operation"]: op for op in data["by_operation"]}
    assert "push_silence" in op_map
    assert op_map["push_silence"]["success"] == 1
    assert op_map["push_silence"]["failed"] == 0


async def test_e2e_am_sync_failure_to_am_sync_api(
    db_session, client, as_role
) -> None:
    """v1.36 T3.1: AM 推送失败 → am_sync_failed → am-sync API success_rate 下降."""
    from app.monitoring.am_sync import push_silence

    as_role("admin", 3)

    silence = {
        "matchers": [{"name": "alertname", "value": "X", "isRegex": False}],
        "startsAt": "2026-06-03T00:00:00Z",
        "endsAt": "2026-06-04T00:00:00Z",
        "createdBy": "admin",
        "comment": "fail test",
    }

    with patch("app.monitoring.am_sync._get_am_url", return_value="http://am:9093"), \
         patch("app.monitoring.am_sync.requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "am unavailable"
        mock_post.return_value = mock_resp

        result = await push_silence(silence, db=db_session)
        await db_session.commit()

    assert result is None  # 失败返回 None

    # 验证 DB 写入 am_sync_failed
    log_stmt = select(OperationLog).where(
        OperationLog.action_type == "am_sync_failed"
    )
    logs = (await db_session.execute(log_stmt)).scalars().all()
    assert len(logs) == 1
    detail = json.loads(logs[0].detail)
    assert detail["operation"] == "push_silence"
    assert "error" in detail
    assert "500" in detail["error"]

    # 调 API 验证 recent_failures 包含
    resp = client.get("/api/v1/alerts/observability/am-sync?operation=push_silence")
    assert resp.status_code == 200
    body = resp.json()
    data = body["data"]
    assert data["total_success"] == 0
    assert data["total_failed"] == 1
    assert data["success_rate"] == 0.0
    assert len(data["recent_failures"]) == 1
    rf = data["recent_failures"][0]
    assert rf["operation"] == "push_silence"
    assert "500" in rf["error"]


# ===== test_e2e_lock_fallback_to_stats =====


async def test_e2e_lock_fallback_to_stats(
    db_session, client, as_role
) -> None:
    """v1.36 T3.1: 锁降级 (无 redis) → flush 任务 → lock-stats API 查到."""
    as_role("admin", 3)

    # 重置内存统计
    reset_stats()

    # 1. 触发 3 次 fallback (无 redis_url)
    with patch("app.monitoring.dedup_lock._get_redis_url", return_value=None):
        for fp in ["fp-1", "fp-2", "fp-3"]:
            acquired = await try_acquire_lock(fp)
            assert acquired is True  # 降级: 允许发送

    # 2. 内存统计应有 3 次 fallback
    stats = dedup_lock_mod.get_stats()
    assert stats["fallback"] == 3

    # 3. 调用 flush_lock_stats 写入 OperationLog
    success = await flush_lock_stats(db_session)
    await db_session.commit()
    assert success is True

    # 4. 验证 DB 写入 dedup_lock_stats
    log_stmt = select(OperationLog).where(
        OperationLog.action_type == "dedup_lock_stats",
        OperationLog.target_type == "dedup_lock",
    )
    logs = (await db_session.execute(log_stmt)).scalars().all()
    assert len(logs) == 1
    log = logs[0]
    detail = json.loads(log.detail)
    assert detail["fallback"] == 3
    assert detail["acquired"] == 0
    assert detail["skipped"] == 0
    assert detail["errors"] == 0
    assert "instance_id" in detail

    # 5. 内存计数应清零 (flush 成功)
    stats_after = dedup_lock_mod.get_stats()
    assert stats_after["fallback"] == 0

    # 6. 调 lock-stats API 验证
    resp = client.get("/api/v1/alerts/observability/lock-stats")
    assert resp.status_code == 200, f"lock-stats failed: {resp.text}"
    body = resp.json()
    data = body["data"]
    # recent_flushes 包含我们刚写入的
    assert len(data["recent_flushes"]) == 1
    rf = data["recent_flushes"][0]
    assert rf["fallback"] == 3
    assert rf["acquired"] == 0
    # historical_recent 累计
    h = data["historical_recent"]
    assert h["recent_flush_count"] == 1
    assert h["total_fallback"] == 3
    assert h["total_acquired"] == 0
    assert h["fallback_rate"] == 1.0
    # last_flush_at 应有值
    assert data["last_flush_at"] is not None


async def test_e2e_lock_mixed_paths_to_stats(
    db_session, client, as_role
) -> None:
    """v1.36 T3.1: 锁混合路径 (acquired + skipped + fallback) → flush → lock-stats 全部反映."""
    as_role("admin", 3)
    reset_stats()

    # 1. 模拟 acquired 路径 (mock redis 成功 SET NX)
    with patch("app.monitoring.dedup_lock.aioredis") as mock_aioredis:
        mock_client = MagicMock()
        # 第一次 set 返回 True (acquired), 第二次返回 False (skipped)
        # 注意: set 是 async, 必须用 AsyncMock 才能 await
        mock_client.set = AsyncMock(side_effect=[True, False])
        mock_client.aclose = AsyncMock()
        mock_aioredis.from_url.return_value = mock_client

        a1 = await try_acquire_lock("fp-acquired", redis_url="redis://x:6379/0")
        a2 = await try_acquire_lock("fp-skipped", redis_url="redis://x:6379/0")
        assert a1 is True
        assert a2 is False

    # 2. 模拟 fallback 路径
    with patch("app.monitoring.dedup_lock._get_redis_url", return_value=None):
        a3 = await try_acquire_lock("fp-fallback")
        assert a3 is True  # 降级

    # 3. 内存统计: 1 acquired, 1 skipped, 1 fallback
    stats = dedup_lock_mod.get_stats()
    assert stats["acquired"] == 1
    assert stats["skipped"] == 1
    assert stats["fallback"] == 1

    # 4. flush 到 DB
    success = await flush_lock_stats(db_session)
    await db_session.commit()
    assert success is True

    # 5. 调 lock-stats API
    resp = client.get("/api/v1/alerts/observability/lock-stats")
    assert resp.status_code == 200
    body = resp.json()
    data = body["data"]
    rf = data["recent_flushes"][0]
    assert rf["acquired"] == 1
    assert rf["skipped"] == 1
    assert rf["fallback"] == 1
    # 比例: 1/3 each
    assert abs(rf["fallback"] / 3 - 1 / 3) < 0.001


# ===== 辅助函数 =====


def _make_webhook_notifier(url: str):
    """构造一个指向指定 URL 的 WebhookNotifier (绕过 env var)."""
    from app.monitoring.notifier import WebhookNotifier

    return WebhookNotifier(url=url, max_retries=1)


class _RaisingWebhookNotifier:
    """v1.36 T3.1: 模拟一个 send() 直接抛异常 的 notifier.

    用于触发 CompositeNotifier._dispatch 的 except 异常捕获路径,
    让 OperationLog detail 包含 error 字段.
    """

    name = "webhook"

    def is_configured(self) -> bool:
        return True

    def send(self, payload: AlertPayload) -> bool:
        raise Exception("connection refused")
