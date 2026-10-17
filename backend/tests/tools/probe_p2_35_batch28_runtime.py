"""第二十八批运行时证据（3 项，为裁定提供可客断言）。

E1fallback.py 四处 `_incr_model_fallback` 外层 except 的**可达性**：
   `_incr_model_fallback` 内层已`try/except Exception` 全捕获并warning，
   自身永不抛 ⇒ 外层 except 只在 `from app.core.model_engine.loading import
   _incr_model_fallback` 这一行失败（ImportError）时可达。
   ⇒ 这4 条的分类器粗排（S 型）需修正为 **P 型（特性探测）/ 事实不可达**。

E2 observability_exporter `_loop` 退避重试**不丢 Counter delta**：
   `_safe_set_alert_total` 失败时 `_prev_total_fired` 不更新 ⇒ 下轮
   delta = total_fired - prev 把跳过期间一并计入 ⇒ R 型（自恢复）成立。

E3 notifier `_dispatch` 失败时 `alert_channel_failed` 审计**真的写入**：
   支撑 notifier 5 条复核的 V 型判定（失败被如实呈现，非静默）。

用法：.venv/Scripts/python.exe tests/tools/probe_p2_35_batch28_runtime.py
"""

from __future__ import annotations

import asyncio
import builtins
import importlib
import pathlib
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))


def _cval(counter, **labels) -> float:
    """读自研 Counter 的当前值（collect() 返回 (labels_dict, value) 列表）。"""
    for got, value in counter.collect():
        if got == labels:
            return value
    return 0.0


def e1_fallback_except_reachability() -> None:
    """E1：_incr_model_fallback 是否会向外抛异常。"""
    from app.core.metrics import model_fallback_total

    loading = importlib.import_module("app.core.model_engine.loading")

    # 1a) 正常调用：不抛，且计数器真的涨（M型前提的运行时实证）
    before = _cval(model_fallback_total, model="probe_model", reason="probe_reason")
    loading._incr_model_fallback("probe_model", "probe_reason")
    after = _cval(model_fallback_total, model="probe_model", reason="probe_reason")
    print(f"[E1a] model_fallback_total 真的增长: before={before} after={after}")
    assert after == before + 1, f"专用计数器未增长：{before} -> {after}"

    # 1b) 把 model_fallback_total.inc 打成必炸⇒ _incr_model_fallback 是否吞掉
    real_inc = model_fallback_total.inc
    model_fallback_total.inc = lambda **kw: (_ for _ in ()).throw(RuntimeError("probe: inc boom"))
    try:
        loading._incr_model_fallback("probe_model", "probe_reason")  # 不抛即通过
        print("[E1b] inc 必炸时 _incr_model_fallback 仍未外抛 ⇒ 内层已全捕获")
    except RuntimeError as exc:
        print(f"[E1b] _incr_model_fallback 外抛了：{exc} —— 判据需重估")
        raise
    finally:
        model_fallback_total.inc = real_inc

    # 1c) fallback.py 的外层 except 只在 import 行失败时可达：屏蔽该 import
    fallback = importlib.import_module("app.core.model_engine.fallback")
    fb = fallback.FallbackMixin()

    class _FakeAnalyzer:
        def analyze(self, text):
            return {"heuristic_sentiment_score": -0.3}

    fb.text_analyzer = _FakeAnalyzer()
    fb._score_to_level = lambda s: "low"
    fb._incr_fallback = lambda: None

    real_import = builtins.__import__

    def _blocked(name, *a, **k):
        if name == "app.core.model_engine.loading":
            raise ImportError("probe: loading module blocked")
        return real_import(name, *a, **k)

    builtins.__import__ = _blocked
    try:
        out = fb._text_heuristic_fallback("我今天心情很好")
        print(f"[E1c] import 被屏蔽时 _text_heuristic_fallback 仍返回: {out}")
        assert out["prediction"] in (0, 1), "返回结构应与正常态同形"
        assert out["model_used"] == "text_heuristic_fallback", "降级标记应保留"
    finally:
        builtins.__import__ = real_import
    print("[E1c]⇒ 外层 except 的唯一可达路径是 import 失败（P 型），非运行期降级")


