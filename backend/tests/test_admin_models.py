"""v1.36: OperationLog 模型复合索引测试 (T1.4 / TC-DATA-004).

验证 OperationLog.__table_args__ 中声明的 2 个复合索引:
- idx_oplog_action_created: (action_type, created_at)
- idx_oplog_target_action: (target_type, target_id, action_type)
"""
from __future__ import annotations

import pytest

from app.models.admin import OperationLog


def _get_index_names(table) -> set[str]:
    """从 SQLAlchemy Table 对象提取所有索引名."""
    return {idx.name for idx in table.indexes}


def _get_index(table, name: str):
    """根据名称获取索引对象."""
    for idx in table.indexes:
        if idx.name == name:
            return idx
    return None


def test_idx_oplog_action_created_exists() -> None:
    """v1.36 T1.4: 索引 idx_oplog_action_created 应存在."""
    table = OperationLog.__table__
    names = _get_index_names(table)
    assert "idx_oplog_action_created" in names


def test_idx_oplog_action_created_columns() -> None:
    """v1.36 T1.4: 索引 idx_oplog_action_created 应包含 (action_type, created_at) 列."""
    table = OperationLog.__table__
    idx = _get_index(table, "idx_oplog_action_created")
    assert idx is not None
    col_names = [c.name for c in idx.columns]
    assert col_names == ["action_type", "created_at"]


def test_idx_oplog_target_action_exists() -> None:
    """v1.36 T1.4: 索引 idx_oplog_target_action 应存在."""
    table = OperationLog.__table__
    names = _get_index_names(table)
    assert "idx_oplog_target_action" in names


def test_idx_oplog_target_action_columns() -> None:
    """v1.36 T1.4: 索引 idx_oplog_target_action 应包含 (target_type, target_id, action_type) 列."""
    table = OperationLog.__table__
    idx = _get_index(table, "idx_oplog_target_action")
    assert idx is not None
    col_names = [c.name for c in idx.columns]
    assert col_names == ["target_type", "target_id", "action_type"]


def test_operation_log_table_has_indexes() -> None:
    """v1.36 T1.4: OperationLog 表至少应有 2 个 v1.36 新增索引."""
    table = OperationLog.__table__
    names = _get_index_names(table)
    # 至少应包含 v1.36 新增的 2 个
    new_indexes = {"idx_oplog_action_created", "idx_oplog_target_action"}
    assert new_indexes.issubset(names)
