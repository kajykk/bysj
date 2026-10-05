"""告警可观测性数据访问层.

ARCH-FIX-2026-10-05: 本包从 app/api/v1/observability/ 下沉而来。

下沉原因:
    原实现放在 api 层，导致 services/observability_exporter.py 为了复用聚合
    逻辑反向 import api 层的下划线私有函数（5 处）—— 服务层依赖 HTTP 层，
    方向颠倒。后果是 api 层一旦改名或把这些函数挪进 router，Prometheus
    exporter 会静默失效（不会导入失败，5 个 metric 停止上报，且被
    `except Exception` 吞掉只记一条 warning），监控大盘表现为 NoData 而非报错。

    这批约 1150 行 SQL 聚合本质是数据访问逻辑，也不该位于 HTTP 层。

模块构成:
    _common:   跨方言 JSON 提取 / 时间桶分组表达式 + 规范化工具
    query:     trend / response-time / escalation 的 compute 函数
    aggregate: channel-stats / silence-hit-rate / am-sync / lock-stats

依赖方向（重要）:
    本包只依赖 app.models 与 sqlalchemy，**不依赖任何 api 模块**，
    因此下沉不会产生新的循环依赖。app/api/v1/observability/ 下的
    aggregate.py / query.py 是同名 re-export 的向后兼容层。

新代码请从这里 import，不要再从 app.api.v1.observability 取实现。
"""

from __future__ import annotations

from app.services.observability.aggregate import (
    _compute_am_sync,
    _compute_channel_stats,
    _compute_lock_stats,
    _compute_silence_hit_rate,
)
from app.services.observability.query import (
    _compute_escalation,
    _compute_response_time,
    _compute_trend,
    _percentile,
)

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
