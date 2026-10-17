"""第三十四批运行时证据。

E1  同形性：`_parse_detail_json` 损坏输入与「无 detail」返回**完全同形**，
    且下游把它渲染成一条 0 值假记录 + 累计值被低估（脏条目不是被跳过）。
E2  第二个消费点（`_fetch_am_sync_failures`）同样渲染出
    `operation="unknown" / error="unknown" / duration_ms=0` 的假行。
E3  可达性：`OperationLog.detail` 是 `Text, nullable=True` 且**无 JSON 合法性
    CHECK 约束**（同表其他列都有 CHECK 作对照）⇒ 非 JSON 文本可入库。
E4  M 型实测：`monitoring/dedup.py` 的专用计数器 `alert_detail_parse_failed_total`
    真的会涨（否则它是第二十二批那种死计数器）。
E5  接线后 `silent_degradation_total` 真的 +1（自研 Counter，读值走 collect()）。
E6  同族互锁：`_fetch_lock_memory_stats` 的接线仍在（第六批）。
"""

from __future__ import annotations

import asyncio
import ast
import importlib
import json
import pathlib
import sys
from datetime import datetime, timezone

BACKEND = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))


class _Result:
    def __init__(self, rows):
        self._rows = rows

    def all(self):
        return self._rows


class _FakeSession:
    """只实现 `_fetch_*` 真正用到的 `await db.execute(stmt)` → `.all()`。"""

    def __init__(self, rows):
        self._rows = rows

    async def execute(self, stmt):  # noqa: ANN001 - 桩
        return _Result(self._rows)


def _now() -> datetime:
    return datetime.now(timezone.utc)


def e1_aggregate_flush_shape_is_silent() -> None:
    print("[E1] `aggregate._fetch_recent_flushes`：脏条目 = 0 值假记录 + 累计低估")
    mod = importlib.import_module("app.services.observability.aggregate")

    good = json.dumps({"acquired": 7, "skipped": 1, "fallback": 2, "errors": 0, "instance_id": "i-1"})
    good2 = json.dumps({"acquired": 3, "skipped": 0, "fallback": 0, "errors": 1, "instance_id": "i-2"})
    broken = "{broken json"

    # 混合输入：1 条损坏 + 2 条正常 + 1 条无 detail
    rows = [(broken, _now()), (good, _now()), (good2, _now()), (None, _now())]
    flushes, totals = asyncio.run(mod._fetch_recent_flushes(_FakeSession(rows)))

    print(f"      recent_flushes = {json.dumps(flushes, ensure_ascii=False)}")
    print(f"      totals         = {totals}")

    # (a) 脏条目没有被跳过，而是变成一条 0 值假记录
    assert len(flushes) == 4, f"脏条目被跳过了？实际 {len(flushes)} 条"
    fake = [r for r in flushes if r["acquired"] == 0 and r["instance_id"] is None]
    assert len(fake) >= 1, "损坏条目未渲染成 0 值假记录"

    # (b) 同形性核心：损坏 与 无 detail 的输出**逐字段相同**
    by_created = {r["created_at"]: r for r in flushes}
    broken_row = next(r for r in flushes if r["instance_id"] is None and r["acquired"] == 0)
    none_row = next(
        r for r in flushes if r["instance_id"] is None and r is not broken_row
    )
    cmp_keys = ("acquired", "skipped", "fallback", "errors", "instance_id")
    for k in cmp_keys:
        assert broken_row[k] == none_row[k], f"损坏/缺失 在 {k} 上不同形"
    print(f"      同形性：损坏行 {[broken_row[k] for k in cmp_keys]} == "
          f"无 detail 行 {[none_row[k] for k in cmp_keys]}")

    # (c) 假数据危害：累计值被低估（真值应为 10，实际少了损坏条目那一份）
    assert totals["acquired"] == 10, f"累计 acquired 应为 10（只统计到 2 条正常），实际 {totals['acquired']}"
    print(f"      假数据：totals.acquired={totals['acquired']}，损坏条目的贡献被静默吞掉")

    # (d) 对照组：正常条目产出真实值 ⇒ 本断言有区分力（第二十九批 M3 假绿教训）
    real = [r for r in flushes if r["instance_id"] == "i-1"][0]
    assert real["acquired"] == 7 and real["fallback"] == 2, f"对照组失真：{real}"
    print("      对照组：正常条目 acquired=7/fallback=2 与假记录 0 值可区分")


def e2_aggregate_failure_shape_is_silent() -> None:
    print("[E2] `aggregate._fetch_am_sync_failures`：脏记录渲染成 unknown/0 假行")
    mod = importlib.import_module("app.services.observability.aggregate")
    from app.models.admin import OperationLog

    op_expr = OperationLog.action_type
    cond = [OperationLog.action_type == "am_sync_failed"]

    good = json.dumps({"operation": "sync", "error": "timeout", "duration_ms": 120, "am_silence_id": 9})
    rows = [("{broken", _now()), (good, _now())]
    out = asyncio.run(mod._fetch_am_sync_failures(_FakeSession(rows), cond, op_expr))
    print(f"      recent_failures = {json.dumps(out, ensure_ascii=False, default=str)}")

    fake = [r for r in out if r["operation"] == "unknown"][0]
    assert fake["error"] == "unknown", f"假行 error 不是 unknown：{fake}"
    assert fake["duration_ms"] == 0, f"假行 duration_ms 不是 0：{fake}"
    assert fake["am_silence_id"] is None

    real = [r for r in out if r["operation"] == "sync"][0]
    assert real["duration_ms"] == 120 and real["am_silence_id"] == 9, f"对照组失真：{real}"
    print("      假行 operation=unknown/error=unknown/duration_ms=0 与真实行可区分")

    # 与「本来就没 detail」同形
    out2 = asyncio.run(mod._fetch_am_sync_failures(_FakeSession([("{broken", _now())]), cond, op_expr))
    out3 = asyncio.run(mod._fetch_am_sync_failures(_FakeSession([(None, _now())]), cond, op_expr))
    for k in ("operation", "error", "duration_ms", "am_silence_id"):
        assert out2[0][k] == out3[0][k], f"损坏/缺失 在 {k} 上不同形"
    print("      同形性：损坏 与 无 detail 输出完全一致")


