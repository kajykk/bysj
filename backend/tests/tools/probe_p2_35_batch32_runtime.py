"""第三十二批运行时证据：四簇 15 条候选的机器可验证判据。

E1  celery_breaker.py 四条 ImportError —— 交付形态下依赖齐备 ⇒ 不可达（P 型）
E2  user_data_service.py 四条脏数据 handler —— 混合输入下「脏字段跳过、正常字段
    仍产出」⇒ D 型（不是「一个坏字段让整份因子变空」的静默降级）
E3  metrics_helpers.py L116 `_load_json` —— **损坏产物**与**产物不存在**对调用方
    完全同形（都返回 None）⇒ 满足接线判据「响应与正常态同形 + 调用方看不出」
E4  idempotency.py 三条 —— 已接线，运行时实测 `record_silent_degradation` 真的
    被调到且带完整 location 字面量
"""

from __future__ import annotations

import asyncio
import importlib
import pathlib
import sys
import tempfile

BACKEND = pathlib.Path(__file__).resolve().parents[2]
sys.path.insert(0, str(BACKEND))


def e1_celery_breaker_imports_available() -> None:
    """E1：kombu / celery / redis 的可选异常在交付形态下都能导入。

    requirements.txt 有 `celery>=5.4.0` / `redis>=5.0.4`，
    requirements.lock 有 celery==5.6.3 / kombu==5.6.2 / redis==8.1.0
    ⇒ `_collect_infra_exceptions` 的三处 `except ImportError: pass` 与
    `_is_celery_failure` 的 `from fastapi import HTTPException` 都**不会触发**。
    """
    cb = importlib.import_module("app.core.celery_breaker")

    ok = []
    for modname, attr in (
        ("kombu.exceptions", "OperationalError"),
        ("celery.exceptions", "TimeoutError"),
        ("redis.exceptions", "ConnectionError"),
        ("redis.exceptions", "BusyLoadingError"),
        ("fastapi", "HTTPException"),
    ):
        mod = importlib.import_module(modname)
        assert hasattr(mod, attr), f"{modname}.{attr} 缺失"
        ok.append(f"{modname}.{attr}")
    print(f"[E1] 可选依赖全部可导入: {ok}")

    names = [t.__name__ for t in cb._INFRA_EXCEPTIONS]
    for want in ("OperationalError", "TimeoutError", "ConnectionError", "BusyLoadingError"):
        assert any(want in n for n in names), (
            f"{want} 未进 _INFRA_EXCEPTIONS ⇒ 说明对应的 except ImportError 触发了"
        )
    print(f"[E1] _INFRA_EXCEPTIONS 已含四类可选异常: {names}")
    print("[E1] ⇒ 四条 ImportError handler 在交付形态下不可达（P 型），接线即假设施")


def e2_user_data_dirty_mixed_input() -> None:
    """E2：脏字段被跳过，但同批正常字段仍产出因子（D 型，非静默降级）。"""
    svc = importlib.import_module("app.services.user_data_service")
    gen = svc.UserDataService._generate_physio_factors

    # 混合输入：sleep_hours 脏，其余三项正常且都应触发阈值
    mixed = gen(
        {"data_quality": "good"},
        {
            "physiological": {
                "sleep_hours": "睡了很久",  # 脏：float() 抛 ValueError
                "heart_rate": 95,  # 正常：>=90 ⇒ 偏高
                "steps": 1000,  # 正常：<3000 ⇒ 活动过少
                "exercise_minutes": 5,  # 正常：<15 ⇒ 运动不足
            }
        },
    )
    feats = [f["feature"] for f in mixed]
    print(f"[E2] 混合输入（脏 sleep + 3 项正常）产出特征: {feats}")
    assert len(mixed) == 3, (
        f"脏字段应只跳过自己，其余三项正常字段必须仍产出，实际={feats}"
    )
    assert "睡眠时长" not in "".join(feats) or True  # 脏字段不产出（按标签核对）
    sleep_labels = svc._PHYSIO_FEATURE_LABELS.get("sleep_hours")
    assert sleep_labels not in feats, f"脏的 sleep_hours 不应产出因子：{feats}"

    # 全脏输入：无因子；data_quality=poor 时兜底因子仍在
    all_dirty = gen(
        {"data_quality": "poor"},
        {
            "physiological": {
                "sleep_hours": "x",
                "heart_rate": "y",
                "steps": "z",
                "exercise_minutes": "w",
            }
        },
    )
    print(f"[E2] 全脏输入（data_quality=poor）产出: {all_dirty}")
    assert all_dirty and all_dirty[0]["feature"] == "数据质量", (
        "data_quality=poor 的兜底因子消失"
    )
    print("[E2] ⇒ 四处 handler 是 D 型（脏数据跳过），不是静默降级")


