"""
ROUND_23 补漏：预警列表分页的**确定性排序**闸门。

起因（CI 实锤）：29bf28a 的 backend-coverage 上
`tests/services/test_counselor_service.py::TestListWarningsExtended::test_with_warnings`
偶发失败——`assert 'low' == 'high'`，即 `items[0]` 拿到的不是 current_level=3
那条。根因是 `list_warnings` 只按 `created_at.desc()` 单键排序：同一秒内
产生的多条告警 created_at 相同 ⇒ 顺序由 DB 决定 ⇒ 配 LIMIT/OFFSET 时
同一条可能在相邻两页**重复出现或被整页跳过**（生产侧的真缺陷，不只是测试问题）。

修：加 `id.desc()` 作确定性 tie-break（咨询师端 + 用户端同型两处）。

为什么用**结构见证**而不是行为断言：本机 SQLite 恰好按插入序返回，
去掉二级排序在本机也不会红 ⇒ 行为断言没有区分力（无效变异）。因此这里
断言 SQL 语句**真的包含二级排序键**（编译后的 SQL 文本），变异（去掉
id.desc）会让本闸门红。

记账（ROUND_38 更新）：ROUND_23b 时列出的同型风险已由 ROUND_24/25 与
ROUND_38 两批清零——分页查询均带唯一次级键；剩余单键排序均为语义安全项
（唯一列 / 存在性查询 / 扫描 cap），清单与豁免理由见
`test_p2_62_round38_order_determinism.py`。
"""
from __future__ import annotations

import pytest

from app.services.counselor_service_warning import WarningMixin as CounselorWarningMixin
from app.services.warning_service import WarningService


def _compiled(stmt) -> str:
    return str(stmt.compile(compile_kwargs={"literal_binds": True})).lower()


class _CaptureResult:
    """最小结果替身：list_warnings 只用到 scalars().all() 与 scalar_one()。"""

    def scalars(self):
        return self

    def all(self):
        return []

    def scalar_one(self):
        return 0


class _CaptureDB:
    """记录生产实现真正下发的语句，供编译后做结构断言。"""

    def __init__(self) -> None:
        self.statements = []

    async def execute(self, stmt):
        self.statements.append(stmt)
        return _CaptureResult()


class _CounselorWarningStub(CounselorWarningMixin):
    def __init__(self, db) -> None:
        self.db = db


class TestWarningListDeterministicOrdering:
    """LIMIT/OFFSET 必须配确定性 ORDER BY（同 created_at  행 不得靠 DB 心情排序）。"""

    @pytest.mark.asyncio
    async def test_counselor_list_warnings_has_tie_break(self):
        db = _CaptureDB()
        await _CounselorWarningStub(db).list_warnings(
            counselor_id=1, page=1, page_size=10, only_unhandled=False
        )
        assert len(db.statements) == 2, "应恰好发出数据查询 + count 两条语句"
        sql = _compiled(db.statements[0])
        assert "order by" in sql
        assert "created_at desc" in sql
        assert ".id desc" in sql, (
            "ORDER BY 必须含 id 二级排序键（created_at 非唯一）"
        )
        assert "limit" in sql and "offset" in sql, "分页必须下推到 SQL"

    @pytest.mark.asyncio
    async def test_user_list_warnings_has_tie_break(self):
        db = _CaptureDB()
        await WarningService(db).list_warnings(
            user_id=1, page=1, page_size=10, is_read=None
        )
        assert len(db.statements) == 2, "应恰好发出数据查询 + count 两条语句"
        sql = _compiled(db.statements[0])
        assert "created_at desc" in sql
        assert ".id desc" in sql, (
            "ORDER BY 必须含 id 二级排序键（created_at 非唯一）"
        )
        assert "limit" in sql and "offset" in sql, "分页必须下推到 SQL"

    def test_services_declare_secondary_sort_key(self):
        """源码级见证：两个 list_warnings 的实现都声明了 id 二级排序。

        变异（去掉 `WarningNotification.id.desc()`）⇒ 本用例红。
        """
        from pathlib import Path

        import app

        root = Path(app.__file__).resolve().parent
        for rel in (
            "services/counselor_service_warning.py",
            "services/warning_service.py",
        ):
            text = (root / rel).read_text(encoding="utf-8")
            assert "WarningNotification.created_at.desc()," in text, (
                f"{rel} 的 list_warnings 缺少 created_at 排序"
            )
            assert "WarningNotification.id.desc()," in text, (
                f"{rel} 的 list_warnings 缺少 id 二级排序（created_at 非唯一，"
                "LIMIT/OFFSET 会重复/漏行）"
            )

    @pytest.mark.parametrize("service_cls", [CounselorWarningMixin, WarningService])
    def test_services_are_importable(self, service_cls):
        """两个服务类仍可导入（防止改排序时误伤模块结构）。"""
        assert hasattr(service_cls, "list_warnings")
