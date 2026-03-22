"""base_schema

Revision ID: 00000000
Revises:
Create Date: 2026-03-20 00:00:00.000000

"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


# revision identifiers, used by Alembic.
revision: str = '00000000'
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Create enum types
    session_status = postgresql.ENUM('active', 'expired', 'kicked', name='sessionstatus', create_type=True)
    session_status.create(op.get_bind(), checkfirst=True)

    voucher_type = postgresql.ENUM('time', 'data', name='vouchertype', create_type=True)
    voucher_type.create(op.get_bind(), checkfirst=True)

    pms_adapter_type = postgresql.ENUM(
        'opera', 'opera_fias', 'opera_cloud', 'cloudbeds', 'mews', 'custom', 'standalone',
        name='pmsadaptertype', create_type=True
    )
    pms_adapter_type.create(op.get_bind(), checkfirst=True)

    admin_role = postgresql.ENUM('superadmin', 'staff', name='adminrole', create_type=True)
    admin_role.create(op.get_bind(), checkfirst=True)

    # Create guests table
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

    # Create admin_users table
    op.create_table(
        'admin_users',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('username', sa.String(100), nullable=False, unique=True),
        sa.Column('password_hash', sa.String(200), nullable=False),
        sa.Column('role', postgresql.ENUM('superadmin', 'staff', name='adminrole', create_type=False), nullable=False),
        sa.Column('last_login_at', sa.DateTime(timezone=True), nullable=True),
    )

    # Create vouchers table
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

    # Create policies table
    op.create_table(
        'policies',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('name', sa.String(100), nullable=False),
        sa.Column('bandwidth_up_kbps', sa.Integer, nullable=False, server_default='0'),
        sa.Column('bandwidth_down_kbps', sa.Integer, nullable=False, server_default='0'),
        sa.Column('session_duration_min', sa.Integer, nullable=False, server_default='0'),
        sa.Column('max_devices', sa.Integer, nullable=False, server_default='3'),
    )

    # Create rooms table
    op.create_table(
        'rooms',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('number', sa.String(20), nullable=False, unique=True),
        sa.Column('room_type', sa.String(50), nullable=False, server_default="'standard'"),
        sa.Column('policy_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('policies.id'), nullable=True),
        sa.Column('pms_room_id', sa.String(100), nullable=True),
    )

    # Create pms_adapters table
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

    # Create sessions table
    op.create_table(
        'sessions',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('guest_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('guests.id'), nullable=True),
        sa.Column('voucher_id', postgresql.UUID(as_uuid=True), sa.ForeignKey('vouchers.id'), nullable=True),
        sa.Column('ip_address', postgresql.INET, nullable=False),
        sa.Column('mac_address', postgresql.MACADDR, nullable=True),
        sa.Column('connected_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.text('now()')),
        sa.Column('expires_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('bytes_up', sa.BigInteger, nullable=False, server_default='0'),
        sa.Column('bytes_down', sa.BigInteger, nullable=False, server_default='0'),
        sa.Column('bandwidth_up_kbps', sa.Integer, nullable=False, server_default='0'),
        sa.Column('status', postgresql.ENUM('active', 'expired', 'kicked', name='sessionstatus', create_type=False), nullable=False),
    )


def downgrade() -> None:
    op.drop_table('sessions')
    op.drop_table('pms_adapters')
    op.drop_table('rooms')
    op.drop_table('policies')
    op.drop_table('vouchers')
    op.drop_table('admin_users')
    op.drop_table('guests')

    op.execute('DROP TYPE IF EXISTS sessionstatus')
    op.execute('DROP TYPE IF EXISTS vouchertype')
    op.execute('DROP TYPE IF EXISTS pmsadaptertype')
    op.execute('DROP TYPE IF EXISTS adminrole')
