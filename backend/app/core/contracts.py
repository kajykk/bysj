"""契约聚合层 (Contract Aggregation Layer)

作为系统核心契约的单一事实来源 (Single Source of Truth)，集中定义并 re-export
跨模块共享的关键常量、枚举与转换函数。

本模块职责:
1. 定义风险等级映射 (RISK_LEVEL_MAP) 与标准化函数 (normalize_risk_level)
2. 定义预警动作/状态契约 (WARNING_ACTION_* / WARNING_STATUS_*)
3. 定义预警审计动作类型 (ACTION_TYPE_WARNING_*)
4. 定义用户角色常量 (USER_ROLE_*) — 集中 deps.py/models/user.py 散落的 inline 字符串
5. 定义用户状态常量 (USER_STATUS_*)
6. 定义通知渠道契约 (NOTIFY_CHANNELS) — 集中 warning_service 散落的 _ALLOWED_NOTIFY_CHANNELS
7. re-export 独立域核心枚举: BindingStatus / ReviewReason / Severity

设计原则:
- 本模块仅依赖标准库 + app.core 叶子模块 (states/review_reasons/alert_rules)，零循环导入风险
- 所有公开符号在 __all__ 中显式声明
- 调用方应从 contracts.py 导入而非从原始模块导入，以便未来迁移
- 不修改原始模块的导出，仅在此聚合 re-export

MAINT-P1-003: 从 57 行升级为契约聚合层
"""

from __future__ import annotations

import logging

from app.core.alert_rules import Severity
from app.core.review_reasons import REVIEW_REASON_LABELS, ReviewReason
from app.core.states import BindingStatus

logger = logging.getLogger(__name__)

# =========================================================================
# 1. 风险等级 (Risk Level)
# =========================================================================
RISK_LEVEL_MAP: dict[int, str] = {
    0: "none",
    1: "low",
    2: "medium",
    3: "high",
    4: "critical",
}

RISK_LEVELS: frozenset[str] = frozenset(RISK_LEVEL_MAP.values())


# =========================================================================
# 2. 预警动作与状态 (Warning Action & Status)
# =========================================================================
WARNING_ACTION_HANDLE = "handle"
WARNING_ACTION_IGNORE = "ignore"
# ISS-058: 预警升级动作
WARNING_ACTION_ESCALATE = "escalated"

WARNING_ACTIONS: frozenset[str] = frozenset(
    {WARNING_ACTION_HANDLE, WARNING_ACTION_IGNORE, WARNING_ACTION_ESCALATE}
)

WARNING_STATUS_PENDING = "pending"
WARNING_STATUS_HANDLED = "handled"
WARNING_STATUS_IGNORED = "ignored"
WARNING_STATUS_ESCALATED = "escalated"

WARNING_STATUSES: frozenset[str] = frozenset(
    {
        WARNING_STATUS_PENDING,
        WARNING_STATUS_HANDLED,
        WARNING_STATUS_IGNORED,
        WARNING_STATUS_ESCALATED,
    }
)


# =========================================================================
# 3. 预警审计动作类型 (Warning Audit Action Types)
# =========================================================================
ACTION_TYPE_WARNING_HANDLE = "warning_handle"
ACTION_TYPE_WARNING_IGNORE = "warning_ignore"
ACTION_TYPE_WARNING_READ = "warning_read"
ACTION_TYPE_WARNING_READ_ALL = "warning_read_all"
# ISS-058: 预警升级审计动作类型
ACTION_TYPE_WARNING_ESCALATE = "warning_escalate"


# =========================================================================
# 4. 用户角色 (User Role) — 集中 deps.py/models/user.py 散落的 inline 字符串
# =========================================================================
USER_ROLE_ADMIN = "admin"
USER_ROLE_COUNSELOR = "counselor"
USER_ROLE_USER = "user"

USER_ROLES: frozenset[str] = frozenset(
    {USER_ROLE_ADMIN, USER_ROLE_COUNSELOR, USER_ROLE_USER}
)


# =========================================================================
# 5. 用户状态 (User Status) — 集中 models/user.py CheckConstraint 散落定义
# =========================================================================
USER_STATUS_ACTIVE = "active"
USER_STATUS_INACTIVE = "inactive"
USER_STATUS_DELETED = "deleted"

