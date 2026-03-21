"""dhcp_config

Revision ID: c3d4e5f6
Revises: b2c3d4e5
Create Date: 2026-03-21 00:00:00.000000
"""
from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'c3d4e5f6'
down_revision: Union[str, None] = 'b2c3d4e5'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

DHCP_CONFIG_ID = '00000000-0000-0000-0000-000000000002'


def upgrade() -> None:
    # 1. dnsmodetype enum
    dnsmode_type = postgresql.ENUM('redirect', 'forward', name='dnsmodetype', create_type=True)
    dnsmode_type.create(op.get_bind(), checkfirst=True)

    # 2. dhcp_config table
    op.create_table(
        'dhcp_config',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('enabled', sa.Boolean, nullable=False, server_default='true'),
        sa.Column('interface', sa.String(32), nullable=False, server_default="'wlan0'"),
        sa.Column('gateway_ip', sa.String(15), nullable=False, server_default="'192.168.0.1'"),
        sa.Column('subnet', sa.String(18), nullable=False, server_default="'192.168.0.0/22'"),
        sa.Column('dhcp_range_start', sa.String(15), nullable=False, server_default="'192.168.0.10'"),
        sa.Column('dhcp_range_end', sa.String(15), nullable=False, server_default="'192.168.3.250'"),
        sa.Column('lease_time', sa.String(8), nullable=False, server_default="'8h'"),
        sa.Column('dns_upstream_1', sa.String(45), nullable=False, server_default="'8.8.8.8'"),
        sa.Column('dns_upstream_2', sa.String(45), nullable=False, server_default="'8.8.4.4'"),
        sa.Column('dns_mode', sa.Enum('redirect', 'forward', name='dnsmodetype', create_type=False),
                  nullable=False, server_default="'redirect'"),
        sa.Column('log_queries', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    # Seed default row
    op.execute(
        f"INSERT INTO dhcp_config (id, enabled, interface, gateway_ip, subnet, "
        f"dhcp_range_start, dhcp_range_end, lease_time, dns_upstream_1, dns_upstream_2, "
        f"dns_mode, log_queries, updated_at) "
        f"VALUES ('{DHCP_CONFIG_ID}', true, 'wlan0', '192.168.0.1', '192.168.0.0/22', "
        f"'192.168.0.10', '192.168.3.250', '8h', '8.8.8.8', '8.8.4.4', 'redirect', false, now()) "
        f"ON CONFLICT DO NOTHING"
    )


def downgrade() -> None:
    op.drop_table('dhcp_config')
    op.execute("DROP TYPE IF EXISTS dnsmodetype")