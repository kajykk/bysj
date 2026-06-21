"""v1.33: 告警多通道通知器测试.

v1.36: 增加 T1.1 - notifier 记录通道发送结果到 OperationLog 测试.
"""
from __future__ import annotations

import hashlib
import hmac
import base64
import urllib.parse
from unittest.mock import MagicMock, patch

import pytest

from app.monitoring.notifier import (
    AlertPayload,
    CompositeNotifier,
    DingTalkNotifier,
    EmailNotifier,
    SlackNotifier,
    WebhookNotifier,
)


def _sample_payload() -> AlertPayload:
    return AlertPayload(
        rule="HighErrorRate",
        severity="P0",
        status="firing",
        message="5xx error rate exceeded 5%",
        labels={"service": "backend", "env": "prod"},
        annotations={"summary": "test alert"},
        fingerprint="abc123",
    )


# ===== Webhook Notifier =====


def test_webhook_notifier_is_configured() -> None:
    """v1.33: 未配置 URL 应返回 False."""
    n = WebhookNotifier(url=None)
    n.url = None
    assert n.is_configured() is False


def test_webhook_notifier_is_configured_with_url() -> None:
    """v1.33: 配置 URL 后应返回 True."""
    n = WebhookNotifier(url="https://example.com/hook")
    assert n.is_configured() is True