def e2_counter_delta_survives_backoff() -> None:
    """E2：_safe_set_alert_total 失败后下轮 delta 是否补回跳过期间。"""
    exporter_mod = importlib.import_module("app.services.observability_exporter")
    obs_mod = importlib.import_module("app.services.observability")
    from app.core.metrics import observability_alert_total

    exp = exporter_mod.ObservabilityExporter()
    exp._counter_initialized = True

    # 第 1 轮：基线 100
    exp._prev_total_fired = 100

    # 让 _compute_trend 抛错 ⇒ 采集失败，_prev_total_fired 应保持 100
    real_trend = obs_mod._compute_trend

    async def _boom(*a, **k):
        raise RuntimeError("probe: trend failed")

    obs_mod._compute_trend = _boom
    try:
        before = _cval(observability_alert_total, severity="total")
        asyncio.run(exp._safe_set_alert_total(None, None, None))  # type: ignore[arg-type]
        assert exp._prev_total_fired == 100, (
            f"失败轮不应推进基线，实际={exp._prev_total_fired}"
        )
        after_fail = _cval(observability_alert_total, severity="total")
        print(
            f"[E2a] 失败轮: prev={exp._prev_total_fired} "
            f"counter {before} -> {after_fail}（无增量，符合预期）"
        )
        assert after_fail == before, "失败轮不应递增 Counter"
    finally:
        obs_mod._compute_trend = real_trend

    # 第 2 轮：成功，total_fired=130 ⇒ delta 应为 30（含失败期间新增的 30）
    async def _ok(*a, **k):
        return {"by_status": {"firing": 130, "resolved": 0}}

    obs_mod._compute_trend = _ok
    try:
        before = _cval(observability_alert_total, severity="total")
        asyncio.run(exp._safe_set_alert_total(None, None, None))  # type: ignore[arg-type]
        after = _cval(observability_alert_total, severity="total")
        print(f"[E2b] 恢复轮: counter {before} -> {after}（delta={after - before}）")
        assert after - before == 30, (
            f"恢复轮 delta={after - before}，应为 30 —— "
            "若小于 30 说明退避期间新增告警永久丢失，R 型判定需推翻"
        )
    finally:
        obs_mod._compute_trend = real_trend
        exp._counter_initialized = False
    print("[E2]⇒ 退避重试不丢Counter 增量，R 型（自恢复）判定成立")


def e3_notifier_failure_writes_audit() -> None:
    """E3：通道发送失败时 alert_channel_failed 审计真的写入。"""
    notifier = importlib.import_module("app.monitoring.notifier")
    audit = importlib.import_module("app.core.audit")

    calls: list[dict] = []

    async def _fake_record_audit(db, **kw):
        calls.append(kw)

    real_audit = audit.record_audit
    notifier.record_audit = _fake_record_audit  # type: ignore[attr-defined]

    class _FakeNotifier:
        name = "probe"

        def is_configured(self):
            return True

        def send(self, payload):
            raise RuntimeError("probe: channel boom")

    payload = notifier.AlertPayload(
        rule="ProbeRule", severity="P1", status="firing", message="probe"
    )

    try:
        results = asyncio.run(
            notifier.CompositeNotifier([_FakeNotifier()]).send(payload, db=object())  # type: ignore[arg-type]
        )
    finally:
        notifier.record_audit = real_audit  # type: ignore[attr-defined]

    print(f"[E3a] results={results}（失败以 False 显式呈现给调用方）")
    assert results == {"probe": False}, f"results 应显式携带失败，实际={results}"
    assert len(calls) == 1, f"应写1 条通道审计，实际={len(calls)}"
    action = calls[0]["action"]
    print(f"[E3b] 审计 action={action} detail={calls[0]['detail']}")
    assert action == "alert_channel_failed", f"审计动作漂移为 {action}"
    assert calls[0]["detail"]["channel"] == "probe"
    print("[E3]⇒ 通道失败既进results 又落 alert_channel_failed 审计 ⇒ V 型（失败被如实呈现）")


def main() -> int:
    print("=" * 72)
    print("P2-35 第二十八批运行时证据")
    print("=" * 72)
    e1_fallback_except_reachability()
    print("-" * 72)
    e2_counter_delta_survives_backoff()
    print("-" * 72)
    e3_notifier_failure_writes_audit()
    print("=" * 72)
    print("三项证据全部成立")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())