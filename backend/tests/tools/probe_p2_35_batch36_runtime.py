"""第三十六批运行时探针：接线 1 处生效 + 关键不接点实锤。

E1：predict 失败路径 —— return None 且
     silent_degradation_total{location="core.text_m2_bert_predictor.predict_failed"}
     计数 +1（接线生效；自研 Counter 走 collect()）。
E2：predict 成功路径 —— 返回完整 dict 且计数**不变**
     （防假绿：证明计数只由失败路径触发，不是恒真）。
E3：log_sanitizer L449 **生产可达** —— `exc_info` 是异常实例（非 tuple）时
     L443 `len(record.exc_info)` 抛 TypeError ⇒ L449 触发 ⇒ 未脱敏放行 +
     silent_degradation_total{location="core.log_sanitizer.filter_failed"} +1。
     对照组：exc_info 为合法 tuple（logger.exception 形态）与无 exc_info
     的正常 record **不触发**（防假绿：证明计数只由失败路径触发）。
E4：scaler.py:47 P 型 —— AST 断 try 体内只有 import + 一次调用，
     且被调的 _resolve_artifacts_dir 函数体含 except Exception 全捕获；
     正常访问 SCALER_PATH 走 _resolve_artifacts_dir 的正常/内层分支
     （外层 except 不参与）。
E5：startup_status S 同源 —— 阻断 silent_degradation_total.inc 后
     record_silent_degradation 同样失效（同一 app.core.metrics 源）
     ⇒ 给 L100 接线即恒 0 假设施。
"""

from __future__ import annotations

import ast
import asyncio
import importlib
import logging
import pathlib
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))

from app.core.metrics import silent_degradation_total  # noqa: E402

RESULTS: list[tuple[str, bool, str]] = []


def report(eid: str, ok: bool, detail: str) -> None:
    RESULTS.append((eid, ok, detail))
    print(f"  [{'OK ' if ok else 'FAIL'}] {eid}: {detail}")


def snapshot() -> int:
    rows = silent_degradation_total.collect()
    return sum(v for _, v in rows)


def loc_count(location: str) -> int:
    rows = silent_degradation_total.collect()
    return sum(v for labels, v in rows if labels.get("location") == location)


def e1_e2_predict_paths() -> None:
    mod = importlib.import_module("app.core.text_m2_bert_predictor")
    loc = "core.text_m2_bert_predictor.predict_failed"

    # ---- E1：失败路径 ----
    class _Boom:
        def __call__(self, *a, **k):
            raise RuntimeError("tokenizer boom")

    p = mod.TextM2BertPredictor()
    p._initialized = True
    p._tokenizer = _Boom()
    p._device = "cpu"
    p._threshold = 0.5
    before = loc_count(loc)
    out = asyncio.run(p.predict("测试文本"))
    after = loc_count(loc)
    report(
        "E1",
        out is None and after == before + 1,
        f"predict 失败 → return None（got {out!r}），计数 {before}→{after}",
    )

    # ---- E2：成功路径（防假绿）----
    class _FakeInputs(dict):
        pass

    class _FakeTensor:
        def __init__(self, arr):
            self._arr = arr

        def to(self, device):
            return self

        def cpu(self):
            return self

        def numpy(self):
            return self._arr

    class _FakeHS:
        def __getitem__(self, idx):
            return _FakeTensor([[0.1, 0.2, 0.3]])

    class _FakeOut:
        last_hidden_state = _FakeHS()

    class _Tok:
        def __call__(self, *a, **k):
            return _FakeInputs(input_ids=_FakeTensor([[1, 2, 3]]))

    class _Bert:
        def __call__(self, **k):
            return _FakeOut()

    class _Scaler:
        def transform(self, x):
            return [[0.1, 0.2, 0.3]]

    class _Clf:
        def predict_proba(self, x):
            return [[0.2, 0.8]]

    p2 = mod.TextM2BertPredictor()
    p2._initialized = True
    p2._tokenizer = _Tok()
    p2._bert_model = _Bert()
    p2._scaler = _Scaler()
    p2._classifier = _Clf()
    p2._device = "cpu"
    p2._threshold = 0.5
    before2 = loc_count(loc)
    out2 = asyncio.run(p2.predict("正常文本"))
    after2 = loc_count(loc)
    ok2 = (
        isinstance(out2, dict)
        and out2["prediction"] == 1
        and out2["model_used"] == "text_m2_bert"
        and after2 == before2
    )
    report(
        "E2",
        ok2,
        f"predict 成功 → dict(prediction={out2.get('prediction') if isinstance(out2, dict) else out2!r})，"
        f"计数 {before2}→{after2}（不涨）",
    )


