"""多通道告警通知器 (v1.33).

支持通道:
- webhook: 通用 JSON POST
- slack: Slack Incoming Webhook
- dingtalk: 钉钉机器人 (含签名)
- email: SMTP (复用 settings.smtp_*)
- composite: 多通道并行发送

特性:
- 失败重试 (指数退避, max 3)
- 优雅降级 (单通道失败不影响其他)
- 完整日志 (含 trace_id)
- v1.36: 每个通道发送结果写入 OperationLog (需传 db)
"""
from __future__ import annotations

import asyncio
import base64
import hashlib
import hmac
import json
import logging
import os
import time
import urllib.parse
from dataclasses import dataclass, field
from typing import Any, Protocol, TYPE_CHECKING

import requests

if TYPE_CHECKING:
    from sqlalchemy.ext.asyncio import AsyncSession

logger = logging.getLogger(__name__)

# RES-P1-010 修复: 模块级 requests.Session 复用 TCP 连接, 避免每次请求新建连接 (1-3s 开销)
# requests.Session 内部维护连接池 (urllib3.HTTPConnectionPool), 同一 host 的后续请求复用 TCP 连接
_HTTP_SESSION = requests.Session()


@dataclass
class AlertPayload:
    """v1.33: 告警标准 payload."""

    rule: str
    severity: str  # P0/P1/P2
    status: str  # firing/resolved
    message: str
    labels: dict[str, str] = field(default_factory=dict)
    annotations: dict[str, str] = field(default_factory=dict)
    fingerprint: str | None = None
    starts_at: str | None = None
    ends_at: str | None = None
    generator_url: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "rule": self.rule,
            "severity": self.severity,
            "status": self.status,
            "message": self.message,
            "labels": self.labels,
            "annotations": self.annotations,
            "fingerprint": self.fingerprint,
            "starts_at": self.starts_at,
            "ends_at": self.ends_at,
            "generator_url": self.generator_url,
        }


class Notifier(Protocol):
    """v1.33: 通知器接口."""

    name: str

    def send(self, payload: AlertPayload) -> bool:
        """发送告警. 成功返回 True, 失败返回 False (可重试)."""
        ...

    def is_configured(self) -> bool:
        """是否已配置 (有 URL/凭证)."""
        ...


class WebhookNotifier:
    """v1.33: 通用 JSON Webhook 通知器."""

    name = "webhook"

    def __init__(self, url: str | None = None, timeout: int = 5, max_retries: int = 3) -> None:
        self.url = url or os.getenv("ALERT_WEBHOOK_URL")
        self.timeout = timeout
        self.max_retries = max_retries

    def is_configured(self) -> bool:
        return bool(self.url)

    def send(self, payload: AlertPayload) -> bool:
        if not self.url:
            logger.info("[webhook] 未配置 URL, 跳过")
            return False

        body = payload.to_dict()
        last_error: str | None = None
        for attempt in range(self.max_retries):
            try:
                # RES-P1-010 修复: 使用模块级 _HTTP_SESSION 复用 TCP 连接
                resp = _HTTP_SESSION.post(
                    self.url,
                    json=body,
                    timeout=self.timeout,
                    headers={"Content-Type": "application/json"},
                )
                if 200 <= resp.status_code < 300:
                    logger.info("[webhook] 发送成功 (rule=%s, status=%s)", payload.rule, resp.status_code)
                    return True
                last_error = f"HTTP {resp.status_code}"
            except Exception as exc:
                last_error = str(exc)
            # 指数退避
            if attempt < self.max_retries - 1:
                time.sleep(2 ** attempt)
        logger.error("[webhook] 发送失败 (rule=%s, error=%s)", payload.rule, last_error)
        return False


class SlackNotifier:
    """v1.33: Slack Incoming Webhook 通知器."""

    name = "slack"

    SEVERITY_COLOR = {
        "P0": "#FF0000",  # red
        "P1": "#FFA500",  # orange
        "P2": "#FFFF00",  # yellow
        "critical": "#FF0000",
        "warning": "#FFA500",
        "info": "#0099CC",
    }
    SEVERITY_EMOJI = {
        "P0": ":fire:",
        "P1": ":warning:",
        "P2": ":information_source:",
        "critical": ":fire:",
        "warning": ":warning:",
        "info": ":information_source:",
    }

    def __init__(self, webhook_url: str | None = None, channel: str | None = None) -> None:
        self.webhook_url = webhook_url or os.getenv("ALERT_SLACK_WEBHOOK_URL")
        self.channel = channel or os.getenv("ALERT_SLACK_CHANNEL")

    def is_configured(self) -> bool:
        return bool(self.webhook_url)

    def _build_payload(self, alert: AlertPayload) -> dict:
        color = self.SEVERITY_COLOR.get(alert.severity, "#808080")
        emoji = self.SEVERITY_EMOJI.get(alert.severity, ":bell:")
        fields: list[dict] = []
        for k, v in alert.labels.items():
            fields.append({"title": k, "value": str(v), "short": True})
        for k, v in alert.annotations.items():
            fields.append({"title": k, "value": str(v), "short": True})
        attachment = {
            "color": color,
            "title": f"{emoji} {alert.severity} - {alert.rule}",
            "text": alert.message,
            "fields": fields[:10],
            "ts": int(time.time()),
        }
        body: dict[str, Any] = {
            "attachments": [attachment],
        }
        if self.channel:
            body["channel"] = self.channel
        if alert.status == "resolved":
            attachment["title"] = f":white_check_mark: RESOLVED - {alert.rule}"
        return body

    def send(self, payload: AlertPayload) -> bool:
        if not self.webhook_url:
            return False
        try:
            # RES-P1-010 修复: 使用模块级 _HTTP_SESSION 复用 TCP 连接
            resp = _HTTP_SESSION.post(
                self.webhook_url,
                json=self._build_payload(payload),
                timeout=5,
            )
            if 200 <= resp.status_code < 300:
                logger.info("[slack] 发送成功 (rule=%s)", payload.rule)
                return True
            logger.warning("[slack] 发送失败 status=%s body=%s", resp.status_code, resp.text[:200])
            return False
        except Exception as exc:
            logger.error("[slack] 异常: %s", exc)
            return False


