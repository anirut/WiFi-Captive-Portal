"""phase3_tables

Revision ID: b2c3d4e5
Revises: a1b2c3d4
Create Date: 2026-03-21 00:00:00.000000
"""
from typing import Sequence, Union
import uuid
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'b2c3d4e5'
down_revision: Union[str, None] = 'a1b2c3d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BRAND_CONFIG_ID = '00000000-0000-0000-0000-000000000001'


def upgrade() -> None:
    # 1. language_type enum
    language_type = postgresql.ENUM('th', 'en', name='languagetype', create_type=True)
    language_type.create(op.get_bind())

    # 2. usage_snapshots
    op.create_table(
        'usage_snapshots',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('snapshot_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('active_sessions', sa.Integer, nullable=False, server_default='0'),
        sa.Column('total_bytes_up', sa.BigInteger, nullable=False, server_default='0'),
        sa.Column('total_bytes_down', sa.BigInteger, nullable=False, server_default='0'),
        sa.Column('voucher_uses', sa.Integer, nullable=False, server_default='0'),
    )
    op.create_index('ix_usage_snapshots_snapshot_at', 'usage_snapshots', ['snapshot_at'], postgresql_using='btree')

    # 3. brand_config
    op.create_table(
        'brand_config',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('hotel_name', sa.String(200), nullable=False, server_default='Hotel WiFi'),
        sa.Column('logo_path', sa.String(500), nullable=True),
        sa.Column('primary_color', sa.String(7), nullable=False, server_default="'#3B82F6'"),
        sa.Column('tc_text_th', sa.Text, nullable=True),
        sa.Column('tc_text_en', sa.Text, nullable=True),
        sa.Column('language', sa.Enum('th', 'en', name='languagetype', create_type=False), nullable=False, server_default='th'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    # Seed default row
    op.execute(
        f"INSERT INTO brand_config (id, hotel_name, primary_color, language, updated_at) "
        f"VALUES ('{BRAND_CONFIG_ID}', 'Hotel WiFi', '#3B82F6', 'th', now()) "
        f"ON CONFLICT DO NOTHING"
    )

    # 4. policies (checkfirst — ORM model exists, table may or may not)
    conn = op.get_bind()
    if not conn.dialect.has_table(conn, 'policies'):
        op.create_table(
            'policies',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
            sa.Column('name', sa.String(100), nullable=False),
            sa.Column('bandwidth_up_kbps', sa.Integer, nullable=False, server_default='0'),
            sa.Column('bandwidth_down_kbps', sa.Integer, nullable=False, server_default='0'),
            sa.Column('session_duration_min', sa.Integer, nullable=False, server_default='0'),
            sa.Column('max_devices', sa.Integer, nullable=False, server_default='3'),
        )

    # 5. sessions.bandwidth_up_kbps
    op.add_column('sessions', sa.Column('bandwidth_up_kbps', sa.Integer, nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('sessions', 'bandwidth_up_kbps')
    # Drop policies only if it exists (mirror of conditional creation in upgrade)
    conn = op.get_bind()
    if conn.dialect.has_table(conn, 'policies'):
        op.drop_table('policies')
    op.drop_index('ix_usage_snapshots_snapshot_at', table_name='usage_snapshots')
    op.drop_table('brand_config')
    op.drop_table('usage_snapshots')
    op.execute("DROP TYPE IF EXISTS languagetype")
