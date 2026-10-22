"""ROUND_24 / T1：全仓分页排序确定性闸门（AST 结构见证）。

背景（ROUND_23 补漏 `2d2eb38` 的推广）：
`ORDER BY created_at DESC` 单键排序在 `created_at` 并列时顺序由 DB 决定
（SQLite / PostgreSQL 都**不保证**任何顺序）。一旦配上 `OFFSET/LIMIT` 翻页，
同一条记录可能在相邻两页重复出现，或者整条被跳过。

本闸门**读生产源码**（AST，不做字符串匹配），对每个
`order_by(...<非唯一排序列>...)` 站点判定三件事：
  1. args 里有没有次级排序键（id / pk）；
  2. 该 statement 是否接了 `.offset`（真分页）或 `.limit`（单页截断）；
  3. 若前两者构成风险，是否已在白名单里逐条裁定。

ROUND_25（B 摊）判据扩展（详见 tests/tools/pagination_order_lint.py 常量注释）：
- 列名：`NON_UNIQUE_TIME_COLUMNS` → `NON_UNIQUE_SORT_COLUMNS`（低基数业务列
  status/role/level/category）+ 时间戳族结构判据（`_at` 结尾）；
- 形态：新增函数形态 `desc(Model.col)` 与裸列形态——ROUND_24 判据只认
  `Model.col.desc()` 方法形态，全仓 13 处函数形态站点完全不可见
  （含 3 处 offset 真分页）。扩展后实测 58 站点 / 29 违规，其中 19 处
  为新暴露：14 处已补次级键（7 offset 真分页 + 5 绑定身份 + gauge + 去重窗口），
  5 处聚合/扫描窗口进白名单。

为什么不用"自建 statement 再断言"（p2_50 的 L40/L57 那种弱见证）：
那种写法断言的是测试自己拼的 SQL，生产侧改坏了它照样绿——没有验证力。

三档自检（缺一条就不算闸门）：
  - `TestGateSelfProof`：合成样本两头夹，证明"无分页→放行"与
    "有分页/截断且无次级键→红"两臂都在工作，且变量流/asc/非时间列各形态都覆盖；
  - `TestWhitelistIntegrity`：白名单防腐烂（条目必须仍存在、仍无 offset、
    仍未补次级键、数量对得上），并自证这套检查能抓到伪造条目；
  - `TestGateNotVacuous`：防空转（被扫文件数、站点数、哨兵站点）。
"""
from __future__ import annotations

import pathlib

from tests.tools.pagination_order_lint import (
    OrderBySite,
    find_order_by_sites,
    iter_python_files,
    scan_source,
    scan_tree,
)

BACKEND = pathlib.Path(__file__).resolve().parents[1]
APP = BACKEND / "app"


