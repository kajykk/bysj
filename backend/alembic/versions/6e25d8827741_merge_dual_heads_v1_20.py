"""merge dual heads v1.20

Revision ID: 6e25d8827741
Revises: a1b2c3d4e5f6, b1a7c0d9f4e8
Create Date: 2026-05-01 21:12:50.353102

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = '6e25d8827741'
down_revision: Union[str, None] = ('a1b2c3d4e5f6', 'b1a7c0d9f4e8')
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    pass


def downgrade() -> None:
    pass
