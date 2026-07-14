from __future__ import annotations

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.services.admin_service_archive import ArchiveMixin
from app.services.admin_service_config import ConfigMixin
from app.services.admin_service_log import LogMixin
from app.services.admin_service_model import ModelMixin
from app.services.admin_service_stats import StatsMixin
from app.services.admin_service_template import TemplateMixin
from app.services.admin_service_threshold import ThresholdMixin

logger = logging.getLogger(__name__)

# ISS-078: 配置 key 白名单，仅允许以下 key 通过 upsert_config 写入
_ALLOWED_CONFIG_KEYS: frozenset[str] = frozenset(
    {
        "risk_threshold_low",
        "risk_threshold_medium",
        "risk_threshold_high",
        "max_export_rows",
        "session_timeout",
        "token_expiry",
        "notification_email_enabled",
        "notification_sms_enabled",
        "notification_webhook_url",
        "password_min_length",
        "password_require_special",
        "rate_limit_per_minute",
    }
)


class AdminService(
    TemplateMixin,
    ThresholdMixin,
    ConfigMixin,
    LogMixin,
    ModelMixin,
    StatsMixin,
    ArchiveMixin,
):
    """管理后台服务主入口。

    通过 Mixin 多继承组合以下功能模块:
    - TemplateMixin: 干预模板的列表/创建/更新/删除 (含审计日志)
    - ThresholdMixin: 告警阈值的列表/upsert (含 H-03 竞态修复)
    - ConfigMixin: 系统配置的列表/upsert (含 ISS-078 白名单校验) 与模型反馈查询
    - LogMixin: 操作日志/合规审计日志查询 (含 L-Svc-7 公共过滤抽取)
    - ModelMixin: ML 模型注册表的列表/注册/更新/激活
    - StatsMixin: 管理仪表盘统计聚合 (含 H-9 昨日环比快照)
    - ArchiveMixin: 数据归档与 GDPR 合规 (OperationLog/MonitoringLog/RiskAssessment 归档 + IP 掩码)

    本类仅保留 `__init__` 以及模块级工具:
    - `_ALLOWED_CONFIG_KEYS`: 配置 key 白名单 (ConfigMixin.upsert_config 通过延迟导入引用)
    - `_mask_ip`: IP 地址掩码 (ArchiveMixin.mask_old_ips 通过延迟导入引用)

    MAINT-P2-001: 原 869 行单文件拆分为 8 文件, 每文件 ≤500 行。
    """

    def __init__(self, db: AsyncSession) -> None:
        self.db = db


def _mask_ip(ip: str) -> str:
    """SEC-P2-008: 掩码 IP 地址 (保留网络段用于异常检测).

    IPv4: 192.168.1.100 → 192.168.1.0
    IPv6: 2001:db8::1 → 2001:db8::
    非标准格式: → xxx.xxx.xxx.xxx
    已掩码的: 原样返回 (幂等)

    Args:
        ip: 原始 IP 字符串.

    Returns:
        掩码后的 IP 字符串.
    """
    if not ip:
        return ip

    # IPv4: 4 段以 . 分隔, 全为数字
    if "." in ip and ":" not in ip:
        parts = ip.split(".")
        if len(parts) == 4 and all(p.isdigit() for p in parts):
            # 已掩码 (末段为 0) 不再处理, 幂等
            if parts[3] == "0":
                return ip
            return ".".join(parts[:3]) + ".0"

    # IPv6: 多组以 : 分隔, 保留前两组 + ::
    if ":" in ip:
        parts = ip.split(":")
        # 至少 2 组 (如 "2001:db8::")
        if len(parts) >= 2 and parts[0] and parts[1]:
            # 已掩码 (结尾是 ::) 不再处理, 幂等
            if ip.endswith("::") and len(parts) == 3 and not parts[2]:
                return ip
            return ":".join(parts[:2]) + "::"

    # 非标准格式 (unknown, localhost, 内部标识等)
    return "xxx.xxx.xxx.xxx"