def test_webhook_notifier_send_success() -> None:
    """v1.33: 成功 POST 应返回 True."""
    n = WebhookNotifier(url="https://example.com/hook", max_retries=1)
    with patch("app.monitoring.notifier.requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp
        result = n.send(_sample_payload())
        assert result is True
        assert mock_post.call_count == 1
        call_args = mock_post.call_args
        assert call_args.kwargs["json"]["rule"] == "HighErrorRate"


def test_webhook_notifier_retry_on_5xx() -> None:
    """v1.33: 5xx 应触发重试."""
    n = WebhookNotifier(url="https://example.com/hook", max_retries=3)
    with patch("app.monitoring.notifier.requests.post") as mock_post, patch("app.monitoring.notifier.time.sleep"):
        mock_resp_500 = MagicMock()
        mock_resp_500.status_code = 500
        mock_resp_200 = MagicMock()
        mock_resp_200.status_code = 200
        mock_post.side_effect = [mock_resp_500, mock_resp_200]
        result = n.send(_sample_payload())
        assert result is True
        assert mock_post.call_count == 2


def test_webhook_notifier_give_up_after_max_retries() -> None:
    """v1.33: 超过 max_retries 应返回 False."""
    n = WebhookNotifier(url="https://example.com/hook", max_retries=2)
    with patch("app.monitoring.notifier.requests.post") as mock_post, patch("app.monitoring.notifier.time.sleep"):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_post.return_value = mock_resp
        result = n.send(_sample_payload())
        assert result is False
        assert mock_post.call_count == 2


def test_webhook_notifier_silent_on_exception() -> None:
    """v1.33: 网络异常应被吞掉, 返回 False."""
    n = WebhookNotifier(url="https://example.com/hook", max_retries=1)
    with patch("app.monitoring.notifier.requests.post", side_effect=Exception("network")), patch("app.monitoring.notifier.time.sleep"):
        result = n.send(_sample_payload())
        assert result is False


# ===== Slack Notifier =====


def test_slack_notifier_unconfigured() -> None:
    """v1.33: Slack 未配置应返回 False."""
    n = SlackNotifier(webhook_url=None)
    n.webhook_url = None
    assert n.is_configured() is False


def test_slack_notifier_send_success() -> None:
    """v1.33: Slack 发送应使用 attachments 格式."""
    n = SlackNotifier(webhook_url="https://hooks.slack.com/services/xxx")
    with patch("app.monitoring.notifier.requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp
        result = n.send(_sample_payload())
        assert result is True
        body = mock_post.call_args.kwargs["json"]
        assert "attachments" in body
        assert body["attachments"][0]["color"] == "#FF0000"  # P0
        assert ":fire:" in body["attachments"][0]["title"]


def test_slack_notifier_resolved_status() -> None:
    """v1.33: resolved 状态应使用 :white_check_mark:."""
    n = SlackNotifier(webhook_url="https://hooks.slack.com/services/xxx")
    payload = _sample_payload()
    payload.status = "resolved"
    with patch("app.monitoring.notifier.requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp
        n.send(payload)
        title = mock_post.call_args.kwargs["json"]["attachments"][0]["title"]
        assert ":white_check_mark:" in title


def test_slack_notifier_p1_color() -> None:
    """v1.33: P1 应使用橙色."""
    n = SlackNotifier(webhook_url="https://hooks.slack.com/services/xxx")
    payload = _sample_payload()
    payload.severity = "P1"
    with patch("app.monitoring.notifier.requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp
        n.send(payload)
        color = mock_post.call_args.kwargs["json"]["attachments"][0]["color"]
        assert color == "#FFA500"


# ===== DingTalk Notifier =====


def test_dingtalk_notifier_sign() -> None:
    """v1.33: 钉钉签名应符合规范."""
    secret = "SEC..."
    n = DingTalkNotifier(webhook_url="https://oapi.dingtalk.com/robot/send", secret=secret)
    ts, sign = n._sign()
    # 验证签名格式
    assert ts.isdigit()
    # 重新计算签名验证
    string_to_sign = f"{ts}\n{secret}"
    hmac_code = hmac.new(secret.encode("utf-8"), string_to_sign.encode("utf-8"), digestmod=hashlib.sha256).digest()
    expected_sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    assert sign == expected_sign


def test_dingtalk_notifier_send_without_secret() -> None:
    """v1.33: 无 secret 时应直接发送."""
    n = DingTalkNotifier(webhook_url="https://oapi.dingtalk.com/robot/send", secret=None)
    with patch("app.monitoring.notifier.requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp
        result = n.send(_sample_payload())
        assert result is True
        # URL 不应包含 timestamp/sign
        called_url = mock_post.call_args.args[0]
        assert "timestamp=" not in called_url


def test_dingtalk_notifier_at_mobiles_p0() -> None:
    """v1.33: P0 应 @ 指定手机号."""
    n = DingTalkNotifier(
        webhook_url="https://oapi.dingtalk.com/robot/send",
        at_mobiles=["13800000000"],
    )
    with patch("app.monitoring.notifier.requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp
        n.send(_sample_payload())  # P0
        body = mock_post.call_args.kwargs["json"]
        assert body.get("at", {}).get("atMobiles") == ["13800000000"]


def test_dingtalk_notifier_no_at_for_p1() -> None:
    """v1.33: P1 不应 @."""
    n = DingTalkNotifier(
        webhook_url="https://oapi.dingtalk.com/robot/send",
        at_mobiles=["13800000000"],
    )
    payload = _sample_payload()
    payload.severity = "P1"
    with patch("app.monitoring.notifier.requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp
        n.send(payload)
        body = mock_post.call_args.kwargs["json"]
        assert "at" not in body


# ===== Email Notifier =====


def test_email_notifier_no_recipients() -> None:
    """v1.33: 无收件人应返回 False."""
    n = EmailNotifier(recipients=[])
    assert n.is_configured() is False


def test_email_notifier_smtp_not_configured() -> None:
    """v1.33: SMTP 未配置应返回 False."""
    from app.core import config
    n = EmailNotifier(recipients=["a@example.com"])
    with patch.object(config, "settings") as mock_settings:
        mock_settings.smtp_host = ""
        mock_settings.smtp_from_email = ""
        result = n.send(_sample_payload())
        assert result is False


def test_email_notifier_send_success() -> None:
    """v1.33: SMTP 发送成功."""
    from app.core import config

    n = EmailNotifier(recipients=["a@example.com"])
    with patch.object(config, "settings") as mock_settings, patch("smtplib.SMTP") as mock_smtp:
        mock_settings.smtp_host = "smtp.example.com"
        mock_settings.smtp_port = 587
        mock_settings.smtp_from_email = "alert@example.com"
        mock_settings.smtp_use_tls = True
        mock_settings.smtp_user = ""
        mock_settings.smtp_password = ""
        result = n.send(_sample_payload())
        assert result is True
        mock_smtp.assert_called_once()


# ===== Composite Notifier (v1.36: now async) =====


async def test_composite_skips_unconfigured() -> None:
    """v1.33: 未配置的通道应跳过."""
    composite = CompositeNotifier(
        notifiers=[
            WebhookNotifier(url=None),
            WebhookNotifier(url=None),
        ]
    )
    # 确保 url 为 None
    for n in composite.notifiers:
        n.url = None
    results = await composite.send(_sample_payload())
    assert all(v is False for v in results.values())


async def test_composite_fans_out() -> None:
    """v1.33: 多通道应并行发送."""
    n1 = WebhookNotifier(url="https://a.example.com")
    n2 = SlackNotifier(webhook_url="https://b.example.com")
    composite = CompositeNotifier(notifiers=[n1, n2])
    with patch("app.monitoring.notifier.requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp
        results = await composite.send(_sample_payload())
        assert results["webhook"] is True
        assert results["slack"] is True
        assert mock_post.call_count == 2


async def test_composite_partial_failure() -> None:
    """v1.33: 部分失败不应阻塞其他通道."""
    n1 = WebhookNotifier(url="https://a.example.com", max_retries=1)
    n2 = SlackNotifier(webhook_url="https://b.example.com")
    composite = CompositeNotifier(notifiers=[n1, n2])
    with patch("app.monitoring.notifier.requests.post") as mock_post, patch("app.monitoring.notifier.time.sleep"):
        # 第一次失败, 第二次成功
        mock_fail = MagicMock()
        mock_fail.status_code = 500
        mock_success = MagicMock()
        mock_success.status_code = 200
        mock_post.side_effect = [mock_fail, mock_success]
        results = await composite.send(_sample_payload())
        assert results["webhook"] is False
        assert results["slack"] is True


async def test_composite_handles_exception() -> None:
    """v1.33: 单通道异常不应影响其他通道."""
    n1 = WebhookNotifier(url="https://a.example.com", max_retries=1)
    n2 = SlackNotifier(webhook_url="https://b.example.com")
    composite = CompositeNotifier(notifiers=[n1, n2])
    with patch("app.monitoring.notifier.requests.post", side_effect=[Exception("boom"), MagicMock(status_code=200)]), patch("app.monitoring.notifier.time.sleep"):
        results = await composite.send(_sample_payload())
        assert results["webhook"] is False
        assert results["slack"] is True


# ===== v1.36: T1.1 notifier 记录通道发送 (TC-DATA-001) =====


async def test_channel_sent_logged_on_success() -> None:
    """v1.36 T1.1: 通道成功时写入 OperationLog (alert_channel_sent)."""
    n1 = WebhookNotifier(url="https://a.example.com", max_retries=1)
    composite = CompositeNotifier(notifiers=[n1])
    db = MagicMock()
    db.add = MagicMock()

    with patch("app.monitoring.notifier.requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp
        await composite.send(_sample_payload(), db=db)

    # 验证 db.add 被调用, 且参数是 OperationLog
    assert db.add.called
    call_args = db.add.call_args
    log_obj = call_args.args[0]
    assert log_obj.action_type == "alert_channel_sent"
    assert log_obj.target_type == "alert_channel"
    assert log_obj.operator_role == "system"
    assert log_obj.operator_id is None


async def test_channel_failed_logged_on_failure() -> None:
    """v1.36 T1.1: 通道失败时写入 OperationLog (alert_channel_failed)."""
    n1 = WebhookNotifier(url="https://a.example.com", max_retries=1)
    composite = CompositeNotifier(notifiers=[n1])
    db = MagicMock()
    db.add = MagicMock()

    with patch("app.monitoring.notifier.requests.post") as mock_post, patch("app.monitoring.notifier.time.sleep"):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_post.return_value = mock_resp
        await composite.send(_sample_payload(), db=db)

    assert db.add.called
    log_obj = db.add.call_args.args[0]
    assert log_obj.action_type == "alert_channel_failed"


async def test_channel_log_includes_duration_ms() -> None:
    """v1.36 T1.1: detail 包含 duration_ms 字段."""
    import json as json_mod

    n1 = WebhookNotifier(url="https://a.example.com", max_retries=1)
    composite = CompositeNotifier(notifiers=[n1])
    db = MagicMock()
    db.add = MagicMock()

    with patch("app.monitoring.notifier.requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp
        await composite.send(_sample_payload(), db=db)

    log_obj = db.add.call_args.args[0]
    detail = json_mod.loads(log_obj.detail)
    assert "duration_ms" in detail
    assert isinstance(detail["duration_ms"], int)
    assert detail["duration_ms"] >= 0
    # 同时包含 channel 与 rule
    assert detail["channel"] == "webhook"
    assert detail["rule"] == "HighErrorRate"


async def test_channel_log_detail_includes_error() -> None:
    """v1.36 T1.1: 失败时 detail 包含 error 字段."""
    import json as json_mod

    # 使用会抛异常的 notifier (绕过 WebhookNotifier 内部 try/except)
    class _RaisingNotifier:
        name = "raising"
        def is_configured(self) -> bool:
            return True
        def send(self, payload: AlertPayload) -> bool:
            raise Exception("boom")

    composite = CompositeNotifier(notifiers=[_RaisingNotifier()])
    db = MagicMock()
    db.add = MagicMock()

    results = await composite.send(_sample_payload(), db=db)

    # 主流程仍返回结果 (异常被 _dispatch 捕获, success=False)
    assert results["raising"] is False
    # detail 应包含 error
    log_obj = db.add.call_args.args[0]
    detail = json_mod.loads(log_obj.detail)
    assert "error" in detail
    assert "boom" in detail["error"]


async def test_channel_log_failure_does_not_block_notification() -> None:
    """v1.36 T1.1: 写日志失败不影响通知返回结果."""
    n1 = WebhookNotifier(url="https://a.example.com", max_retries=1)
    composite = CompositeNotifier(notifiers=[n1])

    # 模拟 db.add 抛异常
    db = MagicMock()
    db.add = MagicMock(side_effect=Exception("db unavailable"))

    with patch("app.monitoring.notifier.requests.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp
        # 不应抛异常
        results = await composite.send(_sample_payload(), db=db)

    # 通知结果正常
    assert results["webhook"] is True