class DingTalkNotifier:
    """v1.33: 钉钉机器人通知器 (含签名)."""

    name = "dingtalk"

    SEVERITY_EMOJI = {
        "P0": "🔥",
        "P1": "⚠️",
        "P2": "ℹ️",
        "critical": "🔥",
        "warning": "⚠️",
        "info": "ℹ️",
    }

    def __init__(
        self,
        webhook_url: str | None = None,
        secret: str | None = None,
        at_mobiles: list[str] | None = None,
    ) -> None:
        self.webhook_url = webhook_url or os.getenv("ALERT_DINGTALK_WEBHOOK_URL")
        self.secret = secret or os.getenv("ALERT_DINGTALK_SECRET")
        self.at_mobiles = at_mobiles or []

    def is_configured(self) -> bool:
        return bool(self.webhook_url)

    def _sign(self) -> tuple[str, str]:
        """生成钉钉签名.

        Returns:
            (timestamp, signature)
        """
        if not self.secret:
            return "", ""
        timestamp = str(round(time.time() * 1000))
        string_to_sign = f"{timestamp}\n{self.secret}"
        hmac_code = hmac.new(
            self.secret.encode("utf-8"),
            string_to_sign.encode("utf-8"),
            digestmod=hashlib.sha256,
        ).digest()
        sign = urllib.parse.quote_plus(base64.b64encode(hmac_code))
        return timestamp, sign

    def _build_payload(self, alert: AlertPayload) -> dict:
        emoji = self.SEVERITY_EMOJI.get(alert.severity, "🔔")
        text = f"## {emoji} {alert.severity} - {alert.rule}\n\n{alert.message}\n\n"
        if alert.labels:
            text += "**Labels:**\n"
            for k, v in alert.labels.items():
                text += f"- {k}: {v}\n"
        if alert.annotations:
            text += "\n**Annotations:**\n"
            for k, v in alert.annotations.items():
                text += f"- {k}: {v}\n"

        body: dict[str, Any] = {
            "msgtype": "markdown",
            "markdown": {
                "title": f"{emoji} {alert.severity} - {alert.rule}",
                "text": text,
            },
        }
        if self.at_mobiles and alert.severity in ("P0", "critical"):
            body["at"] = {"atMobiles": self.at_mobiles, "isAtAll": False}
        return body

    def send(self, payload: AlertPayload) -> bool:
        if not self.webhook_url:
            return False
        url = self.webhook_url
        if self.secret:
            ts, sign = self._sign()
            separator = "&" if "?" in url else "?"
            url = f"{url}{separator}timestamp={ts}&sign={sign}"
        try:
            # RES-P1-010 修复: 使用模块级 _HTTP_SESSION 复用 TCP 连接
            resp = _HTTP_SESSION.post(url, json=self._build_payload(payload), timeout=5)
            if 200 <= resp.status_code < 300:
                logger.info("[dingtalk] 发送成功 (rule=%s)", payload.rule)
                return True
            logger.warning("[dingtalk] 发送失败 status=%s body=%s", resp.status_code, resp.text[:200])
            return False
        except Exception as exc:
            logger.error("[dingtalk] 异常: %s", exc)
            return False


