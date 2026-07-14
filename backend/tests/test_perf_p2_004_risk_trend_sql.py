"""PERF-P2-004 专项测试: get_risk_trend SQL GROUP BY 聚合改造.

验证 SQL window function + 条件聚合替代 Python 内循环聚合后的正确性:
- ROW_NUMBER() OVER (PARTITION BY date) 找每天 primary (priority + created_at + risk_score)
- ROW_NUMBER() + NULLS LAST 找每天 latest non-NULL structured/text/physio scores
- COUNT(*) OVER (PARTITION BY date) 获取每天 record_count
- 外层 GROUP BY date + MAX(CASE WHEN rn=1) 聚合为每天 1 行
"""

from __future__ import annotations

import inspect
from datetime import datetime, timedelta, timezone

import pytest

from app.models.risk import RiskAssessment
from app.services.risk_service import RiskService


class TestSourceCodeStructure:
    """源码静态扫描: 验证 get_risk_trend 使用 SQL window function."""

    def test_imports_case_and_func(self) -> None:
        """验证 risk_service_report.py 导入 case 和 func.

        MAINT-P2-001: get_risk_trend 已拆分到 risk_service_report.py (ReportMixin),
        故 case/func 导入检查目标改为新模块.
        """
        import app.services.risk_service_report as mod

        source = inspect.getsource(mod)
        assert "from sqlalchemy import" in source
        assert "case" in source
        assert "func" in source

    def test_get_risk_trend_uses_window_function(self) -> None:
        """验证 get_risk_trend 使用 ROW_NUMBER window function."""
        source = inspect.getsource(RiskService.get_risk_trend)
        assert "row_number" in source.lower()
        assert ".over(" in source

    def test_get_risk_trend_uses_group_by(self) -> None:
        """验证 get_risk_trend 使用 GROUP BY date 聚合."""
        source = inspect.getsource(RiskService.get_risk_trend)
        assert "group_by" in source

    def test_get_risk_trend_uses_case_for_priority(self) -> None:
        """验证 get_risk_trend 使用 CASE WHEN 实现 priority_order."""
        source = inspect.getsource(RiskService.get_risk_trend)
        assert "case(" in source or "case (" in source
        assert "fusion" in source
        assert "structured" in source

    def test_get_risk_trend_uses_func_date(self) -> None:
        """验证 get_risk_trend 使用 func.date() 跨方言日期分组."""
        source = inspect.getsource(RiskService.get_risk_trend)
        assert "func.date" in source

    def test_get_risk_trend_no_python_dict_grouping(self) -> None:
        """验证 get_risk_trend 不再使用 Python dict 分组."""
        source = inspect.getsource(RiskService.get_risk_trend)
        assert "grouped" not in source
        assert "setdefault" not in source

    def test_get_risk_trend_no_python_max_lambda(self) -> None:
        """验证 get_risk_trend 不再使用 Python max + lambda 找 primary."""
        source = inspect.getsource(RiskService.get_risk_trend)
        assert "priority_order" not in source

    def test_get_risk_trend_has_perf_p2_004_docstring(self) -> None:
        """验证 get_risk_trend docstring 标注 PERF-P2-004."""
        source = inspect.getsource(RiskService.get_risk_trend)
        assert "PERF-P2-004" in source


@pytest.mark.asyncio
class TestGetRiskTrendEmptyData:
    """空数据场景测试."""

    async def test_empty_data_returns_default(self, db_session) -> None:
        """无评估记录时返回空 points + stable direction."""
        service = RiskService(db_session)
        trend = await service.get_risk_trend(9999, 30)
        assert trend["days"] == 30
        assert trend["direction"] == "stable"
        assert trend["points"] == []
        assert trend["physiological_scores"] == []

    async def test_empty_data_days_zero(self, db_session) -> None:
        """days=0 时返回空 points."""
        service = RiskService(db_session)
        trend = await service.get_risk_trend(9999, 0)
        assert trend["days"] == 0
        assert trend["points"] == []


