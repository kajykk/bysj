"""add_canary_route_prefix

STAB-P2-006: 为 canary_records 表添加 route_prefix 列, 支持按路由前缀分流.
- NULL 表示覆盖所有路由 (向后兼容, 模型预测路由)
- 非 NULL 值 (如 "/api/v1/reports") 表示仅覆盖该路由前缀的请求

Revision ID: k2a7b8c9d0e1
Revises: j1f6a7b8c9d0
Create Date: 2026-07-14 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "k2a7b8c9d0e1"
down_revision: Union[str, None] = "j1f6a7b8c9d0"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # STAB-P2-006: 新增 route_prefix 列, nullable=True (NULL=覆盖所有路由)
    op.add_column(
        "canary_records",
        sa.Column(
            "route_prefix",
            sa.String(100),
            nullable=True,
            comment="STAB-P2-006: 路由前缀分流 (NULL=覆盖所有路由)",
        ),
    )

    # 创建索引: 加速 get_active_canary 按 route_prefix 过滤查询
    # 复合索引 (status, route_prefix) 支持 WHERE status='running' AND route_prefix IS [NOT] NULL
    op.create_index(
        "ix_canary_records_status_route_prefix",
        "canary_records",
        ["status", "route_prefix"],
    )


def downgrade() -> None:
    op.drop_index(
        "ix_canary_records_status_route_prefix", table_name="canary_records"
    )
    op.drop_column("canary_records", "route_prefix")
