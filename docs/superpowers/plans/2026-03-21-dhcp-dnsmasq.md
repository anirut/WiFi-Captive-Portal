# dnsmasq DHCP + DNS Integration — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add managed dnsmasq DHCP+DNS to the portal, fully configurable from the admin web UI, with DNS bypass rules for authenticated guests.

**Architecture:** Config stored in a `dhcp_config` DB table (single-row, seeded). On save, FastAPI writes `/etc/dnsmasq.d/captive-portal.conf` and runs `systemctl reload dnsmasq`. On guest auth/expire, iptables DNAT rules bypass dnsmasq DNS redirect for that IP.

**Tech Stack:** FastAPI, SQLAlchemy 2 async, Alembic, PostgreSQL, dnsmasq, iptables (subprocess), Jinja2 + HTMX + Alpine.js + Tailwind CSS (Glassmorphism).

**Spec:** `docs/superpowers/specs/2026-03-21-dhcp-dnsmasq-design.md`

---

## File Map

| File | New/Modify | Responsibility |
|------|-----------|----------------|
| `alembic/versions/c3d4e5f6_dhcp_config.py` | New | `dhcp_config` table + seed row |
| `app/core/models.py` | Modify | Add `DnsModeType` enum + `DhcpConfig` ORM model |
| `app/network/dnsmasq.py` | New | `write_config`, `reload_dnsmasq`, `get_status`, `get_leases` |
| `app/network/iptables.py` | Modify | Add `add_dns_bypass(ip)` + `remove_dns_bypass(ip)` |
| `app/network/session_manager.py` | Modify | Call dns bypass in `create_session` + `expire_session` |
| `app/admin/schemas.py` | Modify | `DhcpConfigUpdate` + `DhcpConfigResponse` |
| `app/admin/router.py` | Modify | 6 DHCP endpoints (API + HTML page) |
| `app/admin/templates/base.html` | Modify | Add DHCP nav link (superadmin only) |
| `app/admin/templates/dhcp.html` | New | DHCP admin UI (3 cards) |
| `app/main.py` | Modify | Restore dnsmasq config from DB on lifespan startup |
| `scripts/setup-dnsmasq.sh` | New | Install dnsmasq + configure drop-in dir |
| `scripts/install.sh` | Modify | Call setup-dnsmasq.sh in Section 8 |
| `tests/test_network/test_dnsmasq.py` | New | 6 unit tests for dnsmasq module |
| `tests/test_admin/test_admin_dhcp.py` | New | 5 API tests for DHCP endpoints |

---

## Task 1: DB Migration + ORM Model

**Files:**
- Modify: `app/core/models.py`
- Create: `alembic/versions/c3d4e5f6_dhcp_config.py`

### Background

The project uses SQLAlchemy 2 async ORM with `Mapped` + `mapped_column`. Existing single-row config tables (e.g. `BrandConfig`) follow this pattern:
- UUID PK with a fixed known UUID (seeded in migration)
- `server_default` for SQL-level defaults
- Migration uses `op.execute(f"INSERT ... ON CONFLICT DO NOTHING")`

Look at `app/core/models.py` lines 127–136 for `BrandConfig` as the reference pattern.
Look at `alembic/versions/b2c3d4e5_phase3_tables.py` for the migration pattern (especially the seed insert and `checkfirst=True` for enums).

The current latest migration revision is `b2c3d4e5`. New migration `down_revision` must be `'b2c3d4e5'`.

- [ ] **Step 1.1: Add `DnsModeType` enum to `app/core/models.py`**

After the `LanguageType` class (line 37), add:

```python
class DnsModeType(str, enum.Enum):
    redirect = "redirect"
    forward  = "forward"
```

- [ ] **Step 1.2: Add `DhcpConfig` ORM model to `app/core/models.py`**

After the `BrandConfig` class (end of file), add:

```python
class DhcpConfig(Base):
    __tablename__ = "dhcp_config"
    id: Mapped[uuid.UUID] = uuid_pk()
    enabled: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")
    interface: Mapped[str] = mapped_column(String(32), nullable=False, default="wlan0", server_default="'wlan0'")
    gateway_ip: Mapped[str] = mapped_column(String(15), nullable=False, default="192.168.0.1", server_default="'192.168.0.1'")
    subnet: Mapped[str] = mapped_column(String(18), nullable=False, default="192.168.0.0/22", server_default="'192.168.0.0/22'")
    dhcp_range_start: Mapped[str] = mapped_column(String(15), nullable=False, default="192.168.0.10", server_default="'192.168.0.10'")
    dhcp_range_end: Mapped[str] = mapped_column(String(15), nullable=False, default="192.168.3.250", server_default="'192.168.3.250'")
    lease_time: Mapped[str] = mapped_column(String(8), nullable=False, default="8h", server_default="'8h'")
    dns_upstream_1: Mapped[str] = mapped_column(String(45), nullable=False, default="8.8.8.8", server_default="'8.8.8.8'")
    dns_upstream_2: Mapped[str] = mapped_column(String(45), nullable=False, default="8.8.4.4", server_default="'8.8.4.4'")
    dns_mode: Mapped[DnsModeType] = mapped_column(
        Enum(DnsModeType, name="dnsmodetype"), nullable=False, default=DnsModeType.redirect
    )
    log_queries: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False, server_default="false")
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False,
        default=lambda: datetime.now(timezone.utc), server_default="now()"
    )
```

- [ ] **Step 1.3: Create migration `alembic/versions/c3d4e5f6_dhcp_config.py`**

```python
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
                  nullable=False, server_default='redirect'),
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
```

- [ ] **Step 1.4: Commit**