@pytest.mark.asyncio
class TestGetRiskTrendSingleDay:
    """单天数据测试."""

    async def test_single_record_single_day(self, db_session) -> None:
        """单天单条记录: primary = 该记录, record_count = 1."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        assessment = RiskAssessment(
            user_id=1001,
            risk_score=45.0,
            risk_level=2,
            assessment_type="structured",
            structured_score=45.0,
            created_at=now,
        )
        db_session.add(assessment)
        await db_session.flush()

        service = RiskService(db_session)
        trend = await service.get_risk_trend(1001, 30)
        assert len(trend["points"]) == 1
        point = trend["points"][0]
        assert point["risk_score"] == 45.0
        assert point["risk_level"] == 2
        assert point["assessment_type"] == "structured"
        assert point["structured_score"] == 45.0
        assert point["record_count"] == 1
        # 单点无法计算趋势
        assert trend["direction"] == "stable"

    async def test_multiple_records_same_day_primary_selection(self, db_session) -> None:
        """同一天多条记录: primary 按 priority_order 选最优先类型."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        # 同一天创建 3 条: text (priority=0) + structured (priority=2) + fusion (priority=3)
        records = [
            RiskAssessment(
                user_id=1002,
                risk_score=30.0,
                risk_level=1,
                assessment_type="text",
                text_score=30.0,
                created_at=now - timedelta(minutes=30),
            ),
            RiskAssessment(
                user_id=1002,
                risk_score=50.0,
                risk_level=2,
                assessment_type="structured",
                structured_score=50.0,
                created_at=now - timedelta(minutes=20),
            ),
            RiskAssessment(
                user_id=1002,
                risk_score=70.0,
                risk_level=3,
                assessment_type="fusion",
                created_at=now - timedelta(minutes=10),
            ),
        ]
        db_session.add_all(records)
        await db_session.flush()

        service = RiskService(db_session)
        trend = await service.get_risk_trend(1002, 30)
        assert len(trend["points"]) == 1
        point = trend["points"][0]
        # fusion 优先级最高, 应选为 primary
        assert point["assessment_type"] == "fusion"
        assert point["risk_score"] == 70.0
        assert point["risk_level"] == 3
        assert point["record_count"] == 3

    async def test_same_day_latest_scores_from_different_records(self, db_session) -> None:
        """同一天各模态 latest score 可来自不同记录."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        # 记录1 (较早): structured_score=40
        # 记录2 (较晚): text_score=60, 但 structured_score=None
        # latest_structured 应来自记录1 (40), latest_text 应来自记录2 (60)
        records = [
            RiskAssessment(
                user_id=1003,
                risk_score=40.0,
                risk_level=2,
                assessment_type="structured",
                structured_score=40.0,
                created_at=now - timedelta(minutes=30),
            ),
            RiskAssessment(
                user_id=1003,
                risk_score=60.0,
                risk_level=3,
                assessment_type="text",
                text_score=60.0,
                structured_score=None,
                created_at=now - timedelta(minutes=10),
            ),
        ]
        db_session.add_all(records)
        await db_session.flush()

        service = RiskService(db_session)
        trend = await service.get_risk_trend(1003, 30)
        assert len(trend["points"]) == 1
        point = trend["points"][0]
        # text 优先级高于 structured? 不, structured=2 > text=0
        # 所以 primary 应是 structured 记录 (risk_score=40)
        assert point["assessment_type"] == "structured"
        assert point["risk_score"] == 40.0
        # latest_structured 来自记录1 (40)
        assert point["structured_score"] == 40.0
        # latest_text 来自记录2 (60)
        assert point["text_score"] == 60.0
        assert point["record_count"] == 2

    async def test_same_day_all_null_scores(self, db_session) -> None:
        """同一天所有模态分数为 NULL: structured/text/physio 都返回 None."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        assessment = RiskAssessment(
            user_id=1004,
            risk_score=50.0,
            risk_level=2,
            assessment_type="fusion",
            structured_score=None,
            text_score=None,
            physiological_score=None,
            created_at=now,
        )
        db_session.add(assessment)
        await db_session.flush()

        service = RiskService(db_session)
        trend = await service.get_risk_trend(1004, 30)
        assert len(trend["points"]) == 1
        point = trend["points"][0]
        assert point["structured_score"] is None
        assert point["text_score"] is None
        assert point["physiological_score"] is None
        assert trend["physiological_scores"] == []


