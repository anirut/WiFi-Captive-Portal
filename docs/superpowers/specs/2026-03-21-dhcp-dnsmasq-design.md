# dnsmasq DHCP + DNS Integration — Design Spec

**Date:** 2026-03-21
**Project:** WiFi Captive Portal
**Status:** Approved

---

## Goal

Add a managed dnsmasq service to the WiFi Captive Portal that provides DHCP and DNS for guest devices, fully configurable via the existing admin web UI. Replaces any external DHCP/DNS dependency.

## Background

The portal currently assumes DHCP and DNS are managed externally. This spec integrates dnsmasq (lightweight, battle-tested, handles DHCP + DNS in one process) so the portal server becomes fully self-contained. Configuration is stored in PostgreSQL and applied to dnsmasq on save.

---

## Architecture

```
[Guest Device]
      │  DHCP request (UDP 67/68)
      ▼
[dnsmasq on gateway] ──── assign IP from configured pool
      │  DNS query (UDP/TCP 53)
      ▼
[dnsmasq]
      ├── dns_mode=redirect → answer all domains with portal IP (pre-auth captive detection)
      │   authenticated guests: iptables DNAT redirects their port-53 to upstream DNS directly
      └── dns_mode=forward  → forward to upstream DNS (8.8.8.8, 8.8.4.4) for all guests

[Admin UI] → PUT /admin/api/dhcp → write /etc/dnsmasq.d/captive-portal.conf → systemctl reload dnsmasq
```

The FastAPI app runs as root (per existing install.sh), so it can write to `/etc/dnsmasq.d/` and call `systemctl reload dnsmasq` directly.

---

## Data Model

### `dhcp_config` table

Single-row configuration table (seeded with defaults on migration, same pattern as `brand_config`).

Seed row UUID: `DHCP_CONFIG_ID = '00000000-0000-0000-0000-000000000002'`

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | UUID PK | DHCP_CONFIG_ID | |
| `enabled` | Boolean | true | Enable/disable dnsmasq management |
| `interface` | String(32) | wlan0 | WiFi interface to bind |
| `gateway_ip` | String(15) | 192.168.0.1 | Gateway IP (this server on WiFi side) |
| `subnet` | String(18) | 192.168.0.0/22 | Subnet in CIDR notation |
| `dhcp_range_start` | String(15) | 192.168.0.10 | First IP to assign |
| `dhcp_range_end` | String(15) | 192.168.3.250 | Last IP to assign |
| `lease_time` | String(8) | 8h | Lease duration: "30m", "1h", "4h", "8h", "12h", "24h" |
| `dns_upstream_1` | String(45) | 8.8.8.8 | Primary upstream DNS |
| `dns_upstream_2` | String(45) | 8.8.4.4 | Secondary upstream DNS |
| `dns_mode` | Enum(DnsModeType) | redirect | `redirect` or `forward` |
| `log_queries` | Boolean | false | Enable dnsmasq query + DHCP logging |
| `updated_at` | DateTime(tz) | now | Last saved |

### `DnsModeType` enum

```python
class DnsModeType(str, enum.Enum):
    redirect = "redirect"   # answer all DNS with portal IP (pre-auth); bypassed for authed guests via iptables
    forward  = "forward"    # forward to upstream DNS directly for all guests
```

### ORM model location

Add `DhcpConfig` and `DnsModeType` to `app/core/models.py`.

---

## File Map

| File | New/Modify | Responsibility |
|------|-----------|----------------|
| `alembic/versions/c3d4e5f6_dhcp_config.py` | New | Create `dhcp_config` table + seed default row |
| `app/core/models.py` | Modify | Add `DnsModeType` enum + `DhcpConfig` ORM model |
| `app/network/dnsmasq.py` | New | Config generation, file writing, reload, status, lease parsing |
| `app/network/iptables.py` | Modify | Add `add_dns_bypass(ip)` + `remove_dns_bypass(ip)` |
| `app/network/session_manager.py` | Modify | Call `add_dns_bypass(ip)` in `create_session()`, `remove_dns_bypass(ip)` in `expire_session()` |
| `app/admin/router.py` | Modify | DHCP API + HTML page routes |
| `app/admin/schemas.py` | Modify | `DhcpConfigUpdate` + `DhcpConfigResponse` Pydantic schemas |
| `app/admin/templates/base.html` | Modify | Add DHCP nav link to sidebar |
| `app/admin/templates/dhcp.html` | New | Admin DHCP configuration UI |
| `scripts/setup-dnsmasq.sh` | New | Install dnsmasq, disable default config, initial setup |
| `tests/test_network/test_dnsmasq.py` | New | Unit tests for dnsmasq module |
| `tests/test_admin/test_admin_dhcp.py` | New | API tests for DHCP endpoints |