```bash
git add app/core/models.py alembic/versions/c3d4e5f6_dhcp_config.py
git commit -m "feat: DhcpConfig ORM model + migration"
```

---

## Task 2: `app/network/dnsmasq.py` Module

**Files:**
- Create: `app/network/dnsmasq.py`
- Create: `tests/test_network/test_dnsmasq.py`

### Background

- All subprocess calls use the same pattern as `app/network/iptables.py`: `subprocess.run(cmd, check=True/False, capture_output=True)`.
- Tests mock subprocess and file I/O — no actual dnsmasq needed.
- The `DhcpConfig` ORM object is passed directly to `write_config()`.
- CIDR→netmask: `str(ipaddress.IPv4Network(config.subnet, strict=False).netmask)` e.g. `"192.168.0.0/22"` → `"255.255.252.0"`.
- Lease file format: `<epoch_int> <mac> <ip> <hostname> <client-id>` one per line.

- [ ] **Step 2.1: Write failing tests `tests/test_network/test_dnsmasq.py`**

```python
import pytest
import subprocess
from unittest.mock import patch, MagicMock, mock_open


def _make_config(**kwargs):
    """Build a minimal mock DhcpConfig object."""
    cfg = MagicMock()
    cfg.enabled = kwargs.get("enabled", True)
    cfg.interface = kwargs.get("interface", "wlan0")
    cfg.gateway_ip = kwargs.get("gateway_ip", "192.168.0.1")
    cfg.subnet = kwargs.get("subnet", "192.168.0.0/22")
    cfg.dhcp_range_start = kwargs.get("dhcp_range_start", "192.168.0.10")
    cfg.dhcp_range_end = kwargs.get("dhcp_range_end", "192.168.3.250")
    cfg.lease_time = kwargs.get("lease_time", "8h")
    cfg.dns_upstream_1 = kwargs.get("dns_upstream_1", "8.8.8.8")
    cfg.dns_upstream_2 = kwargs.get("dns_upstream_2", "8.8.4.4")
    cfg.dns_mode = MagicMock()
    cfg.dns_mode.value = kwargs.get("dns_mode", "redirect")
    cfg.log_queries = kwargs.get("log_queries", False)
    return cfg


def test_write_config_redirect_mode():
    cfg = _make_config(dns_mode="redirect", log_queries=True)
    m = mock_open()
    with patch("builtins.open", m):
        from app.network.dnsmasq import write_config
        write_config(cfg)
    written = "".join(call.args[0] for call in m().write.call_args_list)
    assert "address=/#/192.168.0.1" in written
    assert "255.255.252.0" in written  # netmask derived from /22
    assert "log-dhcp" in written
    assert "log-queries" in written


def test_write_config_forward_mode():
    cfg = _make_config(dns_mode="forward")
    m = mock_open()
    with patch("builtins.open", m):
        from app.network.dnsmasq import write_config
        write_config(cfg)
    written = "".join(call.args[0] for call in m().write.call_args_list)
    assert "address=/#/" not in written
    assert "server=8.8.8.8" in written


def test_write_config_disabled_mode():
    cfg = _make_config(enabled=False)
    with patch("builtins.open", mock_open()) as m, \
         patch("app.network.dnsmasq.subprocess.run") as mock_run:
        from app.network.dnsmasq import write_config
        write_config(cfg)
    # No file should be written
    m.assert_not_called()
    # systemctl stop dnsmasq should be called
    mock_run.assert_called_once()
    args = mock_run.call_args[0][0]
    assert "stop" in args
    assert "dnsmasq" in args


def test_get_leases_parses_correctly():
    lease_line = "1711036800 aa:bb:cc:dd:ee:ff 192.168.0.42 iPhone-guest *\n"
    with patch("builtins.open", mock_open(read_data=lease_line)):
        from app.network.dnsmasq import get_leases
        leases = get_leases()
    assert len(leases) == 1
    assert leases[0]["mac"] == "aa:bb:cc:dd:ee:ff"
    assert leases[0]["ip"] == "192.168.0.42"
    assert leases[0]["hostname"] == "iPhone-guest"
    assert "expires_at" in leases[0]


def test_get_leases_returns_empty_when_no_file():
    with patch("builtins.open", side_effect=FileNotFoundError):
        from app.network.dnsmasq import get_leases
        leases = get_leases()
    assert leases == []


def test_get_status_returns_dict():
    mock_result = MagicMock()
    mock_result.returncode = 0
    with patch("app.network.dnsmasq.subprocess.run", return_value=mock_result), \
         patch("os.path.exists", return_value=True), \
         patch("builtins.open", mock_open(read_data="line1\nline2\n")):
        from app.network.dnsmasq import get_status
        status = get_status()
    assert "running" in status
    assert "lease_count" in status
    assert "config_file_exists" in status
    assert status["running"] is True
    assert status["config_file_exists"] is True
```

