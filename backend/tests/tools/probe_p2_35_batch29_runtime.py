"""第二十九批运行时证据（4 项，为裁定提供可客断言）。

E1 `otel_enabled` 曾是**全仓零消费**的死配置（第二十九批时点）；ROUND_42
   已接线改判：`main._init_otel` 透传 `enabled=settings.otel_enabled`，
   `init_otel` 在装配前按 `enabled` 硬性判定。本探针反转为「唯一消费位置」。
E2 otel 依赖形态不变：`requirements.txt` 无任何 opentelemetry 条目，
   `requirements.lock` 只有间接依赖 `opentelemetry-api==1.45.0`（无 sdk /
   exporter / instrumentation）。ROUND_42 后 main 路径的默认阻断是
   `otel_enabled=False`；库级直调（`enabled` 默认 True）在 endpoint 为空时
   仍走 endpoint 空分支返回 SKIPPED（ROUND_40 起三态）。
E3 `main.py:_init_otel` 曾**丢弃 `init_otel` 的返回值** ⇒ `record_step_sync(
   "init_otel", _init_otel, fatal=False)` 把状态记为 `ok`。ROUND_40 已修复
   （三态契约 + 模块级映射），本探针反转为验证 failed 状态可见。
E4 `_common.py` 五处脏数据 handler：非数值特征值被 `continue` 跳过，返回结构
   与正常态同形，且 `data_quality=="poor"` 时仍有兜底因子。

用法：.venv/Scripts/python.exe tests/tools/probe_p2_35_batch29_runtime.py
"""

from __future__ import annotations

import ast
import builtins
import importlib
import pathlib
import sys

BACKEND = pathlib.Path(__file__).resolve().parents[2]
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

DOCS = ("app/core/otel.py", "app/api/v1/model_predict/_common.py")


def e1_otel_enabled_wired() -> None:
    """E1（ROUND_42 反转）：`otel_enabled` 的实际消费位置恰好一处。"""
    consumers: list[str] = []
    for p in (BACKEND / "app").rglob("*.py"):
        if "__pycache__" in p.parts:
            continue
        try:
            tree = ast.parse(p.read_text(encoding="utf-8"))
        except Exception:
            continue
        for n in ast.walk(tree):
            if isinstance(n, ast.Attribute) and n.attr == "otel_enabled":
                consumers.append(f"{p.relative_to(BACKEND).as_posix()}:{n.lineno} Attribute")
    print(f"[E1] otel_enabled 代码消费点: {consumers}")
    assert len(consumers) == 1 and consumers[0].startswith("app/main.py:"), (
        f"otel_enabled 消费点应为恰好 1 处且在 main.py，实际 {consumers}"
    )
    main_src = (BACKEND / "app" / "main.py").read_text(encoding="utf-8")
    assert "enabled=settings.otel_enabled," in main_src, "main.py 未透传 otel_enabled"
    assert "resource_attributes=settings.otel_resource_attributes," in main_src, (
        "main.py 未透传 otel_resource_attributes"
    )
    assert "otlp_endpoint=settings.otlp_endpoint," in main_src, "main.py 的参数透传形态漂移"
    from app.core.config import Settings

    s = Settings()
    print(f"[E1b] Settings().otel_enabled={s.otel_enabled} otlp_endpoint={s.otlp_endpoint!r}")
    assert s.otel_enabled is False, "otel_enabled 默认值不再是 False"
    assert s.otlp_endpoint == "", "otlp_endpoint 默认值不再是空串"
    print("[E1]⇒ otel_enabled 由死配置改判为真开关（单一消费位置）")


def e2_otel_dependency_unreachable() -> None:
    """E2：otel 依赖在交付物中不完整 ⇒ 装配路径无真实 SDK（库级直调可证）。"""
    lock = (BACKEND / "requirements.lock").read_text(encoding="utf-8")
    req = (BACKEND / "requirements.txt").read_text(encoding="utf-8")
    assert "opentelemetry-sdk" not in lock, "sdk 已进requirements.lock ⇒ E2 需重估"
    assert "opentelemetry-exporter" not in lock, "exporter 已进 lock ⇒ E2 需重估"
    assert "opentelemetry-instrumentation" not in lock, "instrumentation 已进 lock ⇒ E2 需重估"
    assert "opentelemetry" not in req.lower(), "requirements.txt 出现 opentelemetry 条目 ⇒ E2 需重估"
    print("[E2a] requirements.txt 零 opentelemetry；lock 仅间接依赖 opentelemetry-api")

    otel = importlib.import_module("app.core.otel")
    available = otel._check_otel_available()
    print(f"[E2b] _check_otel_available() -> {available}（不钉环境，仅记录）")
    # endpoint 空 ⇒ 无论依赖门开/关，init_otel 都返回 SKIPPED
    otel._otel_initialized = False
    rc = otel.init_otel("probe", otlp_endpoint="")
    print(f"[E2c] init_otel(endpoint='') -> {rc}")
    assert rc is otel.OtelInit.SKIPPED, "默认配置下 init_otel 应返回 SKIPPED"
    print(
        "[E2]⇒ 依赖未交付（无 sdk/exporter）+ 库级 endpoint 空 ⇒ 装配前的 "
        "两条 SKIPPED 路径；ROUND_42 后 main 路径另由 otel_enabled=False 前置阻断"
    )


