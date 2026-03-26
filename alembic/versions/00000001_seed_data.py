"""seed_data

Revision ID: 00000001
Revises: 00000000
Create Date: 2026-03-20 00:00:00.000000

Inserts required default rows for brand_config and dhcp_config, and
optional test MAC bypass entries for development/staging environments.
"""
from typing import Sequence, Union
import uuid

from alembic import op
import sqlalchemy as sa


revision: str = '00000001'
down_revision: Union[str, None] = '00000000'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BRAND_CONFIG_ID = '00000000-0000-0000-0000-000000000001'
DHCP_CONFIG_ID = '00000000-0000-0000-0000-000000000002'

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
    op.execute(
        f"INSERT INTO brand_config (id, hotel_name, primary_color, language, updated_at) "
        f"VALUES ('{BRAND_CONFIG_ID}', 'Hotel WiFi', '#3B82F6', 'th', now()) "
        f"ON CONFLICT DO NOTHING"
    )

    op.execute(
        f"INSERT INTO dhcp_config (id, enabled, interface, gateway_ip, subnet, "
        f"dhcp_range_start, dhcp_range_end, lease_time, dns_upstream_1, dns_upstream_2, "
        f"dns_mode, log_queries, updated_at) "
        f"VALUES ('{DHCP_CONFIG_ID}', true, 'wlan0', '192.168.0.1', '192.168.0.0/22', "
        f"'192.168.0.10', '192.168.3.250', '8h', '8.8.8.8', '8.8.4.4', 'redirect', false, now()) "
        f"ON CONFLICT DO NOTHING"
    )

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
    op.execute(f"DELETE FROM mac_bypass WHERE mac_address LIKE 'AA:BB:CC:DD:EE:%'")
    op.execute(f"DELETE FROM dhcp_config WHERE id = '{DHCP_CONFIG_ID}'")
    op.execute(f"DELETE FROM brand_config WHERE id = '{BRAND_CONFIG_ID}'")