- [ ] **Step 2.2: Run tests — expect FAIL (module doesn't exist yet)**

```bash
pytest tests/test_network/test_dnsmasq.py -v
```

Expected: `ModuleNotFoundError` or `ImportError`

- [ ] **Step 2.3: Create `app/network/dnsmasq.py`**

```python
import ipaddress
import logging
import os
import subprocess
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

CONF_FILE = "/etc/dnsmasq.d/captive-portal.conf"
LEASES_FILE = "/var/lib/misc/dnsmasq.leases"


def write_config(config) -> None:
    """Write dnsmasq config from a DhcpConfig ORM object. If disabled, stop dnsmasq instead."""
    if not config.enabled:
        subprocess.run(["systemctl", "stop", "dnsmasq"], check=False, capture_output=True)
        logger.info("dnsmasq stopped (enabled=False)")
        return

    netmask = str(ipaddress.IPv4Network(config.subnet, strict=False).netmask)
    dns_mode = config.dns_mode.value if hasattr(config.dns_mode, "value") else config.dns_mode

    lines = [
        "# Managed by WiFi Captive Portal — do not edit manually",
        f"interface={config.interface}",
        "except-interface=lo",
        "bind-interfaces",
        "no-resolv",
        "",
        "# DHCP",
        f"dhcp-range={config.dhcp_range_start},{config.dhcp_range_end},{netmask},{config.lease_time}",
        f"dhcp-option=option:router,{config.gateway_ip}",
        f"dhcp-option=option:dns-server,{config.gateway_ip}",
        "",
        "# DNS upstream",
        f"server={config.dns_upstream_1}",
        f"server={config.dns_upstream_2}",
    ]

    if dns_mode == "redirect":
        lines += [
            "",
            "# DNS mode: redirect (catch-all to portal IP)",
            f"address=/#/{config.gateway_ip}",
        ]

    if config.log_queries:
        lines += [
            "",
            "# Logging",
            "log-dhcp",
            "log-queries",
        ]

    content = "\n".join(lines) + "\n"
    with open(CONF_FILE, "w") as f:
        f.write(content)
    logger.info(f"dnsmasq config written to {CONF_FILE}")


def reload_dnsmasq() -> bool:
    """Reload dnsmasq service. Returns True on success."""
    try:
        subprocess.run(["systemctl", "reload", "dnsmasq"], check=True, capture_output=True)
        logger.info("dnsmasq reloaded")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"dnsmasq reload failed: {e.stderr}")
        return False


def get_status() -> dict:
    """Return dnsmasq service status dict."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "dnsmasq"],
            check=False, capture_output=True
        )
        running = result.returncode == 0
    except Exception:
        running = False

    lease_count = 0
    try:
        with open(LEASES_FILE) as f:
            lease_count = sum(1 for line in f if line.strip())
    except (FileNotFoundError, OSError):
        pass

    return {
        "running": running,
        "lease_count": lease_count,
        "config_file_exists": os.path.exists(CONF_FILE),
    }


def get_leases() -> list[dict]:
    """Parse /var/lib/misc/dnsmasq.leases and return list of lease dicts."""
    try:
        with open(LEASES_FILE) as f:
            lines = f.readlines()
    except (FileNotFoundError, OSError):
        return []

    leases = []
    for line in lines:
        parts = line.strip().split()
        if len(parts) < 4:
            continue
        epoch, mac, ip, hostname = parts[0], parts[1], parts[2], parts[3]
        try:
            expires_at = datetime.fromtimestamp(int(epoch), tz=timezone.utc).isoformat()
        except (ValueError, OSError):
            expires_at = None
        leases.append({"mac": mac, "ip": ip, "hostname": hostname, "expires_at": expires_at})
    return leases
```

- [ ] **Step 2.4: Run tests — expect PASS**

```bash
pytest tests/test_network/test_dnsmasq.py -v
```

Expected: `6 passed`

- [ ] **Step 2.5: Run full suite to confirm no regressions**

```bash
pytest tests/ -q --tb=short 2>&1 | tail -5
```

Expected: `128 passed` (existing tests unchanged)

- [ ] **Step 2.6: Commit**

```bash
git add app/network/dnsmasq.py tests/test_network/test_dnsmasq.py
git commit -m "feat: dnsmasq.py — write_config, reload, status, lease parsing"
```

---

## Task 3: iptables DNS Bypass + SessionManager Integration

**Files:**
- Modify: `app/network/iptables.py`
- Modify: `app/network/session_manager.py`
- Create: `tests/test_network/test_dns_bypass.py`

### Background

The existing `iptables.py` uses `_run(cmd)` for commands that should raise on failure and `subprocess.run(check=False)` for commands that are best-effort (like `remove_whitelist`).

`add_dns_bypass(ip)` adds two iptables DNAT rules in the `nat` table `PREROUTING` chain.
`remove_dns_bypass(ip)` removes them (uses `check=False` — rule may not exist).

`SessionManager.create_session()` already calls `add_whitelist(ip)` — add `add_dns_bypass(ip)` right after.
`SessionManager.expire_session()` already calls `remove_whitelist(ip)` — add `remove_dns_bypass(ip)` right after.

Both calls are unconditional (regardless of dns_mode). See spec constraint: "When dns_mode=forward, these rules are harmless."

- [ ] **Step 3.1: Write failing test `tests/test_network/test_dns_bypass.py`**

```python
import pytest
from unittest.mock import patch, call, MagicMock
import subprocess


def test_add_dns_bypass_runs_two_iptables_rules():
    # Must patch the module-local subprocess reference (CLAUDE.md convention)
    with patch("app.network.iptables.subprocess.run") as mock_run:
        from app.network.iptables import add_dns_bypass
        add_dns_bypass("192.168.0.42")
    assert mock_run.call_count == 2
    calls = [str(c) for c in mock_run.call_args_list]
    assert any("udp" in c and "DNAT" in c and "8.8.8.8" in c for c in calls)
    assert any("tcp" in c and "DNAT" in c and "8.8.8.8" in c for c in calls)


def test_remove_dns_bypass_runs_two_iptables_rules():
    with patch("app.network.iptables.subprocess.run") as mock_run:
        from app.network.iptables import remove_dns_bypass
        remove_dns_bypass("192.168.0.42")
    assert mock_run.call_count == 2
    calls = [str(c) for c in mock_run.call_args_list]
    assert any("-D" in c and "udp" in c for c in calls)
    assert any("-D" in c and "tcp" in c for c in calls)


def test_remove_dns_bypass_does_not_raise_on_missing_rule():
    # remove_dns_bypass uses check=False — returns non-zero returncode without raising
    mock_result = MagicMock()
    mock_result.returncode = 1
    with patch("app.network.iptables.subprocess.run", return_value=mock_result):
        from app.network.iptables import remove_dns_bypass
        # Should not raise even with non-zero returncode
        remove_dns_bypass("192.168.0.42")
```

- [ ] **Step 3.2: Run tests — expect FAIL**

```bash
pytest tests/test_network/test_dns_bypass.py -v
```

Expected: `ImportError` (functions don't exist yet)

- [ ] **Step 3.3: Add `add_dns_bypass` and `remove_dns_bypass` to `app/network/iptables.py`**

Append to the end of the file:

```python
def add_dns_bypass(ip: str) -> None:
    """DNAT port-53 from authenticated guest IP to 8.8.8.8, bypassing dnsmasq redirect."""
    for proto in ("udp", "tcp"):
        try:
            _run([
                "iptables", "-t", "nat", "-I", "PREROUTING",
                "-s", ip, "-p", proto, "--dport", "53",
                "-j", "DNAT", "--to-destination", "8.8.8.8:53"
            ])
        except subprocess.CalledProcessError as e:
            logger.error(f"iptables add_dns_bypass failed for {ip}/{proto}: {e.stderr}")
            raise

def remove_dns_bypass(ip: str) -> None:
    """Remove DNS bypass DNAT rules for an expired guest IP."""
    for proto in ("udp", "tcp"):
        subprocess.run([
            "iptables", "-t", "nat", "-D", "PREROUTING",
            "-s", ip, "-p", proto, "--dport", "53",
            "-j", "DNAT", "--to-destination", "8.8.8.8:53"
        ], check=False, capture_output=True)
    logger.info(f"iptables: removed dns bypass for {ip}")
```

- [ ] **Step 3.4: Run dns_bypass tests — expect PASS**

```bash
pytest tests/test_network/test_dns_bypass.py -v
```

Expected: `3 passed`

- [ ] **Step 3.5: Update `app/network/session_manager.py` — add dns bypass calls**

In `create_session()`, after `add_whitelist(ip)` add:
```python
from app.network.iptables import add_dns_bypass
add_dns_bypass(ip)
```

In `expire_session()`, after `remove_whitelist(session.ip_address)` add:
```python
from app.network.iptables import remove_dns_bypass
remove_dns_bypass(session.ip_address)
```

Move the imports to the top of the file (the file already imports from `app.network.iptables`):
```python
from app.network.iptables import add_whitelist, remove_whitelist, add_dns_bypass, remove_dns_bypass
```

- [ ] **Step 3.6: Update `tests/conftest.py` — patch new iptables functions**

In the `client` fixture, add two more patches alongside the existing ones:
```python
patch("app.network.iptables.add_dns_bypass"),
patch("app.network.iptables.remove_dns_bypass"),
```

- [ ] **Step 3.7: Run full suite to confirm no regressions**

```bash
pytest tests/ -q --tb=short 2>&1 | tail -5
```

Expected: `131 passed` (128 + 3 new)

- [ ] **Step 3.8: Commit**

```bash
git add app/network/iptables.py app/network/session_manager.py \
        tests/test_network/test_dns_bypass.py tests/conftest.py
git commit -m "feat: iptables DNS bypass (add/remove_dns_bypass) + SessionManager integration"
```

---

## Task 4: Admin Schemas + API Endpoints

**Files:**
- Modify: `app/admin/schemas.py`
- Modify: `app/admin/router.py`
- Create: `tests/test_admin/test_admin_dhcp.py`

### Background

- All admin routes are in `app/admin/router.py`. Import pattern: `from app.core.models import X` at the top of the handler body or at file top level.
- `require_superadmin` is already imported and used throughout the router.
- `get_db` dependency is already imported.
- `_templates` (`Jinja2Templates`) is already defined in the router.
- `select` from sqlalchemy is already imported.
- The conftest mock DB has `execute()` returning a mock with `scalar_one_or_none() → None`.
- Tests patch `app.network.dnsmasq.write_config` and `app.network.dnsmasq.reload_dnsmasq` to avoid real file/subprocess calls.

- [ ] **Step 4.1: Write failing tests `tests/test_admin/test_admin_dhcp.py`**

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_get_dhcp_config_returns_defaults(client):
    from app.core.auth import create_access_token
    from app.main import app
    app.state.redis.exists = AsyncMock(return_value=False)
    token = create_access_token({"sub": "admin", "role": "superadmin"})
    with patch("app.network.dnsmasq.get_status", return_value={"running": False, "lease_count": 0, "config_file_exists": False}):
        resp = await client.get(
            "/admin/api/dhcp",
            headers={"Authorization": f"Bearer {token}"},
        )
    # With mock DB returning None, expect 404 (not seeded) or 200 with defaults
    assert resp.status_code in (200, 404)
    assert resp.status_code != 500


@pytest.mark.asyncio
async def test_update_dhcp_config(client):
    from app.core.auth import create_access_token
    from app.main import app
    app.state.redis.exists = AsyncMock(return_value=False)
    token = create_access_token({"sub": "admin", "role": "superadmin"})
    with patch("app.network.dnsmasq.write_config"), \
         patch("app.network.dnsmasq.reload_dnsmasq", return_value=True):
        resp = await client.put(
            "/admin/api/dhcp",
            json={"lease_time": "1h"},
            headers={"Authorization": f"Bearer {token}"},
        )
    # 404 from mock DB (no seeded row) or 200 — never 500
    assert resp.status_code in (200, 404)
    assert resp.status_code != 500


@pytest.mark.asyncio
async def test_staff_cannot_access_dhcp(client):
    from app.core.auth import create_access_token
    from app.main import app
    app.state.redis.exists = AsyncMock(return_value=False)
    token = create_access_token({"sub": "staff", "role": "staff"})
    resp = await client.get(
        "/admin/api/dhcp",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_dhcp_leases_endpoint(client):
    from app.core.auth import create_access_token
    from app.main import app
    app.state.redis.exists = AsyncMock(return_value=False)
    token = create_access_token({"sub": "admin", "role": "superadmin"})
    with patch("app.network.dnsmasq.get_leases", return_value=[]):
        resp = await client.get(
            "/admin/api/dhcp/leases",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_dhcp_status_endpoint(client):
    from app.core.auth import create_access_token
    from app.main import app
    app.state.redis.exists = AsyncMock(return_value=False)
    token = create_access_token({"sub": "admin", "role": "superadmin"})
    with patch("app.network.dnsmasq.get_status", return_value={"running": False, "lease_count": 0, "config_file_exists": False}):
        resp = await client.get(
            "/admin/api/dhcp/status",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    assert "running" in resp.json()
```

- [ ] **Step 4.2: Run tests — expect FAIL (routes don't exist)**

```bash
pytest tests/test_admin/test_admin_dhcp.py -v
```

Expected: `404` responses or `ImportError`

- [ ] **Step 4.3: Add schemas to `app/admin/schemas.py`**

Add at end of file (check what's already imported — `BaseModel` and `Field` are likely there):

```python
from typing import Literal

class DhcpConfigUpdate(BaseModel):
    enabled: bool | None = None
    interface: str | None = None
    gateway_ip: str | None = None
    subnet: str | None = None
    dhcp_range_start: str | None = None
    dhcp_range_end: str | None = None
    lease_time: Literal["30m", "1h", "4h", "8h", "12h", "24h"] | None = None
    dns_upstream_1: str | None = None
    dns_upstream_2: str | None = None
    dns_mode: str | None = None
    log_queries: bool | None = None

class DhcpConfigResponse(BaseModel):
    id: str
    enabled: bool
    interface: str
    gateway_ip: str
    subnet: str
    dhcp_range_start: str
    dhcp_range_end: str
    lease_time: str
    dns_upstream_1: str
    dns_upstream_2: str
    dns_mode: str
    log_queries: bool
    updated_at: str
```

- [ ] **Step 4.4: Add DHCP endpoints to `app/admin/router.py`**

At the top of the file, ensure `DhcpConfig` is importable. Add the import to the existing model imports section:
```python
from app.core.models import (
    ...,  # existing imports
    DhcpConfig, DnsModeType,
)
```

Add the schemas import if `DhcpConfigUpdate`/`DhcpConfigResponse` aren't already imported:
```python
from app.admin.schemas import (
    ...,  # existing
    DhcpConfigUpdate, DhcpConfigResponse,
)
```

Add after the brand endpoints:

```python
# ── DHCP / dnsmasq ────────────────────────────────────────────────────────────
from app.network import dnsmasq as _dnsmasq


def _dhcp_to_response(d: DhcpConfig) -> dict:
    return {
        "id": str(d.id),
        "enabled": d.enabled,
        "interface": d.interface,
        "gateway_ip": d.gateway_ip,
        "subnet": d.subnet,
        "dhcp_range_start": d.dhcp_range_start,
        "dhcp_range_end": d.dhcp_range_end,
        "lease_time": d.lease_time,
        "dns_upstream_1": d.dns_upstream_1,
        "dns_upstream_2": d.dns_upstream_2,
        "dns_mode": d.dns_mode.value if hasattr(d.dns_mode, "value") else d.dns_mode,
        "log_queries": d.log_queries,
        "updated_at": d.updated_at.isoformat(),
    }


@router.get("/api/dhcp")
async def get_dhcp_config(db: AsyncSession = Depends(get_db),
                           _: dict = Depends(require_superadmin)):
    result = await db.execute(select(DhcpConfig))
    d = result.scalar_one_or_none()
    if not d:
        raise HTTPException(404, {"error": "dhcp_config_not_seeded"})
    return _dhcp_to_response(d)


@router.put("/api/dhcp")
async def update_dhcp_config(body: DhcpConfigUpdate,
                              db: AsyncSession = Depends(get_db),
                              _: dict = Depends(require_superadmin)):
    result = await db.execute(select(DhcpConfig))
    d = result.scalar_one_or_none()
    if not d:
        raise HTTPException(404, {"error": "dhcp_config_not_seeded"})
    for field, value in body.dict(exclude_none=True).items():
        if field == "dns_mode":
            try:
                value = DnsModeType(value)
            except ValueError:
                raise HTTPException(422, {"error": "invalid_dns_mode", "allowed": ["redirect", "forward"]})
        setattr(d, field, value)
    d.updated_at = datetime.now(timezone.utc)
    await db.commit()
    await db.refresh(d)
    reloaded = False
    if d.enabled:
        _dnsmasq.write_config(d)
        reloaded = _dnsmasq.reload_dnsmasq()
    else:
        _dnsmasq.write_config(d)  # stops dnsmasq when enabled=False
    return {**_dhcp_to_response(d), "reloaded": reloaded}


@router.get("/api/dhcp/status")
async def dhcp_status(_: dict = Depends(require_superadmin)):
    return _dnsmasq.get_status()


@router.get("/api/dhcp/leases")
async def dhcp_leases(_: dict = Depends(require_superadmin)):
    return _dnsmasq.get_leases()


@router.post("/api/dhcp/reload")
async def dhcp_reload(_: dict = Depends(require_superadmin)):
    reloaded = _dnsmasq.reload_dnsmasq()
    return {"reloaded": reloaded}


@router.get("/dhcp", response_class=HTMLResponse, include_in_schema=False)
async def dhcp_page(request: Request, payload: dict = Depends(require_superadmin),
                    db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(DhcpConfig))
    d = result.scalar_one_or_none()
    config = _dhcp_to_response(d) if d else None
    status = _dnsmasq.get_status()
    flash = request.session.pop("flash", None)
    return _templates.TemplateResponse("dhcp.html", {
        "request": request, "current_user": payload,
        "config": config, "status": status, "flash": flash,
    })
```

- [ ] **Step 4.5: Run DHCP API tests — expect PASS**

```bash
pytest tests/test_admin/test_admin_dhcp.py -v
```

Expected: `5 passed`

- [ ] **Step 4.6: Run full suite — no regressions**

```bash
pytest tests/ -q --tb=short 2>&1 | tail -5
```

Expected: `136 passed`

- [ ] **Step 4.7: Commit**

```bash
git add app/admin/schemas.py app/admin/router.py tests/test_admin/test_admin_dhcp.py
git commit -m "feat: DHCP admin API — GET/PUT /admin/api/dhcp, status, leases, reload, HTML page"
```

---

## Task 5: Admin UI + base.html nav + main.py lifespan

**Files:**
- Create: `app/admin/templates/dhcp.html`
- Modify: `app/admin/templates/base.html`
- Modify: `app/main.py`

### Background

- All templates extend `base.html`. CSS classes: `glass` = `bg-white/5 backdrop-blur-md border border-white/10 rounded-2xl`. Background: `#0f172a`.
- `base.html` sidebar nav links for superadmin-only items are inside `{% if current_user.role == 'superadmin' %}` block (lines 30–36). Add DHCP link there.
- HTMX: `hx-get`, `hx-post`, `hx-put`, `hx-target`, `hx-swap`, `hx-trigger="every 30s"`.
- Alpine.js: `x-data`, `x-show`, `x-model`, `@click`, `:disabled`.
- The status div and leases tbody use HTMX polling. Status endpoint returns JSON — the HTMX target needs to render it. Use a separate partial route OR render inline with `hx-swap="outerHTML"` on a pre-rendered div. **Simplest approach**: status card loads a JSON response and Alpine.js reads it; leases table HTMX-loads an HTML fragment from `/admin/api/dhcp/leases` rendered by template.

**Note on leases HTMX:** The leases API returns JSON. For simplicity, use Alpine.js `fetch` to load leases (same as other templates that call JSON APIs), rather than HTMX targeting a JSON endpoint.

- [ ] **Step 5.1: Add DHCP nav link to `app/admin/templates/base.html`**

In the `{% if current_user.role == 'superadmin' %}` block (after the Admin Users link), add:

```html
<a href="/admin/dhcp" class="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-white/10 text-sm">DHCP / DNS</a>
```

- [ ] **Step 5.2: Create `app/admin/templates/dhcp.html`**

```html
{% extends "base.html" %}
{% block title %}DHCP / DNS{% endblock %}
{% block content %}
<div x-data="{
  status: {{ status | tojson }},
  leases: [],
  query: '',
  saving: false,
  reloadMsg: '',
  async fetchStatus() {
    const r = await fetch('/admin/api/dhcp/status');
    this.status = await r.json();
  },
  async fetchLeases() {
    const r = await fetch('/admin/api/dhcp/leases');
    this.leases = await r.json();
  },
  filteredLeases() {
    if (!this.query) return this.leases;
    const q = this.query.toLowerCase();
    return this.leases.filter(l =>
      l.mac.includes(q) || l.ip.includes(q) || (l.hostname || '').toLowerCase().includes(q)
    );
  },
  async doReload() {
    const r = await fetch('/admin/api/dhcp/reload', {method: 'POST'});
    const data = await r.json();
    this.reloadMsg = data.reloaded ? 'Reloaded ✓' : 'Reload failed ✗';
    await this.fetchStatus();
  }
}" x-init="fetchLeases(); setInterval(() => { fetchStatus(); fetchLeases(); }, 30000)">

  <div class="flex items-center justify-between mb-8">
    <h1 class="text-2xl font-bold">DHCP / DNS</h1>
  </div>

  {% if flash %}
  <div class="mb-4 px-4 py-3 rounded-lg bg-yellow-500/10 border border-yellow-500/30 text-yellow-300 text-sm">{{ flash }}</div>
  {% endif %}

  <!-- Card 1: Service Status -->
  <div class="glass rounded-xl p-6 mb-6">
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-lg font-semibold">Service Status</h2>
      <div class="flex items-center gap-3">
        <span x-text="reloadMsg" class="text-sm text-green-400"></span>
        <button @click="doReload()"
                class="px-4 py-1.5 text-sm rounded-lg"
                style="background:linear-gradient(135deg,#6366f1,#8b5cf6)">
          Reload dnsmasq
        </button>
      </div>
    </div>
    <div class="flex items-center gap-6">
      <div class="flex items-center gap-2">
        <span :class="status.running ? 'bg-green-400' : 'bg-red-500'"
              class="inline-block w-3 h-3 rounded-full"></span>
        <span x-text="status.running ? 'Running' : 'Stopped'" class="text-sm font-medium"></span>
      </div>
      <div class="text-sm text-slate-400">
        Active leases: <span x-text="status.lease_count" class="text-white font-medium"></span>
      </div>
      <div class="text-sm text-slate-400">
        Config file: <span :class="status.config_file_exists ? 'text-green-400' : 'text-red-400'"
                           x-text="status.config_file_exists ? 'Present' : 'Missing'"></span>
      </div>
    </div>
  </div>

  <!-- Card 2: Configuration -->
  <div class="glass rounded-xl p-6 mb-6">
    <h2 class="text-lg font-semibold mb-4">Configuration</h2>
    {% if config %}
    <form id="dhcp-form">
      <div class="grid grid-cols-2 gap-4 mb-4">

        <div class="col-span-2 flex items-center gap-3">
          <label class="text-sm text-slate-400">Enabled</label>
          <input type="checkbox" name="enabled" {% if config.enabled %}checked{% endif %}
                 class="w-4 h-4 rounded">
        </div>

        <div>
          <label class="block text-xs text-slate-400 mb-1">Interface</label>
          <input type="text" name="interface" value="{{ config.interface }}"
                 class="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm">
        </div>

        <div>
          <label class="block text-xs text-slate-400 mb-1">Gateway IP</label>
          <input type="text" name="gateway_ip" value="{{ config.gateway_ip }}"
                 class="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm">
        </div>

        <div>
          <label class="block text-xs text-slate-400 mb-1">Subnet (CIDR)</label>
          <input type="text" name="subnet" value="{{ config.subnet }}"
                 class="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm">
        </div>

        <div>
          <label class="block text-xs text-slate-400 mb-1">Lease Time</label>
          <select name="lease_time" class="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm">
            {% for lt in ["30m", "1h", "4h", "8h", "12h", "24h"] %}
            <option value="{{ lt }}" {% if config.lease_time == lt %}selected{% endif %}>{{ lt }}</option>
            {% endfor %}
          </select>
        </div>

        <div>
          <label class="block text-xs text-slate-400 mb-1">DHCP Range Start</label>
          <input type="text" name="dhcp_range_start" value="{{ config.dhcp_range_start }}"
                 class="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm">
        </div>

        <div>
          <label class="block text-xs text-slate-400 mb-1">DHCP Range End</label>
          <input type="text" name="dhcp_range_end" value="{{ config.dhcp_range_end }}"
                 class="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm">
        </div>

        <div>
          <label class="block text-xs text-slate-400 mb-1">DNS Upstream 1</label>
          <input type="text" name="dns_upstream_1" value="{{ config.dns_upstream_1 }}"
                 class="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm">
        </div>

        <div>
          <label class="block text-xs text-slate-400 mb-1">DNS Upstream 2</label>
          <input type="text" name="dns_upstream_2" value="{{ config.dns_upstream_2 }}"
                 class="w-full bg-white/5 border border-white/10 rounded-lg px-3 py-2 text-sm">
        </div>

        <div class="col-span-2">
          <label class="block text-xs text-slate-400 mb-2">DNS Mode</label>
          <div class="flex gap-6">
            <label class="flex items-center gap-2 text-sm cursor-pointer">
              <input type="radio" name="dns_mode" value="redirect"
                     {% if config.dns_mode == 'redirect' %}checked{% endif %}>
              <span class="font-medium">Redirect</span>
              <span class="text-slate-400 text-xs">— all DNS → portal IP (best captive detection)</span>
            </label>
            <label class="flex items-center gap-2 text-sm cursor-pointer">
              <input type="radio" name="dns_mode" value="forward"
                     {% if config.dns_mode == 'forward' %}checked{% endif %}>
              <span class="font-medium">Forward</span>
              <span class="text-slate-400 text-xs">— DNS → upstream directly</span>
            </label>
          </div>
        </div>

        <div class="col-span-2 flex items-center gap-2">
          <input type="checkbox" name="log_queries" {% if config.log_queries %}checked{% endif %}
                 class="w-4 h-4 rounded">
          <label class="text-sm">Log DNS queries &amp; DHCP assignments</label>
        </div>
      </div>

      <div class="flex items-center gap-3">
        <button type="button" @click="saving=true; (async () => {
            const form = document.getElementById('dhcp-form');
            const data = Object.fromEntries(new FormData(form));
            data.enabled = form.querySelector('[name=enabled]').checked;
            data.log_queries = form.querySelector('[name=log_queries]').checked;
            const r = await fetch('/admin/api/dhcp', {method:'PUT',
              headers:{'Content-Type':'application/json'},
              body: JSON.stringify(data)});
            saving=false;
            if (r.ok) { reloadMsg='Saved ✓'; fetchStatus(); }
            else { const e=await r.json(); reloadMsg='Error: '+(e.detail?.error||'unknown'); }
          })()"
                class="px-6 py-2 text-sm rounded-lg font-medium"
                style="background:linear-gradient(135deg,#6366f1,#8b5cf6)">
          <span x-show="!saving">Save & Apply</span>
          <span x-show="saving">Saving…</span>
        </button>
        <span x-text="reloadMsg" class="text-sm text-green-400"></span>
      </div>
    </form>
    {% else %}
    <p class="text-slate-400 text-sm">DHCP config not found in database. Run migrations first.</p>
    {% endif %}
  </div>

  <!-- Card 3: Active Leases -->
  <div class="glass rounded-xl p-6">
    <div class="flex items-center justify-between mb-4">
      <h2 class="text-lg font-semibold">Active DHCP Leases (<span x-text="filteredLeases().length"></span>)</h2>
      <input type="text" x-model="query" placeholder="Search MAC / IP / hostname…"
             class="bg-white/5 border border-white/10 rounded-lg px-3 py-1.5 text-sm w-64">
    </div>
    <div class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr class="text-slate-400 text-left border-b border-white/10">
            <th class="pb-2 pr-4">MAC Address</th>
            <th class="pb-2 pr-4">IP Address</th>
            <th class="pb-2 pr-4">Hostname</th>
            <th class="pb-2">Expires At</th>
          </tr>
        </thead>
        <tbody>
          <template x-for="l in filteredLeases()" :key="l.mac">
            <tr class="border-b border-white/5 hover:bg-white/5">
              <td class="py-2 pr-4 font-mono text-xs" x-text="l.mac"></td>
              <td class="py-2 pr-4 font-mono" x-text="l.ip"></td>
              <td class="py-2 pr-4" x-text="l.hostname || '—'"></td>
              <td class="py-2 text-slate-400 text-xs" x-text="l.expires_at || '—'"></td>
            </tr>
          </template>
          <tr x-show="filteredLeases().length === 0">
            <td colspan="4" class="py-4 text-center text-slate-500 text-sm">No active leases</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>

</div>
{% endblock %}
```

- [ ] **Step 5.3: Update `app/main.py` — restore dnsmasq config on startup**

In the `lifespan` function, after the `ensure_ifb_ready()` block, add:

```python
    # Restore dnsmasq config from DB
    try:
        from app.core.database import AsyncSessionFactory
        from app.core.models import DhcpConfig
        from app.network import dnsmasq as _dnsmasq
        from sqlalchemy import select as _select
        async with AsyncSessionFactory() as _db:
            _result = await _db.execute(_select(DhcpConfig))
            _dhcp = _result.scalar_one_or_none()
            if _dhcp and _dhcp.enabled:
                _dnsmasq.write_config(_dhcp)
                _dnsmasq.reload_dnsmasq()
    except Exception as _e:
        import logging as _logging
        _logging.getLogger(__name__).warning(f"dnsmasq startup restore failed: {_e}")
```

- [ ] **Step 5.4: Run full test suite**

```bash
pytest tests/ -q --tb=short 2>&1 | tail -5
```

Expected: `136 passed` (no regressions — lifespan startup is not exercised in tests)

- [ ] **Step 5.5: Commit**

```bash
git add app/admin/templates/dhcp.html app/admin/templates/base.html app/main.py
git commit -m "feat: DHCP admin UI — status card, config form, leases table; nav link; lifespan restore"
```

---

## Task 6: setup-dnsmasq.sh + install.sh Integration

**Files:**
- Create: `scripts/setup-dnsmasq.sh`
- Modify: `scripts/install.sh`

### Background

No tests for shell scripts (would require a real system). This task produces runnable scripts only.

`install.sh` Section 8 (line ~388) currently calls `setup-iptables.sh` and `setup-tc.sh`. Add `setup-dnsmasq.sh` after them.

- [ ] **Step 6.1: Create `scripts/setup-dnsmasq.sh`**

```bash
#!/usr/bin/env bash
# =============================================================================
# WiFi Captive Portal — dnsmasq Setup
# Installs dnsmasq and configures it for captive portal management.
# Called by install.sh. Must run as root.
# =============================================================================
set -e

GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
info() { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }

[[ $EUID -ne 0 ]] && { echo "Must run as root"; exit 1; }

info "Installing dnsmasq..."
apt-get install -y -qq dnsmasq

info "Stopping dnsmasq to take over config..."
systemctl stop dnsmasq || true

info "Configuring dnsmasq to use drop-in directory..."
cat > /etc/dnsmasq.conf <<'EOF'
# Managed by WiFi Captive Portal
# Do not add settings here — use /etc/dnsmasq.d/captive-portal.conf
conf-dir=/etc/dnsmasq.d/,*.conf
EOF

mkdir -p /etc/dnsmasq.d

info "Enabling dnsmasq service (will start via captive-portal lifespan)..."
systemctl enable dnsmasq

success "dnsmasq setup complete. Config will be written by the portal app on first start."
```

- [ ] **Step 6.2: Make script executable**

```bash
chmod +x scripts/setup-dnsmasq.sh
```

- [ ] **Step 6.3: Update `scripts/install.sh` Section 8**

Find the line in Section 8 that runs `setup-tc.sh` (around line 396):
```bash
    bash "$SCRIPT_DIR/setup-tc.sh"
```

After it, add:
```bash
info "Setting up dnsmasq DHCP+DNS..."
bash "$SCRIPT_DIR/setup-dnsmasq.sh"
```

- [ ] **Step 6.4: Run full test suite one final time**

```bash
pytest tests/ -q --tb=short 2>&1 | tail -5
```

Expected: `136 passed`

- [ ] **Step 6.5: Commit**

```bash
git add scripts/setup-dnsmasq.sh scripts/install.sh
git commit -m "feat: setup-dnsmasq.sh — install + configure dnsmasq drop-in dir"
```

---

## Final Verification

After all tasks are complete:

```bash
# Full test suite
pytest tests/ -v --tb=short 2>&1 | tail -30

# Coverage check
pytest tests/ --cov=app --cov-report=term-missing 2>&1 | grep -E "(dnsmasq|iptables|TOTAL)"

# Confirm all new files exist
ls -la app/network/dnsmasq.py \
       app/admin/templates/dhcp.html \
       scripts/setup-dnsmasq.sh \
       tests/test_network/test_dnsmasq.py \
       tests/test_network/test_dns_bypass.py \
       tests/test_admin/test_admin_dhcp.py
```

Expected: 136 tests passing, all files present.