USER_STATUSES: frozenset[str] = frozenset(
    {USER_STATUS_ACTIVE, USER_STATUS_INACTIVE, USER_STATUS_DELETED}
)


# =========================================================================
# 6. 通知渠道 (Notification Channels) — 集中 warning_service 散落定义
# =========================================================================
NOTIFY_CHANNEL_IN_APP = "in_app"
NOTIFY_CHANNEL_EMAIL = "email"
NOTIFY_CHANNEL_SMS = "sms"
NOTIFY_CHANNEL_WEBSOCKET = "websocket"

NOTIFY_CHANNELS: frozenset[str] = frozenset(
    {
        NOTIFY_CHANNEL_IN_APP,
        NOTIFY_CHANNEL_EMAIL,
        NOTIFY_CHANNEL_SMS,
        NOTIFY_CHANNEL_WEBSOCKET,
    }
)


# =========================================================================
# 7. Re-export 独立域核心枚举
# =========================================================================
# BindingStatus: 绑定状态 (from states.py)
# ReviewReason: 人工复核原因 (from review_reasons.py)
# REVIEW_REASON_LABELS: 复核原因标签 (from review_reasons.py)
# Severity: 告警严重程度 (from alert_rules.py)


# =========================================================================
# 函数
# =========================================================================
def normalize_risk_level(level: int | None) -> str:
    """将数值风险等级转换为字符串标签。

    P1-F7 修复：原逻辑对未知 level 默认返回 "critical"，会导致：
    - 模型输出异常值（如 5、-1）被误报为最高风险
    - 触发虚假紧急告警和人工干预流程
    - 隐藏上游 bug 而非暴露问题
    改为返回 "unknown" 并记录警告日志，让调用方显式处理异常情况。
    """
    if level is None:
        return "none"
    result = RISK_LEVEL_MAP.get(level)
    if result is None:
        logger.warning(
            "Unknown risk level %r received, expected 0-4; returning 'unknown'",
            level,
        )
        return "unknown"
    return result


def resolve_warning_status(is_handled: bool, handle_action: str | None) -> str:
    if not is_handled:
        return WARNING_STATUS_PENDING
    if handle_action == WARNING_ACTION_IGNORE:
        return WARNING_STATUS_IGNORED
    # ISS-058: 升级状态优先于已处理
    if handle_action == WARNING_ACTION_ESCALATE:
        return WARNING_STATUS_ESCALATED
    return WARNING_STATUS_HANDLED


__all__ = [
    # 风险等级
    "RISK_LEVEL_MAP",
    "RISK_LEVELS",
    # 预警动作与状态
    "WARNING_ACTION_HANDLE",
    "WARNING_ACTION_IGNORE",
    "WARNING_ACTION_ESCALATE",
    "WARNING_ACTIONS",
    "WARNING_STATUS_PENDING",
    "WARNING_STATUS_HANDLED",
    "WARNING_STATUS_IGNORED",
    "WARNING_STATUS_ESCALATED",
    "WARNING_STATUSES",
    # 预警审计动作类型
    "ACTION_TYPE_WARNING_HANDLE",
    "ACTION_TYPE_WARNING_IGNORE",
    "ACTION_TYPE_WARNING_READ",
    "ACTION_TYPE_WARNING_READ_ALL",
    "ACTION_TYPE_WARNING_ESCALATE",
    # 用户角色
    "USER_ROLE_ADMIN",
    "USER_ROLE_COUNSELOR",
    "USER_ROLE_USER",
    "USER_ROLES",
    # 用户状态
    "USER_STATUS_ACTIVE",
    "USER_STATUS_INACTIVE",
    "USER_STATUS_DELETED",
    "USER_STATUSES",
    # 通知渠道
    "NOTIFY_CHANNEL_IN_APP",
    "NOTIFY_CHANNEL_EMAIL",
    "NOTIFY_CHANNEL_SMS",
    "NOTIFY_CHANNEL_WEBSOCKET",
    "NOTIFY_CHANNELS",
    # Re-export 枚举
    "BindingStatus",
    "ReviewReason",
    "REVIEW_REASON_LABELS",
    "Severity",
    # 函数
    "normalize_risk_level",
    "resolve_warning_status",
]
