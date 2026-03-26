"""base_schema

Revision ID: 00000000
Revises:
Create Date: 2026-03-20 00:00:00.000000

Consolidated migration — creates all tables, enums, and indexes in their
final state. Replaces the previous incremental migration chain.
"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = '00000000'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ── Enum types ───────────────────────────────────────────────────────────

    postgresql.ENUM(
        'active', 'expired', 'kicked', name='sessionstatus', create_type=True
    ).create(op.get_bind(), checkfirst=True)

    postgresql.ENUM(
        'time', 'data', name='vouchertype', create_type=True
    ).create(op.get_bind(), checkfirst=True)

    postgresql.ENUM(
        'opera', 'opera_fias', 'opera_cloud', 'cloudbeds', 'mews', 'custom', 'standalone',
        name='pmsadaptertype', create_type=True
    ).create(op.get_bind(), checkfirst=True)

    postgresql.ENUM(
        'superadmin', 'staff', name='adminrole', create_type=True
    ).create(op.get_bind(), checkfirst=True)

    postgresql.ENUM(
        'th', 'en', name='languagetype', create_type=True
    ).create(op.get_bind(), checkfirst=True)

    postgresql.ENUM(
        'redirect', 'forward', name='dnsmodetype', create_type=True
    ).create(op.get_bind(), checkfirst=True)

    # ── Tables ───────────────────────────────────────────────────────────────

    op.create_table(
        'guests',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('room_number', sa.String(20), nullable=False),
        sa.Column('last_name', sa.String(100), nullable=False),
        sa.Column('first_name', sa.String(100), nullable=True),
        sa.Column('pms_guest_id', sa.String(100), nullable=True),
        sa.Column('check_in', sa.DateTime(timezone=True), nullable=False),
        sa.Column('check_out', sa.DateTime(timezone=True), nullable=False),
        sa.Column('max_devices', sa.Integer, nullable=False, server_default='3'),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
    )

    op.create_table(
        'admin_users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('username', sa.String(100), nullable=False, unique=True),
        sa.Column('password_hash', sa.String(200), nullable=False),
        sa.Column('role', postgresql.ENUM('superadmin', 'staff', name='adminrole', create_type=False), nullable=False),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    )

    op.create_table(
        'policies',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('bandwidth_up_kbps', sa.Integer, nullable=False, server_default='0'),
        sa.Column('bandwidth_down_kbps', sa.Integer, nullable=False, server_default='0'),
        sa.Column('session_duration_min', sa.Integer, nullable=False, server_default='0'),
        sa.Column('max_devices', sa.Integer, nullable=False, server_default='3'),
    )

    op.create_table(
        'vouchers',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('code', sa.String(50), nullable=False, unique=True),
        sa.Column('type', postgresql.ENUM('time', 'data', name='vouchertype', create_type=False), nullable=False),
        sa.Column('duration_minutes', sa.Integer, nullable=True),
        sa.Column('data_limit_mb', sa.Integer, nullable=True),
        sa.Column('max_devices', sa.Integer, nullable=False, server_default='1'),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('admin_users.id'), nullable=False),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('used_count', sa.Integer, nullable=False, server_default='0'),
        sa.Column('max_uses', sa.Integer, nullable=False, server_default='1'),
    )

    op.create_table(
        'rooms',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('number', sa.String(20), nullable=False, unique=True),
        sa.Column('room_type', sa.String(50), nullable=False, server_default="'standard'"),
        sa.Column('policy_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('policies.id'), nullable=True),
        sa.Column('pms_room_id', sa.String(100), nullable=True),
    )

    op.create_table(
        'pms_adapters',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('type', postgresql.ENUM(
            'opera', 'opera_fias', 'opera_cloud', 'cloudbeds', 'mews', 'custom', 'standalone',
            name='pmsadaptertype', create_type=False
        ), nullable=False),
        sa.Column('config_encrypted', sa.LargeBinary, nullable=True),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('last_sync_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('webhook_secret', sa.String(200), nullable=True),
    )

    op.create_table(
        'sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('guest_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('guests.id'), nullable=True),
        sa.Column('voucher_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('vouchers.id'), nullable=True),
        sa.Column('ip_address', postgresql.INET, nullable=False),
        sa.Column('mac_address', sa.String(17), nullable=True),
        sa.Column('connected_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('bytes_up', sa.BigInteger, nullable=False, server_default='0'),
        sa.Column('bytes_down', sa.BigInteger, nullable=False, server_default='0'),
        sa.Column('bandwidth_up_kbps', sa.Integer, nullable=False, server_default='0'),
        sa.Column('status', postgresql.ENUM('active', 'expired', 'kicked', name='sessionstatus', create_type=False), nullable=False),
    )

    op.create_table(
        'usage_snapshots',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('snapshot_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('active_sessions', sa.Integer, nullable=False, server_default='0'),
        sa.Column('total_bytes_up', sa.BigInteger, nullable=False, server_default='0'),
        sa.Column('total_bytes_down', sa.BigInteger, nullable=False, server_default='0'),
        sa.Column('voucher_uses', sa.Integer, nullable=False, server_default='0'),
    )

    op.create_table(
        'brand_config',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('hotel_name', sa.String(200), nullable=False, server_default="'Hotel WiFi'"),
        sa.Column('logo_path', sa.String(500), nullable=True),
        sa.Column('primary_color', sa.String(7), nullable=False, server_default="'#3B82F6'"),
        sa.Column('tc_text_th', sa.Text, nullable=True),
        sa.Column('tc_text_en', sa.Text, nullable=True),
        sa.Column('language', sa.Enum('th', 'en', name='languagetype', create_type=False), nullable=False, server_default="'th'"),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

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
        sa.Column('dns_mode', sa.Enum('redirect', 'forward', name='dnsmodetype', create_type=False), nullable=False, server_default="'redirect'"),
        sa.Column('log_queries', sa.Boolean, nullable=False, server_default='false'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )

    op.create_table(
        'mac_bypass',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('mac_address', sa.String(17), nullable=False, unique=True),
        sa.Column('description', sa.String(200), nullable=True),
        sa.Column('created_by', postgresql.UUID(as_uuid=True), sa.ForeignKey('admin_users.id'), nullable=True),
        sa.Column('created_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=True),
        sa.Column('is_active', sa.Boolean, nullable=False, server_default='true'),
    )

    # ── Indexes ──────────────────────────────────────────────────────────────

    op.create_index('ix_sessions_status_expires_at', 'sessions', ['status', 'expires_at'])
    op.create_index('ix_sessions_ip_address', 'sessions', ['ip_address'])
    op.create_index('ix_guests_room_number', 'guests', ['room_number'])
    op.create_index('ix_usage_snapshots_snapshot_at', 'usage_snapshots', ['snapshot_at'], postgresql_using='btree')


def downgrade() -> None:
    op.drop_index('ix_usage_snapshots_snapshot_at', table_name='usage_snapshots')
    op.drop_index('ix_guests_room_number', table_name='guests')
    op.drop_index('ix_sessions_ip_address', table_name='sessions')
    op.drop_index('ix_sessions_status_expires_at', table_name='sessions')

    op.drop_table('mac_bypass')
    op.drop_table('dhcp_config')
    op.drop_table('brand_config')
    op.drop_table('usage_snapshots')
    op.drop_table('sessions')
    op.drop_table('pms_adapters')
    op.drop_table('rooms')
    op.drop_table('vouchers')
    op.drop_table('policies')
    op.drop_table('admin_users')
    op.drop_table('guests')

    op.execute('DROP TYPE IF EXISTS dnsmodetype')
    op.execute('DROP TYPE IF EXISTS languagetype')
    op.execute('DROP TYPE IF EXISTS adminrole')
    op.execute('DROP TYPE IF EXISTS pmsadaptertype')
    op.execute('DROP TYPE IF EXISTS vouchertype')
    op.execute('DROP TYPE IF EXISTS sessionstatus')
