from __future__ import annotations

RISK_LEVEL_MAP: dict[int, str] = {
    0: "none",
    1: "low",
    2: "medium",
    3: "high",
    4: "critical",
}

WARNING_ACTION_HANDLE = "handle"
WARNING_ACTION_IGNORE = "ignore"

ACTION_TYPE_WARNING_HANDLE = "warning_handle"
ACTION_TYPE_WARNING_IGNORE = "warning_ignore"
ACTION_TYPE_WARNING_READ = "warning_read"
ACTION_TYPE_WARNING_READ_ALL = "warning_read_all"


def normalize_risk_level(level: int | None) -> str:
    if level is None:
        return "none"
    return RISK_LEVEL_MAP.get(level, "critical")


def resolve_warning_status(is_handled: bool, handle_action: str | None) -> str:
    if not is_handled:
        return "pending"
    if handle_action == WARNING_ACTION_IGNORE:
        return "ignored"
    return "handled"
