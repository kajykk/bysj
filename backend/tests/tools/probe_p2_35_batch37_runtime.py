"""第三十七批运行时探针：1 接线（fusion canary 事件写入失败）+ 14 不接的
结构/同源/不可达证据。

E1：fusion `_log_canary_event` DB 写入失败 → 接线计数 +1（warning 仍在）。
E2：防假绿——DB 写入成功 → 计数不涨。
E3：唯一写入方结构钉——全仓 AST 扫描，MonitoringLog 的 INFERENCE/FALLBACK
    事件只有 fusion.py 写（alert_lifecycle 只写 DRIFT_ALERT），而
    auto_rollback_service.check_canary_rollback 正是按这两类事件计数。
E4：reports `_notify` P 型——ws.py 的 `_local_send_to_user` 与
    `_publish_to_redis`（send_to_user 的两条内层路径）各自已接线，
    外层 except 是防御性重复层。
E5：inference `_fire_shadow_check` P 型——包裹的三个调用在生产形态
    不可抛：`get_shadow_comparison_service` 是单例获取；`record_inference`
    是纯内存 dict 更新（无 await/IO）；`fire_shadow_check` 唯一能抛的
    `asyncio.create_task`（无事件循环）已被内层 `except RuntimeError`
    捕获且第十批已接线。
E6：kill_switch `_get_redis` V 型——Redis 不可用时返回 None 不抛，
    调用方 `_degrade` 显式写 degraded=True + source="unavailable"
    （fail-closed 由 settings.kill_switch_fail_closed 决定，P1-7 设计）。
"""

from __future__ import annotations

import ast
import asyncio
import importlib
import pathlib
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[2]
APP = BACKEND / "app"
sys.path.insert(0, str(BACKEND))

LOCATION = "services.model_predict.fusion.canary_event_log_failed"

RESULTS: list[tuple[str, bool, str]] = []


def report(eid: str, ok: bool, detail: str) -> None:
    RESULTS.append((eid, ok, detail))
    print(f"[{'OK ' if ok else 'FAIL'}] {eid}: {detail}")


def loc_count(location: str) -> int:
    from app.core.metrics import silent_degradation_total

    return sum(
        v
        for labels, v in silent_degradation_total.collect()
        if labels.get("location") == location
    )


def e1_e2_fusion_wiring() -> None:
    fusion = importlib.import_module("app.services.model_predict.fusion")
    import app.core.database as database

    svc = fusion.FusionMixin()

    class _BoomSession:
        def __init__(self, *a, **k):
            pass

        async def __aenter__(self):
            raise RuntimeError("db unreachable (simulated)")

        async def __aexit__(self, *a):
            return False

    class _OkSession:
        def __init__(self, *a, **k):
            self.added = None

        async def __aenter__(self):
            return self

        async def __aexit__(self, *a):
            return False

        def add(self, obj):
            self.added = obj

        async def commit(self):
            pass

    real = database.AsyncSessionLocal
    try:
        # E1: 失败路径
        database.AsyncSessionLocal = _BoomSession  # type: ignore[assignment]
        before = loc_count(LOCATION)
        asyncio.run(
            svc._log_canary_event(
                event_type="fallback",
                model_version="v-test",
                user_id=1,
                latency_ms=12.5,
                fallback_reason="simulated",
            )
        )
        after = loc_count(LOCATION)
        report(
            "E1",
            after == before + 1,
            f"DB 写入失败 → 接线计数 {before}→{after}（+1 且不抛，"
            "warning 日志仍在）",
        )
        # E2: 成功对照
        database.AsyncSessionLocal = _OkSession  # type: ignore[assignment]
        before2 = loc_count(LOCATION)
        asyncio.run(
            svc._log_canary_event(
                event_type="inference",
                model_version="v-test",
                user_id=1,
                latency_ms=8.0,
                response_summary={"risk_level": "low"},
            )
        )
        after2 = loc_count(LOCATION)
        report(
            "E2",
            after2 == before2,
            f"DB 写入成功 → 计数不涨（{before2}→{after2}），防假绿",
        )
    finally:
        database.AsyncSessionLocal = real  # type: ignore[assignment]


