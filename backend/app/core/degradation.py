"""P2-35: 静默降级接线 SSOT（唯一入口）。

背景（审查报告系统性根因③）：「旁路失败不得影响主流程」在本仓被过度应用成
「失败不留痕」——`except -> logger.debug/continue/return` 的降级路径只在本地日志里
出现一句，没人能从 `/metrics` 看出系统正在降级。在心理健康预警场景，这直接
转化为漏预警而无人察觉。

用法（一行，放在降级分支里）：

    except Exception as exc:
        logger.debug("...: %s", exc)
        record_silent_degradation("core.ws.publish_to_user")

约定：
- `location` 一律用 ``模块.函数`` 全限定名（可在 /metrics 里直接定位到代码）；
- 本函数**吞掉一切异常**：metrics 子系统本身不可用时绝不允许反过来打断它被
  保护的主流程（这是它存在的全部前提，故此处刻意「静默」，不做二次上报）；
- 计数经 ``silent_degradation_total{location}`` 由 ``render_exposition``（/metrics）
  暴露，与 `app/core/metrics.py` 的注册共用同一 Counter 对象。
"""

from __future__ import annotations

__all__ = ["record_silent_degradation"]


def record_silent_degradation(location: str) -> None:
    """给 `location` 处的静默降级计一次数。失败不影响调用方。"""
    try:
        from app.core.metrics import silent_degradation_total

        silent_degradation_total.inc(location=location)
    except Exception:  # pragma: no cover - metrics 不可用时的兜底
        pass
