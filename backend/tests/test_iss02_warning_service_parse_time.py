"""ISS-02 第五轮：WarningService._parse_time_value 纯方法边界测试。

_parse_time_value 是 @staticmethod，无需实例/DB，覆盖：
- time 实例透传；
- "HH:MM:SS" / "HH:MM" / "HH" 部分字符串解析；
- 非数字分量降级为 0；
- hour/minute/second 越界抛 ValueError（M-Svc-9 修复分支）；
- 非 str/非 time 输入返回 time(0,0,0)。

说明：warning_service 顶层不导入 numpy，但经 app.services.__init__ 会拉起重依赖链，
本地 coverage.py 插桩时偶发 SIGSEGV；pass/fail 已稳定验证，覆盖率以稳定 CI 为准。
"""

from __future__ import annotations

from datetime import time

import pytest

from app.services.warning_service import WarningService


def test_parse_time_passthrough_time_instance():
    t = time(8, 30, 15)
    assert WarningService._parse_time_value(t) is t


def test_parse_time_full_hms_string():
    assert WarningService._parse_time_value("22:15:30") == time(22, 15, 30)


def test_parse_time_hh_mm_string_defaults_seconds():
    assert WarningService._parse_time_value("07:05") == time(7, 5, 0)


def test_parse_time_hour_only_string():
    assert WarningService._parse_time_value("09") == time(9, 0, 0)


def test_parse_time_non_numeric_parts_default_zero():
    # 非数字分量 → 各自降级为 0
    assert WarningService._parse_time_value("aa:bb:cc") == time(0, 0, 0)


def test_parse_time_hour_out_of_range_raises():
    with pytest.raises(ValueError, match="hour"):
        WarningService._parse_time_value("24:00:00")


def test_parse_time_minute_out_of_range_raises():
    with pytest.raises(ValueError, match="minute"):
        WarningService._parse_time_value("12:60:00")


def test_parse_time_second_out_of_range_raises():
    with pytest.raises(ValueError, match="second"):
        WarningService._parse_time_value("12:00:60")


def test_parse_time_non_str_non_time_returns_midnight():
    assert WarningService._parse_time_value(12345) == time(0, 0, 0)
    assert WarningService._parse_time_value(None) == time(0, 0, 0)
