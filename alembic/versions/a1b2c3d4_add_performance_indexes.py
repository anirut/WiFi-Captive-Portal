"""add_performance_indexes

Revision ID: a1b2c3d4
Revises: f0b338e7
Create Date: 2026-03-21 00:00:00.000000

"""
from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = 'a1b2c3d4'
down_revision: Union[str, None] = 'f0b338e7'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Speed up scheduler expiry queries and session lookups by IP
    op.create_index('ix_sessions_status_expires_at', 'sessions', ['status', 'expires_at'])
    op.create_index('ix_sessions_ip_address', 'sessions', ['ip_address'])
    # Speed up guest lookups by room number (used in auth and checkout polling)
    op.create_index('ix_guests_room_number', 'guests', ['room_number'])


def downgrade() -> None:
    op.drop_index('ix_sessions_status_expires_at', table_name='sessions')
    op.drop_index('ix_sessions_ip_address', table_name='sessions')
    op.drop_index('ix_guests_room_number', table_name='guests')
