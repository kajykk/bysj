"""P0-FIX-2026-10-11: 三个熔断器的 init_* 必须就地更新单例，不得重绑定模块全局。

背景（来自 2026-10-11 全量源码审查）：

``ml_breaker`` / ``celery_breaker`` / ``smtp_breaker`` 的 ``init_*()`` 原先写成：:

    global ml_breaker
    ml_breaker = CircuitBreaker(...)      # 重新赋值模块全局

而 Python 的 ``from app.core.ml_breaker import ml_breaker`` 是**值拷贝绑定**：
任何在 ``init_ml_breaker()`` 之前完成导入的模块会一直持有启动时创建的那个实例，
新参数（阈值 / 恢复超时）与后续状态对它完全无效 —— **熔断器状态分裂**：
一部分代码路径看到 OPEN，另一部分仍 CLOSED 并继续向已故障的下游发请求。

同目录 ``db_breaker.CircuitBreaker.configure`` 的 docstring 早就明文禁止这种写法
（「必须就地更新既有单例，不能重新赋值模块全局」），四个 breaker 里三个用错。
本测试把「对象标识不变 + 参数生效」这条契约固化下来。
"""

from __future__ import annotations

import pytest

from app.core.celery_breaker import celery_breaker, init_celery_breaker
from app.core.db_breaker import CircuitState
from app.core.ml_breaker import init_ml_breaker, ml_breaker
from app.core.smtp_breaker import init_smtp_breaker, smtp_breaker

CASES = [
    ("ml", ml_breaker, init_ml_breaker),
    ("celery", celery_breaker, init_celery_breaker),
    ("smtp", smtp_breaker, init_smtp_breaker),
]


@pytest.mark.parametrize(("label", "breaker", "init_fn"), CASES, ids=[c[0] for c in CASES])
def test_init_preserves_object_identity(label, breaker, init_fn, monkeypatch):
    """init_* 之后模块全局必须仍是**同一个对象**（值拷贝绑定方才看得见新参数）。"""
    from app.core.config import settings

    # 用一组与默认值明显不同的参数，确保「参数生效」可判定
    monkeypatch.setattr(settings, f"{label}_failure_threshold", 17, raising=False)
    monkeypatch.setattr(settings, f"{label}_recovery_timeout", 91, raising=False)
    monkeypatch.setattr(settings, f"{label}_half_open_max_calls", 3, raising=False)

    before = breaker
    init_fn()

    # 关键断言：模块全局未被重绑定（否则已导入模块持有的是陈旧实例）
    assert breaker is before, (
        f"{label}_breaker 的 init_* 重新绑定了模块全局，会让 `from ... import "
        f"{label}_breaker` 的调用方继续持有旧实例 → 熔断器状态分裂"
    )
    assert breaker.failure_threshold == 17
    assert breaker.recovery_timeout == 91
    assert breaker.half_open_max_calls == 3
    # configure() 会把状态重置为 CLOSED，与新建实例语义一致
    assert breaker._state == CircuitState.CLOSED


@pytest.mark.parametrize(("label", "breaker", "init_fn"), CASES, ids=[c[0] for c in CASES])
def test_init_keeps_name_and_classifier(label, breaker, init_fn):
    """就地更新不得丢失构造时设定的 name / failure_classifier。"""
    init_fn()
    assert breaker.name == label, f"{label}_breaker 的 name 应保持不变"
    assert callable(breaker._failure_classifier), (
        f"{label}_breaker 的 failure_classifier 应保持不变，否则所有异常都会被计入熔断"
    )
