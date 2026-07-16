#!/usr/bin/env python
"""STAB-P2-007: 部署窗口检查脚本.

在 CI/CD pipeline 中执行, 验证当前时间是否在允许的部署窗口内.
不在窗口内时返回非零退出码, 阻塞部署.

环境变量配置:
    DEPLOY_WINDOW_START      窗口开始时间 (HH:MM, 24h), 默认 "09:00"
    DEPLOY_WINDOW_END        窗口结束时间 (HH:MM, 24h), 默认 "18:00"
    DEPLOY_WINDOW_DAYS       允许的星期 (逗号分隔: mon,tue,wed,thu,fri,sat,sun),
                             默认 "mon,tue,wed,thu,fri"
    DEPLOY_WINDOW_TIMEZONE   时区 (IANA 名称), 默认 "Asia/Shanghai"
    DEPLOY_WINDOW_EMERGENCY  紧急覆盖 ("true"/"1" 跳过检查), 默认 ""

退出码:
    0  在部署窗口内 (允许部署)
    1  不在部署窗口内 (阻塞部署)
    2  配置错误
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, time, timedelta

try:
    from zoneinfo import ZoneInfo
except ImportError:
    # Python < 3.9 回退 (CI 使用 3.12, 此分支仅防御)
    ZoneInfo = None  # type: ignore[assignment,misc]

DAY_NAME_TO_INT: dict[str, int] = {
    "mon": 0,
    "tue": 1,
    "wed": 2,
    "thu": 3,
    "fri": 4,
    "sat": 5,
    "sun": 6,
}

EXIT_ALLOWED = 0
EXIT_BLOCKED = 1
EXIT_CONFIG_ERROR = 2


def _parse_time(value: str, env_name: str) -> time:
    """解析 HH:MM 格式时间字符串."""
    try:
        parts = value.strip().split(":")
        if len(parts) != 2:
            raise ValueError(f"expected HH:MM, got '{value}'")
        hour, minute = int(parts[0]), int(parts[1])
        return time(hour=hour, minute=minute)
    except (ValueError, AttributeError) as exc:
        print(f"[deploy-window] {env_name} 配置错误: {exc}", file=sys.stderr)
        raise SystemExit(EXIT_CONFIG_ERROR)


def _parse_days(value: str) -> set[int]:
    """解析星期列表 (mon,tue,...) 为整数集合."""
    if not value or not value.strip():
        return {0, 1, 2, 3, 4}  # 默认周一至周五
    days: set[int] = set()
    for token in value.split(","):
        token = token.strip().lower()
        if token not in DAY_NAME_TO_INT:
            print(
                f"[deploy-window] DEPLOY_WINDOW_DAYS 包含无效星期: '{token}'",
                file=sys.stderr,
            )
            raise SystemExit(EXIT_CONFIG_ERROR)
        days.add(DAY_NAME_TO_INT[token])
    return days


def _get_timezone(name: str):
    """获取时区对象."""
    if ZoneInfo is None:
        print("[deploy-window] zoneinfo 不可用, 请使用 Python >= 3.9", file=sys.stderr)
        raise SystemExit(EXIT_CONFIG_ERROR)
    try:
        return ZoneInfo(name)
    except Exception as exc:
        print(
            f"[deploy-window] DEPLOY_WINDOW_TIMEZONE 无效时区 '{name}': {exc}",
            file=sys.stderr,
        )
        raise SystemExit(EXIT_CONFIG_ERROR)


def is_within_window(
    now: datetime,
    start: time,
    end: time,
    allowed_days: set[int],
) -> bool:
    """检查 ``now`` 是否在 [start, end) 时间窗口内且星期允许.

    支持跨日窗口 (如 22:00~06:00 夜间窗口):
        - start < end: 同日窗口 (09:00~18:00)
        - start > end: 跨日窗口 (22:00~次日06:00), 当前时间 >= start 或 < end
    """
    if now.weekday() not in allowed_days:
        return False

    current_time = now.time()

    if start < end:
        # 同日窗口: start <= current < end
        return start <= current_time < end
    elif start > end:
        # 跨日窗口: current >= start OR current < end
        return current_time >= start or current_time < end
    else:
        # start == end: 空窗口, 不允许
        return False


def check_deployment_window() -> int:
    """主检查函数, 返回退出码."""
    # 紧急覆盖
    emergency = os.environ.get("DEPLOY_WINDOW_EMERGENCY", "").strip().lower()
    if emergency in ("true", "1", "yes"):
        print("[deploy-window] 紧急覆盖已激活, 跳过部署窗口检查")
        return EXIT_ALLOWED

    start_str = os.environ.get("DEPLOY_WINDOW_START", "09:00")
    end_str = os.environ.get("DEPLOY_WINDOW_END", "18:00")
    days_str = os.environ.get("DEPLOY_WINDOW_DAYS", "mon,tue,wed,thu,fri")
    tz_name = os.environ.get("DEPLOY_WINDOW_TIMEZONE", "Asia/Shanghai")

    start = _parse_time(start_str, "DEPLOY_WINDOW_START")
    end = _parse_time(end_str, "DEPLOY_WINDOW_END")
    allowed_days = _parse_days(days_str)
    tz = _get_timezone(tz_name)

    now = datetime.now(tz)
    allowed = is_within_window(now, start, end, allowed_days)

    day_name = ["mon", "tue", "wed", "thu", "fri", "sat", "sun"][now.weekday()]
    print(
        f"[deploy-window] 当前时间: {now.strftime('%Y-%m-%d %H:%M:%S %Z')} ({day_name})"
    )
    print(
        f"[deploy-window] 允许窗口: {start.strftime('%H:%M')}-{end.strftime('%H:%M')} "
        f"({','.join(sorted(DAY_NAME_TO_INT, key=lambda d: DAY_NAME_TO_INT[d]) ) if len(allowed_days) == 7 else ','.join(d for d in ['mon','tue','wed','thu','fri','sat','sun'] if DAY_NAME_TO_INT[d] in allowed_days)}) "
        f"[{tz_name}]"
    )

    if allowed:
        print("[deploy-window] ✅ 在部署窗口内, 允许部署")
        return EXIT_ALLOWED
    else:
        print("[deploy-window] ❌ 不在部署窗口内, 部署被阻塞", file=sys.stderr)
        print(
            "[deploy-window] 如需紧急部署, 设置 DEPLOY_WINDOW_EMERGENCY=true",
            file=sys.stderr,
        )
        return EXIT_BLOCKED


def main() -> None:
    sys.exit(check_deployment_window())


if __name__ == "__main__":
    main()