# ---------------------------------------------------------------------------
# 白名单：只收「单页、无跨页语义」的站点，逐条给理由。
#
# key = (相对 app 的文件路径, 所在函数, order_by 里出现的列名元组)
# value = (该 key 在源码中应有的站点数, 理由)
#
# 纪律：白名单**不是**豁免通道。若某条目接上了 `.offset`（真分页），
# 白名单立即失效（见 TestWhitelistIntegrity）——必须补次级键，不得留在白名单。
# ---------------------------------------------------------------------------
PAGING_WHITELIST: dict[tuple[str, str, tuple[str, ...]], tuple[int, str]] = {
    ("api/v1/content_governance.py", "get_content_history", ("created_at",)): (
        1,
        "单页：.limit(100) 取该内容的最近 100 条审核日志，无 offset；"
        "同秒并列只影响第 100 条截断点，不产生跨页重复/漏行",
    ),
    ("api/v1/ops_dashboard.py", "_get_recent_audit_events", ("created_at",)): (
        1,
        "单页：.limit(10) 仪表盘最近审计事件，无 offset",
    ),
    ("services/counselor_service_user.py", "get_user_detail", ("created_at",)): (
        3,
        "单页 ×3（风险历史/评估/干预各 .limit(100)）：一次返回完整时间线，无 offset",
    ),
    ("services/drift_monitoring_service.py", "_create_drift_alert", ("created_at",)): (
        2,
        "取最新一条做去重存在性判断，.limit(1)，无分页语义",
    ),
    ("services/intervention_service.py", "get_active", ("created_at",)): (
        1,
        "取当前 active 计划，.limit(1)；ROUND_23a 后每用户至多一条 active"
        "（部分唯一索引 uq_intervention_plans_active_per_user）⇒ 并列组大小恒为 1",
    ),
    ("services/risk_service_report.py", "get_risk_report", ("created_at",)): (
        1,
        "单页：报告用最近 20 条，.limit(20)，无 offset",
    ),
    ("services/risk_service_warning.py", "_check_warning_trigger", ("created_at",)): (
        1,
        "取上一条评估，.limit(1)，无分页语义",
    ),
    (
        "services/crisis_export_service.py",
        "iter_export_crisis_csv",
        ("created_at",),
    ): (
        1,
        "L20 已知项（本轮按边界只登记不动）：全量流式导出，服务端游标"
        " yield_per=1000 分块，无 offset/limit 子句；同一次查询执行内"
        "游标不跨页，不产生重复/漏行",
    ),
    # ---- ROUND_25 (B 摊) 新增：判据扩展后逐条裁定的单页扫描/展示窗口 ----
    (
        "monitoring/escalation.py",
        "run_escalation_check",
        ("created_at",),
    ): (
        1,
        "单页扫描窗口：.limit(500) 取最近 firing 告警做升级判断；同秒并列"
        "只影响本轮窗口构成（边界条目下轮补判），无跨页重复/漏行",
    ),
    (
        "services/observability/aggregate.py",
        "_fetch_am_sync_failures",
        ("created_at",),
    ): (
        1,
        "单页 top-10 展示样本（recent_failures 失败详情）；并列只影响样本构成",
    ),
    (
        "services/observability/aggregate.py",
        "_fetch_recent_flushes",
        ("created_at",),
    ): (
        1,
        "单页 top-10 展示样本（最近 flush 日志）；并列只影响样本构成",
    ),
    (
        "services/observability/query.py",
        "_fetch_fired_rows",
        ("created_at",),
    ): (
        1,
        "单页扫描窗口：.limit(5000) 拉 fired 行做分位数聚合；指标为抽样口径，"
        "并列只影响窗口构成，无跨页语义",
    ),
    (
        "tasks/alerts.py",
        "_archive_impl",
        ("created_at",),
    ): (
        1,
        "单页扫描窗口：.limit(1000) 归档候选；幂等由 original_id 去重兜底"
        "（P1-D-7），边界并列条目下轮补归档，无跨页重复/漏行",
    ),
}


def _key(site: OrderBySite) -> tuple[str, str, tuple[str, ...]]:
    return (site.file, site.func, site.sort_columns)


def whitelist_problems(
    sites: list[OrderBySite],
    whitelist: dict[tuple[str, str, tuple[str, ...]], tuple[int, str]],
) -> list[str]:
    """白名单防腐烂检查（纯函数，便于自证）。

    返回问题列表；空列表 = 干净。检查四件事：
      1. 条目在源码里仍存在（否则是腐烂条目：站点被删/改名/列名变了）；
      2. 条目的站点数对得上（防「一个 key 掩盖多处」）；
      3. 条目仍无 `.offset`（接上真分页就必须修，不得继续豁免）；
      4. 条目仍未补次级键（已修的站点要从白名单移除，防囤积）。
    """
    by_key: dict[tuple[str, str, tuple[str, ...]], list[OrderBySite]] = {}
    for site in sites:
        by_key.setdefault(_key(site), []).append(site)

    problems: list[str] = []
    for key, (expected_count, _reason) in whitelist.items():
        found = by_key.get(key, [])
        if not found:
            problems.append(f"腐烂条目（源码中已不存在）: {key}")
            continue
        if len(found) != expected_count:
            problems.append(
                f"站点数不符: {key} 期望 {expected_count} 实际 {len(found)}"
            )
        for site in found:
            if site.has_offset:
                problems.append(
                    f"已接 offset（真分页，必须补次级键并移出白名单）: {site.loc} {key[1]}"
                )
            if site.has_secondary_key:
                problems.append(
                    f"已补次级键（应移出白名单，白名单不得囤积已修站点）: {site.loc} {key[1]}"
                )
    return problems