---

## Module: `app/network/dnsmasq.py`

### `write_config(config: DhcpConfig) -> None`

Generates `/etc/dnsmasq.d/captive-portal.conf` from the DB config object.

**CIDR to netmask conversion:** Use Python stdlib:
```python
import ipaddress
netmask = str(ipaddress.IPv4Network(config.subnet, strict=False).netmask)
# e.g. "192.168.0.0/22" → "255.255.252.0"
```

Template output (dns_mode=redirect, log_queries=True example):
```
# Managed by WiFi Captive Portal — do not edit manually
interface=wlan0
except-interface=lo
bind-interfaces
no-resolv

# DHCP
dhcp-range=192.168.0.10,192.168.3.250,255.255.252.0,8h
dhcp-option=option:router,192.168.0.1
dhcp-option=option:dns-server,192.168.0.1

# DNS upstream
server=8.8.8.8
server=8.8.4.4

# DNS mode: redirect (catch-all to portal IP)
address=/#/192.168.0.1

# Logging (log_queries=True writes both directives)
log-dhcp
log-queries
```

Template output (dns_mode=forward): identical but WITHOUT the `address=/#/...` line.

**When `enabled=False`:**
- Do NOT write a config file
- Run `systemctl stop dnsmasq` (subprocess, check=False, log errors)
- `get_status()` will return `running: false`

### `reload_dnsmasq() -> bool`

Runs `systemctl reload dnsmasq`. Returns True on success, False on failure. Logs errors.
Only called when `enabled=True`.

### `get_status() -> dict`

Returns:
```python
{
    "running": bool,             # systemctl is-active dnsmasq (exit code 0 = True)
    "lease_count": int,          # count of lines in /var/lib/misc/dnsmasq.leases (0 if missing)
    "config_file_exists": bool,  # os.path.exists("/etc/dnsmasq.d/captive-portal.conf")
}
```

All subprocess errors are caught and return `running: False`.

### `get_leases() -> list[dict]`

Parses `/var/lib/misc/dnsmasq.leases`. Each line format:
`<expiry_epoch> <mac> <ip> <hostname> <client-id>`

Returns:
```python
[
    {
        "mac": "aa:bb:cc:dd:ee:ff",
        "ip": "192.168.0.42",
        "hostname": "iPhone-guest",
        "expires_at": "2026-03-21T18:00:00+00:00",  # ISO format, UTC
    },
    ...
]
```

Returns `[]` if file does not exist or cannot be read.

---

## Module: `app/network/iptables.py` additions

Required for `dns_mode=redirect` to work correctly after authentication.

### `add_dns_bypass(ip: str) -> None`

Adds an iptables DNAT rule in the `nat` `PREROUTING` chain that redirects port-53 traffic from an authenticated guest IP directly to upstream DNS (`8.8.8.8`), bypassing dnsmasq's catch-all redirect:

```bash
iptables -t nat -I PREROUTING -s <ip> -p udp --dport 53 -j DNAT --to-destination 8.8.8.8:53
iptables -t nat -I PREROUTING -s <ip> -p tcp --dport 53 -j DNAT --to-destination 8.8.8.8:53
```

Uses existing `_run()` helper (same pattern as `add_whitelist`). Called from `SessionManager.create_session()`.

### `remove_dns_bypass(ip: str) -> None`

Removes the DNAT rules added by `add_dns_bypass`:

```bash
iptables -t nat -D PREROUTING -s <ip> -p udp --dport 53 -j DNAT --to-destination 8.8.8.8:53
iptables -t nat -D PREROUTING -s <ip> -p tcp --dport 53 -j DNAT --to-destination 8.8.8.8:53
```

