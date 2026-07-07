"""v1.33: 告警多通道通知器测试.

v1.36: 增加 T1.1 - notifier 记录通道发送结果到 OperationLog 测试.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import urllib.parse
from unittest.mock import MagicMock, patch

from app.monitoring.notifier import (
    AlertPayload,
    CompositeNotifier,
    DingTalkNotifier,
    EmailNotifier,
    SlackNotifier,
    WebhookNotifier,
    get_default_notifier,
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
    with patch("app.monitoring.notifier._HTTP_SESSION.post") as mock_post:
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
    with patch("app.monitoring.notifier._HTTP_SESSION.post") as mock_post, patch(
        "app.monitoring.notifier.time.sleep"
    ):
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
    with patch("app.monitoring.notifier._HTTP_SESSION.post") as mock_post, patch(
        "app.monitoring.notifier.time.sleep"
    ):
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_post.return_value = mock_resp
        result = n.send(_sample_payload())
        assert result is False
        assert mock_post.call_count == 2


def test_webhook_notifier_silent_on_exception() -> None:
    """v1.33: 网络异常应被吞掉, 返回 False."""
    n = WebhookNotifier(url="https://example.com/hook", max_retries=1)
    with patch(
        "app.monitoring.notifier._HTTP_SESSION.post", side_effect=Exception("network")
    ), patch("app.monitoring.notifier.time.sleep"):
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
    with patch("app.monitoring.notifier._HTTP_SESSION.post") as mock_post:
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
    with patch("app.monitoring.notifier._HTTP_SESSION.post") as mock_post:
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
    with patch("app.monitoring.notifier._HTTP_SESSION.post") as mock_post:
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
    n = DingTalkNotifier(
        webhook_url="https://oapi.dingtalk.com/robot/send", secret=secret
    )
    ts, sign = n._sign()
    # 验证签名格式
    assert ts.isdigit()
    # 重新计算签名验证
    string_to_sign = f"{ts}\n{secret}"
    hmac_code = hmac.new(
        secret.encode("utf-8"), string_to_sign.encode("utf-8"), digestmod=hashlib.sha256
    ).digest()
    expected_sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
    assert sign == expected_sign


def test_dingtalk_notifier_send_without_secret() -> None:
    """v1.33: 无 secret 时应直接发送."""
    n = DingTalkNotifier(
        webhook_url="https://oapi.dingtalk.com/robot/send", secret=None
    )
    with patch("app.monitoring.notifier._HTTP_SESSION.post") as mock_post:
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
    with patch("app.monitoring.notifier._HTTP_SESSION.post") as mock_post:
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
    with patch("app.monitoring.notifier._HTTP_SESSION.post") as mock_post:
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
    with patch.object(config, "settings") as mock_settings, patch(
        "smtplib.SMTP"
    ) as mock_smtp:
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
    with patch("app.monitoring.notifier._HTTP_SESSION.post") as mock_post:
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
    with patch("app.monitoring.notifier._HTTP_SESSION.post") as mock_post, patch(
        "app.monitoring.notifier.time.sleep"
    ):
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
    with patch(
        "app.monitoring.notifier._HTTP_SESSION.post",
        side_effect=[Exception("boom"), MagicMock(status_code=200)],
    ), patch("app.monitoring.notifier.time.sleep"):
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

    with patch("app.monitoring.notifier._HTTP_SESSION.post") as mock_post:
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

    with patch("app.monitoring.notifier._HTTP_SESSION.post") as mock_post, patch(
        "app.monitoring.notifier.time.sleep"
    ):
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

    with patch("app.monitoring.notifier._HTTP_SESSION.post") as mock_post:
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

    with patch("app.monitoring.notifier._HTTP_SESSION.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp
        # 不应抛异常
        results = await composite.send(_sample_payload(), db=db)

    # 通知结果正常
    assert results["webhook"] is True


# ===== 新增: 覆盖 WebhookNotifier 未配置分支 (L96-97) =====


def test_webhook_send_unconfigured_returns_false() -> None:
    """未配置 URL 时 send 应返回 False (覆盖 L96-97)."""
    n = WebhookNotifier(url=None)
    n.url = None
    assert n.send(_sample_payload()) is False


# ===== 新增: 覆盖 SlackNotifier 失败路径 (L170, L177, L187-191) =====


def test_slack_build_payload_with_channel() -> None:
    """配置 channel 时 payload 应包含 channel 字段 (覆盖 L170)."""
    n = SlackNotifier(
        webhook_url="https://hooks.slack.com/services/xxx", channel="#alerts"
    )
    body = n._build_payload(_sample_payload())
    assert body["channel"] == "#alerts"


def test_slack_build_payload_no_channel() -> None:
    """未配置 channel 时 payload 不应包含 channel 字段."""
    n = SlackNotifier(webhook_url="https://hooks.slack.com/services/xxx")
    body = n._build_payload(_sample_payload())
    assert "channel" not in body


def test_slack_send_unconfigured_returns_false() -> None:
    """未配置 webhook_url 时 send 应返回 False (覆盖 L177)."""
    n = SlackNotifier(webhook_url=None)
    n.webhook_url = None
    assert n.send(_sample_payload()) is False


def test_slack_send_http_error_returns_false() -> None:
    """Slack 返回非 2xx 应返回 False (覆盖 L187-188)."""
    n = SlackNotifier(webhook_url="https://hooks.slack.com/services/xxx")
    with patch("app.monitoring.notifier._HTTP_SESSION.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "internal server error"
        mock_post.return_value = mock_resp
        assert n.send(_sample_payload()) is False


def test_slack_send_exception_returns_false() -> None:
    """Slack 网络异常应返回 False (覆盖 L189-191)."""
    n = SlackNotifier(webhook_url="https://hooks.slack.com/services/xxx")
    with patch(
        "app.monitoring.notifier._HTTP_SESSION.post",
        side_effect=ConnectionError("network"),
    ):
        assert n.send(_sample_payload()) is False


# ===== 新增: 覆盖 DingTalkNotifier 分支 (L219, L228, L264, L267-269, L275-279) =====


def test_dingtalk_is_configured_true() -> None:
    """配置 webhook_url 后 is_configured 应返回 True (覆盖 L219)."""
    n = DingTalkNotifier(webhook_url="https://oapi.dingtalk.com/robot/send")
    assert n.is_configured() is True


def test_dingtalk_is_configured_false() -> None:
    """未配置 webhook_url 时 is_configured 应返回 False."""
    n = DingTalkNotifier(webhook_url=None)
    n.webhook_url = None
    assert n.is_configured() is False


def test_dingtalk_sign_no_secret_returns_empty() -> None:
    """无 secret 时 _sign 应返回空字符串 (覆盖 L228)."""
    n = DingTalkNotifier(
        webhook_url="https://oapi.dingtalk.com/robot/send", secret=None
    )
    ts, sign = n._sign()
    assert ts == ""
    assert sign == ""


def test_dingtalk_send_unconfigured_returns_false() -> None:
    """未配置 webhook_url 时 send 应返回 False (覆盖 L264)."""
    n = DingTalkNotifier(webhook_url=None)
    n.webhook_url = None
    assert n.send(_sample_payload()) is False


def test_dingtalk_send_with_secret_adds_signature_to_url() -> None:
    """有 secret 时 URL 应包含 timestamp 和 sign (覆盖 L267-269)."""
    n = DingTalkNotifier(
        webhook_url="https://oapi.dingtalk.com/robot/send",
        secret="SECtest123",
    )
    with patch("app.monitoring.notifier._HTTP_SESSION.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp
        result = n.send(_sample_payload())
        assert result is True
        called_url = mock_post.call_args.args[0]
        assert "timestamp=" in called_url
        assert "sign=" in called_url


def test_dingtalk_send_with_secret_and_query_in_url() -> None:
    """URL 已含 query string 时 separator 应为 '&'."""
    n = DingTalkNotifier(
        webhook_url="https://oapi.dingtalk.com/robot/send?access_token=xxx",
        secret="SECtest123",
    )
    with patch("app.monitoring.notifier._HTTP_SESSION.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp
        n.send(_sample_payload())
        called_url = mock_post.call_args.args[0]
        # 应使用 & 而非 ? 连接 timestamp
        assert "?access_token=xxx&timestamp=" in called_url


def test_dingtalk_send_http_error_returns_false() -> None:
    """钉钉返回非 2xx 应返回 False (覆盖 L275-276)."""
    n = DingTalkNotifier(webhook_url="https://oapi.dingtalk.com/robot/send")
    with patch("app.monitoring.notifier._HTTP_SESSION.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 500
        mock_resp.text = "error"
        mock_post.return_value = mock_resp
        assert n.send(_sample_payload()) is False


def test_dingtalk_send_exception_returns_false() -> None:
    """钉钉网络异常应返回 False (覆盖 L277-279)."""
    n = DingTalkNotifier(webhook_url="https://oapi.dingtalk.com/robot/send")
    with patch(
        "app.monitoring.notifier._HTTP_SESSION.post",
        side_effect=ConnectionError("net error"),
    ):
        assert n.send(_sample_payload()) is False


# ===== 新增: 覆盖 EmailNotifier 分支 (L302, L328, L332-334) =====


def test_email_send_no_recipients_returns_false() -> None:
    """直接调用 send 时无收件人应返回 False (覆盖 L302)."""
    n = EmailNotifier(recipients=[])
    assert n.send(_sample_payload()) is False


def test_email_send_with_smtp_login() -> None:
    """SMTP 配置了用户名密码时应调用 login (覆盖 L328)."""
    from app.core import config

    n = EmailNotifier(recipients=["a@example.com"])
    with patch.object(config, "settings") as mock_settings, patch(
        "smtplib.SMTP"
    ) as mock_smtp:
        mock_settings.smtp_host = "smtp.example.com"
        mock_settings.smtp_port = 587
        mock_settings.smtp_from_email = "alert@example.com"
        mock_settings.smtp_use_tls = False
        mock_settings.smtp_user = "alert_user"
        mock_settings.smtp_password = "alert_pass"
        result = n.send(_sample_payload())
        assert result is True
        mock_smtp.return_value.__enter__.return_value.login.assert_called_once_with(
            "alert_user", "alert_pass"
        )


def test_email_send_with_tls_login() -> None:
    """启用 TLS 时应调用 starttls 并登录."""
    from app.core import config

    n = EmailNotifier(recipients=["a@example.com"])
    with patch.object(config, "settings") as mock_settings, patch(
        "smtplib.SMTP"
    ) as mock_smtp:
        mock_settings.smtp_host = "smtp.example.com"
        mock_settings.smtp_port = 587
        mock_settings.smtp_from_email = "alert@example.com"
        mock_settings.smtp_use_tls = True
        mock_settings.smtp_user = "user"
        mock_settings.smtp_password = "pass"
        result = n.send(_sample_payload())
        assert result is True
        server = mock_smtp.return_value.__enter__.return_value
        server.starttls.assert_called_once()
        server.login.assert_called_once_with("user", "pass")


def test_email_send_exception_returns_false() -> None:
    """SMTP 发送异常应返回 False (覆盖 L332-334)."""
    from app.core import config

    n = EmailNotifier(recipients=["a@example.com"])
    with patch.object(config, "settings") as mock_settings, patch(
        "smtplib.SMTP", side_effect=Exception("smtp error")
    ):
        mock_settings.smtp_host = "smtp.example.com"
        mock_settings.smtp_port = 587
        mock_settings.smtp_from_email = "alert@example.com"
        mock_settings.smtp_use_tls = False
        mock_settings.smtp_user = ""
        mock_settings.smtp_password = ""
        result = n.send(_sample_payload())
        assert result is False


def test_email_send_with_labels_and_annotations() -> None:
    """发送邮件时应调用 sendmail 并传入正确收件人."""
    from app.core import config

    n = EmailNotifier(recipients=["a@example.com", "b@example.com"])
    with patch.object(config, "settings") as mock_settings, patch(
        "smtplib.SMTP"
    ) as mock_smtp:
        mock_settings.smtp_host = "smtp.example.com"
        mock_settings.smtp_port = 587
        mock_settings.smtp_from_email = "alert@example.com"
        mock_settings.smtp_use_tls = False
        mock_settings.smtp_user = ""
        mock_settings.smtp_password = ""
        result = n.send(_sample_payload())
        assert result is True
        # 验证 sendmail 被调用, from 和 recipients 正确
        sendmail_args = mock_smtp.return_value.__enter__.return_value.sendmail.call_args
        assert sendmail_args.args[0] == "alert@example.com"
        assert sendmail_args.args[1] == ["a@example.com", "b@example.com"]
        # msg 应包含 Subject
        assert "[P0]" in sendmail_args.args[2]


# ===== 新增: 覆盖 CompositeNotifier 默认初始化 (L347) =====


def test_composite_default_notifiers_includes_all_channels() -> None:
    """无参构造时应使用默认 4 个通道 (覆盖 L347)."""
    composite = CompositeNotifier()
    names = [n.name for n in composite.notifiers]
    assert "webhook" in names
    assert "slack" in names
    assert "dingtalk" in names
    assert "email" in names
    assert len(composite.notifiers) == 4


def test_composite_empty_notifiers_list() -> None:
    """传入空列表时应使用空列表 (非 None)."""
    composite = CompositeNotifier(notifiers=[])
    assert composite.notifiers == []


# ===== 新增: 覆盖 get_default_notifier 单例 (L453-457) =====


def test_get_default_notifier_creates_singleton() -> None:
    """首次调用 get_default_notifier 应创建单例 (覆盖 L453-457 NameError 分支)."""
    import app.monitoring.notifier as notifier_mod

    # 清除已存在的单例 (触发 NameError 分支)
    if hasattr(notifier_mod, "_default_notifier"):
        del notifier_mod._default_notifier

    n1 = get_default_notifier()
    assert isinstance(n1, CompositeNotifier)

    n2 = get_default_notifier()
    assert n1 is n2  # 同一实例

    # 清理, 避免影响其他测试
    del notifier_mod._default_notifier


def test_get_default_notifier_reuses_existing() -> None:
    """已存在单例时应直接返回 (覆盖 L454 try 分支)."""
    import app.monitoring.notifier as notifier_mod

    preset = CompositeNotifier()
    notifier_mod._default_notifier = preset

    result = get_default_notifier()
    assert result is preset

    # 清理
    del notifier_mod._default_notifier


# ===== 新增: 通知模板渲染验证 =====


def test_slack_build_payload_with_labels_and_annotations() -> None:
    """Slack payload 应将 labels 和 annotations 渲染为 fields."""
    n = SlackNotifier(webhook_url="https://hooks.slack.com/services/xxx")
    payload = AlertPayload(
        rule="TestRule",
        severity="P1",
        status="firing",
        message="test msg",
        labels={"env": "prod", "service": "api"},
        annotations={"summary": "test summary", "runbook": "url"},
    )
    body = n._build_payload(payload)
    fields = body["attachments"][0]["fields"]
    field_titles = [f["title"] for f in fields]
    assert "env" in field_titles
    assert "service" in field_titles
    assert "summary" in field_titles
    assert "runbook" in field_titles


def test_dingtalk_build_payload_with_labels_and_annotations() -> None:
    """钉钉 markdown 应包含 labels 和 annotations."""
    n = DingTalkNotifier(webhook_url="https://oapi.dingtalk.com/robot/send")
    payload = AlertPayload(
        rule="TestRule",
        severity="P0",
        status="firing",
        message="test msg",
        labels={"env": "prod"},
        annotations={"summary": "test"},
    )
    body = n._build_payload(payload)
    text = body["markdown"]["text"]
    assert "Labels" in text
    assert "Annotations" in text
    assert "env: prod" in text


def test_dingtalk_build_payload_minimal() -> None:
    """无 labels/annotations 时 markdown 应正常构建."""
    n = DingTalkNotifier(webhook_url="https://oapi.dingtalk.com/robot/send")
    payload = AlertPayload(rule="Test", severity="P2", status="firing", message="msg")
    body = n._build_payload(payload)
    assert body["msgtype"] == "markdown"
    assert "markdown" in body
    assert "P2" in body["markdown"]["title"]


def test_slack_build_payload_truncates_fields_to_10() -> None:
    """Slack fields 超过 10 个时应截断."""
    n = SlackNotifier(webhook_url="https://hooks.slack.com/services/xxx")
    payload = AlertPayload(
        rule="Test",
        severity="P0",
        status="firing",
        message="msg",
        labels={f"k{i}": f"v{i}" for i in range(15)},
    )
    body = n._build_payload(payload)
    fields = body["attachments"][0]["fields"]
    assert len(fields) == 10


# ===== 新增: 多通道通知综合测试 =====


async def test_composite_all_channels_success() -> None:
    """所有通道成功时应全部返回 True."""
    n1 = WebhookNotifier(url="https://a.example.com", max_retries=1)
    n2 = SlackNotifier(webhook_url="https://b.example.com")
    n3 = DingTalkNotifier(webhook_url="https://c.example.com")
    composite = CompositeNotifier(notifiers=[n1, n2, n3])
    with patch("app.monitoring.notifier._HTTP_SESSION.post") as mock_post:
        mock_resp = MagicMock()
        mock_resp.status_code = 200
        mock_post.return_value = mock_resp
        results = await composite.send(_sample_payload())
    assert results["webhook"] is True
    assert results["slack"] is True
    assert results["dingtalk"] is True


async def test_composite_mixed_success_failure() -> None:
    """混合成功/失败时各通道独立返回结果."""
    n1 = WebhookNotifier(url="https://a.example.com", max_retries=1)
    n2 = DingTalkNotifier(webhook_url="https://c.example.com")
    composite = CompositeNotifier(notifiers=[n1, n2])
    with patch("app.monitoring.notifier._HTTP_SESSION.post") as mock_post, patch(
        "app.monitoring.notifier.time.sleep"
    ):
        mock_fail = MagicMock()
        mock_fail.status_code = 500
        mock_fail.text = "error"
        mock_success = MagicMock()
        mock_success.status_code = 200
        # webhook 重试1次都失败, dingtalk 成功
        mock_post.side_effect = [mock_fail, mock_success]
        results = await composite.send(_sample_payload())
    assert results["webhook"] is False
    assert results["dingtalk"] is True