def unlisted_violations(
    sites: list[OrderBySite],
    whitelist: dict[tuple[str, str, tuple[str, ...]], tuple[int, str]],
) -> list[OrderBySite]:
    """未被白名单覆盖的违规站点（闸门的核心判据）。"""
    allowed = set(whitelist)
    return [s for s in sites if s.is_violation and _key(s) not in allowed]


# ---------------------------------------------------------------------------
# 生产代码闸门
# ---------------------------------------------------------------------------


class TestGateOnProduction:
    def test_no_unlisted_violations(self):
        """全仓 order_by 站点：分页/截断 + 无非唯一排序列 tie-break 必须为 0（白名单外）。"""
        sites = scan_tree(APP)
        bad = unlisted_violations(sites, PAGING_WHITELIST)
        detail = "\n".join(
            f"  {s.loc} {s.func} cols={s.sort_columns} "
            f"offset={s.has_offset} limit={s.has_limit}" for s in bad
        )
        assert not bad, (
            f"发现 {len(bad)} 处分页/截断排序缺少确定性次级键：\n{detail}\n"
            "修法：在 order_by(...) 末尾追加 <表>.id.desc()（升序场景用 id.asc()），"
            "或若确属单页无跨页语义，登记进 PAGING_WHITELIST 并写明理由。"
        )

    def test_whitelist_entries_are_real(self):
        """白名单防腐烂：条目必须仍存在、仍无 offset、仍未补次级键、数量对得上。"""
        problems = whitelist_problems(scan_tree(APP), PAGING_WHITELIST)
        assert not problems, "白名单校验失败：\n" + "\n".join(f"  {p}" for p in problems)

    def test_every_whitelist_entry_has_reason(self):
        """每条白名单必须写明理由（空理由 = 隐性豁免）。"""
        empty = [k for k, (_n, reason) in PAGING_WHITELIST.items() if not reason.strip()]
        assert not empty, f"白名单条目缺理由: {empty}"


class TestGateNotVacuous:
    """防空转：扫描器坏了（路径错/正则失效/AST walk 断）不能让闸门静默变绿。"""

    def test_scanned_files_not_degraded(self):
        files = iter_python_files(APP)
        assert len(files) >= 260, (
            f"被扫文件数 {len(files)} < 260：疑似扫描路径失效（app 实际 268 个 .py）"
        )

    def test_site_count_not_degraded(self):
        sites = scan_tree(APP)
        assert len(sites) >= 50, (
            f"order_by 站点数 {len(sites)} < 50：疑似 AST 判定退化"
            "（ROUND_25 判据扩展后实际 58 处含非唯一排序列）"
        )

    def test_sentinel_site_present(self):
        """哨兵：一个已知站点的字段必须逐项正确，防「扫到了但字段全错」。"""
        sites = scan_tree(APP)
        sentinel = [
            s
            for s in sites
            if s.file == "services/counselor_service_warning.py"
            and s.func == "list_warnings"
        ]
        assert len(sentinel) == 1, f"哨兵站点缺失或重复: {sentinel}"
        site = sentinel[0]
        assert site.has_secondary_key is True, "ROUND_23 补的 id 次级键未被识别"
        assert site.has_offset is True, "该站点的 offset 未被识别"
        assert site.is_violation is False, "有次级键的站点被判成违规（判据过严）"


# ---------------------------------------------------------------------------
# 自证：合成样本两头夹
# ---------------------------------------------------------------------------

_PAGED_NO_TIEBREAK = """
async def list_things(db, offset: int, page_size: int):
    stmt = select(Thing).order_by(Thing.created_at.desc()).offset(offset).limit(page_size)
    return await db.execute(stmt)
"""