def e3_sole_db_writer() -> None:
    """全仓 AST：生产中真正落库的 INFERENCE/FALLBACK 写入方只有 fusion.py。

    observability_service 也构造这两类 MonitoringLog，但只 append 进
    内存 `_pending_logs`；其唯一落库出口 `flush_to_db` **生产零调用**
    （仅测试覆盖，类 docstring 自述「仅测试用例覆盖」）⇒ 那些事件永远
    到不了 MonitoringLog 表。auto_rollback_service 正是从该表计数。
    """
    direct_writers: set[str] = set()
    memory_only: set[str] = set()
    for p in sorted(APP.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        try:
            src = p.read_text(encoding="utf-8")
            tree = ast.parse(src)
        except Exception:
            continue
        rel = str(p.relative_to(BACKEND)).replace("\\", "/")
        for fn in ast.walk(tree):
            if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            fn_src = ast.unparse(fn)
            if "MonitoringLog(" not in fn_src:
                continue
            if "INFERENCE" not in fn_src and "FALLBACK" not in fn_src:
                continue
            # 同一函数内是否直接写库（db 会话 + commit）
            writes_db = (
                "AsyncSessionLocal" in fn_src or "db.commit()" in fn_src
            )
            if writes_db:
                direct_writers.add(rel)
            elif "_pending_logs.append" in fn_src:
                memory_only.add(rel)
    # flush_to_db 生产调用点（排除定义文件自身与 docstring/注释）
    flush_callers = 0
    for p in sorted(APP.rglob("*.py")):
        if "__pycache__" in p.parts:
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        for node in ast.walk(tree):
            if (
                isinstance(node, ast.Call)
                and isinstance(node.func, ast.Attribute)
                and node.func.attr == "flush_to_db"
            ):
                flush_callers += 1
    ok = (
        direct_writers == {"app/services/model_predict/fusion.py"}
        and memory_only == {"app/services/observability_service.py"}
        and flush_callers == 0
    )
    report(
        "E3",
        ok,
        f"直接落库写入方={sorted(direct_writers)}；仅内存构造方="
        f"{sorted(memory_only)}；flush_to_db 生产调用点={flush_callers}"
        " ⇒ fusion 是生产中唯一落库的 INFERENCE/FALLBACK 写入方",
    )


def e4_reports_inner_wired() -> None:
    """reports `_notify` 的两条内层路径已接线（P 型结构证据）。"""
    ws = APP / "core" / "ws.py"
    tree = ast.parse(ws.read_text(encoding="utf-8"))
    wired_funcs: set[str] = set()
    for fn in ast.walk(tree):
        if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if "record_silent_degradation" in ast.unparse(fn):
                wired_funcs.add(fn.name)
    ok = {"_local_send_to_user", "_publish_to_redis"} <= wired_funcs
    report(
        "E4",
        ok,
        f"ws.py 已接线函数含 _local_send_to_user/_publish_to_redis：{ok}"
        f"（send_to_user 的两条内层路径，外层 reports._notify 是防御性重复层）",
    )


def e5_fire_shadow_defensive() -> None:
    """inference `_fire_shadow_call` 包裹调用在生产形态不可抛。"""
    scs = APP / "services" / "shadow_comparison_service.py"
    tree = ast.parse(scs.read_text(encoding="utf-8"))
    record_pure = False
    getter_trivial = False
    fire_guarded = False
    for fn in ast.walk(tree):
        if not isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
            continue
        body = ast.unparse(fn)
        if fn.name == "record_inference":
            record_pure = (
                "await" not in body
                and "open(" not in body
                and "execute" not in body
            )
        if fn.name == "get_shadow_comparison_service":
            getter_trivial = (
                len(fn.body) <= 3 and "raise" not in body
            )
        if fn.name == "fire_shadow_check":
            # 唯一能抛的 create_task 必须被 except RuntimeError 捕获且已接线
            for node in ast.walk(fn):
                if isinstance(node, ast.Try):
                    for h in node.handlers:
                        hsrc = ast.unparse(h)
                        if "RuntimeError" in hsrc and (
                            "record_silent_degradation" in hsrc
                        ):
                            fire_guarded = True
    ok = record_pure and getter_trivial and fire_guarded
    report(
        "E5",
        ok,
        f"record_inference 纯内存={record_pure}；单例获取平凡={getter_trivial}；"
        f"create_task 的 RuntimeError 已内层捕获+接线={fire_guarded}"
        " ⇒ 外层 except 运行期不可达（P 型）",
    )


def e6_kill_switch_degrade_explicit() -> None:
    """kill_switch `_get_redis` 失败返回 None；`_degrade` 显式标记。"""
    ks = importlib.import_module("app.core.kill_switch")
    import app.core.cache as cache

    async def _boom():
        raise RuntimeError("redis down (simulated)")

    real = cache.get_redis_client
    try:
        cache.get_redis_client = _boom  # type: ignore[assignment]
        out = asyncio.run(ks._get_redis())
    finally:
        cache.get_redis_client = real  # type: ignore[assignment]
    src = (APP / "core" / "kill_switch.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    degrade_marks = False
    for fn in ast.walk(tree):
        if isinstance(fn, ast.FunctionDef) and fn.name == "_degrade":
            degrade_marks = '"degraded": True' in ast.unparse(fn) or (
                "'degraded': True" in ast.unparse(fn)
            )
    report(
        "E6",
        out is None and degrade_marks,
        f"_get_redis 失败→None（不抛）：{out is None}；_degrade 显式写 "
        f"degraded=True：{degrade_marks} ⇒ V 型（调用方可见，P1-7 设计）",
    )


def main() -> int:
    print("=" * 78)
    print("第三十七批运行时探针（E1~E6）")
    print("=" * 78)
    e1_e2_fusion_wiring()
    e3_sole_db_writer()
    e4_reports_inner_wired()
    e5_fire_shadow_defensive()
    e6_kill_switch_degrade_explicit()
    failed = [r for r in RESULTS if not r[1]]
    print("-" * 78)
    print(f"共 {len(RESULTS)} 项，失败 {len(failed)} 项")
    return 0 if not failed else 1


if __name__ == "__main__":
    sys.exit(main())
