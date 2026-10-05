"""兼容层: 告警可观测性聚合函数已下沉至 services 层.

ARCH-FIX-2026-10-05（下沉本模块的原因）:
    原实现位于 api 层, 导致 services/observability_exporter.py 为了复用聚合
    逻辑反向 import api 层的下划线私有函数（5 处）。这是明确的跨层反向依赖:
    服务层依赖 HTTP 层, 方向颠倒。后果是 api 层一改名或把这些函数挪进
    router, Prometheus exporter 会**静默失效** —— 不会导入失败, 5 个 metric
    全部停止上报, 且被 `except Exception` 吞掉只记一条 warning。监控大盘上
    表现为「NoData」而非报错, 定位成本极高。

    同时这批 SQL 聚合本质是数据访问逻辑, 不该放在 HTTP 层:
    aggregate.py + query.py 合计约 1150 行 ORM 代码全在 api 层。

实现已移至 app/services/observability/（aggregate.py / query.py / _common.py）,
那里只依赖 app.models 与 sqlalchemy, 不依赖任何 api 模块, 因此不存在
「下沉后产生新循环依赖」的风险。

本模块是**向后兼容层而非实现层**, 存在两个理由:
    1. 约 90 处测试与若干 grafana_adapter 引用 app.api.v1.observability 命名空间;
    2. 端点的 __globals__ 即本包命名空间, 测试的 monkeypatch 依赖这一点。

关于转发方式 —— 用模块级 __getattr__ 而非逐个 re-export:
    手写 re-export 列表**必然遗漏**。实测第一次尝试就漏了 15 个内部函数
    （如 _fetch_lock_memory_stats），导致 tests/api/test_observability_equivalence.py
    的 test_lock_stats_snapshot 报 AttributeError。
    模块级 __getattr__（PEP 562）把所有未在本地定义的属性一律转发给
    services 层实现，新增函数无需再改本文件，从根上消除遗漏可能。

注意: 转发发生在**属性读取时**，不是 import 时绑定。因此 patch services 层
    才会影响真正被调用的实现 —— 新测试应 patch services 层。
"""

from __future__ import annotations

from typing import Any

# 显式导入常用符号（保留 __all__ 与 IDE 可发现性；其余走 __getattr__ 转发）
from app.services.observability.aggregate import (  # noqa: F401
    _compute_am_sync,
    _compute_channel_stats,
    _compute_lock_stats,
    _compute_silence_hit_rate,
)
from app.services.observability.query import (  # noqa: F401
    _compute_escalation,
    _compute_response_time,
    _compute_trend,
    _percentile,
)

_IMPL_MODULE = "app.services.observability.aggregate"


def __getattr__(name: str) -> Any:
    """PEP 562: 把本模块未定义的属性转发到 services 层实现.

    aggregate.py 里的 _fetch_* / _aggregate_* 等内部函数也自动可见，
    新增或改名符号无需再维护本文件的清单。
    """
    if name.startswith("__"):
        raise AttributeError(name)
    import importlib

    return getattr(importlib.import_module(_IMPL_MODULE), name)


__all__ = [
    "_compute_am_sync",
    "_compute_channel_stats",
    "_compute_lock_stats",
    "_compute_silence_hit_rate",
    "_compute_escalation",
    "_compute_response_time",
    "_compute_trend",
    "_percentile",
]
