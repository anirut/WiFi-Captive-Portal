"""alter macaddr columns to varchar

Revision ID: e6f7a8b9
Revises: d5e6f7a8
Create Date: 2026-03-25 00:00:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa

revision: str = "e6f7a8b9"
down_revision: Union[str, None] = "d5e6f7a8"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.alter_column(
        "sessions",
        "mac_address",
        type_=sa.String(17),
        existing_nullable=True,
        postgresql_using="mac_address::text",
    )
    op.alter_column(
        "mac_bypass",
        "mac_address",
        type_=sa.String(17),
        existing_nullable=False,
        postgresql_using="mac_address::text",
    )


def downgrade() -> None:
    from sqlalchemy.dialects.postgresql import MACADDR
    op.alter_column(
        "mac_bypass",
        "mac_address",
        type_=MACADDR,
        existing_nullable=False,
        postgresql_using="mac_address::macaddr",
    )
    op.alter_column(
        "sessions",
        "mac_address",
        type_=MACADDR,
        existing_nullable=True,
        postgresql_using="mac_address::macaddr",
    )
