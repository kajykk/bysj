"""第二十九批运行时证据（4 项，为裁定提供可客断言）。

E1 `otel_enabled` 配置项**全仓零消费**（AST 证据）：唯一命中是 otel.py 模块
   docstring 里的说明文字，不是代码读取。`main.py:_init_otel` 只看
   `settings.otlp_endpoint`（默认 `""`）⇒ 默认部署走 `return False` 分支。
E2 otel 依赖**双重不可达**：`requirements.txt` 无任何 opentelemetry 条目，
   `requirements.lock` 只有间接依赖 `opentelemetry-api==1.45.0`（无 sdk /
   exporter / instrumentation）⇒ `_check_otel_available()` 返回 False，
   `init_otel` 在 L63 提前返回，走不到 L133 的 handler。
E3 `main.py:_init_otel` **丢弃 `init_otel` 的返回值** ⇒ `record_step_sync(
   "init_otel", _init_otel, fatal=False)` 把状态记为 `ok` —— 与第二十七批
   `init_sentry` 完全同型（第二次出现该信号）。
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


def e1_otel_enabled_zero_consumers() -> None:
    """E1：`otel_enabled` 只有定义与 docstring，无任何代码读取。"""
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
                consumers.append(f"{p.name}:{n.lineno} Attribute")
    print(f"[E1] otel_enabled 代码消费点: {consumers}")
    assert consumers == [], (
        f"otel_enabled 出现代码消费点 {consumers} —— "
        "「配置项声明但从不消费」的发现需重估"
    )
    # main.py 的 _init_otel 只透传 otlp_endpoint，不透传 otel_enabled
    main_src = (BACKEND / "app" / "main.py").read_text(encoding="utf-8")
    assert "otel_enabled" not in main_src, "main.py 开始读otel_enabled 了"
    assert "otlp_endpoint=settings.otlp_endpoint," in main_src, "main.py 的参数透传形态漂移"
    from app.core.config import Settings

    s = Settings()
    print(f"[E1b] Settings().otel_enabled={s.otel_enabled} otlp_endpoint={s.otlp_endpoint!r}")
    assert s.otel_enabled is False, "otel_enabled 默认值不再是 False"
    assert s.otlp_endpoint == "", "otlp_endpoint 默认值不再是空串 ⇒ E2 的提前 return 前提需重估"
    print("[E1]⇒ otel_enabled 是**死配置**：默认部署下从未被任何代码读取")


def e2_otel_dependency_unreachable() -> None:
    """E2：otel 依赖在交付物中不存在 ⇒ init_otel 提前 return，走不到 L133。"""
    lock = (BACKEND / "requirements.lock").read_text(encoding="utf-8")
    req = (BACKEND / "requirements.txt").read_text(encoding="utf-8")
    assert "opentelemetry-sdk" not in lock, "sdk 已进requirements.lock ⇒ E2 需重估"
    assert "opentelemetry-exporter" not in lock, "exporter 已进 lock ⇒ E2 需重估"
    assert "opentelemetry-instrumentation" not in lock, "instrumentation 已进 lock ⇒ E2 需重估"
    assert "opentelemetry" not in req.lower(), "requirements.txt 出现 opentelemetry 条目 ⇒ E2 需重估"
    print("[E2a] requirements.txt 零 opentelemetry；lock 仅间接依赖 opentelemetry-api")

    otel = importlib.import_module("app.core.otel")
    print(f"[E2b] _check_otel_available() -> {otel._check_otel_available()}")
    assert otel._check_otel_available() is False, (
        "opentelemetry 可导入 —— 本机环境与交付物不一致，E2 结论仅对交付物成立"
    )
    # otel_enabled=False + endpoint 空 ⇒ init_otel 必走L71 的 `return False`
    rc = otel.init_otel("probe", otlp_endpoint="")
    print(f"[E2c] init_otel(endpoint='') -> {rc}")
    assert rc is False, "默认配置下init_otel 应返回 False"
    print(
        "[E2]⇒ 双重不可达（依赖未交付 + endpoint 默认空）⇒ "
        "L133/L151/L166/L180 的 handler 在交付形态下不可达"
    )


def e3_init_otel_return_value_discarded() -> None:
    """E3：main.py 丢弃 init_otel 返回值 ⇒ /health/startup 把失败记为 ok。"""
    importlib.import_module("app.core.otel")
    ss = importlib.import_module("app.core.startup_status")

    from app.core.config import settings

    def _init_otel():
        from app.core.otel import init_otel

        # 与 main.py L253-262逐字同形：调用但不 return
        init_otel(
            service_name=settings.otel_service_name,
            service_version=settings.app_version,
            otlp_endpoint=settings.otlp_endpoint,
            otlp_protocol=settings.otlp_protocol,
            environment=settings.sentry_environment,
        )

    ss.record_step_sync("init_otel", _init_otel, fatal=False)
    rec = ss.startup_status.components["init_otel"]
    print(f"[E3] init_otel 启动状态 -> status={rec.status!r} error_type={rec.error_type!r}")
    assert rec.status == "ok", (
        f"启动状态变为 {rec.status!r} —— 若改为 failed/skipped，"
        "第二十七/二十九批的「S 型不接线」判据需重估"
    )
    assert rec.error_type == "", "不应有 error_type"
    print(
        "[E3]⇒ 与第二十七批 init_sentry 完全同型：SDK/依赖不可用时"
        "/health/startup 记 ok，运维无法区分「追踪已启用」与「依赖根本没装」"
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
    e1_otel_enabled_zero_consumers()
    print("-" * 72)
    e2_otel_dependency_unreachable()
    print("-" * 72)
    e3_init_otel_return_value_discarded()
    print("-" * 72)
    e4_common_dirty_data_same_shape()
    print("=" * 72)
    print("四项证据全部成立")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())