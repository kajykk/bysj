"""第三十三批运行时证据：12 个文件 15 条候选的机器可验证判据。

E1  api/v1/user_upload.py:161 `_validate_mime_type` —— **libmagic 不可用**与
    **MIME 校验通过**对调用方完全同形（`_process_batch_file` 都返回带 url 的
    成功结果）⇒ 满足接线判据。对照组（MIME 与扩展名不匹配）返回 error，
    证明该断言有区分力，不是恒真。
E2  core/fire_forget_metrics.py 两条 —— 失败的是**可观测设施自身**；且
    `record_silent_degradation` 同样走 `app.core.metrics`（degradation.py:30），
    当 metrics 子系统不可用时**两者同时失效** ⇒ 接线即恒 0 假设施（S 型）。
E3  db_breaker 2 / smtp_breaker 1 / ml_breaker 1 / drift_detector 1 ——
    sqlalchemy / asyncpg / fastapi / scipy 在交付形态下全部可导入 ⇒
    5 条 `except ImportError` 不可达（P 型）。
E4  两个 job_store 的 `_cleanup_expired` —— 混合输入下「脏 created_at 只跳过
    自己，其余过期条目照常清理」⇒ D 型。
E5  services/email_service.py:164 `_send_smtp` —— 重试耗尽后 `raise last_exc`
    向上传播，上层再转 `ValueError` ⇒ **失败态与正常态不同形**（V 型），
    分类器按 sleep+retry 粗判 R 属误并。
"""

from __future__ import annotations

import asyncio
import importlib
import io
import pathlib
import sys
import tempfile
import time
import types

BACKEND = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))


def e1_mime_check_skipped_is_silent() -> None:
    """E1：libmagic 不可用时 MIME 校验被**静默跳过**，与校验通过完全同形。"""
    mod = importlib.import_module("app.api.v1.user_upload")

    class _FakeUpload:
        def __init__(self, name: str, payload: bytes) -> None:
            self.filename = name
            self._buf = io.BytesIO(payload)
            self._pos = 0

        async def read(self, n: int = -1) -> bytes:
            return self._buf.read(n)

        async def seek(self, offset: int) -> int:
            return self._buf.seek(offset)

    def _stub_security(file_path, category):  # noqa: ANN001 - 探针桩
        return True, "stub"

    async def _drive() -> dict:
        with tempfile.TemporaryDirectory() as td:
            base = pathlib.Path(td)
            (base / "1").mkdir()
            f = _FakeUpload("a.png", b"\x89PNG\r\n\x1a\n" + b"0" * 64)
            return await mod._process_batch_file(f, "image", base, "1", 1)

    orig_security = mod.process_uploaded_file
    orig_from_buffer = mod.magic.from_buffer
    try:
        mod.process_uploaded_file = _stub_security

        # (a) 正常态：MIME 与扩展名匹配
        mod.magic.from_buffer = lambda *a, **k: "image/png"
        ok_shape = asyncio.run(_drive())

        # (b) 降级态：libmagic 抛异常（MagicException）
        def _boom(*a, **k):  # noqa: ANN001 - 探针桩
            raise mod.magic.MagicException("libmagic database unavailable")

        mod.magic.from_buffer = _boom
        degraded_shape = asyncio.run(_drive())

        # (c) 对照组：MIME 与扩展名不匹配 ⇒ 必须被拒（证明断言有区分力）
        mod.magic.from_buffer = lambda *a, **k: "text/plain"
        mismatch = asyncio.run(_drive())
    finally:
        mod.process_uploaded_file = orig_security
        mod.magic.from_buffer = orig_from_buffer

    print(f"[E1] 正常态(MIME 匹配)      -> {ok_shape}")
    print(f"[E1] 降级态(libmagic 抛错)  -> {degraded_shape}")
    print(f"[E1] 对照组(MIME 不匹配)    -> {mismatch}")

    assert "url" in ok_shape and "error" not in ok_shape, (
        f"正常态应上传成功，实际={ok_shape}"
    )
    assert "url" in degraded_shape and "error" not in degraded_shape, (
        f"降级态应同样上传成功（静默跳过 MIME 校验），实际={degraded_shape}"
    )
    assert "error" in mismatch and "url" not in mismatch, (
        f"对照组：MIME 不匹配必须被拒，否则 E1 同形性断言是恒真的，实际={mismatch}"
    )
    assert set(ok_shape) == set(degraded_shape), (
        f"两种形态返回键必须一致：{set(ok_shape)} vs {set(degraded_shape)}"
    )
    print("[E1] ⇒ 降级态与正常态响应**同形**（都返回 url），调用方无从察觉；")
    print("     对照组被拒证明该同形性断言有区分力 ⇒ 满足接线判据")


