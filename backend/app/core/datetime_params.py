"""API 层日期 / 时间范围参数解析（M10 修复，2026-10-20 ROUND_19）。

问题（审查报告 M10）
-------------------
查询参数 ``end_date=2026-10-20`` 经 ``datetime.fromisoformat`` 得到
``2026-10-20 00:00:00``，服务层再用 ``created_at <= end_dt`` 过滤 ⇒
**当天 00:00 之后的数据被整体排除**：用户选「10-01 ~ 10-20」实际只拿到
10-01 ~ 10-19 23:59。用户数据历史、管理端危机事件列表都踩过这一条。

口径（写死在这里，调用方不再各自解释）
------------------------------------
- **日期型**（只有日期、没有时间部分，如 ``2026-10-20``）：视为**闭区间含当天整日** ——
  起点取当天 ``00:00:00``，终点取当天 ``23:59:59.999999``。
- **日期时间型**（带时间部分，如 ``2026-10-20T12:30:00``）：按字面值使用，不再扩张
  （调用方显式给了时刻，扩张会把 12:30 之后的记录也算进来）。
- aware datetime 统一转 **naive UTC**：DB 列是 ``timestamp without time zone``，
  与之比较的必须是无时区的 UTC 值。

为什么放在 ``app.core``
----------------------
两个调用方（``app/api/v1/user_data.py``、``app/api/v1/review.py``）原先各写一份
解析，其中一份还会把时区处理漏掉；口径必须只有一处实现，否则必然再次漂移。
"""

from __future__ import annotations

from datetime import date, datetime, time, timezone


def _to_naive_utc(dt: datetime) -> datetime:
    """aware → naive UTC；naive 原样返回（调用方需保证传入的是 UTC 口径）。"""
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc).replace(tzinfo=None)
    return dt


def _end_of_day(d: date) -> datetime:
    return datetime.combine(d, time.max)


def parse_datetime_param(
    value: str | None,
    *,
    field: str = "end_date",
    inclusive_end: bool = True,
) -> datetime | None:
    """解析单个日期 / 日期时间查询参数为 naive UTC datetime。

    Args:
        value: 原始字符串；空 / None 直接返回 None。
        field: 参数名，仅用于错误信息。
        inclusive_end: 日期型参数是否扩张到当天结束（23:59:59.999999）。
            传 False 时按字面 00:00:00 使用 —— 留给"就是要当天零点"的调用方，
            默认值即 M10 修复口径。

    Raises:
        ValueError: 不是合法 ISO8601 日期 / 日期时间。
    """
    if value is None:
        return None
    text = value.strip()
    if not text:
        return None

    # 先试纯日期：命中即按"整天闭区间"口径处理
    try:
        only_date = date.fromisoformat(text)
    except ValueError:
        only_date = None

    if only_date is not None:
        if inclusive_end:
            return _end_of_day(only_date)
        return datetime.combine(only_date, time.min)

    try:
        parsed = datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError(
            f"{field} 必须是 ISO8601 日期(YYYY-MM-DD)或日期时间(YYYY-MM-DDTHH:MM:SS)，"
            f"当前值: {value!r}"
        ) from exc
    return _to_naive_utc(parsed)


def parse_range_params(
    start_value: str | None,
    end_value: str | None,
    *,
    start_field: str = "start_date",
    end_field: str = "end_date",
) -> tuple[datetime | None, datetime | None]:
    """解析 (start, end) 一对范围参数；start 保持当天 00:00，end 扩张到当天结束。

    两个参数独立解析：只有 end 传了日期型时同样扩张（半开区间由调用方决定）。
    """
    return (
        parse_datetime_param(start_value, field=start_field, inclusive_end=False),
        parse_datetime_param(end_value, field=end_field, inclusive_end=True),
    )
