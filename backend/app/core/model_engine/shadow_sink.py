"""影子模式对拍 sink 的协议定义.

ARCH-FIX-2026-10-05: 引入本协议以解除 core → services 的跨层反向依赖。

原问题:
    app/core/model_engine/predict.py 的 _maybe_fire_shadow_predict 为触发
    M2 BERT 对拍，在函数体内 `from app.services.shadow_mode_service import
    get_shadow_mode_service` —— core 层（被定义为最底层）反向依赖 services 层。
    连带后果:
      - core/model_engine 一旦被 import 就拉起 app.ml.* 与（延迟）services 依赖树；
      - 任何脚本 / 单测只想用 ModelEngine 做纯推理，也必须能 import 完整
        services + ML 依赖树，缺 transformers 就在 import 期炸掉，
        而不是真正调用推理时才失败。

解法（依赖倒置）:
    core 只声明它需要的「能力」，具体实现由外层在启动时注入。
    core 不再 import services —— 依赖方向变为 services → core，符合分层。

    ShadowSink 故意定义在 core 而不是 services：它是 core 的**依赖契约**，
    归属被依赖方是正确方向（就像 core 声明 DB 接口由上层实现）。
"""

from __future__ import annotations

from typing import Any, Protocol, runtime_checkable


@runtime_checkable
class ShadowSink(Protocol):
    """core 层对「影子对拍接收端」的能力要求。

    实现方通常是 app.services.shadow_mode_service.ShadowModeService，
    但 core 不需要知道具体类型 —— 任何满足本协议的对象都能注入。
    """

    def fire_shadow_predict(
        self,
        text: str,
        production_result: dict[str, Any],
        sample_rate: float = 1.0,
    ) -> None:
        """异步触发一次对拍（fire-and-forget，不得阻塞主请求）。

        实现方必须自行保证不抛异常到调用方：对拍失败绝不能影响生产结果。

        Args:
            text: 生产请求的原始文本
            production_result: 生产链路的推理结果（用于对比）
            sample_rate: 采样率，0~1；实现方可自行决定是否跳过
        """
        ...


class NullShadowSink:
    """默认实现：什么都不做。

    用于两种场景:
      1. 未注入（单元测试、CLI 脚本、Celery worker 等非 Web 入口）;
      2. 影子模式开关关闭。

    之所以提供 no-op 而不是让 core 直接 raise，是为了让「未配置」与
    「配置为空」行为一致 —— 影子对拍本身是可选的旁路功能，
    它不可用绝不能影响生产推理。
    """

    __slots__ = ()

    def fire_shadow_predict(
        self,
        text: str,
        production_result: dict[str, Any],
        sample_rate: float = 1.0,
    ) -> None:
        """直接返回，不做任何对拍。"""
        return None


__all__ = ["NullShadowSink", "ShadowSink"]
