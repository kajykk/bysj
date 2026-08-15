"""v1.33: 告警 payload schema 定义 (从 alerts.py 拆分).

包含:
- _validate_url_safety: SSRF 防护工具函数
- AlertManagerAlert / AlertManagerPayload / AlertHistoryItem: Pydantic 模型
- _ALERT_MAX_* 常量
"""

from __future__ import annotations

import ipaddress
from urllib.parse import urlparse

from pydantic import BaseModel, Field, model_validator

# P1-SEC-024 修复：AlertManager payload 大小限制，防止恶意大 payload 耗尽资源
_ALERT_MAX_LABELS = 50
_ALERT_MAX_LABEL_KEY_LEN = 128
_ALERT_MAX_LABEL_VAL_LEN = 2048
_ALERT_MAX_ANNOTATIONS = 50
_ALERT_MAX_ANNOTATION_VAL_LEN = 4096
_ALERT_MAX_URL_LEN = 2048
_ALERT_MAX_LIST_SIZE = 500
_ALERT_MAX_MSG_LEN = 4096


def _validate_url_safety(url: str | None, field_name: str = "url") -> str | None:
    """C-API-3 修复：校验 URL 安全性，防止 SSRF.

    策略:
    - 必须以 http:// 或 https:// 开头（拒绝 javascript:, data:, file: 等, 直接 422）
    - 指向本机/内网/元数据地址的 http(s) URL 会被中性化 (置为 None):
      这些字段 (generatorURL/externalURL) 仅用于展示与审计, 后端从不抓取;
      中性化而非整包拒绝, 是因为内部自部署的 Grafana/AlertManager
      (本项目即如此, GF_SERVER_ROOT_URL=https://localhost/grafana) 发出的
      payload 必然携带内网地址, 整包拒绝会让告警链路在真实部署中彻底失效.
      置 None 后即使未来代码错误地尝试抓取该 URL, 也没有可抓取的目标.
    """
    if not url:
        return url
    url = url.strip()
    if not url:
        return url
    if not url.startswith(("http://", "https://")):
        raise ValueError(f"{field_name} 必须以 http:// 或 https:// 开头")
    try:
        parsed = urlparse(url)
        hostname = parsed.hostname
        if not hostname:
            return url
        # 本机/云元数据地址 -> 中性化
        if hostname in ("localhost", "0.0.0.0", "::1") or hostname.startswith(  # nosec B104  security check, not actual bind
            "169.254."
        ):
            return None
        try:
            ip = ipaddress.ip_address(hostname)
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                return None
        except ValueError:
            # 非 IP 格式（域名），允许通过
            pass
    except ValueError:
        raise
    except Exception:
        # 解析失败时放行（AlertManager 的 generatorURL 通常是合法 URL）
        pass
    return url


# ===== Request/Response Models =====


class AlertManagerAlert(BaseModel):
    """v1.33: AlertManager 单条告警."""

    status: str = "firing"  # firing/resolved
    labels: dict[str, str] = Field(default_factory=dict, max_length=_ALERT_MAX_LABELS)
    annotations: dict[str, str] = Field(
        default_factory=dict, max_length=_ALERT_MAX_ANNOTATIONS
    )
    startsAt: str | None = Field(default=None, max_length=64)
    endsAt: str | None = Field(default=None, max_length=64)
    generatorURL: str | None = Field(default=None, max_length=_ALERT_MAX_URL_LEN)
    fingerprint: str | None = Field(default=None, max_length=128)

    @model_validator(mode="after")
    def _validate_alert_fields(self) -> "AlertManagerAlert":
        """P1-SEC-024 修复：校验 labels/annotations 键值长度."""
        for key, value in self.labels.items():
            if len(key) > _ALERT_MAX_LABEL_KEY_LEN:
                raise ValueError(
                    f"label key 长度不能超过 {_ALERT_MAX_LABEL_KEY_LEN} 字符"
                )
            if len(value) > _ALERT_MAX_LABEL_VAL_LEN:
                raise ValueError(
                    f"label value 长度不能超过 {_ALERT_MAX_LABEL_VAL_LEN} 字符"
                )
        for key, value in self.annotations.items():
            if len(key) > _ALERT_MAX_LABEL_KEY_LEN:
                raise ValueError(
                    f"annotation key 长度不能超过 {_ALERT_MAX_LABEL_KEY_LEN} 字符"
                )
            if len(value) > _ALERT_MAX_ANNOTATION_VAL_LEN:
                raise ValueError(
                    f"annotation value 长度不能超过 {_ALERT_MAX_ANNOTATION_VAL_LEN} 字符"
                )
        # C-API-3 修复：校验 generatorURL 协议，防止 SSRF
        if self.generatorURL:
            self.generatorURL = _validate_url_safety(self.generatorURL, "generatorURL")
        return self


class AlertManagerPayload(BaseModel):
    """v1.33: AlertManager webhook payload (v4 格式)."""

    version: str = Field(default="1", max_length=32)
    groupKey: str | None = Field(default=None, max_length=512)
    status: str = Field(default="firing", max_length=32)
    receiver: str | None = Field(default=None, max_length=128)
    groupLabels: dict[str, str] = Field(
        default_factory=dict, max_length=_ALERT_MAX_LABELS
    )
    commonLabels: dict[str, str] = Field(
        default_factory=dict, max_length=_ALERT_MAX_LABELS
    )
    commonAnnotations: dict[str, str] = Field(
        default_factory=dict, max_length=_ALERT_MAX_ANNOTATIONS
    )
    externalURL: str | None = Field(default=None, max_length=_ALERT_MAX_URL_LEN)
    alerts: list[AlertManagerAlert] = Field(
        default_factory=list, max_length=_ALERT_MAX_LIST_SIZE
    )

    @model_validator(mode="after")
    def _validate_payload_urls(self) -> "AlertManagerPayload":
        """C-API-3 修复：校验 externalURL 协议，防止 SSRF."""
        if self.externalURL:
            self.externalURL = _validate_url_safety(self.externalURL, "externalURL")
        return self


class AlertHistoryItem(BaseModel):
    """v1.33: 告警历史条目."""

    id: int
    rule: str
    severity: str
    status: str
    message: str
    fingerprint: str | None = None
    operator_id: int | None = None
    operator_role: str | None = None
    created_at: str | None = None
