"""mac_bypass

Revision ID: d5e6f7a8
Revises: c3d4e5f6
Create Date: 2026-03-25 00:00:00.000000
"""

from typing import Sequence, Union
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql
import uuid

revision: str = "d5e6f7a8"
down_revision: Union[str, None] = "c3d4e5f6"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

TEST_MAC_ADDRESSES = [
    ("AA:BB:CC:DD:EE:01", "Test device 1 - iPhone"),
    ("AA:BB:CC:DD:EE:02", "Test device 2 - iPad"),
    ("AA:BB:CC:DD:EE:03", "Test device 3 - MacBook"),
    ("AA:BB:CC:DD:EE:04", "Test device 4 - Windows Laptop"),
    ("AA:BB:CC:DD:EE:05", "Test device 5 - Android Phone"),
    ("AA:BB:CC:DD:EE:06", "Test device 6 - Android Tablet"),
    ("AA:BB:CC:DD:EE:07", "Test device 7 - Smart TV"),
    ("AA:BB:CC:DD:EE:08", "Test device 8 - Chromecast"),
    ("AA:BB:CC:DD:EE:09", "Test device 9 - Alexa Device"),
    ("AA:BB:CC:DD:EE:10", "Test device 10 - Guest Laptop"),
]


def upgrade() -> None:
    op.create_table(
        "mac_bypass",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("mac_address", sa.String(17), nullable=False, unique=True),
        sa.Column("description", sa.String(200), nullable=True),
        sa.Column(
            "created_by",
            postgresql.UUID(as_uuid=True),
            sa.ForeignKey("admin_users.id"),
            nullable=True,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
    )

    # Use the first superadmin's ID; fall back to NULL if none exists yet
    conn = op.get_bind()
    row = conn.execute(
        sa.text("SELECT id FROM admin_users WHERE role = 'superadmin' LIMIT 1")
    ).fetchone()
    admin_id = str(row[0]) if row else None

    for mac, desc in TEST_MAC_ADDRESSES:
        op.execute(
            sa.text(
                "INSERT INTO mac_bypass (id, mac_address, description, created_by, is_active) "
                "VALUES (:id, :mac, :desc, :admin_id, true) ON CONFLICT (mac_address) DO NOTHING"
            ).bindparams(id=uuid.uuid4(), mac=mac, desc=desc, admin_id=admin_id)
        )


def downgrade() -> None:
    op.drop_table("mac_bypass")