def e3_log_sanitizer_reachable() -> None:
    ls = importlib.import_module("app.core.log_sanitizer")
    f = ls.SanitizingFilter()
    loc = "core.log_sanitizer.filter_failed"

    def make(msg, args=None, exc_info=None):
        return logging.LogRecord(
            name="t", level=logging.INFO, pathname="x.py", lineno=1,
            msg=msg, args=args, exc_info=exc_info,
        )

    # ---- 触发：exc_info 是异常实例（非 tuple）----
    # CPython LogRecord 对非 tuple 的 exc_info 有专门分支（保留异常实例），
    # L443 len(record.exc_info) ⇒ TypeError ⇒ L449。
    try:
        raise ValueError("boom password=secret")
    except ValueError as e:
        exc_obj = e
    before = loc_count(loc)
    out = f.filter(make("failed", (), exc_obj))
    after = loc_count(loc)
    report(
        "E3",
        out is True and after == before + 1,
        f"exc_info=异常实例 → filter 仍返回 True（未脱敏放行），"
        f"计数 {before}→{after}（接线生效；L443 len() TypeError 被 L449 捕获）",
    )

    # ---- 对照组①：exc_info 为合法 tuple（logger.exception 形态）----
    try:
        raise ValueError("boom password=secret")
    except ValueError as e:
        tup = (type(e), e, e.__traceback__)
    before2 = loc_count(loc)
    f.filter(make("failed", (), tup))
    after2 = loc_count(loc)
    report(
        "E3b",
        after2 == before2,
        f"exc_info=合法 tuple → 计数 {before2}→{after2}（不涨；"
        "证明接线只钉脱敏失败路径，不是恒真）",
    )

    # ---- 对照组②：无 exc_info 的正常 record（含 PII）----
    before3 = loc_count(loc)
    f.filter(make("login ok password=%s", ("secret",)))
    after3 = loc_count(loc)
    report(
        "E3c",
        after3 == before3,
        f"正常 record → 计数 {before3}→{after3}（不涨）",
    )


def e4_scaler_p_type() -> None:
    src = pathlib.Path(BACKEND / "app/ml/scaler.py").read_text(encoding="utf-8")
    tree = ast.parse(src)
    # 找 L47 的 ExceptHandler
    target = None
    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler) and node.lineno == 47:
            target = node
            break
    assert target is not None, "scaler.py:47 except handler 不见了"
    body = target.body
    # try 体内只有 import + 一次调用
    try_body: list[ast.stmt] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Try):
            for h in node.handlers:
                if h is target:
                    try_body = node.body
    kinds = [type(s).__name__ for s in try_body]
    ok_shape = kinds == ["ImportFrom", "Assign"] and isinstance(
        try_body[1].value, ast.Call
    )
    # 被调函数 _resolve_artifacts_dir 内层全捕获
    ml_src = pathlib.Path(BACKEND / "app/ml/model_loader.py").read_text(encoding="utf-8")
    ml_tree = ast.parse(ml_src)
    callee_has_catch = False
    for node in ast.walk(ml_tree):
        if isinstance(node, ast.FunctionDef) and node.name == "_resolve_artifacts_dir":
            callee_has_catch = any(
                isinstance(s, ast.Try) and any(
                    h.type is not None and getattr(h.type, "id", "") == "Exception"
                    for h in s.handlers
                )
                for s in node.body
            )
    report(
        "E4",
        ok_shape and callee_has_catch,
        f"try 体形态 {kinds}（只有 import+调用），被调 _resolve_artifacts_dir "
        f"内层 except Exception 全捕获={callee_has_catch} ⇒ 外层唯一可达路径是 import 失败",
    )

    # 正常访问：走 _resolve_artifacts_dir 的自身分支（本机 artifacts 存在时
    # 是正常分支；不存在时是其内层 except 的 fallback 分支）——两条都不经过
    # scaler.py:47 外层 except。
    scaler = importlib.import_module("app.ml.scaler")
    ml = importlib.import_module("app.ml.model_loader")
    path = scaler.SCALER_PATH
    resolved = ml._resolve_artifacts_dir()
    report(
        "E4b",
        path == resolved / "scaler.json",
        f"SCALER_PATH={path} == _resolve_artifacts_dir()/{'scaler.json'} "
        f"（{resolved}）⇒ 外层 except 不参与",
    )


def e5_startup_status_homologous() -> None:
    import app.core.metrics as metrics_mod
    from app.core.degradation import record_silent_degradation

    real_inc = metrics_mod.silent_degradation_total.inc

    class _Boom:
        def inc(self, *a, **k):
            raise RuntimeError("metrics subsystem down")

    metrics_mod.silent_degradation_total = _Boom()  # type: ignore[assignment]
    try:
        before = snapshot()
        record_silent_degradation("probe.startup_status.homologous")  # 不抛
        after = snapshot()
        # 真实 inc 也被同一次阻断影响（record 自身吞异常）
        real_inc_ok = True
        try:
            metrics_mod.startup_component_failures_total.inc(component="probe")
        except Exception:
            real_inc_ok = False
        report(
            "E5",
            after == before and not real_inc_ok,
            f"阻断 app.core.metrics 后：record_silent_degradation 计数 {before}→{after}"
            f"（0 增量 = 同源失效），startup_component_failures_total.inc 同样抛"
            f"（{real_inc_ok}）⇒ L100 接线即恒 0",
        )
    finally:
        metrics_mod.silent_degradation_total = type(  # type: ignore[assignment]
            "R", (), {}
        )()
        # 还原：重新 import 拿真对象
        import importlib as _il

        fresh = _il.import_module("app.core.metrics")
        metrics_mod.silent_degradation_total = fresh.silent_degradation_total


def main() -> int:
    print("=" * 78)
    print("第三十六批运行时探针（E1~E5）")
    print("=" * 78)
    e1_e2_predict_paths()
    e3_log_sanitizer_reachable()
    e4_scaler_p_type()
    e5_startup_status_homologous()
    print("-" * 78)
    failed = [e for e, ok, _ in RESULTS if not ok]
    print(f"{len(RESULTS) - len(failed)}/{len(RESULTS)} 成立；失败: {failed or '无'}")
    return 1 if failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