Uses `_run()` with `check=False` (same pattern as `remove_whitelist`). Called from `SessionManager.expire_session()`.

**Note:** `add_dns_bypass` / `remove_dns_bypass` are always called unconditionally in `SessionManager` (regardless of current `dns_mode`). When `dns_mode=forward`, these rules are harmless no-ops because dnsmasq does not have a catch-all redirect in that mode. This avoids coupling `SessionManager` to the DHCP config.

---

## Schemas: `app/admin/schemas.py`

### `DhcpConfigUpdate`

```python
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
    dns_mode: str | None = None  # "redirect" | "forward"
    log_queries: bool | None = None
```

### `DhcpConfigResponse`

```python
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
    updated_at: str  # ISO format
```

`GET /admin/api/dhcp` uses `DhcpConfigResponse`.
`PUT /admin/api/dhcp` returns `DhcpConfigResponse` + `reloaded: bool`.

---

## Admin API Endpoints

All endpoints require `require_superadmin` dependency.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/admin/api/dhcp` | Return current `DhcpConfig` as `DhcpConfigResponse` |
| `PUT` | `/admin/api/dhcp` | Update config → write file → reload dnsmasq → return updated config + `reloaded` |
| `GET` | `/admin/api/dhcp/status` | Return `get_status()` dict |
| `GET` | `/admin/api/dhcp/leases` | Return `get_leases()` list |
| `POST` | `/admin/api/dhcp/reload` | Manually trigger `reload_dnsmasq()` → return `{"reloaded": bool}` |
| `GET` | `/admin/dhcp` | HTML page rendering `dhcp.html` |

---

## Admin UI: `dhcp.html`

Extends `base.html`. Glassmorphism style (matching existing templates). Three cards:

### Card 1 — Service Status
- Green/red badge: dnsmasq running/stopped
- Active lease count
- "Reload dnsmasq" button → `hx-post="/admin/api/dhcp/reload"` with inline result
- HTMX poll every 30s: `hx-get="/admin/api/dhcp/status"` on status div

### Card 2 — Configuration
- Enable/disable toggle
- Interface (text input)
- Gateway IP (text input)
- Subnet (text input, CIDR)
- DHCP Range Start / End (text inputs)
- Lease Time (select: 30m / 1h / 4h / 8h / 12h / 24h)
- DNS Upstream 1 + 2 (text inputs)
- DNS Mode (radio buttons: `redirect` / `forward`, with tooltip explaining each)
- Log Queries (checkbox — enables both `log-dhcp` and `log-queries` in dnsmasq)
- Save button → `hx-put="/admin/api/dhcp"` with inline success/error feedback

### Card 3 — Active DHCP Leases
- Search box (Alpine.js client-side filter on MAC/IP/hostname)
- Table: MAC Address | IP Address | Hostname | Expires At
- HTMX poll every 30s: `hx-get="/admin/api/dhcp/leases"` on tbody

---

## Script: `scripts/setup-dnsmasq.sh`

One-time setup script (called during `install.sh` Section 8):

```bash
#!/usr/bin/env bash
set -e
apt-get install -y dnsmasq
systemctl stop dnsmasq || true
# Replace default config to only load our drop-in
echo "conf-dir=/etc/dnsmasq.d/,*.conf" > /etc/dnsmasq.conf
mkdir -p /etc/dnsmasq.d
systemctl enable dnsmasq
# Don't start here — write_config() + reload_dnsmasq() called from app lifespan
```

`install.sh` is updated to call `bash "$SCRIPT_DIR/setup-dnsmasq.sh"` in Section 8 (Network Rules), after iptables/tc setup.

---

## app/main.py lifespan integration

In the existing `lifespan` async context manager, add dnsmasq startup restoration after the IFB/tc setup:

```python
# In lifespan startup block:
from app.core.database import AsyncSessionFactory
from app.core.models import DhcpConfig
from app.network import dnsmasq as _dnsmasq
from sqlalchemy import select

try:
    async with AsyncSessionFactory() as _db:
        _result = await _db.execute(select(DhcpConfig))
        _dhcp = _result.scalar_one_or_none()
        if _dhcp and _dhcp.enabled:
            _dnsmasq.write_config(_dhcp)
            _dnsmasq.reload_dnsmasq()
            logger.info("dnsmasq config restored from DB")