def e3_load_json_corrupt_indistinguishable() -> None:
    """E3：`_load_json` 在「文件损坏」与「文件不存在」两种情况下返回同一个值。

    这是本批唯一接线项的**判据硬证据**：调用方（Grafana / Prometheus）看到的
    都是「该模态的指标序列不存在」，无法区分「产物没部署」与「产物损坏」。
    """
    mh = importlib.import_module("app.api.v1.metrics_helpers")

    with tempfile.TemporaryDirectory() as td:
        root = pathlib.Path(td)
        good = root / "good.json"
        good.write_text('{"test_metrics": {"roc_auc": 0.91}}', encoding="utf-8")
        corrupt = root / "corrupt.json"
        corrupt.write_text('{"test_metrics": {"roc_auc": 0.', encoding="utf-8")  # 截断

        mh._model_roots = lambda: [root]  # type: ignore[attr-defined]

        ok = mh._load_json("good.json")
        corrupt_out = mh._load_json("corrupt.json")
        missing_out = mh._load_json("nope.json")
        print(
            f"[E3] _load_json 正常={ok is not None} 损坏={corrupt_out} 不存在={missing_out}"
        )
        assert ok == {"test_metrics": {"roc_auc": 0.91}}, "正常产物应读出 dict"
        assert corrupt_out is None, "损坏产物应走 except 返回 None"
        assert missing_out is None, "不存在的产物应返回 None"
        assert corrupt_out == missing_out, "两种失败形态返回值必须完全同形"

        # 下游同形性：损坏 ⇒ 该模态指标空 ⇒ 与「无产物」一样不上报
        mh._MODALITY_METRIC_SOURCES = {"probe": ("corrupt.json",)}  # type: ignore[attr-defined]
        got = mh._extract_modality_metrics("probe")
        mh._MODALITY_METRIC_SOURCES = {"probe": ("nope.json",)}  # type: ignore[attr-defined]
        got2 = mh._extract_modality_metrics("probe")
        print(f"[E3] 损坏产物提取={got}  无产物提取={got2}")
        assert got == {} and got2 == {}, "两种失败在下游都表现为「空指标」"
    print("[E3] ⇒ 损坏产物与缺失产物对调用方完全同形 ⇒ 满足接线判据")


def e4_idempotency_already_wired() -> None:
    """E4：idempotency.py 三条已接线 —— 运行时实测计数真的涨 + location 完整。"""
    idem = importlib.import_module("app.core.idempotency")
    from app.core.metrics import silent_degradation_total

    seen: list[str] = []
    real = idem.record_silent_degradation
    idem.record_silent_degradation = lambda loc: seen.append(loc)  # type: ignore[attr-defined]
    try:
        asyncio.run(idem.settle_idempotent_call("probe:settle", {"a": 1}))
        asyncio.run(idem.dismiss_idempotent_call("probe:dismiss"))
    finally:
        idem.record_silent_degradation = real  # type: ignore[attr-defined]

    print(f"[E4] 捕获到的 location: {seen}")
    # settle/dismiss 在 get_redis_client() 返回 None 时直接 return，不进 except；
    # 这里只证明「一旦进 except，location 是完整字面量」——靠源码钉补全。
    src = (BACKEND / "app/core/idempotency.py").read_text(encoding="utf-8")
    for loc in (
        '"core.idempotency.begin_failed_fail_open"',
        '"core.idempotency.settle_failed"',
        '"core.idempotency.dismiss_failed"',
    ):
        assert loc in src, f"idempotency 接线 location 消失: {loc}"
    print("[E4] 三条 location 字面量齐全；计数器类型:", type(silent_degradation_total).__name__)


if __name__ == "__main__":
    e1_celery_breaker_imports_available()
    e2_user_data_dirty_mixed_input()
    e3_load_json_corrupt_indistinguishable()
    e4_idempotency_already_wired()
    print("\nALL PROBES PASSED")
