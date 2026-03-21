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
      └── dns_mode=forward  → forward to upstream DNS (8.8.8.8, 8.8.4.4)

[Admin UI] → PUT /admin/api/dhcp → write /etc/dnsmasq.d/captive-portal.conf → systemctl reload dnsmasq
```

The FastAPI app runs as root (per existing install.sh), so it can write to `/etc/dnsmasq.d/` and call `systemctl reload dnsmasq` directly.

---

## Data Model

### `dhcp_config` table

Single-row configuration table (seeded with defaults on migration, same pattern as `brand_config`).

| Column | Type | Default | Description |
|--------|------|---------|-------------|
| `id` | UUID PK | generated | |
| `enabled` | Boolean | true | Enable/disable dnsmasq management |
| `interface` | String(32) | wlan0 | WiFi interface to bind |
| `gateway_ip` | String(15) | 192.168.0.1 | Gateway IP (this server on WiFi side) |
| `subnet` | String(18) | 192.168.0.0/22 | Subnet in CIDR notation |
| `dhcp_range_start` | String(15) | 192.168.0.10 | First IP to assign |
| `dhcp_range_end` | String(15) | 192.168.3.250 | Last IP to assign |
| `lease_time` | String(8) | 8h | Lease duration (e.g. "1h", "8h", "24h") |
| `dns_upstream_1` | String(45) | 8.8.8.8 | Primary upstream DNS |
| `dns_upstream_2` | String(45) | 8.8.4.4 | Secondary upstream DNS |
| `dns_mode` | Enum(DnsModeType) | redirect | `redirect` or `forward` |
| `log_queries` | Boolean | false | Enable dnsmasq query logging |
| `updated_at` | DateTime(tz) | now | Last saved |

### `DnsModeType` enum

```python
class DnsModeType(str, enum.Enum):
    redirect = "redirect"   # answer all DNS with portal IP (pre-auth)
    forward  = "forward"    # forward to upstream DNS directly
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
| `app/admin/router.py` | Modify | DHCP API + HTML page routes |
| `app/admin/schemas.py` | Modify | `DhcpConfigUpdate` Pydantic schema |
| `app/admin/templates/dhcp.html` | New | Admin DHCP configuration UI |
| `scripts/setup-dnsmasq.sh` | New | Install dnsmasq, disable default config, initial setup |
| `tests/test_network/test_dnsmasq.py` | New | Unit tests for dnsmasq module |
| `tests/test_admin/test_admin_dhcp.py` | New | API tests for DHCP endpoints |

---

## Module: `app/network/dnsmasq.py`

### `write_config(config: DhcpConfig) -> None`

Generates `/etc/dnsmasq.d/captive-portal.conf` from the DB config object.

Template output (dns_mode=redirect example):
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

# DNS mode: redirect (catch-all to portal)
address=/#/192.168.0.1

# Logging
log-dhcp
```

Template output (dns_mode=forward):
```
# Same as above but WITHOUT address=/#/... line
# DNS queries forwarded normally to upstream
```

When `enabled=False`, writes an empty/comment-only config and reloads (dnsmasq falls back to defaults or stops if no valid config).

### `reload_dnsmasq() -> bool`

Runs `systemctl reload dnsmasq`. Returns True on success, False on failure. Logs errors.

### `get_status() -> dict`

Returns:
```python
{
    "running": bool,        # systemctl is-active dnsmasq
    "lease_count": int,     # count of lines in /var/lib/misc/dnsmasq.leases
    "config_file_exists": bool,
}
```

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
        "expires_at": "2026-03-21T18:00:00+00:00",  # ISO format
    },
    ...
]
```

Returns `[]` if file does not exist.

---

## Admin API Endpoints

