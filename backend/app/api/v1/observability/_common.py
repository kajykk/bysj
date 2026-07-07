"""v1.36 告警可观测性 API: 跨模块共享工具.

提供跨方言 JSON 提取 / 时间桶分组 / 规范化函数, 供 query / aggregate 子模块复用.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from sqlalchemy.ext.compiler import compiles
from sqlalchemy.sql.expression import ColumnElement

# PERF-P1-001: 优先使用 orjson (若安装) 加速 JSON 解析，否则回退到标准库 json
try:
    import orjson  # type: ignore

    _json_loads = orjson.loads
except ImportError:
    _json_loads = json.loads

logger = logging.getLogger(__name__)

# 兜底 LIMIT：配合时间范围强制后，从 10000 降至 5000 进一步降低聚合压力
DEFAULT_LIMIT = 5000


# ===== PERF-P1-001: 跨方言 JSON 提取 + 时间桶分组工具 =====
# OperationLog.detail 列为 Text 类型 (非 JSONB)，业务维度嵌在 JSON 字符串中。
# 不同方言的 JSON 提取语法不同:
#   SQLite:     json_extract(detail, '$.field')
#   PostgreSQL: detail::json->>'field'
# 通过 @compiles 装饰器实现跨方言编译，将 Python Counter 聚合下推为 SQL GROUP BY。


class _JsonExtract(ColumnElement):
    """PERF-P1-001: 跨方言 JSON 字段提取表达式.

    将 Text 列中的 JSON 字段提取为文本，用于 SQL GROUP BY 聚合下推.
    """

    inherit_cache = True

    def __init__(self, column, field: str):
        self.column = column
        self.field = field


@compiles(_JsonExtract, "sqlite")
def _json_extract_sqlite(element, compiler, **kw):
    return (
        f"json_extract({compiler.process(element.column, **kw)}, "
        f"'$.{element.field}')"
    )


@compiles(_JsonExtract, "postgresql")
def _json_extract_pg(element, compiler, **kw):
    return f"{compiler.process(element.column, **kw)}::json->>'{element.field}'"


@compiles(_JsonExtract)
def _json_extract_default(element, compiler, **kw):
    # 默认使用 SQLite 语法 (测试环境)
    return _json_extract_sqlite(element, compiler, **kw)


class _BucketExpr(ColumnElement):
    """PERF-P1-001: 跨方言时间桶分组表达式.

    将 created_at 向下对齐到 bucket 边界 (epoch seconds 取模对齐).
    返回 datetime，用于 GROUP BY 时间桶聚合.

    SQLite:  datetime((strftime('%s', col) / :secs) * :secs, 'unixepoch')
    PG:      to_timestamp(floor(extract(epoch from col) / :secs) * :secs)
    """

    inherit_cache = True

    def __init__(self, column, bucket_secs: int):
        self.column = column
        self.bucket_secs = bucket_secs


@compiles(_BucketExpr, "sqlite")
def _bucket_sqlite(element, compiler, **kw):
    col = compiler.process(element.column, **kw)
    secs = element.bucket_secs
    return f"datetime((strftime('%s', {col}) / {secs}) * {secs}, 'unixepoch')"


@compiles(_BucketExpr, "postgresql")
def _bucket_pg(element, compiler, **kw):
    col = compiler.process(element.column, **kw)
    secs = element.bucket_secs
    return f"to_timestamp(floor(extract(epoch from {col}) / {secs}) * {secs})"


@compiles(_BucketExpr)
def _bucket_default(element, compiler, **kw):
    return _bucket_sqlite(element, compiler, **kw)


def _norm_json_value(val: Any) -> str:
    """PERF-P1-001: 规范化 SQL 返回的 JSON 提取值.

    json_extract 在字段缺失时返回 NULL，PG ->> 返回 NULL.
    统一为 'unknown' 以兼容原 Python dict.get('field', 'unknown') 语义.
    """
    if val is None:
        return "unknown"
    return str(val)