def e2_fire_forget_is_same_source_as_wiring() -> None:
    """E2：fire_forget 的降级与「接线设施」同源 —— metrics 挂了两者一起失效。

    `record_silent_degradation`（degradation.py:30-32）内部就是
    `from app.core.metrics import silent_degradation_total` + `.inc()`；
    `record_scheduled` / `_callback` 保护的也是 `app.core.metrics` 的 Counter。
    ⇒ 若给这两条接上 `record_silent_degradation`，在 metrics 不可用时
    接线**同样静默失效**（被 degradation.py:33 的 `except: pass` 吞掉），
    构成第二十九批所禁止的「看起来有降级观测、实际永不触发」的假设施。
    """
    ffm = importlib.import_module("app.core.fire_forget_metrics")

    class _Blocker:
        """拦截 app.core.metrics 的导入（模拟 metrics 子系统不可用）。"""

        def find_module(self, fullname, path=None):  # noqa: ANN001 - 探针桩
            return None

        def find_spec(self, fullname, path=None, target=None):  # noqa: ANN001
            if fullname == "app.core.metrics":
                raise ImportError("metrics subsystem unavailable (simulated)")
            return None

    calls = {"scheduled": 0}

    # 未阻断：fire_forget 真的打到 Counter（对照，证明它不是天生静默）
    metrics_mod = importlib.import_module("app.core.metrics")
    counter = metrics_mod.silent_degradation_total  # 先握住对象引用，阻断后仍可读
    orig_inc = metrics_mod.fire_forget_tasks_total.inc
    metrics_mod.fire_forget_tasks_total.inc = lambda *a, **k: calls.__setitem__(
        "scheduled", calls["scheduled"] + 1
    )
    ffm.record_scheduled("probe")
    metrics_mod.fire_forget_tasks_total.inc = orig_inc
    print(f"[E2] 对照（metrics 可用）：record_scheduled 打到 Counter 次数 = {calls['scheduled']}")
    assert calls["scheduled"] == 1, "metrics 可用时 record_scheduled 应真的打到 Counter"

    def _read(loc: str) -> float:
        for labels, value in counter.collect():
            if labels.get("location") == loc:
                return float(value)
        return 0.0

    probe_loc = "probe.batch33.same_source"
    before = _read(probe_loc)

    # 阻断：光插 meta_path 不够 —— `app.core.metrics` 已在 sys.modules 缓存里，
    # `from app.core.metrics import x` 不会再走 finder。必须同时清缓存。
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
            pass  # 预期
        else:
            raise AssertionError("阻断未生效（app.core.metrics 仍可导入）⇒ E2 是假证据")

        # 阻断后：fire_forget 的 except 触发（静默）
        ffm.record_scheduled("probe")  # 不应抛

        # 阻断后：接线设施同样静默失效
        deg = importlib.import_module("app.core.degradation")
        deg.record_silent_degradation(probe_loc)  # 不应抛
    finally:
        sys.meta_path.remove(blocker)
        sys.modules.update(saved)

    after = _read(probe_loc)
    print(
        f"[E2] metrics 不可用时：record_scheduled 静默返回；"
        f"record_silent_degradation 也静默返回，"
        f"silent_degradation_total{{location={probe_loc}}} {before} -> {after}"
    )
    assert after == before, (
        f"metrics 不可用时接线设施不应产生任何计数（{before} -> {after}）—— "
        "它同样依赖 app.core.metrics，与 fire_forget 同源"
    )
    print("[E2] ⇒ 两者同源（都依赖 app.core.metrics）⇒ 接线即恒 0 假设施，判 S 型不接")


