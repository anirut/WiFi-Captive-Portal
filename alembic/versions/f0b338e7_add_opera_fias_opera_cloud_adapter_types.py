"""add_opera_fias_opera_cloud_adapter_types

Revision ID: f0b338e7
Revises:
Create Date: 2026-03-20 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision: str = 'f0b338e7'
down_revision: Union[str, None] = '00000000'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.execute("ALTER TYPE pmsadaptertype ADD VALUE IF NOT EXISTS 'opera_fias'")
    op.execute("ALTER TYPE pmsadaptertype ADD VALUE IF NOT EXISTS 'opera_cloud'")


def downgrade() -> None:
    # PostgreSQL does not support removing enum values; downgrade is a no-op
    pass