_NO_PAGING_CLAUSE = """
async def latest_thing(db):
    stmt = select(Thing).order_by(Thing.created_at.desc())
    return await db.execute(stmt)
"""

_TIEBREAK_PRESENT = """
async def list_things(db, offset: int, page_size: int):
    stmt = (
        select(Thing)
        .order_by(Thing.created_at.desc(), Thing.id.desc())
        .offset(offset)
        .limit(page_size)
    )
    return await db.execute(stmt)
"""

_LIMIT_ONLY = """
async def recent_things(db):
    stmt = select(Thing).order_by(Thing.created_at.desc()).limit(20)
    return await db.execute(stmt)
"""

_VARIABLE_FLOW = """
async def list_things(db, offset: int, page_size: int):
    stmt = select(Thing).order_by(Thing.created_at.desc())
    stmt = stmt.offset(offset)
    stmt = stmt.limit(page_size)
    return await db.execute(stmt)
"""

_ASC_ORDER = """
async def list_things(db, offset: int, page_size: int):
    stmt = select(Thing).order_by(Thing.created_at.asc()).offset(offset).limit(page_size)
    return await db.execute(stmt)
"""

_NON_TIME_COLUMN = """
async def list_things(db, offset: int, page_size: int):
    stmt = select(Thing).order_by(Thing.title.desc()).offset(offset).limit(page_size)
    return await db.execute(stmt)
"""

# ---- ROUND_25 (B 摊) 新增自证样本 ----

_FUNCTION_FORM = """
async def list_things(db, offset: int, page_size: int):
    stmt = select(Thing).order_by(desc(Thing.created_at)).offset(offset).limit(page_size)
    return await db.execute(stmt)
"""

_BUSINESS_COLUMN = """
async def list_things(db, offset: int, page_size: int):
    stmt = select(Thing).order_by(Thing.status.desc()).offset(offset).limit(page_size)
    return await db.execute(stmt)
"""

_TIMESTAMP_PATTERN = """
async def list_things(db, offset: int, page_size: int):
    stmt = select(Thing).order_by(Thing.reviewed_at.desc()).offset(offset).limit(page_size)
    return await db.execute(stmt)
"""

_UNIQUE_COLUMN = """
async def list_things(db, offset: int, page_size: int):
    stmt = select(Thing).order_by(Thing.id.desc()).offset(offset).limit(page_size)
    return await db.execute(stmt)
"""


def _scan_source(source: str) -> list[OrderBySite]:
    """内存态扫描自证样本（不落盘）——避免把 tmp_path 清理抖动引进断言。

    2026-10-22 实测教训：自证用例原先写临时文件再扫，固定 basetemp 复用
    时 pytest 的 tmp_path 在 Windows 上出现非确定性 teardown ERROR，
    15 个自证用例集体红、与判据内容无关 ⇒ 改为直接传源码字符串。
    """
    return scan_source(source)


