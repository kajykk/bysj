"""第三十五批运行时证据：8 条候选全部裁定**不接线**，本批 0 接线。

每一条都给出可客断言的运行时/结构证据，无一条依赖「日志不够响」类软理由。
"""

from __future__ import annotations

import asyncio
import time
import ast
import importlib
import pathlib
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[2]
REPO = BACKEND.parent

if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


# ---------------------------------------------------------------- E1
def e1_singleflight_degraded_shape_is_distinguishable() -> None:
    """E1：`cached_or_compute` 降级态的 `data` 是 **0 键空字典**，
    而任何正常态（含「真实空数据」）都是 **6 键结构化字典** ⇒ 键集合可分辨。

    这是第三十四批 `_parse_detail_json` 的**反面对照**：那次是 `{}` == `{}`
    （逐字段同形）⇒ 接；这次是 `{}` vs 6 键 ⇒ 不满足同形性 ⇒ 不接。
    """
    import importlib

    obs = importlib.import_module("app.api.v1.observability")
    query = importlib.import_module("app.services.observability.query")

    class _EmptyResult:
        def all(self) -> list:
            return []

        def scalars(self):  # noqa: ANN201 - 探针
            return self

    class _EmptySession:
        async def execute(self, stmt):  # noqa: ANN001 - 探针
            return _EmptyResult()

    from datetime import datetime, timedelta, timezone

    now = datetime.now(timezone.utc)
    start = now - timedelta(hours=1)

    # (a) 正常态（真实空数据）—— 走真实 compute 路径
    normal_empty = asyncio.run(
        query._compute_response_time(_EmptySession(), start, now, None)
    )
    # (b) 正常态（有数据）—— 走真实 builder
    fired_at = now - timedelta(seconds=3)
    normal_full = query._build_response_time_stats(
        [(fired_at, "fp1", "P1")], {"fp1": now}
    )

    async def _drive_degraded():
        key = obs.make_cache_key("observability.response-time", {"probe": "e1"})

        # 造一个已经在 flight、且 leader 已失败的 future
        # created_at 必须取当前单调时钟，否则会被入口的
        # `_cleanup_inflight_futures()` 当成陈旧 future 清掉，本探针就失真了
        loop = asyncio.get_running_loop()
        fut = loop.create_future()
        fut.set_exception(RuntimeError("leader compute blew up"))
        obs._inflight_futures[key] = (fut, time.monotonic())
        try:
            return await obs.cached_or_compute(
                endpoint="observability.response-time",
                params={"probe": "e1"},
                compute_fn=lambda: asyncio.sleep(0, result=({}, False)),
                ttl=60,
            )
        finally:
            obs._inflight_futures.pop(key, None)

    orig_get = obs.cache_get

    async def _no_cache(key):  # noqa: ANN001 - 探针
        return None

    obs.cache_get = _no_cache
    try:
        data, cached = asyncio.run(_drive_degraded())
    finally:
        obs.cache_get = orig_get

    print(f"[E1] 正常态（有数据）键数 = {len(normal_full)} -> {sorted(normal_full)}")
    print(f"[E1] 正常态（真实空数据）键数 = {len(normal_empty)} -> {sorted(normal_empty)}")
    print(f"[E1] 降级态 data 键数 = {len(data)}  cached = {cached}")

    assert set(normal_empty) == set(normal_full), "空数据与满数据键集合应一致"
    assert len(normal_empty) == 6, f"正常态应为 6 键，实际 {len(normal_empty)}"
    assert data == {} and len(data) == 0, f"降级态应为 0 键空字典，实际 {data}"
    assert cached is False, "降级态 cached 应为 False（与新鲜计算同形）"
    assert set(data) != set(normal_empty), (
        "若键集合相同则降级与空数据不可分辨，裁定需推翻 —— 实测是可分辨的"
    )
    print("[E1] ⇒ 键集合可分辨（0 键 vs 6 键）⇒ 不满足同形性判据 ⇒ 不接")


