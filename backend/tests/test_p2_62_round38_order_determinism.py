"""ROUND_38：排序确定性收口闸门（同型风险清零）。

背景：ROUND_23b 修掉预警分页的单键排序，并在文档里记账「全仓另有 10+ 处
``order_by(<created_at>.desc())`` 同型风险，本轮不动」。此后 ROUND_24/25
已把分页（LIMIT/OFFSET）全部补上唯一次级键；ROUND_38 清掉剩余**非分页但
同样影响「选哪条 / 输出顺序」**的单键排序：

- 时间线、CSV 导出、最近 N 条、窗口取最新、批量扫描边界 —— 全部补 id 次级键；
- 语义安全的单键排序**不改**，豁免理由登记在下方 ``EXEMPTIONS``：
  唯一列（``SystemConfig.config_key`` / ``WarningThreshold.level``）、
  存在性查询（``review_service`` pending 去重、``drift`` dedup）、
  内部分组 cap（anomaly 扫描）。唯一约束若被删，本文件会红。

测试分两层：
1) 行为层：捕获型 DB 替身调用生产方法，对**实际下发语句**断言排序键
   （不接受「自建 SQL 断言自己」——ROUND_00 审计 B3 的教训）；
2) 结构层：表驱动 AST 见证（API 函数难以直接调用），断言目标函数内每个
   ``.order_by(...)`` / 窗口 ``over(order_by=...)`` 都含唯一次级键。
"""
from __future__ import annotations

import ast
from datetime import date
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND = Path(__file__).resolve().parents[1]


class _Result:
    """最小结果替身：覆盖生产代码用到的 scalars/all/scalar_one(_or_none)。"""

    def __init__(self, rows=None, one=None):
        self._rows = list(rows or [])
        self._one = one

    def scalars(self):
        return self

    def all(self):
        return list(self._rows)

    def scalar_one(self):
        return self._one

    def scalar_one_or_none(self):
        return self._one


class _DB:
    """按调用顺序返回预设结果，并记录生产实现真正下发的语句。"""

    def __init__(self, results):
        self._results = list(results)
        self.statements = []

    async def execute(self, stmt):
        self.statements.append(stmt)
        return self._results.pop(0) if self._results else _Result()

    async def commit(self):
        return None


class _StreamRows:
    def scalars(self):
        return self

    def __aiter__(self):
        return self

    async def __anext__(self):
        raise StopAsyncIteration


class _StreamDB:
    def __init__(self):
        self.statements = []

    async def stream(self, stmt):
        self.statements.append(stmt)
        return _StreamRows()


def _sql(stmt) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": True})).lower()


def _assert_tie_break(stmt, *fragments: str) -> None:
    sql = _sql(stmt)
    assert "order by" in sql, f"缺少 ORDER BY：{sql}"
    for fragment in fragments:
        assert fragment in sql, f"ORDER BY 缺少唯一次级键 {fragment!r}：{sql}"