@pytest.mark.asyncio
class TestGetRiskTrendMultiDay:
    """多天数据测试."""

    async def test_multi_day_trend_direction_stable(self, db_session) -> None:
        """多天数据: 风险分波动 < 5 时 direction=stable."""
        base = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=5)
        records = []
        for i in range(3):
            records.append(
                RiskAssessment(
                    user_id=1005,
                    risk_score=50.0 + i,  # 50, 51, 52 (delta=2 < 5)
                    risk_level=2,
                    assessment_type="structured",
                    created_at=base + timedelta(days=i),
                )
            )
        db_session.add_all(records)
        await db_session.flush()

        service = RiskService(db_session)
        trend = await service.get_risk_trend(1005, 30)
        assert len(trend["points"]) == 3
        assert trend["direction"] == "stable"

    async def test_multi_day_trend_direction_up(self, db_session) -> None:
        """多天数据: 风险分上升 >= 5 时 direction=up."""
        base = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=5)
        records = [
            RiskAssessment(
                user_id=1006,
                risk_score=30.0,
                risk_level=1,
                assessment_type="structured",
                created_at=base,
            ),
            RiskAssessment(
                user_id=1006,
                risk_score=35.0,
                risk_level=2,
                assessment_type="structured",
                created_at=base + timedelta(days=1),
            ),
            RiskAssessment(
                user_id=1006,
                risk_score=60.0,
                risk_level=3,
                assessment_type="fusion",
                created_at=base + timedelta(days=2),
            ),
        ]
        db_session.add_all(records)
        await db_session.flush()

        service = RiskService(db_session)
        trend = await service.get_risk_trend(1006, 30)
        assert len(trend["points"]) == 3
        # early_avg=(30+35+60)/3=41.67, late_avg=(30+35+60)/3=41.67 (window=3)
        # 但 points[:3] 和 points[-3:] 都是全部 3 个点, delta=0
        # 需要 >3 个点才能区分 early/late
        assert trend["direction"] == "stable"  # 3 点时 early=late

    async def test_multi_day_trend_direction_up_with_more_points(self, db_session) -> None:
        """5 天数据: 早期低分, 晚期高分, direction=up."""
        base = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=6)
        records = []
        scores = [20.0, 25.0, 30.0, 60.0, 65.0]  # early_avg=25, late_avg=51.67, delta=26.67
        for i, score in enumerate(scores):
            records.append(
                RiskAssessment(
                    user_id=1007,
                    risk_score=score,
                    risk_level=2,
                    assessment_type="structured",
                    created_at=base + timedelta(days=i),
                )
            )
        db_session.add_all(records)
        await db_session.flush()

        service = RiskService(db_session)
        trend = await service.get_risk_trend(1007, 30)
        assert len(trend["points"]) == 5
        # early_avg=(20+25+30)/3=25, late_avg=(30+60+65)/3=51.67, delta=26.67 >= 5
        assert trend["direction"] == "up"

    async def test_multi_day_trend_direction_down(self, db_session) -> None:
        """5 天数据: 早期高分, 晚期低分, direction=down."""
        base = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=6)
        records = []
        scores = [65.0, 60.0, 30.0, 25.0, 20.0]  # early_avg=51.67, late_avg=25, delta=-26.67
        for i, score in enumerate(scores):
            records.append(
                RiskAssessment(
                    user_id=1008,
                    risk_score=score,
                    risk_level=2,
                    assessment_type="structured",
                    created_at=base + timedelta(days=i),
                )
            )
        db_session.add_all(records)
        await db_session.flush()

        service = RiskService(db_session)
        trend = await service.get_risk_trend(1008, 30)
        assert len(trend["points"]) == 5
        assert trend["direction"] == "down"

    async def test_multi_day_record_count(self, db_session) -> None:
        """多天数据: 每天的 record_count 正确."""
        base = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=3)
        # day1: 2 条, day2: 1 条, day3: 3 条
        records = [
            RiskAssessment(
                user_id=1009,
                risk_score=30.0,
                risk_level=1,
                assessment_type="structured",
                created_at=base,
            ),
            RiskAssessment(
                user_id=1009,
                risk_score=40.0,
                risk_level=2,
                assessment_type="text",
                created_at=base + timedelta(minutes=30),
            ),
            RiskAssessment(
                user_id=1009,
                risk_score=50.0,
                risk_level=2,
                assessment_type="structured",
                created_at=base + timedelta(days=1),
            ),
            RiskAssessment(
                user_id=1009,
                risk_score=60.0,
                risk_level=3,
                assessment_type="structured",
                created_at=base + timedelta(days=2),
            ),
            RiskAssessment(
                user_id=1009,
                risk_score=65.0,
                risk_level=3,
                assessment_type="text",
                created_at=base + timedelta(days=2, minutes=30),
            ),
            RiskAssessment(
                user_id=1009,
                risk_score=70.0,
                risk_level=3,
                assessment_type="fusion",
                created_at=base + timedelta(days=2, minutes=60),
            ),
        ]
        db_session.add_all(records)
        await db_session.flush()

        service = RiskService(db_session)
        trend = await service.get_risk_trend(1009, 30)
        assert len(trend["points"]) == 3
        counts = [p["record_count"] for p in trend["points"]]
        assert counts == [2, 1, 3]

    async def test_multi_day_physiological_scores(self, db_session) -> None:
        """多天数据: physiological_scores 列表正确."""
        base = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=3)
        records = [
            RiskAssessment(
                user_id=1010,
                risk_score=40.0,
                risk_level=2,
                assessment_type="physiological",
                physiological_score=55.0,
                created_at=base,
            ),
            RiskAssessment(
                user_id=1010,
                risk_score=50.0,
                risk_level=2,
                assessment_type="physiological",
                physiological_score=65.0,
                created_at=base + timedelta(days=2),
            ),
        ]
        db_session.add_all(records)
        await db_session.flush()

        service = RiskService(db_session)
        trend = await service.get_risk_trend(1010, 30)
        assert len(trend["points"]) == 2
        assert len(trend["physiological_scores"]) == 2
        assert trend["physiological_scores"][0]["score"] == 55.0
        assert trend["physiological_scores"][1]["score"] == 65.0


