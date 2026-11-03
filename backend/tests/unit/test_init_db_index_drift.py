"""迁移 job 的期望索引自检 / 可选补建回归测试。

背景: 全新部署走 ``Base.metadata.create_all + alembic stamp head``。改前
``uq_canary_records_single_running`` 只存在于迁移 n2b3c4d5e6f7，create_all
不会创建它 → 每个新库天生漂移。现在该索引已在 ``CanaryRecord.__table_args__``
声明，新库自带；自检保留用于兜住历史库漏跑迁移的漂移。迁移 job 需要：
(a) 默认只读自检，缺失时告警并列出补建 SQL；
(b) 幂等补建只在 ``--repair-drift`` 后面执行，绝不在默认路径改生产库结构。
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

BACKEND_ROOT = Path(__file__).resolve().parents[2]


def _load_init_db():
    spec = importlib.util.spec_from_file_location(
        "init_db_under_test", BACKEND_ROOT / "scripts" / "init_db.py"
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    # dataclass 在 exec 期需要从 sys.modules 反查模块，先注册再执行。
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


init_db = _load_init_db()


class _FakeResult:
    def __init__(self, rows):
        self._rows = rows

    def fetchall(self):
        return self._rows


class _FakeConnection:
    def __init__(self, existing_indexes):
        self.existing_indexes = existing_indexes
        self.executed: list[str] = []

    async def execute(self, statement, *_args, **_kwargs):
        sql = str(statement)
        self.executed.append(sql)
        if "sqlite_master" in sql or "pg_indexes" in sql:
            return _FakeResult([(name,) for name in self.existing_indexes])
        return _FakeResult([])


class _FakeBegin:
    def __init__(self, conn):
        self.conn = conn

    async def __aenter__(self):
        return self.conn

    async def __aexit__(self, *_exc):
        return False


class _FakeEngine:
    def __init__(self, existing_indexes):
        self.dialect = SimpleNamespace(name="sqlite")
        self.conn = _FakeConnection(existing_indexes)

    def begin(self):
        return _FakeBegin(self.conn)


def test_expected_indexes_include_canary_idempotent_ddl():
    """清单必须包含 canary 唯一索引，且 DDL 是幂等 + 部分索引语义。"""
    canary = {idx.name: idx for idx in init_db.EXPECTED_INDEXES}[
        "uq_canary_records_single_running"
    ]
    assert canary.table == "canary_records"
    assert canary.auto_repair is True
    assert "CREATE UNIQUE INDEX IF NOT EXISTS" in canary.ddl
    assert "COALESCE(route_prefix, '')" in canary.ddl
    assert "status = 'running'" in canary.ddl


def test_find_missing_indexes_flags_canary_drift():
    existing = {"uq_risk_assessments_latest", "uq_warning_notifications_assessment"}
    missing = init_db.find_missing_indexes(existing)
    assert [idx.name for idx in missing] == ["uq_canary_records_single_running"]


@pytest.mark.asyncio
async def test_default_check_is_read_only_and_lists_repair_sql(capsys):
    """默认路径：只查询、不执行任何 DDL，并把补建 SQL 打到日志。"""
    engine = _FakeEngine({"uq_risk_assessments_latest", "uq_warning_notifications_assessment"})

    missing = await init_db.check_index_drift(engine_obj=engine)

    assert [idx.name for idx in missing] == ["uq_canary_records_single_running"]
    assert len(engine.conn.executed) == 1, "默认路径只能有一条只读查询"
    assert "sqlite_master" in engine.conn.executed[0]
    assert not any("CREATE UNIQUE INDEX" in sql for sql in engine.conn.executed)

    stderr = capsys.readouterr().err
    assert "CREATE UNIQUE INDEX IF NOT EXISTS uq_canary_records_single_running" in stderr
    assert "--repair-drift" in stderr


@pytest.mark.asyncio
async def test_repair_drift_only_creates_auto_repair_index():
    """--repair-drift 只补建 auto_repair 的白名单索引，并复用 IF NOT EXISTS。"""
    engine = _FakeEngine({"uq_risk_assessments_latest", "uq_warning_notifications_assessment"})

    remaining = await init_db.check_index_drift(repair_drift=True, engine_obj=engine)

    assert remaining == []
    ddl = [sql for sql in engine.conn.executed if "CREATE UNIQUE INDEX" in sql]
    assert len(ddl) == 1
    assert "uq_canary_records_single_running" in ddl[0]
    assert "IF NOT EXISTS" in ddl[0]


@pytest.mark.asyncio
async def test_repair_drift_does_not_touch_manual_indexes():
    """未标记 auto_repair 的缺失索引只告警，不自动建（避免默认改库）。"""
    engine = _FakeEngine({"uq_risk_assessments_latest"})

    remaining = await init_db.check_index_drift(repair_drift=True, engine_obj=engine)

    names = {idx.name for idx in remaining}
    assert names == {"uq_warning_notifications_assessment"}
    created = [sql for sql in engine.conn.executed if "CREATE UNIQUE INDEX" in sql]
    assert len(created) == 1
    assert "uq_canary_records_single_running" in created[0]
    assert "uq_warning_notifications_assessment" not in created[0]


@pytest.mark.asyncio
async def test_no_drift_returns_empty():
    engine = _FakeEngine({idx.name for idx in init_db.EXPECTED_INDEXES})
    missing = await init_db.check_index_drift(engine_obj=engine)
    assert missing == []
    assert len(engine.conn.executed) == 1


def test_cli_flag_defaults_off():
    """开关默认关闭：迁移 job 默认不得改生产库结构。"""
    assert init_db.parse_args([]).repair_drift is False
    assert init_db.parse_args(["--repair-drift"]).repair_drift is True