All endpoints require `require_superadmin` dependency.

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/admin/api/dhcp` | Return current `DhcpConfig` as JSON |
| `PUT` | `/admin/api/dhcp` | Update config → write file → reload dnsmasq |
| `GET` | `/admin/api/dhcp/status` | Return `get_status()` dict |
| `GET` | `/admin/api/dhcp/leases` | Return `get_leases()` list |
| `POST` | `/admin/api/dhcp/reload` | Manually trigger `reload_dnsmasq()` |
| `GET` | `/admin/dhcp` | HTML page rendering `dhcp.html` |

### PUT /admin/api/dhcp response

On success, returns updated config fields + `{"reloaded": true/false}` indicating whether dnsmasq reload succeeded.

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
- Lease Time (select: 30m / 1h / 4h / 8h / 12h / 24h / custom text)
- DNS Upstream 1 + 2 (text inputs)
- DNS Mode (radio buttons: `redirect` / `forward`, with tooltip explaining each)
- Log DNS Queries (checkbox)
- Save button → `hx-put="/admin/api/dhcp"` with inline success/error feedback

### Card 3 — Active DHCP Leases
- Search box (Alpine.js client-side filter)
- Table: MAC Address | IP Address | Hostname | Expires At
- HTMX poll every 30s: `hx-get="/admin/api/dhcp/leases"` on tbody

---

## Script: `scripts/setup-dnsmasq.sh`

One-time setup script (called during `install.sh`):

1. `apt-get install -y dnsmasq`
2. `systemctl stop dnsmasq` (before we take over config)
3. Disable default config: `echo "conf-dir=/etc/dnsmasq.d/,*.conf" > /etc/dnsmasq.conf`
4. Create `/etc/dnsmasq.d/` directory if needed
5. `systemctl enable dnsmasq`
6. `systemctl start dnsmasq`

`install.sh` will be updated to call this script in Section 8 (after iptables/tc).

---

## Tests

### `tests/test_network/test_dnsmasq.py`

- `test_write_config_redirect_mode` — call `write_config()` with mock config, assert file content contains `address=/#/`
- `test_write_config_forward_mode` — assert file content does NOT contain `address=/#/`
- `test_get_leases_parses_correctly` — mock lease file content, assert parsed dicts match expected
- `test_get_leases_returns_empty_when_no_file` — assert returns `[]` when file missing
- `test_get_status_returns_dict` — mock subprocess, assert keys present

### `tests/test_admin/test_admin_dhcp.py`

- `test_get_dhcp_config_returns_defaults` — GET /admin/api/dhcp → 200, has all expected keys
- `test_update_dhcp_config` — PUT with new lease_time → config updated (mock DB)
- `test_staff_cannot_access_dhcp` — GET /admin/api/dhcp with staff token → 403
- `test_dhcp_leases_endpoint` — GET /admin/api/dhcp/leases → 200, returns list
- `test_dhcp_status_endpoint` — GET /admin/api/dhcp/status → 200, has `running` key

---

## Integration with Existing System

- **install.sh**: Add call to `scripts/setup-dnsmasq.sh` in Section 8 (Network Rules)
- **app/main.py**: On lifespan startup, read `DhcpConfig` from DB — if `enabled=True` and config exists, call `write_config()` + `reload_dnsmasq()` to restore config after server restart
- **iptables**: No changes needed. Existing rules already allow DNS passthrough (`FORWARD` on port 53). dnsmasq listens on the gateway IP itself (INPUT chain), not via FORWARD.
- **`app/network/arp.py`**: No changes. MAC lookup still works the same way.

---

## Constraints

- dnsmasq must be installed separately via `setup-dnsmasq.sh` — not auto-installed by the FastAPI app
- File writes go to `/etc/dnsmasq.d/captive-portal.conf` — requires root
- `reload_dnsmasq()` uses subprocess, same pattern as `iptables.py` and `tc.py`
- `write_config()` and `reload_dnsmasq()` are called synchronously in the PUT handler (fast operations, < 1s)
- Tests mock all subprocess calls and file I/O — no actual dnsmasq required for tests

---

## DNS Mode Detail

| Mode | Behavior | Use case |
|------|----------|----------|
| `redirect` | dnsmasq answers ALL DNS queries with portal IP (`address=/#/<gateway_ip>`) | Pre-auth captive portal detection — mobile OS detects portal faster |
| `forward` | dnsmasq forwards DNS to upstream (8.8.8.8) normally | Sites that need DNS to work pre-auth, or when iptables HTTP redirect is sufficient |

**Recommended default:** `redirect` — works best with iOS/Android captive portal detection.

After guest authenticates, iptables allows their traffic through (including DNS port 53 to upstream). However, since dnsmasq is the advertised DNS server, authenticated guests' DNS still goes through dnsmasq on the gateway. In `redirect` mode this means their DNS is answered with portal IP even after auth — which would break internet.

**Solution:** When a guest authenticates, `SessionManager.create_session()` also adds an iptables rule allowing the guest's DNS to bypass dnsmasq (DNAT port 53 from whitelisted IPs to upstream directly). This is handled in `app/network/iptables.py` — add `add_dns_bypass(ip)` and `remove_dns_bypass(ip)`.

Alternatively (simpler): use `forward` mode and rely on iptables HTTP redirect for captive portal detection (already works for most devices). `redirect` mode is available as an option for environments where HTTP redirect alone is insufficient.