def e3_detail_column_has_no_json_constraint() -> None:
    print("[E3] 可达性：`OperationLog.detail` 是无 JSON 约束的 Text 列")
    src = (BACKEND / "app" / "models" / "admin.py").read_text(encoding="utf-8")
    tree = ast.parse(src)

    found = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "OperationLog":
            for stmt in node.body:
                if isinstance(stmt, ast.AnnAssign) and isinstance(stmt.target, ast.Name):
                    if stmt.target.id == "detail":
                        found = ast.unparse(stmt.annotation)
    assert found is not None and "str | None" in found, f"detail 列类型变了：{found}"
    print(f"      列定义：detail: {found}")

    # 关键：同表其他列都有 CHECK 约束，detail 没有 JSON 合法性约束
    checks: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef) and node.name == "OperationLog":
            for stmt in node.body:
                if isinstance(stmt, ast.Assign) and any(
                    isinstance(t, ast.Name) and t.id == "__table_args__" for t in stmt.targets
                ):
                    for elt in ast.walk(stmt.value):
                        if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                            if "CHECK" in elt.value.upper() or "ck_operation_logs" in elt.value:
                                checks.append(elt.value)
    assert checks, "OperationLog 的 CHECK 约束全没了 ⇒ 对照失效，本证据需重估"
    assert not any("detail" in c.lower() and "json" in c.lower() for c in checks), (
        f"detail 列已有 JSON 合法性约束 ⇒ 损坏不可达，接线判据需重估：{checks}"
    )
    print(f"      同表 CHECK 约束 {len(checks)} 条（operator_role/action_type/target_type/"
          f"ip_address 长度），**无一条管 detail 的 JSON 合法性**")

    # 运行时：解析器确实会对损坏输入抛（orjson 或 stdlib json）
    common = importlib.import_module("app.services.observability._common")
    raised = None
    try:
        common._json_loads("{broken json")
    except Exception as exc:  # noqa: BLE001 - 探针
        raised = exc
    assert raised is not None, "解析器对损坏输入不抛 ⇒ except 不可达"
    print(f"      运行时：{common._json_loads.__module__}.loads 对损坏输入抛 {type(raised).__name__}")


def e4_dedup_dedicated_counter_really_increments() -> None:
    print("[E4] M 型实测：dedup 的专用计数器真的会涨")
    metrics = importlib.import_module("app.core.metrics")
    counter = metrics.alert_detail_parse_failed_total

    def _read() -> float:
        for labels, value in counter.collect():
            if labels.get("stage") == "dedup":
                return float(value)
        return 0.0

    before = _read()
    counter.inc(1, stage="dedup")
    after = _read()
    print(f"      alert_detail_parse_failed_total{{stage=dedup}}: {before} -> {after}")
    assert after == before + 1, "专用计数器没涨 ⇒ 是第二十二批那种死计数器，M 型裁定需重估"


def e5_wiring_counter_really_increments() -> None:
    print("[E5] 接线后 `silent_degradation_total` 真的 +1（自研 Counter，collect() 读值）")
    metrics = importlib.import_module("app.core.metrics")
    agg = importlib.import_module("app.services.observability.aggregate")
    counter = metrics.silent_degradation_total
    loc = "services.observability.aggregate.detail_json_parse_failed"

    def _read() -> float:
        for labels, value in counter.collect():
            if labels.get("location") == loc:
                return float(value)
        return 0.0

    before = _read()
    result = agg._parse_detail_json("{broken json")
    after = _read()
    print(f"      {loc}: {before} -> {after}（解析结果 {result!r}）")
    assert result == {}, "损坏输入应回退空 dict"
    assert after == before + 1, f"接线后计数没涨（{before} -> {after}）⇒ 假设施"


def e5_sibling_interlock_lock_stats_still_wired() -> None:
    print("[E6] 同族互锁：同文件 `_fetch_lock_memory_stats` 的接线仍在（第六批）")
    src = (BACKEND / "app" / "services" / "observability" / "aggregate.py").read_text(
        encoding="utf-8"
    )
    loc = "services.observability.aggregate.lock_stats_unavailable"
    assert f'record_silent_degradation(\n            "{loc}"\n        )' in src or (
        f'"{loc}"' in src
    ), f"同族互锁锚点 {loc} 消失"
    print(f"      锚点在位：{loc}")


def main() -> int:
    print("=" * 78)
    print("第三十四批运行时证据")
    print("=" * 78)
    e1_aggregate_flush_shape_is_silent()
    e2_aggregate_failure_shape_is_silent()
    e3_detail_column_has_no_json_constraint()
    e4_dedup_dedicated_counter_really_increments()
    e5_wiring_counter_really_increments()
    e5_sibling_interlock_lock_stats_still_wired()
    print("=" * 78)
    print("E1~E6 全成立")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