class TestBehavioralOrderDeterminism:
    """直接调用生产方法，断言真实下发的 SQL（变异去掉 id 键即红）。"""

    @pytest.mark.asyncio
    async def test_counselor_user_detail_timelines_have_tie_break(self):
        from app.services.counselor_service_user import UserMixin

        class _Stub(UserMixin):
            def __init__(self, db):
                self.db = db

        user = SimpleNamespace(
            id=7, username="u", nickname=None, status="active"
        )
        db = _DB(
            [
                _Result(one=SimpleNamespace()),  # binding
                _Result(one=user),  # user
                _Result(one=None),  # latest risk
                _Result(rows=[]),  # risk history
                _Result(rows=[]),  # assessments
                _Result(rows=[]),  # interventions
            ]
        )
        await _Stub(db).get_user_detail(1, 7, tenant_id=1)
        assert len(db.statements) == 6
        _assert_tie_break(
            db.statements[3], "risk_assessments.created_at desc", "risk_assessments.id desc"
        )
        _assert_tie_break(
            db.statements[4],
            "structured_assessments.created_at desc",
            "structured_assessments.id desc",
        )
        _assert_tie_break(
            db.statements[5],
            "intervention_plans.created_at desc",
            "intervention_plans.id desc",
        )

    @pytest.mark.asyncio
    async def test_crisis_export_has_tie_break(self):
        from app.services.crisis_export_service import CrisisExportService

        db = _StreamDB()
        chunks = [
            chunk
            async for chunk in CrisisExportService(db).iter_export_crisis_csv(
                date(2026, 1, 1), date(2026, 1, 2)
            )
        ]
        assert chunks, "导出至少应产出表头"
        assert len(db.statements) == 1
        _assert_tie_break(
            db.statements[0], "crisis_events.created_at desc", "crisis_events.id desc"
        )

    @pytest.mark.asyncio
    async def test_intervention_active_plan_has_tie_break(self):
        from app.services.intervention_service import InterventionService

        db = _DB([_Result(one=None)])
        result = await InterventionService(db).get_active(1, create_missing=False)
        assert result["plan"]["id"] is None
        assert len(db.statements) == 1
        _assert_tie_break(
            db.statements[0],
            "intervention_plans.created_at desc",
            "intervention_plans.id desc",
        )

    @pytest.mark.asyncio
    async def test_risk_report_recent_has_tie_break(self):
        from app.services.risk_service import RiskService

        db = _DB([_Result(rows=[])])
        await RiskService(db).get_risk_report(1)
        assert len(db.statements) == 1
        _assert_tie_break(
            db.statements[0], "risk_assessments.created_at desc", "risk_assessments.id desc"
        )

    @pytest.mark.asyncio
    async def test_warning_trigger_previous_has_tie_break(self):
        from app.services.risk_service import RiskService

        current = SimpleNamespace(id=10, risk_level=0)
        db = _DB([_Result(one=None), _Result(one=None)])
        result = await RiskService(db)._check_warning_trigger(1, current)
        assert result is None
        _assert_tie_break(
            db.statements[0], "risk_assessments.created_at desc", "risk_assessments.id desc"
        )

    @pytest.mark.asyncio
    async def test_recent_audit_events_have_tie_break(self):
        from app.api.v1.ops_dashboard import _get_recent_audit_events

        db = _DB([_Result(rows=[])])
        rows = await _get_recent_audit_events(db, limit=10)
        assert rows == []
        assert len(db.statements) == 1
        sql = _sql(db.statements[0])
        _assert_tie_break(
            db.statements[0], "operation_logs.created_at desc", "operation_logs.id desc"
        )
        assert "limit" in sql


# 表驱动结构见证：(文件, 函数, 按源码顺序的 order_by 期望次级键)
ORDER_BY_TARGETS = [
    (
        "app/services/counselor_service_user.py",
        "get_user_detail",
        ["RiskAssessment.id", "StructuredAssessment.id", "InterventionPlan.id"],
    ),
    ("app/services/crisis_export_service.py", "iter_export_crisis_csv", ["CrisisEvent.id"]),
    ("app/services/intervention_service.py", "get_active", ["InterventionPlan.id", "InterventionTask.id"]),
    ("app/services/risk_service_report.py", "get_risk_report", ["RiskAssessment.id"]),
    (
        "app/services/risk_service_warning.py",
        "_check_warning_trigger",
        ["RiskAssessment.id", "UserCounselorBinding.id"],
    ),
    (
        "app/services/content_service.py",
        "get_recommendations",
        [
            "EducationContent.category.asc()",
            "EducationContent.id",
            "EducationContent.id",
        ],
    ),
    ("app/api/v1/content_governance.py", "get_content_history", ["OperationLog.id"]),
    ("app/monitoring/escalation.py", "run_escalation_check", ["OperationLog.id"]),
    ("app/tasks/alerts.py", "_archive_impl", ["OperationLog.id"]),
    ("app/services/observability/aggregate.py", "_fetch_am_sync_failures", ["OperationLog.id"]),
    ("app/services/observability/aggregate.py", "_fetch_recent_flushes", ["OperationLog.id"]),
    ("app/services/observability/query.py", "_fetch_fired_rows", ["OperationLog.id"]),
    ("app/api/v1/silences.py", "list_active_silences", ["AlertSilence.id"]),
]

