"""mac_bypass and walled_garden

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

ADMIN_ID = "00000000-0000-0000-0000-000000000001"
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
TEST_DOMAINS = [
    ("apple.com", "Test domain 1 - Apple"),
    ("icloud.com", "Test domain 2 - iCloud"),
    ("microsoft.com", "Test domain 3 - Microsoft"),
    ("google.com", "Test domain 4 - Google"),
    ("facebook.com", "Test domain 5 - Facebook"),
    ("instagram.com", "Test domain 6 - Instagram"),
    ("whatsapp.com", "Test domain 7 - WhatsApp"),
    ("telegram.org", "Test domain 8 - Telegram"),
    ("zoom.us", "Test domain 9 - Zoom"),
    ("spotify.com", "Test domain 10 - Spotify"),
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

    op.create_table(
        "walled_garden_domains",
        sa.Column("id", postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column("domain", sa.String(253), nullable=False, unique=True),
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
        sa.Column("is_active", sa.Boolean, nullable=False, server_default="true"),
    )

    for mac, desc in TEST_MAC_ADDRESSES:
        op.execute(
            f"INSERT INTO mac_bypass (id, mac_address, description, created_by, is_active) "
            f"VALUES ('{uuid.uuid4()}', '{mac}', '{desc}', '{ADMIN_ID}', true)"
        )

    for domain, desc in TEST_DOMAINS:
        op.execute(
            f"INSERT INTO walled_garden_domains (id, domain, description, created_by, is_active) "
            f"VALUES ('{uuid.uuid4()}', '{domain}', '{desc}', '{ADMIN_ID}', true)"
        )


def downgrade() -> None:
    op.drop_table("mac_bypass")
    op.drop_table("walled_garden_domains")