class TestGateSelfProof:
    """自证两臂：既能红，也能放行。缺任一条，闸门就可能是恒真/恒假。"""

    def test_detects_paginated_without_tiebreak(self):
        sites = _scan_source(_PAGED_NO_TIEBREAK)
        assert len(sites) == 1
        assert sites[0].has_offset is True
        assert sites[0].has_secondary_key is False
        assert sites[0].is_violation is True
        assert unlisted_violations(sites, {}), "红臂失效：违规站点没被闸门抓住"

    def test_allows_no_paging_clause(self):
        sites = _scan_source(_NO_PAGING_CLAUSE)
        assert len(sites) == 1
        assert sites[0].has_offset is False
        assert sites[0].has_limit is False
        assert sites[0].is_violation is False
        assert not unlisted_violations(sites, {}), "放行臂失效：无分页也被判违规"

    def test_allows_tiebreak(self):
        sites = _scan_source(_TIEBREAK_PRESENT)
        assert len(sites) == 1
        assert sites[0].has_secondary_key is True
        assert sites[0].is_violation is False

    def test_detects_limit_only(self):
        """单页截断也纳入裁定：N 边界可能落在并列组中间。"""
        sites = _scan_source(_LIMIT_ONLY)
        assert len(sites) == 1
        assert sites[0].has_offset is False
        assert sites[0].has_limit is True
        assert sites[0].is_violation is True

    def test_detects_variable_split_flow(self):
        """`stmt = stmt.offset(...)` 拆分形态（user_data_service 的真实写法）。"""
        sites = _scan_source(_VARIABLE_FLOW)
        assert len(sites) == 1
        assert sites[0].has_offset is True, "拆分形态的 offset 未被识别"
        assert sites[0].is_violation is True

    def test_detects_asc_order(self):
        """asc 与 desc 同为非唯一键排序，方向不影响重复/漏行。"""
        sites = _scan_source(_ASC_ORDER)
        assert len(sites) == 1
        assert sites[0].is_violation is True

    def test_ignores_non_time_column(self):
        """判据外的列（title）不在判据内（不误报）。"""
        assert _scan_source(_NON_TIME_COLUMN) == []

    # ---- ROUND_25 (B 摊) 扩展判据自证 ----

    def test_detects_function_form(self):
        """函数形态 desc(Model.col) 必须可判（ROUND_24 判据完全看不见它）。"""
        sites = _scan_source(_FUNCTION_FORM)
        assert len(sites) == 1
        assert sites[0].sort_columns == ("created_at",)
        assert sites[0].has_offset is True
        assert sites[0].is_violation is True

    def test_detects_business_column(self):
        """低基数业务列（status/role/level/category）纳入判据。"""
        sites = _scan_source(_BUSINESS_COLUMN)
        assert len(sites) == 1
        assert sites[0].sort_columns == ("status",)
        assert sites[0].is_violation is True

    def test_detects_timestamp_suffix_pattern(self):
        """`_at` 结构判据覆盖未显式枚举的时间戳列（如 reviewed_at）。"""
        sites = _scan_source(_TIMESTAMP_PATTERN)
        assert len(sites) == 1
        assert sites[0].sort_columns == ("reviewed_at",)
        assert sites[0].is_violation is True

    def test_allows_unique_column(self):
        """排除判据自证：id 等唯一列 + 分页也不判违规（防判据过严）。"""
        assert _scan_source(_UNIQUE_COLUMN) == []

    def test_whitelist_guard_catches_removed_entry(self):
        """防腐烂自证 1：条目指向已不存在/已改名的站点 ⇒ 红。"""
        sites = _scan_source(_NO_PAGING_CLAUSE)
        fake = {("sample.py", "renamed_func", ("created_at",)): (1, "伪造条目")}
        problems = whitelist_problems(sites, fake)
        assert any("腐烂条目" in p for p in problems), problems

    def test_whitelist_guard_catches_stale_entry(self):
        """防腐烂自证 2：站点已补次级键却仍留在白名单 ⇒ 红（不得囤积已修站点）。"""
        sites = _scan_source(_TIEBREAK_PRESENT)
        key = _key(sites[0])
        problems = whitelist_problems(sites, {key: (1, "伪造条目")})
        assert any("已补次级键" in p for p in problems), problems

    def test_whitelist_guard_catches_gained_offset(self):
        """白名单站点若接上 offset，必须立刻失效（不得用白名单替代修复）。"""
        sites = _scan_source(_PAGED_NO_TIEBREAK)
        key = _key(sites[0])
        problems = whitelist_problems(sites, {key: (1, "伪造豁免")})
        assert any("已接 offset" in p for p in problems), problems

    def test_whitelist_guard_catches_count_drift(self):
        """防腐烂自证 3：一个 key 下有 2 处站点但只登记 1 处 ⇒ 红（防一处掩盖多处）。"""
        sites = _scan_source(_LIMIT_ONLY + _LIMIT_ONLY)
        assert len(sites) == 2
        problems = whitelist_problems(sites, {_key(sites[0]): (1, "少登记")})
        assert any("站点数不符" in p for p in problems), problems