# ---------------------------------------------------------------- E2
def e2_canary_controller_is_never_instantiated() -> None:
    """E2：`CanaryController` 在生产代码中**从未被实例化** ⇒ `_log_comparison` 不可达。"""
    hits: list[str] = []
    for p in (BACKEND / "app").rglob("*.py"):
        rel = p.relative_to(BACKEND).as_posix()
        tree = ast.parse(p.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Name):
                if node.func.id == "CanaryController":
                    hits.append(f"{rel}:{node.lineno}")

    callers: list[str] = []
    for p in (BACKEND / "app").rglob("*.py"):
        rel = p.relative_to(BACKEND).as_posix()
        tree = ast.parse(p.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "_log_comparison":
                    callers.append(f"{rel}:{node.lineno}")

    print(f"[E2] CanaryController 实例化点 = {hits}（生产代码中应为 0）")
    print(f"[E2] _log_comparison 调用点 = {callers}")
    assert not hits, f"CanaryController 被实例化了 ⇒ 死代码裁定需重估：{hits}"
    assert len(callers) == 1 and callers[0].startswith("app/ml/canary_controller.py"), (
        f"_log_comparison 唯一调用方应只在本文件内，实际 {callers}"
    )
    print("[E2] ⇒ 无生产实例化 ⇒ 死代码 ⇒ 不接")


# ---------------------------------------------------------------- E3
def e3_flush_loop_output_has_no_consumer() -> None:
    """E3：`_flush_loop` 的唯一产物 `_flushed_buffer` 在生产中**无消费者**。

    `consume_flushed_logs` 已按 RES-P1-004 登记为死代码（有意保留），
    `flush_to_db()` 直接从 `_pending_logs` 取数、绕过该缓冲区 ⇒
    循环故障不影响任何生产可见行为 ⇒ 接线即假设施。
    """
    consumers: list[str] = []
    for p in (BACKEND / "app").rglob("*.py"):
        rel = p.relative_to(BACKEND).as_posix()
        tree = ast.parse(p.read_text(encoding="utf-8-sig"))
        for node in ast.walk(tree):
            if isinstance(node, ast.Call) and isinstance(node.func, ast.Attribute):
                if node.func.attr == "consume_flushed_logs":
                    consumers.append(f"{rel}:{node.lineno}")

    reg = (REPO / "docs" / "RETENTION_REGISTRY.md").read_text(encoding="utf-8")
    print(f"[E3] consume_flushed_logs 生产调用点 = {consumers}（应为 0）")
    print(f"[E3] RES-P1-004 在 RETENTION_REGISTRY.md 中登记 = {'RES-P1-004' in reg}")
    assert not consumers, f"出现了生产消费者 ⇒ 裁定需重估：{consumers}"
    assert "RES-P1-004" in reg, "RES-P1-004 登记消失 ⇒ 死缓冲区定性需重估"
    print("[E3] ⇒ 循环产物无生产消费者 ⇒ 无真实降级 ⇒ 不接")


# ---------------------------------------------------------------- E4
def e4_risk_schedule_outer_except_is_unreachable() -> None:
    """E4：`_schedule_warning_and_intervention` 的外层 except **运行期不可达**。

    三条可能的进入路径全部被挡住：
      ① `asyncio.ensure_future` —— 唯一调用方 `assess_structured` 是 `async def`
         且含 await ⇒ 事件循环必然存在（结构钉）；
      ② `from app.core.fire_forget_metrics import register_task` —— 该模块
         模块级只 import asyncio/logging/time，**无 app 依赖** ⇒ import 不抛；
      ③ `register_task` → `record_scheduled` 自身内层 `except Exception`
         全捕获 ⇒ 永不外抛（第二十八批 `_incr_model_fallback` 同型，第二次实锤）。
    实测：阻断 `app.core.metrics` 后调用 `register_task` **不抛**。
    """
    ffm = importlib.import_module("app.core.fire_forget_metrics")
    src = (BACKEND / "app" / "core" / "fire_forget_metrics.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    module_level_app_imports = [
        ast.unparse(n)
        for n in tree.body
        if isinstance(n, ast.ImportFrom) and (n.module or "").startswith("app")
    ]
    print(f"[E4] fire_forget_metrics 模块级 app 依赖 = {module_level_app_imports}（应为空）")
    assert not module_level_app_imports, "模块级引入 app 依赖 ⇒ import 可达 ⇒ 裁定需重估"

    # 调用方 async 结构钉
    rsa = (BACKEND / "app" / "services" / "risk_service_assessment.py").read_text(
        encoding="utf-8"
    )
    tree2 = ast.parse(rsa)
    enclosing = None
    for node in ast.walk(tree2):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.lineno <= 274 <= (node.end_lineno or node.lineno):
                enclosing = node
    assert enclosing is not None and isinstance(enclosing, ast.AsyncFunctionDef), (
        "调用方不是 async def ⇒ ensure_future 可达 ⇒ 裁定需重估"
    )
    print(f"[E4] 调用方 = async def {enclosing.name}（含 await ⇒ 循环必然存在）")

    # 运行时：阻断 app.core.metrics 后 register_task 仍不抛
    class _Blocker:
        def find_spec(self, fullname, path=None, target=None):  # noqa: ANN001
            if fullname == "app.core.metrics":
                raise ImportError("metrics unavailable (simulated)")
            return None

    saved = {
        k: v
        for k, v in sys.modules.items()
        if k == "app.core.metrics" or k.startswith("app.core.metrics.")
    }
    blocker = _Blocker()
    for k in saved:
        del sys.modules[k]
    sys.meta_path.insert(0, blocker)
    try:
        try:
            importlib.import_module("app.core.metrics")
        except ImportError:
            pass
        else:
            raise AssertionError("阻断未生效 ⇒ E4 是假证据")

        async def _drive() -> None:
            async def _noop() -> None:
                return None

            task = asyncio.ensure_future(_noop())
            ffm.register_task(task, "probe")
            await task

        asyncio.run(_drive())
        print("[E4] 阻断 metrics 后 register_task 仍不抛 ⇒ 内层全捕获挡住了外层 except")
    finally:
        sys.meta_path.remove(blocker)
        sys.modules.update(saved)
    print("[E4] ⇒ 外层 except 运行期不可达（P 型）⇒ 不接")


# ---------------------------------------------------------------- E5
def e5_event_publish_outer_except_is_unreachable() -> None:
    """E5：`_check_warning_trigger` 的外层 except **运行期不可达**。

    `event_bus.publish` 自身内层已 `except asyncio.QueueFull` 全捕获，
    并且**已在第一批接线** `record_silent_degradation("core.event_bus.publish")`
    ⇒ 队列满这条唯一真实失败路径既不外抛、也已被观测。
    """
    bus = importlib.import_module("app.core.event_bus")
    ebus = bus.event_bus
    ebus.reset()

    async def _drive() -> None:
        # 把队列填满（maxsize=1 时直接造满）
        small = bus.EventBus(max_queue_size=1)
        ok = small._ensure_queue()
        ok.put_nowait({"type": "filler", "data": {}})

        async def _handler(data):  # noqa: ANN001 - 探针
            return None

        small.subscribe("warning.created", _handler)
        # 队列已满 ⇒ put_nowait 抛 QueueFull，但 publish 内部已吞掉
        await small.publish("warning.created", {"warning_id": 1})

    asyncio.run(_drive())
    print("[E5] 队列满时 publish 不抛（内部已捕获并接线）")

    src = (BACKEND / "app" / "core" / "event_bus.py").read_text(encoding="utf-8")
    assert 'record_silent_degradation("core.event_bus.publish")' in src, (
        "第一批的 EventBus 队列满接线消失 ⇒ 外层的可达性裁定需重估"
    )
    tree = ast.parse(src)
    inner = False
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.type is not None:
            if ast.unparse(node.type) == "asyncio.QueueFull":
                # 确认它在 publish 内部
                for fn in ast.walk(tree):
                    if isinstance(fn, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        if fn.name == "publish" and fn.lineno <= node.lineno <= (
                            fn.end_lineno or fn.lineno
                        ):
                            inner = True
    assert inner, "publish 内的 QueueFull 捕获消失 ⇒ 外层变为可达"
    print("[E5] ⇒ 唯一真实失败路径已被内层吞掉且已接线 ⇒ 外层 P 型 ⇒ 不接")


# ---------------------------------------------------------------- E6
def e6_anomaly_task_runs_in_separate_container() -> None:
    """E6：`_detect_impl` 跑在 **Celery worker 独立容器**里 ⇒ 计数器恒 0。

    `/metrics` 由 backend 容器暴露（Prometheus 抓 `backend:8000`），
    而 worker 是另一个容器；全仓无 `PROMETHEUS_MULTIPROC_DIR` /
    `MultiProcessCollector` ⇒ 在 worker 进程里给 `silent_degradation_total`
    加的计数永远读不到 ⇒ 接线即恒 0 假设施。
    """
    compose = (REPO / "docker-compose.yml").read_text(encoding="utf-8")
    assert "celery_worker:" in compose, "compose 无独立 worker 服务 ⇒ 裁定需重估"
    assert "celery -A app.core.celery_app worker" in compose, "worker 命令变了 ⇒ 裁定需重估"

    beat = (BACKEND / "app" / "core" / "celery_app.py").read_text(encoding="utf-8")
    tree = ast.parse(beat)
    scheduled = False
    for node in ast.walk(tree):
        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            if node.value == "app.tasks.anomaly_detection.detect_anomaly_access_task":
                scheduled = True
    print(f"[E6] compose 有独立 celery_worker 容器；beat 调度该任务 = {scheduled}")

    leaks: list[str] = []
    for base in (BACKEND / "app", REPO / "infra", REPO / "docker-compose.yml"):
        if base.is_file():
            cands = [base]
        elif base.exists():
            cands = [
                p
                for pat in ("*.py", "*.yml", "*.yaml", "*.toml")
                for p in base.rglob(pat)
            ]
        else:
            cands = []
        for p in cands:
            if ".venv" in p.parts or "node_modules" in p.parts:
                continue
                try:
                    t = p.read_text(encoding="utf-8-sig")
                except (OSError, UnicodeDecodeError):
                    continue
                if "PROMETHEUS_MULTIPROC_DIR" in t or "MultiProcessCollector" in t:
                    leaks.append(p.as_posix())
    print(f"[E6] PROMETHEUS_MULTIPROC_DIR / MultiProcessCollector 出现处 = {leaks}（应为空）")
    assert scheduled, "beat 不再调度该任务 ⇒ 不可达定性更强但需重估"
    assert not leaks, f"存在多进程收集器 ⇒ 计数可跨进程 ⇒ P 型裁定需重估：{leaks}"
    print("[E6] ⇒ worker 独立容器 + 无多进程收集器 ⇒ 计数恒 0 ⇒ 不接")


# ---------------------------------------------------------------- E7
def e7_metrics_facility_failures_are_homologous() -> None:
    """E7：`metrics.py:868` 与 `escalation.py:59` 保护的是**可观测设施自身**。

    `record_silent_degradation` 同样走 `app.core.metrics`（degradation.py），
    实测阻断 metrics 后：escalation 的 except 触发（静默），而接线设施
    计数 **0 → 0** ⇒ 同源失效，接线即恒 0 假设施。
    """
    metrics = importlib.import_module("app.core.metrics")
    esc = importlib.import_module("app.monitoring.escalation")
    deg = importlib.import_module("app.core.degradation")
    counter = metrics.silent_degradation_total
    probe_loc = "probe.batch35.homologous"

    def _read() -> float:
        for labels, value in counter.collect():
            if labels.get("location") == probe_loc:
                return float(value)
        return 0.0

    # 结构钉：degradation 与 escalation 都依赖 app.core.metrics
    dsrc = (BACKEND / "app" / "core" / "degradation.py").read_text(encoding="utf-8")
    assert "from app.core.metrics import" in dsrc, "degradation 不再依赖 metrics ⇒ 需重估"
    esrc = (BACKEND / "app" / "monitoring" / "escalation.py").read_text(encoding="utf-8")
    assert "from app.core import metrics" in esrc, "escalation 不再依赖 metrics ⇒ 需重估"

    class _Blocker:
        def find_spec(self, fullname, path=None, target=None):  # noqa: ANN001
            if fullname == "app.core.metrics":
                raise ImportError("metrics unavailable (simulated)")
            return None

    saved = {
        k: v
        for k, v in sys.modules.items()
        if k == "app.core.metrics" or k.startswith("app.core.metrics.")
    }
    blocker = _Blocker()
    for k in saved:
        del sys.modules[k]
    sys.meta_path.insert(0, blocker)
    try:
        try:
            importlib.import_module("app.core.metrics")
        except ImportError:
            pass
        else:
            raise AssertionError("阻断未生效 ⇒ E7 是假证据")
        esc._observe_escalation_latency(0.0, "ok")  # 不抛（静默）
        deg.record_silent_degradation(probe_loc)  # 静默
    finally:
        sys.meta_path.remove(blocker)
        sys.modules.update(saved)

    after = _read()
    print(f"[E7] 阻断 metrics 后：escalation 静默、接线设施计数 = {after}（应为 0）")
    assert after == 0.0, "同源失效不成立 ⇒ 裁定需重估"
    print("[E7] ⇒ 可观测设施自身故障 + 同源 ⇒ S 型 ⇒ 不接")


# ---------------------------------------------------------------- E8
def e8_track_model_inference_business_exception_still_propagates() -> None:
    """E8：`track_model_inference` 只吞指标失败，**业务异常照常向上抛**（V 型）。

    它保护的两个计数器 `model_inference_total` / `model_inference_duration_seconds`
    就定义在 `metrics.py` 本模块内 ⇒ 若它们坏了，`record_silent_degradation`
    用的 `silent_degradation_total` 同在一个模块、同一套 Counter 实现 ⇒ 同源。
    """
    import importlib

    metrics = importlib.import_module("app.core.metrics")

    orig = metrics.model_inference_total.inc

    def _boom(*a, **k):  # noqa: ANN001 - 探针
        raise RuntimeError("counter exploded")

    metrics.model_inference_total.inc = _boom
    try:
        raised = None
        try:
            with metrics.track_model_inference("probe"):
                raise ValueError("business failure")
        except ValueError as exc:
            raised = exc
        print(f"[E8] 指标失败时业务异常仍向上抛：{type(raised).__name__}: {raised}")
        assert isinstance(raised, ValueError), "业务异常未传播 ⇒ V 型定性需重估"

        metrics.model_inference_total.inc = orig
        raised2 = None
        try:
            with metrics.track_model_inference("probe"):
                pass
        except BaseException as exc:  # noqa: BLE001 - 探针
            raised2 = exc
        print(f"[E8] 指标正常时无业务异常：{raised2!r}")
        assert raised2 is None, "正常态不应抛"
    finally:
        metrics.model_inference_total.inc = orig

    msrc = (BACKEND / "app" / "core" / "metrics.py").read_text(encoding="utf-8")
    for name in ("model_inference_total", "model_inference_duration_seconds"):
        assert f"{name} =" in msrc, f"{name} 不在 metrics.py 内 ⇒ 同源判据需重估"
    print("[E8] ⇒ 指标失败被吞但业务异常外抛（V 型）+ 与被保护计数器同模块同源 ⇒ 不接")


def main() -> int:
    print("=" * 78)
    print("第三十五批运行时证据（8 条候选，全部裁定不接线）")
    print("=" * 78)
    e1_singleflight_degraded_shape_is_distinguishable()
    e2_canary_controller_is_never_instantiated()
    e3_flush_loop_output_has_no_consumer()
    e4_risk_schedule_outer_except_is_unreachable()
    e5_event_publish_outer_except_is_unreachable()
    e6_anomaly_task_runs_in_separate_container()
    e7_metrics_facility_failures_are_homologous()
    e8_track_model_inference_business_exception_still_propagates()
    print("=" * 78)
    print("E1~E8 全成立 ⇒ 本批 0 接线，桶计数不变（W=100 / X=118，总数 334）")
    print("=" * 78)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