except Exception as e:
    logger.warning(f"dnsmasq startup restore failed: {e}")
```

---

## Tests

### `tests/test_network/test_dnsmasq.py`

- `test_write_config_redirect_mode` — call `write_config()` with mock config (redirect mode), mock `open()`, assert written content contains `address=/#/` and correct CIDR-derived netmask
- `test_write_config_forward_mode` — assert written content does NOT contain `address=/#/`
- `test_write_config_disabled_mode` — when `enabled=False`, assert `systemctl stop dnsmasq` is called (mock subprocess), no file written
- `test_get_leases_parses_correctly` — mock lease file with sample line, assert parsed dict has correct mac/ip/hostname/expires_at
- `test_get_leases_returns_empty_when_no_file` — assert returns `[]` when file missing
- `test_get_status_returns_dict` — mock subprocess, assert all three keys present (`running`, `lease_count`, `config_file_exists`)

### `tests/test_admin/test_admin_dhcp.py`

- `test_get_dhcp_config_returns_defaults` — GET /admin/api/dhcp with superadmin token → 200, response has all `DhcpConfigResponse` fields
- `test_update_dhcp_config` — PUT /admin/api/dhcp with `lease_time="1h"` → mock DB returns updated record (404 with mock DB is acceptable, assert not 500)
- `test_staff_cannot_access_dhcp` — GET /admin/api/dhcp with staff token → 403
- `test_dhcp_leases_endpoint` — GET /admin/api/dhcp/leases → 200, returns list
- `test_dhcp_status_endpoint` — GET /admin/api/dhcp/status → 200, has `running` key

---

## Integration with Existing System

- **install.sh**: Add call to `scripts/setup-dnsmasq.sh` in Section 8
- **app/main.py**: Restore dnsmasq config from DB on lifespan startup (see above)
- **iptables**: `add_whitelist`/`remove_whitelist` unchanged. New `add_dns_bypass`/`remove_dns_bypass` added for redirect mode support.
- **SessionManager**: Call `add_dns_bypass(ip)` in `create_session()` and `remove_dns_bypass(ip)` in `expire_session()` — always, unconditionally.
- **base.html**: Add DHCP nav link in sidebar (superadmin-only, matching existing pattern)

---

## Constraints

- dnsmasq must be installed separately via `setup-dnsmasq.sh` — not auto-installed by the FastAPI app
- File writes go to `/etc/dnsmasq.d/captive-portal.conf` — requires root
- All subprocess calls use the existing `_run()` helper pattern from `iptables.py`
- `write_config()` and `reload_dnsmasq()` are called synchronously in the PUT handler (fast operations, < 1s)
- Tests mock all subprocess calls and file I/O — no actual dnsmasq required for tests

---

## DNS Mode Detail

| Mode | Behavior | Use case |
|------|----------|----------|
| `redirect` | dnsmasq answers ALL DNS with portal IP; authenticated guest DNS is DNAT'd to 8.8.8.8 via iptables | Best captive portal detection on iOS/Android |
| `forward` | dnsmasq forwards DNS to upstream normally; iptables HTTP redirect handles portal detection | Simpler; works for most devices |

**Recommended default:** `redirect`.

**DNS bypass iptables rules** (added by `add_dns_bypass(ip)`, removed by `remove_dns_bypass(ip)`):
```bash
# Add (on auth):
iptables -t nat -I PREROUTING -s <ip> -p udp --dport 53 -j DNAT --to-destination 8.8.8.8:53
iptables -t nat -I PREROUTING -s <ip> -p tcp --dport 53 -j DNAT --to-destination 8.8.8.8:53

# Remove (on expire):
iptables -t nat -D PREROUTING -s <ip> -p udp --dport 53 -j DNAT --to-destination 8.8.8.8:53
iptables -t nat -D PREROUTING -s <ip> -p tcp --dport 53 -j DNAT --to-destination 8.8.8.8:53
```

These rules are in the `nat` table `PREROUTING` chain, which runs before the `filter` table — so they intercept DNS before dnsmasq's catch-all can respond.