def e3_breaker_and_scipy_imports_available() -> None:
    """E3：sqlalchemy / asyncpg / fastapi / scipy 在交付形态下全部可导入。"""
    for modname, attr in (
        ("sqlalchemy.exc", "DBAPIError"),
        ("asyncpg", "PostgresConnectionError"),
        ("fastapi", "HTTPException"),
        ("scipy.stats", "ks_2samp"),
    ):
        mod = importlib.import_module(modname)
        assert hasattr(mod, attr), f"{modname}.{attr} 缺失"
        print(f"[E3] {modname}.{attr} 可导入")

    req = (BACKEND / "requirements.txt").read_text(encoding="utf-8")
    for token in ("asyncpg>=", "sqlalchemy[asyncio]>=", "scipy>="):
        assert token in req, f"requirements.txt 缺 {token} ⇒ P 型判据需重估"
    print("[E3] requirements.txt 顶层含 asyncpg / sqlalchemy / scipy ⇒ 5 条 ImportError 不可达")

    # drift_detector：scipy 可用时 compute_ks_test 不走近似分支
    dd = importlib.import_module("app.ml.drift_detector")
    import numpy as np  # type: ignore[import-untyped]

    det = dd.DriftDetector() if hasattr(dd, "DriftDetector") else None
    if det is not None and hasattr(det, "compute_ks_test"):
        ref = np.random.default_rng(0).normal(0, 1, 200)
        cur = np.random.default_rng(1).normal(0.5, 1, 200)
        out = det.compute_ks_test(ref, cur)
        assert "statistic" in out and "error" not in out, f"应走精确 ks_2samp，实际={out}"
        print(f"[E3] compute_ks_test 走精确分支（无 error 键）：{sorted(out)}")


def e4_job_store_dirty_skips_only_itself() -> None:
    """E4：脏 created_at 只跳过自己，其余过期条目照常清理（D 型）。"""
    mod = importlib.import_module("app.services.pdf_job_store")
    from datetime import datetime, timedelta, timezone

    store = mod.PdfJobStore()
    old = (datetime.now(timezone.utc) - timedelta(seconds=mod.JOB_TTL_SECONDS + 60)).isoformat()
    fresh = datetime.now(timezone.utc).isoformat()

    store._jobs = {
        "dirty": mod.PdfJob("dirty", "completed", "u", 1, "not-a-timestamp"),
        "expired1": mod.PdfJob("expired1", "completed", "u", 1, old),
        "expired2": mod.PdfJob("expired2", "completed", "u", 1, old),
        "alive": mod.PdfJob("alive", "running", "u", 1, fresh),
    }
    store._cleanup_expired()
    left = sorted(store._jobs)
    print(f"[E4] 清理后剩余：{left}")
    assert "dirty" in left, "脏 created_at 无法解析 ⇒ 保留（不确定就不删，保守）"
    assert "expired1" not in left and "expired2" not in left, (
        f"两条正常过期条目必须被清理，实际剩余={left}"
    )
    assert "alive" in left, "未过期条目不应被清理"
    print("[E4] ⇒ 脏条目只跳过自己（混合输入实测），其余照常清理 ⇒ D 型")


