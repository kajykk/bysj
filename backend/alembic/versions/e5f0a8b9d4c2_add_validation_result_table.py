"""add_validation_result_table

Revision ID: e5f0a8b9d4c2
Revises: d4e9f7a8c3b1
Create Date: 2026-04-28 12:10:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = "e5f0a8b9d4c2"
down_revision: Union[str, None] = "d4e9f7a8c3b1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.create_table(
        "validation_results",
        sa.Column("id", sa.Integer(), primary_key=True, nullable=False),
        sa.Column("sample_id", sa.String(length=100), nullable=False, comment="样本唯一标识"),
        sa.Column("model_version", sa.String(length=50), nullable=False, comment="模型版本号"),
        sa.Column("ground_truth", sa.Integer(), nullable=True, comment="真实标签"),
        sa.Column("prediction", sa.Integer(), nullable=True, comment="预测标签"),
        sa.Column("confidence", sa.Float(), nullable=True, comment="预测置信度"),
        sa.Column("is_correct", sa.Integer(), nullable=True, comment="是否正确 (1=正确, 0=错误, NULL=未评估)"),
        sa.Column("failure_reason", sa.Text(), nullable=True, comment="失败原因 (如预测错误则记录)"),
        sa.Column("created_at", sa.DateTime(), server_default=sa.func.now(), nullable=False, comment="记录创建时间"),
    )
    op.create_index("ix_validation_results_model_version_created_at", "validation_results", ["model_version", "created_at"], unique=False)
    op.create_index("ix_validation_results_is_correct_created_at", "validation_results", ["is_correct", "created_at"], unique=False)


def downgrade() -> None:
    op.drop_index("ix_validation_results_is_correct_created_at", table_name="validation_results")
    op.drop_index("ix_validation_results_model_version_created_at", table_name="validation_results")
    op.drop_table("validation_results")