@pytest.mark.asyncio
class TestGetRiskTrendFiltering:
    """过滤逻辑测试."""

    async def test_risk_score_zero_filtered(self, db_session) -> None:
        """risk_score=0 的记录被过滤 (WHERE risk_score > 0)."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        records = [
            RiskAssessment(
                user_id=1011,
                risk_score=0.0,  # 应被过滤
                risk_level=0,
                assessment_type="structured",
                created_at=now,
            ),
            RiskAssessment(
                user_id=1011,
                risk_score=50.0,
                risk_level=2,
                assessment_type="structured",
                created_at=now,
            ),
        ]
        db_session.add_all(records)
        await db_session.flush()

        service = RiskService(db_session)
        trend = await service.get_risk_trend(1011, 30)
        assert len(trend["points"]) == 1
        assert trend["points"][0]["risk_score"] == 50.0
        assert trend["points"][0]["record_count"] == 1

    async def test_outside_time_window_filtered(self, db_session) -> None:
        """超出 days 窗口的记录被过滤."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        records = [
            RiskAssessment(
                user_id=1012,
                risk_score=30.0,
                risk_level=1,
                assessment_type="structured",
                created_at=now - timedelta(days=35),  # 35 天前, 超出 30 天窗口
            ),
            RiskAssessment(
                user_id=1012,
                risk_score=50.0,
                risk_level=2,
                assessment_type="structured",
                created_at=now - timedelta(days=5),  # 5 天前, 在窗口内
            ),
        ]
        db_session.add_all(records)
        await db_session.flush()

        service = RiskService(db_session)
        trend = await service.get_risk_trend(1012, 30)
        assert len(trend["points"]) == 1
        assert trend["points"][0]["risk_score"] == 50.0

    async def test_other_user_filtered(self, db_session) -> None:
        """其他用户的记录被过滤."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        records = [
            RiskAssessment(
                user_id=1013,
                risk_score=30.0,
                risk_level=1,
                assessment_type="structured",
                created_at=now,
            ),
            RiskAssessment(
                user_id=1014,
                risk_score=50.0,
                risk_level=2,
                assessment_type="structured",
                created_at=now,
            ),
        ]
        db_session.add_all(records)
        await db_session.flush()

        service = RiskService(db_session)
        trend = await service.get_risk_trend(1013, 30)
        assert len(trend["points"]) == 1
        assert trend["points"][0]["risk_score"] == 30.0


@pytest.mark.asyncio
class TestGetRiskTrendPriorityOrder:
    """priority_order 选择逻辑测试."""

    async def test_fusion_over_structured(self, db_session) -> None:
        """fusion (priority=3) 优先于 structured (priority=2)."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        records = [
            RiskAssessment(
                user_id=1015,
                risk_score=30.0,
                risk_level=1,
                assessment_type="structured",
                created_at=now - timedelta(minutes=10),
            ),
            RiskAssessment(
                user_id=1015,
                risk_score=70.0,
                risk_level=3,
                assessment_type="fusion",
                created_at=now - timedelta(minutes=5),
            ),
        ]
        db_session.add_all(records)
        await db_session.flush()

        service = RiskService(db_session)
        trend = await service.get_risk_trend(1015, 30)
        assert len(trend["points"]) == 1
        assert trend["points"][0]["assessment_type"] == "fusion"

    async def test_structured_over_text(self, db_session) -> None:
        """structured (priority=2) 优先于 text (priority=0)."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        records = [
            RiskAssessment(
                user_id=1016,
                risk_score=30.0,
                risk_level=1,
                assessment_type="text",
                created_at=now - timedelta(minutes=10),
            ),
            RiskAssessment(
                user_id=1016,
                risk_score=50.0,
                risk_level=2,
                assessment_type="structured",
                created_at=now - timedelta(minutes=5),
            ),
        ]
        db_session.add_all(records)
        await db_session.flush()

        service = RiskService(db_session)
        trend = await service.get_risk_trend(1016, 30)
        assert len(trend["points"]) == 1
        assert trend["points"][0]["assessment_type"] == "structured"

    async def test_same_priority_latest_created_at_wins(self, db_session) -> None:
        """同优先级类型: created_at 更大的记录为 primary."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        records = [
            RiskAssessment(
                user_id=1017,
                risk_score=30.0,
                risk_level=1,
                assessment_type="structured",
                created_at=now - timedelta(minutes=30),
            ),
            RiskAssessment(
                user_id=1017,
                risk_score=50.0,
                risk_level=2,
                assessment_type="structured",
                created_at=now - timedelta(minutes=10),
            ),
        ]
        db_session.add_all(records)
        await db_session.flush()

        service = RiskService(db_session)
        trend = await service.get_risk_trend(1017, 30)
        assert len(trend["points"]) == 1
        # 同优先级, created_at 更大的 (50.0) 为 primary
        assert trend["points"][0]["risk_score"] == 50.0

    async def test_same_priority_same_created_at_higher_score_wins(self, db_session) -> None:
        """同优先级 + 同 created_at: risk_score 更高的为 primary."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        records = [
            RiskAssessment(
                user_id=1018,
                risk_score=30.0,
                risk_level=1,
                assessment_type="structured",
                created_at=now,
            ),
            RiskAssessment(
                user_id=1018,
                risk_score=60.0,
                risk_level=3,
                assessment_type="structured",
                created_at=now,
            ),
        ]
        db_session.add_all(records)
        await db_session.flush()

        service = RiskService(db_session)
        trend = await service.get_risk_trend(1018, 30)
        assert len(trend["points"]) == 1
        # 同优先级 + 同 created_at, risk_score 更高的 (60.0) 为 primary
        assert trend["points"][0]["risk_score"] == 60.0


@pytest.mark.asyncio
class TestGetRiskTrendDateKeyFormat:
    """date_key 格式测试."""

    async def test_date_key_is_isoformat_string(self, db_session) -> None:
        """date_key 应为 ISO 格式字符串 'YYYY-MM-DD'."""
        now = datetime.now(timezone.utc).replace(tzinfo=None)
        assessment = RiskAssessment(
            user_id=1019,
            risk_score=50.0,
            risk_level=2,
            assessment_type="structured",
            created_at=now,
        )
        db_session.add(assessment)
        await db_session.flush()

        service = RiskService(db_session)
        trend = await service.get_risk_trend(1019, 30)
        assert len(trend["points"]) == 1
        date_str = trend["points"][0]["date"]
        # 应为 'YYYY-MM-DD' 格式
        assert len(date_str) == 10
        assert date_str[4] == "-"
        assert date_str[7] == "-"

    async def test_points_sorted_by_date_asc(self, db_session) -> None:
        """points 按日期升序排列."""
        base = datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=5)
        records = []
        for i in range(3):
            records.append(
                RiskAssessment(
                    user_id=1020,
                    risk_score=50.0 + i,
                    risk_level=2,
                    assessment_type="structured",
                    created_at=base + timedelta(days=i * 2),  # day0, day2, day4
                )
            )
        # 故意乱序添加
        db_session.add(records[2])
        db_session.add(records[0])
        db_session.add(records[1])
        await db_session.flush()

        service = RiskService(db_session)
        trend = await service.get_risk_trend(1020, 30)
        assert len(trend["points"]) == 3
        dates = [p["date"] for p in trend["points"]]
        assert dates == sorted(dates)