class EmailNotifier:
    """v1.33: SMTP 邮件通知器."""

    name = "email"

    def __init__(self, recipients: list[str] | None = None) -> None:
        self.recipients = recipients or self._load_recipients()

    @staticmethod
    def _load_recipients() -> list[str]:
        raw = os.getenv("ALERT_EMAIL_RECIPIENTS", "")
        return [r.strip() for r in raw.split(",") if r.strip()]

    def is_configured(self) -> bool:
        return bool(self.recipients)

    def send(self, payload: AlertPayload) -> bool:
        from app.core.config import settings

        if not self.recipients:
            return False
        if not settings.smtp_host or not settings.smtp_from_email:
            logger.info("[email] SMTP 未配置, 跳过")
            return False
        try:
            import smtplib
            from email.mime.multipart import MIMEMultipart
            from email.mime.text import MIMEText

            msg = MIMEMultipart()
            msg["From"] = settings.smtp_from_email
            msg["To"] = ", ".join(self.recipients)
            msg["Subject"] = f"[{payload.severity}] {payload.rule}"

            body_text = f"{payload.message}\n\n"
            if payload.labels:
                body_text += "Labels:\n" + json.dumps(payload.labels, indent=2) + "\n"
            if payload.annotations:
                body_text += "Annotations:\n" + json.dumps(payload.annotations, indent=2) + "\n"

            msg.attach(MIMEText(body_text, "plain", "utf-8"))

            with smtplib.SMTP(settings.smtp_host, settings.smtp_port, timeout=10) as server:
                if settings.smtp_use_tls:
                    server.starttls()
                if settings.smtp_user and settings.smtp_password:
                    server.login(settings.smtp_user, settings.smtp_password)
                server.sendmail(settings.smtp_from_email, self.recipients, msg.as_string())
            logger.info("[email] 发送成功 (rule=%s, recipients=%d)", payload.rule, len(self.recipients))
            return True
        except Exception as exc:
            logger.error("[email] 异常: %s", exc)
            return False


class CompositeNotifier:
    """v1.33: 多通道并行发送.

    v1.36: 可选 db 参数 - 传入 AsyncSession 时, 每个通道的发送结果
    会写入 OperationLog (action_type=alert_channel_sent/alert_channel_failed).
    写日志失败不会影响通知返回值.
    """

    def __init__(self, notifiers: list[Notifier] | None = None) -> None:
        if notifiers is None:
            notifiers = [
                WebhookNotifier(),
                SlackNotifier(),
                DingTalkNotifier(),
                EmailNotifier(),
            ]
        self.notifiers = notifiers

    async def send(
        self,
        payload: AlertPayload,
        db: AsyncSession | None = None,
    ) -> dict[str, bool]:
        """发送告警到所有已配置通道.

        Args:
            payload: 告警 payload.
            db: v1.36 可选. 传入 AsyncSession 时, 每个通道的成功/失败会
                写入 OperationLog (alert_channel_sent/alert_channel_failed).

        Returns:
            {notifier_name: success}
        """
        results: dict[str, bool] = {}
        for n in self.notifiers:
            if not n.is_configured():
                results[n.name] = False  # 未配置视为跳过
                # v1.36: 未配置不写日志, 视为"未尝试"
                continue
            # RES-P1-008 修复: _dispatch 内部调用同步 n.send → requests.post, 会阻塞事件循环.
            # 使用 asyncio.to_thread 卸载到线程池, 避免阻塞主事件循环.
            success, error_msg, duration_ms = await asyncio.to_thread(
                self._dispatch, n, payload
            )
            results[n.name] = success
            if db is not None:
                await self._write_channel_log(
                    db=db,
                    channel=n.name,
                    payload=payload,
                    success=success,
                    duration_ms=duration_ms,
                    error_msg=error_msg,
                )
        return results

    @staticmethod
    def _dispatch(
        n: Notifier, payload: AlertPayload
    ) -> tuple[bool, str | None, int]:
        """调用单个 notifier 并测量耗时. 返回 (success, error_msg, duration_ms)."""
        start = time.monotonic()
        error_msg: str | None = None
        success = False
        try:
            success = n.send(payload)
        except Exception as exc:
            error_msg = str(exc)
            logger.error("[%s] 未捕获异常: %s", n.name, exc)
            success = False
        duration_ms = int((time.monotonic() - start) * 1000)
        return success, error_msg, duration_ms

    @staticmethod
    async def _write_channel_log(
        db: AsyncSession,
        channel: str,
        payload: AlertPayload,
        success: bool,
        duration_ms: int,
        error_msg: str | None,
    ) -> None:
        """v1.36: 写入通道发送结果 OperationLog. 失败不影响主流程."""
        # 延迟导入避免循环依赖
        from app.models.admin import OperationLog

        try:
            action_type = "alert_channel_sent" if success else "alert_channel_failed"
            detail_dict: dict[str, Any] = {
                "channel": channel,
                "duration_ms": duration_ms,
                "rule": payload.rule,
                "severity": payload.severity,
                "status": payload.status,
                "fingerprint": payload.fingerprint,
            }
            if error_msg:
                detail_dict["error"] = error_msg
            log = OperationLog(
                operator_id=None,
                operator_role="system",
                action_type=action_type,
                target_type="alert_channel",
                target_id=None,
                detail=json.dumps(detail_dict, ensure_ascii=False),
            )
            db.add(log)
            await db.flush()
        except Exception as exc:
            # 写日志失败不影响通知返回
            logger.error(
                "[notifier] 写 OperationLog 失败 (channel=%s, error=%s)",
                channel,
                exc,
            )


def get_default_notifier() -> CompositeNotifier:
    """获取默认通知器 (单例)."""
    global _default_notifier
    try:
        return _default_notifier
    except NameError:
        _default_notifier = CompositeNotifier()
        return _default_notifier
