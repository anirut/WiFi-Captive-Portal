# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Commands

```bash
# Activate virtualenv (assumed)
source .venv/bin/activate

# Run all tests
pytest tests/ -v

# Run a single test
pytest tests/test_portal/test_portal_routes.py::test_room_auth_success -v

# Run with coverage
pytest tests/ --cov=app --cov-report=term-missing

# Dev server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080

# Apply DB migrations
alembic upgrade head

# Apply iptables/tc rules (run as root on the gateway host)
sudo bash scripts/setup-iptables.sh
sudo bash scripts/setup-tc.sh
```

## Architecture

This is a **FastAPI modular monolith** for a hotel captive portal. Guests authenticate via room+last-name (PMS lookup) or voucher code, then get nftables/tc rules applied to allow internet access with optional bandwidth shaping.

### Session lifecycle

1. Guest POSTs to `/auth/room` or `/auth/voucher`
2. `SessionManager.create_session()` writes a `Session` row, calls `nftables.add_whitelist(ip)`, `nftables.add_dns_bypass(ip)`, and `tc.apply_bandwidth_limit(ip, kbps)` via subprocess
3. APScheduler runs `expire_overdue_sessions()` every 60 seconds — this calls `nftables.remove_whitelist` + `nftables.remove_dns_bypass` + `tc.remove_bandwidth_limit` and marks sessions `expired`
4. Guest can also self-disconnect via `POST /session/disconnect`
5. Guest can disconnect by navigating to `http://logout.wifi` — portal detects active session by MAC and shows `disconnect.html`

### Module map

| Path | Responsibility |
|------|---------------|
| `app/core/` | Config (pydantic-settings from `.env`), SQLAlchemy async engine/session, ORM models, Fernet encryption, JWT auth, rate limiter |
| `app/network/` | `nftables.py` (whitelist + dns_bypass sets), `tc.py` (HTB bandwidth shaping), `arp.py` (MAC lookup from `/proc/net/arp`), `dnsmasq.py` (write configs for both dnsmasq port 53 + dnsmasq-auth port 5354, reload), `https_redirect.py` (mini TLS server on port 8443), `session_manager.py` (orchestrates DB + network), `scheduler.py` (APScheduler wrapper) |
| `app/pms/` | `base.py` (abstract `PMSAdapter` + `GuestInfo` dataclass), `standalone.py` (DB-backed adapter), `factory.py` (load active adapter from DB or fall back to standalone) |
| `app/voucher/` | Code generation (ambiguous-char-free) and validation with `VoucherValidationError` |
| `app/portal/` | Guest-facing FastAPI router (`/`, `/auth/*`, `/success`, `/expired`, `/session/disconnect`), Jinja2 templates, request schemas. `GET /` shows `disconnect.html` if client has active session, otherwise `login.html`. Includes RFC 8910 captive portal API at `/captive-portal/api/v1/portal-info` |
| `app/admin/` | Admin router (`/admin/sessions` list + kick), JWT-protected. Includes MAC Bypass CRUD page at `/admin/mac-bypass` |

### Network enforcement

- **nftables** (`scripts/setup-nftables.sh`): manages four sets — `whitelist` (internet access), `dns_bypass` (DNS routing to dnsmasq-auth), `doh_servers` (known DoH provider IPs), `mac_bypass` (MAC addresses that skip auth). `nftables.py` uses `nft` CLI to add/remove elements. Patch target: `patch("app.network.nftables.subprocess.run")`.
- **tc HTB**: class ID computed as `int(parts[2]) * 256 + int(parts[3])` from the IP's last two octets. Upload shaping via IFB device.
- **dnsmasq** (port 53): DHCP + DNS for guests. In `redirect` mode answers all DNS with portal IP.
- **dnsmasq-auth** (port 5354): second instance for authenticated clients. Resolves `logout`/`logout.wifi` → portal IP, forwards all other queries to upstream. Configured by `dnsmasq.py` alongside the main instance.
- **Patch targets** in tests must be module-local: `patch("app.network.nftables.subprocess.run")`, never `patch("subprocess.run")`.

### PMS adapter pattern

`load_adapter(db)` reads `PMSAdapterModel` for the active adapter config, decrypts credentials with Fernet, instantiates the matching class, caches it in `_active_adapter`. Falls back to `StandaloneAdapter` if none configured. `get_adapter()` returns the cached instance.

### Key conventions

- Always use `datetime.now(timezone.utc)` — never `datetime.utcnow()`.
- Redis client must use `decode_responses=True`.
- pytest-asyncio runs in **strict mode** — all async tests need `@pytest.mark.asyncio`.
- `HTTPException` detail in portal router is always `{"error": "reason_string"}` (not a bare string).
- Scheduler `shutdown` uses `wait=False`: `scheduler.shutdown(wait=False)`.

### Environment variables (`.env`)

| Variable | Purpose |
|----------|---------|
| `SECRET_KEY` | JWT signing (≥32 chars) |
| `ENCRYPTION_KEY` | Fernet key for PMS credentials |
| `DATABASE_URL` | `postgresql+asyncpg://...` |
| `REDIS_URL` | `redis://...` |
| `WIFI_INTERFACE` / `WAN_INTERFACE` | Used in nftables/tc scripts |
| `PORTAL_IP` / `PORTAL_PORT` | Portal IP and port (default 8080) |
| `DNS_UPSTREAM_IP` | Upstream DNS for auth proxy (default `8.8.8.8`) |

### Testing

`tests/conftest.py` sets env vars before any app import, then provides a `client` fixture that:
- Patches `iptables`, `tc`, `arp`, `scheduler`, and `pms.factory.load_adapter`
- Overrides `get_db` with an `AsyncMock` (result has `scalar_one_or_none() → None`, `scalars().all() → []`)
- Sets `app.state.redis` to an `AsyncMock` with `incr` returning `1`