WINDOW_TARGETS = [
    ("app/services/anomaly_detection_service.py", "detect_off_hours", "OperationLog.id"),
]


def _function_node(rel: str, name: str) -> tuple[str, ast.AST]:
    src = (BACKEND / rel).read_text(encoding="utf-8")
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name == name:
            return src, node
    raise AssertionError(f"{rel} 中找不到函数 {name}")


def _call_argument_segments(src: str, node: ast.AST, attr: str) -> list[str]:
    """只取 ``.attr(...)`` 的**实参文本**，不含链上的 select/where 列。

    若取整个 Call 节点，``select(RiskAssessment.id, ...).order_by(created_at)``
    会把 select 列的 ``.id`` 也算进来，让「缺 id 次级键」的变异误判为绿。
    """
    found: list[tuple[int, int, str]] = []
    for n in ast.walk(node):
        if not (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == attr
        ):
            continue
        parts = [ast.get_source_segment(src, a) for a in n.args]
        parts += [ast.get_source_segment(src, kw.value) for kw in n.keywords]
        text = ", ".join(p for p in parts if p)
        if text:
            found.append((n.lineno, n.col_offset, text))
    return [text for _, _, text in sorted(found)]


def _over_order_by_segments(src: str, node: ast.AST) -> list[str]:
    """窗口 ``.over(order_by=...)`` 只取 order_by 关键字的值文本。"""
    found: list[tuple[int, int, str]] = []
    for n in ast.walk(node):
        if not (
            isinstance(n, ast.Call)
            and isinstance(n.func, ast.Attribute)
            and n.func.attr == "over"
        ):
            continue
        for kw in n.keywords:
            if kw.arg == "order_by":
                text = ast.get_source_segment(src, kw.value)
                if text:
                    found.append((n.lineno, n.col_offset, text))
    return [text for _, _, text in sorted(found)]


class TestStructuralOrderDeterminism:
    """结构见证：目标函数内每个排序点都必须含唯一次级键。"""

    @pytest.mark.parametrize("rel, func, expected", ORDER_BY_TARGETS)
    def test_every_order_by_has_unique_tie_break(self, rel, func, expected):
        src, node = _function_node(rel, func)
        segments = _call_argument_segments(src, node, "order_by")
        assert len(segments) == len(expected), (
            f"{rel}::{func} 的 order_by 数量变了（{len(segments)} != {len(expected)}）；"
            "新增/删除排序点需同步更新本闸门"
        )
        for segment, key in zip(segments, expected):
            assert key in segment, f"{rel}::{func} 的排序点缺少 {key}：{segment}"

    @pytest.mark.parametrize("rel, func, key", WINDOW_TARGETS)
    def test_window_order_by_has_unique_tie_break(self, rel, func, key):
        src, node = _function_node(rel, func)
        windows = _over_order_by_segments(src, node)
        assert windows, f"{rel}::{func} 未找到窗口 order_by"
        for window in windows:
            assert key in window, f"{rel}::{func} 的窗口排序缺少 {key}：{window}"


class TestExemptions:
    """豁免不是口头承诺：唯一列一旦失去唯一约束，这里会红。"""

    def test_config_key_is_unique(self):
        from app.models.admin import SystemConfig

        assert SystemConfig.__table__.c.config_key.unique is True

    def test_threshold_level_is_unique(self):
        from app.models.admin import WarningThreshold

        assert WarningThreshold.__table__.c.level.unique is True
