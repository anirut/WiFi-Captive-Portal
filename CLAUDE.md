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

This is a **FastAPI modular monolith** for a hotel captive portal. Guests authenticate via room+last-name (PMS lookup) or voucher code, then get iptables/tc rules applied to allow internet access with optional bandwidth shaping.

### Session lifecycle

1. Guest POSTs to `/auth/room` or `/auth/voucher`
2. `SessionManager.create_session()` writes a `Session` row, calls `iptables.add_whitelist(ip)` and `tc.apply_bandwidth_limit(ip, kbps)` via subprocess
3. APScheduler runs `expire_overdue_sessions()` every 60 seconds — this calls `iptables.remove_whitelist` + `tc.remove_bandwidth_limit` and marks sessions `expired`
4. Guest can also self-disconnect via `POST /session/disconnect`

### Module map

| Path | Responsibility |
|------|---------------|
| `app/core/` | Config (pydantic-settings from `.env`), SQLAlchemy async engine/session, ORM models, Fernet encryption, JWT auth, rate limiter |
| `app/network/` | `iptables.py` (subprocess whitelist), `tc.py` (HTB bandwidth shaping), `arp.py` (MAC lookup from `/proc/net/arp`), `session_manager.py` (orchestrates DB + network), `scheduler.py` (APScheduler wrapper) |
| `app/pms/` | `base.py` (abstract `PMSAdapter` + `GuestInfo` dataclass), `standalone.py` (DB-backed adapter), `factory.py` (load active adapter from DB or fall back to standalone) |
| `app/voucher/` | Code generation (ambiguous-char-free) and validation with `VoucherValidationError` |
| `app/portal/` | Guest-facing FastAPI router (`/`, `/auth/*`, `/success`, `/expired`, `/session/disconnect`), Jinja2 templates, request schemas |
| `app/admin/` | Admin router (`/admin/sessions` list + kick), JWT-protected |

### Network enforcement

- **iptables**: `FORWARD` chain whitelist per guest IP. `_run()` wraps subprocess calls, returns `None`. `is_whitelisted` uses `check=False` directly (not via `_run`).
- **tc HTB**: class ID computed as `int(parts[2]) * 256 + int(parts[3])` from the IP's last two octets. Upload shaping is deferred (not implemented).
- **Patch targets** in tests must be module-local: `patch("app.network.iptables.subprocess.run")`, never `patch("subprocess.run")`.

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
| `WIFI_INTERFACE` / `WAN_INTERFACE` | Used in iptables/tc scripts |
| `PORTAL_IP` / `PORTAL_PORT` | Redirect target in iptables |

### Testing

`tests/conftest.py` sets env vars before any app import, then provides a `client` fixture that:
- Patches `iptables`, `tc`, `arp`, `scheduler`, and `pms.factory.load_adapter`
- Overrides `get_db` with an `AsyncMock` (result has `scalar_one_or_none() → None`, `scalars().all() → []`)
- Sets `app.state.redis` to an `AsyncMock` with `incr` returning `1`