def e5_smtp_retry_exhausted_raises() -> None:
    """E5：`_send_smtp` 重试耗尽后**抛**异常（V 型，不是自愈后继续）。"""
    import smtplib

    mod = importlib.import_module("app.services.email_service")
    from email.message import EmailMessage

    svc = mod.EmailService.__new__(mod.EmailService)

    orig_get = mod._get_thread_smtp
    orig_create = mod._create_thread_smtp
    orig_close = mod._close_thread_smtp
    orig_sleep = time.sleep
    try:
        mod._get_thread_smtp = lambda: None
        mod._close_thread_smtp = lambda: None

        def _boom():  # noqa: ANN202 - 探针桩
            raise smtplib.SMTPServerDisconnected("smtp down")

        mod._create_thread_smtp = _boom
        mod.time.sleep = lambda _s: None  # 跳过退避等待

        raised = None
        try:
            svc._send_smtp(EmailMessage())
        except BaseException as exc:  # noqa: BLE001 - 探针
            raised = exc
    finally:
        mod._get_thread_smtp = orig_get
        mod._create_thread_smtp = orig_create
        mod._close_thread_smtp = orig_close
        mod.time.sleep = orig_sleep

    print(f"[E5] 重试耗尽后抛出：{type(raised).__name__}: {raised}")
    assert isinstance(raised, smtplib.SMTPException), (
        f"_send_smtp 重试耗尽后必须把异常抛给上层（V 型），实际={raised!r}"
    )
    print("[E5] ⇒ 失败态（抛异常）与正常态（静默返回）**不同形** ⇒ V 型，分类器判 R 系误并")


def e6_wired_counter_really_increments() -> None:
    """E6：接线后计数器**真的涨**（不是「源码字面量在」就算数）。

    第二十二批教训：专用计数器曾因 `.labels(x).inc()` 误用在自研 Counter 上
    被 except 吞掉，恒 0 却活过全部往批。故接线后必须实测计数值变化。
    """
    mod = importlib.import_module("app.api.v1.user_upload")
    metrics_mod = importlib.import_module("app.core.metrics")

    loc = "api.user_upload.validate_mime_type"

    def _read() -> float:
        # 注意：`app.core.metrics.Counter` 是本仓**自研** Counter（不是
        # prometheus_client），没有 `.labels()` / `._value`，读值走 `collect()`。
        # 第二十二批正是把 prometheus 形态的 `.labels(x).inc()` 用在它上面，
        # 被 except 吞掉后恒 0 —— 故本探针必须按自研形态读。
        for labels, value in metrics_mod.silent_degradation_total.collect():
            if labels.get("location") == loc:
                return float(value)
        return 0.0

    before = _read()

    orig = mod.magic.from_buffer

    def _boom(*a, **k):  # noqa: ANN001 - 探针桩
        raise mod.magic.MagicException("libmagic database unavailable")

    try:
        mod.magic.from_buffer = _boom
        asyncio.run(mod._validate_mime_type(b"\x89PNG\r\n\x1a\n", "image"))
    finally:
        mod.magic.from_buffer = orig

    after = _read()
    print(f"[E6] silent_degradation_total{{location={loc}}}: {before} -> {after}")
    assert after == before + 1, (
        f"接线后计数必须 +1（实际 {before} -> {after}）—— "
        "若恒 0 说明是第二十二批那种死计数器，接线无效"
    )
    print("[E6] ⇒ 接线有效：降级真实进入 /metrics 的 silent_degradation_total")


def main() -> int:
    print("=" * 78)
    print("第三十三批运行时证据")
    print("=" * 78)
    e6_wired_counter_really_increments()
    print()
    e1_mime_check_skipped_is_silent()
    print()
    e2_fire_forget_is_same_source_as_wiring()
    print()
    e3_breaker_and_scipy_imports_available()
    print()
    e4_job_store_dirty_skips_only_itself()
    print()
    e5_smtp_retry_exhausted_raises()
    print("\n全部运行时证据成立。")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