def e3_init_otel_startup_status_exposes_failed() -> None:
    """E3（ROUND_40 反转）：main._init_otel 把 FAILED 如实映射为 failed。"""
    importlib.import_module("app.core.otel")
    main_mod = importlib.import_module("app.main")
    ss = importlib.import_module("app.core.startup_status")
    from app.core.otel import OtelInit

    original = main_mod.init_otel
    ss.startup_status.reset()
    try:
        main_mod.init_otel = lambda **kw: OtelInit.FAILED
        # 生产函数 + fatal=False：失败必须被记录但不阻断启动
        out = ss.record_step_sync("init_otel", main_mod._init_otel, fatal=False)
        rec = ss.startup_status.components["init_otel"]
        print(
            f"[E3] init_otel 启动状态 -> status={rec.status!r} "
            f"error_type={rec.error_type!r} wrapper_return={out!r}"
        )
        assert out is None, "fatal=False 的失败不得冒泡"
        assert rec.status == "failed", "FAILED 又被吞成了非失败状态"
        assert rec.error_type == "OTelInitError"
        assert "init_otel" in ss.startup_status.failed_components
    finally:
        main_mod.init_otel = original
        ss.startup_status.reset()
    print(
        "[E3]⇒ ROUND_40 起 /health/startup 能区分 ok / skipped / failed："
        "配置了 endpoint 但装配失败时记 failed（/health/ready 降级），"
        "未启用记 skipped 且不进 failed_components"
    )


def e4_common_dirty_data_same_shape() -> None:
    """E4：_common.py 五处脏数据 handler —— 返回结构与正常态同形。"""
    common = importlib.import_module("app.api.v1.model_predict._common")

    # 结构化：非数值特征被 continue 跳过
    good = common._generate_structured_factors(
        {"features": {"stress_level": 5, "anxiety": 4}}, {"features": {"stress_level": 5, "anxiety": 4}}
    )
    dirty = common._generate_structured_factors(
        {"features": {"stress_level": "abc", "anxiety": None}},
        {"features": {"stress_level": "abc", "anxiety": None}},
    )
    print(f"[E4a] structured good={good}")
    print(f"[E4a] structured dirty={dirty}")
    assert isinstance(dirty, list), "返回类型应仍是 list"
    assert dirty == [], "全脏数据时应无因子（continue 跳过）"
    assert good, "对照：正常数据应产出因子（证明不是一律返回空的退化实现）"

    # 生理：四个字段分别投脏值，全部被 debug 日志接住并跳过
    for field in ("sleep_hours", "heart_rate", "steps", "exercise_minutes"):
        out = common._generate_physio_factors({"physiological_data": {field: "坏值"}}, {})
        assert isinstance(out, list), f"{field} 脏值返回类型异常"
        assert out == [], f"{field} 脏值应被跳过，实际={out}"
    print("[E4b] physio 四个字段脏值皆被跳过，返回 list 空")

    # poor data_quality 兜底仍在（脏数据不会让整个 factors 消失）
    poor = common._generate_physio_factors({"physiological_data": {}, "data_quality": "poor"}, {})
    print(f"[E4c] data_quality=poor 兜底因子 -> {poor}")
    assert poor and poor[0]["feature"] == "数据质量", "poor 兜底因子消失"
    print("[E4]⇒ 五处 D 型：脏数据被逐字段跳过，返回结构与正常态同形")


def main() -> int:
    print("=" * 72)
    print("P2-35 第二十九批运行时证据")
    print("=" * 72)
    e1_otel_enabled_wired()
    print("-" * 72)
    e2_otel_dependency_unreachable()
    print("-" * 72)
    e3_init_otel_startup_status_exposes_failed()
    print("-" * 72)
    e4_common_dirty_data_same_shape()
    print("=" * 72)
    print("四项证据全部成立")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())