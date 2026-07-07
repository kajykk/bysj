"""add_am_silence_id_column

M-5 修复：为 alert_silences 表添加 am_silence_id 列，持久化 AlertManager 返回的
silenceID，使删除静默规则时能同步取消 AM 侧的静默。

Revision ID: i0e5f6a7b8c9
Revises: h9d4e5f6a7b8
Create Date: 2026-06-24 00:00:00.000000
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "i0e5f6a7b8c9"
down_revision: Union[str, None] = "h9d4e5f6a7b8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # M-5 修复：新增 am_silence_id 列，存储 AlertManager 返回的 silenceID
    op.add_column(
        "alert_silences",
        sa.Column("am_silence_id", sa.String(length=128), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("alert_silences", "am_silence_id")
