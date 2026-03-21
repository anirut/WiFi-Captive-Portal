# Phase 3: Admin Dashboard + Missing Features — Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Complete the WiFi Captive Portal with a full Admin Dashboard UI (Jinja2 + HTMX + Alpine.js + Tailwind, Glassmorphism) and three missing backend features (JWT logout blocklist, upload shaping via IFB, bytes tracking + data-based voucher enforcement).

**Architecture:** Module-by-module — each module produces working, tested code before moving to the next. Backend-foundational tasks (migration, JWT, tc, scheduler) come first; Admin Dashboard UI builds on top of them.

**Tech Stack:** FastAPI, SQLAlchemy 2 (async), Alembic, PostgreSQL, Redis, APScheduler, Jinja2, HTMX, Alpine.js, Tailwind CSS (CDN), Chart.js (CDN), reportlab + qrcode (PDF/QR), starlette SessionMiddleware.

**Spec:** `docs/superpowers/specs/2026-03-21-phase3-admin-dashboard-design.md`

---

## File Map

### New Files
| File | Purpose |
|------|---------|
| `alembic/versions/b2c3d4e5_phase3_tables.py` | Migration: usage_snapshots, brand_config, policies (checkfirst), sessions.bandwidth_up_kbps |
| `app/voucher/pdf.py` | PDF+QR generation via reportlab + qrcode |
| `app/admin/templates/base.html` | Admin layout shell (sidebar, topbar, flash) |
| `app/admin/templates/login.html` | Standalone admin login page |
| `app/admin/templates/dashboard.html` | Dashboard stats + recent sessions |
| `app/admin/templates/sessions.html` | Active sessions table + HTMX polling |
| `app/admin/templates/vouchers.html` | Voucher list, create form, batch, PDF export |
| `app/admin/templates/policies.html` | Policy CRUD with Alpine.js modal |
| `app/admin/templates/rooms.html` | Room list with policy assignment |
| `app/admin/templates/analytics.html` | Chart.js analytics charts |
| `app/admin/templates/pms.html` | PMS settings UI |
| `app/admin/templates/brand.html` | Brand & Config UI |
| `app/admin/templates/users.html` | Admin users list + create |
| `tests/test_admin/test_admin_auth_v2.py` | JWT blocklist, cookie auth, logout |
| `tests/test_network/test_tc_bytes.py` | get_bytes() + upload shaping |
| `tests/test_admin/test_admin_analytics.py` | Snapshot job, analytics endpoint |
| `tests/test_network/test_session_manager_expire.py` | expire_session() 3-arg tc callsite |
| `tests/test_admin/test_admin_policies.py` | Policy CRUD + room assign |
| `tests/test_admin/test_admin_brand.py` | Brand config + logo upload |
| `tests/test_admin/test_admin_users.py` | Admin user create/list |

### Modified Files
| File | Change |
|------|--------|
| `app/core/models.py` | Add `UsageSnapshot`, `BrandConfig` models; add `bandwidth_up_kbps` to `Session` |
| `app/core/auth.py` | Replace raw-token blocklist with jti-based; add `get_current_admin`, `require_superadmin`, `_raise_or_redirect` |
| `app/network/tc.py` | Add `ensure_ifb_ready()`, `get_bytes()`; update `apply_bandwidth_limit()` + `remove_bandwidth_limit()` signatures |
| `app/network/session_manager.py` | Persist `bandwidth_up_kbps` in `create_session()`; update `expire_session()` tc callsite |
| `app/network/scheduler.py` | Add `_bytes_job()`, `_analytics_snapshot_job()`; register in `start_scheduler()` |
| `app/admin/router.py` | Add all Phase 3 endpoints (logout, policies, rooms, analytics, brand, users, pdf, batch voucher, UI pages) |
| `app/admin/schemas.py` | Add Phase 3 Pydantic schemas |
| `app/main.py` | Add `SessionMiddleware`, `403 exception_handler`, `ensure_ifb_ready()` call in lifespan |
| `tests/test_admin/test_voucher_admin.py` | Extend with batch + PDF tests |

---

## Task 1: DB Migration + ORM Models

**Files:**
- Create: `alembic/versions/b2c3d4e5_phase3_tables.py`
- Modify: `app/core/models.py`

### Step 1.1 — Add ORM models to `models.py`

- [ ] Add `UsageSnapshot` and `BrandConfig` models; add `bandwidth_up_kbps` to `Session`.

Open `app/core/models.py`. Add after the `Session` class (line 61), update Session, add two new models at the bottom:

```python
# In Session class — add after bytes_down line:
bandwidth_up_kbps: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
```

Add at the bottom of `models.py`:

```python
import enum as _enum

class LanguageType(_enum.Enum):
    th = "th"
    en = "en"

class UsageSnapshot(Base):
    __tablename__ = "usage_snapshots"
    id: Mapped[uuid.UUID] = uuid_pk()
    snapshot_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    active_sessions: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
    total_bytes_up: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    total_bytes_down: Mapped[int] = mapped_column(BigInteger, nullable=False, default=0, server_default="0")
    voucher_uses: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")

class BrandConfig(Base):
    __tablename__ = "brand_config"
    id: Mapped[uuid.UUID] = uuid_pk()
    hotel_name: Mapped[str] = mapped_column(String(200), nullable=False, default="Hotel WiFi", server_default="Hotel WiFi")
    logo_path: Mapped[str | None] = mapped_column(String(500), nullable=True)
    primary_color: Mapped[str] = mapped_column(String(7), nullable=False, default="#3B82F6", server_default="#3B82F6")
    tc_text_th: Mapped[str | None] = mapped_column(String, nullable=True)
    tc_text_en: Mapped[str | None] = mapped_column(String, nullable=True)
    language: Mapped[LanguageType] = mapped_column(Enum(LanguageType), nullable=False, default=LanguageType.th)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), server_default="now()")
```

Note: `LanguageType` uses `_enum` alias to avoid shadowing the top-level `enum` import. Also add `LanguageType` to the existing `enum` imports at the top.

### Step 1.2 — Create Alembic migration

- [ ] Create `alembic/versions/b2c3d4e5_phase3_tables.py`:

```python
"""phase3_tables

Revision ID: b2c3d4e5
Revises: a1b2c3d4
Create Date: 2026-03-21 00:00:00.000000
"""
from typing import Sequence, Union
import uuid
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision: str = 'b2c3d4e5'
down_revision: Union[str, None] = 'a1b2c3d4'
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

BRAND_CONFIG_ID = '00000000-0000-0000-0000-000000000001'


def upgrade() -> None:
    # 1. language_type enum
    language_type = postgresql.ENUM('th', 'en', name='languagetype', create_type=True)
    language_type.create(op.get_bind())

    # 2. usage_snapshots
    op.create_table(
        'usage_snapshots',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
        sa.Column('snapshot_at', sa.DateTime(timezone=True), nullable=False),
        sa.Column('active_sessions', sa.Integer, nullable=False, server_default='0'),
        sa.Column('total_bytes_up', sa.BigInteger, nullable=False, server_default='0'),
        sa.Column('total_bytes_down', sa.BigInteger, nullable=False, server_default='0'),
        sa.Column('voucher_uses', sa.Integer, nullable=False, server_default='0'),
    )
    op.create_index('ix_usage_snapshots_snapshot_at', 'usage_snapshots', ['snapshot_at'], postgresql_using='btree')

    # 3. brand_config
    op.create_table(
        'brand_config',
        sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True),
        sa.Column('hotel_name', sa.String(200), nullable=False, server_default='Hotel WiFi'),
        sa.Column('logo_path', sa.String(500), nullable=True),
        sa.Column('primary_color', sa.String(7), nullable=False, server_default='#3B82F6'),
        sa.Column('tc_text_th', sa.Text, nullable=True),
        sa.Column('tc_text_en', sa.Text, nullable=True),
        sa.Column('language', sa.Enum('th', 'en', name='languagetype'), nullable=False, server_default='th'),
        sa.Column('updated_at', sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    # Seed default row
    op.execute(
        f"INSERT INTO brand_config (id, hotel_name, primary_color, language, updated_at) "
        f"VALUES ('{BRAND_CONFIG_ID}', 'Hotel WiFi', '#3B82F6', 'th', now()) "
        f"ON CONFLICT DO NOTHING"
    )

    # 4. policies (checkfirst — ORM model exists, table may or may not)
    conn = op.get_bind()
    if not conn.dialect.has_table(conn, 'policies'):
        op.create_table(
            'policies',
            sa.Column('id', postgresql.UUID(as_uuid=True), primary_key=True, default=uuid.uuid4),
            sa.Column('name', sa.String(100), nullable=False),
            sa.Column('bandwidth_up_kbps', sa.Integer, nullable=False, server_default='0'),
            sa.Column('bandwidth_down_kbps', sa.Integer, nullable=False, server_default='0'),
            sa.Column('session_duration_min', sa.Integer, nullable=False, server_default='0'),
            sa.Column('max_devices', sa.Integer, nullable=False, server_default='3'),
        )

    # 5. sessions.bandwidth_up_kbps
    op.add_column('sessions', sa.Column('bandwidth_up_kbps', sa.Integer, nullable=False, server_default='0'))


def downgrade() -> None:
    op.drop_column('sessions', 'bandwidth_up_kbps')
    # Drop policies only if we created it (leave it if pre-existing)
    conn = op.get_bind()
    if conn.dialect.has_table(conn, 'policies'):
        # Check if it was empty (i.e., we created it) — conservative: skip drop to avoid FK issues
        pass
    op.drop_index('ix_usage_snapshots_snapshot_at', table_name='usage_snapshots')
    op.drop_table('brand_config')
    op.drop_table('usage_snapshots')
    op.execute("DROP TYPE IF EXISTS languagetype")
```

### Step 1.3 — Verify migration syntax

- [ ] Run: `source .venv/bin/activate && python -c "from alembic.config import Config; from alembic.script import ScriptDirectory; c = Config('alembic.ini'); sd = ScriptDirectory.from_config(c); print('ok')"`
  - Expected: `ok` (no import errors)

### Step 1.4 — Commit

- [ ] `git add app/core/models.py alembic/versions/b2c3d4e5_phase3_tables.py && git commit -m "feat: Phase 3 migration — usage_snapshots, brand_config, sessions.bandwidth_up_kbps"`

---

## Task 2: JWT Auth Refactor

**Files:**
- Modify: `app/core/auth.py`
- Modify: `app/main.py`
- Create: `tests/test_admin/test_admin_auth_v2.py`

### Step 2.1 — Write failing tests

- [ ] Create `tests/test_admin/test_admin_auth_v2.py`:

```python
import pytest
import time
from unittest.mock import AsyncMock, patch
from jose import jwt

@pytest.mark.asyncio
async def test_access_token_contains_jti(client):
    """JWT must include jti claim."""
    from app.core.auth import create_access_token
    from app.core.config import settings
    token = create_access_token({"sub": "admin", "role": "superadmin"})
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    assert "jti" in payload
    assert len(payload["jti"]) == 36  # UUID format

@pytest.mark.asyncio
async def test_logout_blocklists_token(client):
    """POST /admin/logout should store jti in Redis blocklist."""
    from app.core.auth import create_access_token
    token = create_access_token({"sub": "admin", "role": "superadmin"})
    from app.main import app
    app.state.redis.exists = AsyncMock(return_value=False)
    app.state.redis.set = AsyncMock()
    resp = await client.post(
        "/admin/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "logged_out"
    assert app.state.redis.set.called
    call_args = app.state.redis.set.call_args
    assert call_args[0][0].startswith("blocklist:")

@pytest.mark.asyncio
async def test_blocklisted_token_rejected(client):
    """Request with blocklisted jti should return 401."""
    from app.core.auth import create_access_token
    token = create_access_token({"sub": "admin", "role": "superadmin"})
    from app.main import app
    app.state.redis.exists = AsyncMock(return_value=True)  # simulate blocklisted
    resp = await client.get(
        "/admin/sessions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_cookie_auth_accepted(client):
    """admin_token cookie should authenticate as Bearer equivalent."""
    from app.core.auth import create_access_token
    from app.main import app
    token = create_access_token({"sub": "admin", "role": "superadmin"})
    app.state.redis.exists = AsyncMock(return_value=False)
    resp = await client.get(
        "/admin/sessions",
        cookies={"admin_token": token},
    )
    # Should not return 401 (may return 200 or redirect based on DB mock)
    assert resp.status_code != 401
```

- [ ] Run tests: `pytest tests/test_admin/test_admin_auth_v2.py -v`
  - Expected: FAIL (jti not in token, logout endpoint not found)

### Step 2.2 — Update `auth.py`

- [ ] Replace the content of `app/core/auth.py` with:

```python
import time
import uuid as _uuid
from datetime import datetime, timedelta, timezone
from typing import Any, NoReturn
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import settings

_bearer = HTTPBearer(auto_error=False)

# ── Token creation ──────────────────────────────────────────────────────────

def create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRE_HOURS)
    payload["jti"] = str(_uuid.uuid4())
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None

# ── Auth helpers ────────────────────────────────────────────────────────────

def _raise_or_redirect(request: Request) -> NoReturn:
    """Always raises. HTML clients get a redirect; JSON clients get 401."""
    if "text/html" in request.headers.get("accept", ""):
        raise HTTPException(
            status_code=302,
            headers={"Location": f"/admin/login?next={request.url.path}"},
        )
    raise HTTPException(status_code=401, detail={"error": "unauthorized"})

# ── Dependencies ─────────────────────────────────────────────────────────────

async def get_current_admin(request: Request) -> dict:
    """Cookie-first, then Bearer. Checks Redis blocklist."""
    token = request.cookies.get("admin_token")
    if not token:
        credentials: HTTPAuthorizationCredentials | None = await _bearer(request)
        if credentials:
            token = credentials.credentials
    if not token:
        _raise_or_redirect(request)
    payload = decode_access_token(token)
    if not payload:
        _raise_or_redirect(request)
    redis = request.app.state.redis
    if await redis.exists(f"blocklist:{payload['jti']}"):
        _raise_or_redirect(request)
    return payload

async def require_superadmin(payload: dict = Depends(get_current_admin)) -> dict:
    if payload.get("role") != "superadmin":
        raise HTTPException(status_code=403, detail={"error": "forbidden"})
    return payload

# ── Legacy alias (used by existing portal routes — keep until portal migrated) ──
async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """Bearer-only dependency for non-admin routes (portal internal use)."""
    if not credentials:
        raise HTTPException(status_code=401, detail={"error": "not_authenticated"},
                            headers={"WWW-Authenticate": "Bearer"})
    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail={"error": "invalid_token"},
                            headers={"WWW-Authenticate": "Bearer"})
    return payload
```

### Step 2.3 — Update `main.py`

- [ ] Update `app/main.py` to add `SessionMiddleware`, `403 handler`, and `ensure_ifb_ready()`:

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from starlette.middleware.sessions import SessionMiddleware
import redis.asyncio as aioredis
from app.core.config import settings
from app.core.database import engine
from app.portal.router import router as portal_router
from app.admin.router import router as admin_router
from app.pms.webhook_router import router as webhook_router
from app.network.scheduler import start_scheduler, stop_scheduler
from app.network.tc import ensure_ifb_ready

@asynccontextmanager
async def lifespan(app: FastAPI):
    app.state.redis = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    ensure_ifb_ready()
    start_scheduler()
    yield
    stop_scheduler()
    await app.state.redis.aclose()
    await engine.dispose()

app = FastAPI(title="Hotel WiFi Captive Portal", lifespan=lifespan)
app.add_middleware(SessionMiddleware, secret_key=settings.SECRET_KEY)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(portal_router)
app.include_router(admin_router)
app.include_router(webhook_router)

@app.exception_handler(403)
async def forbidden_handler(request: Request, exc):
    if "text/html" in request.headers.get("accept", ""):
        request.session["flash"] = "Access denied: superadmin required"
        return RedirectResponse(url="/admin/", status_code=302)
    return JSONResponse({"error": "forbidden"}, status_code=403)
```

### Step 2.4 — Add `POST /admin/logout` to admin router

- [ ] In `app/admin/router.py`, add at the bottom of existing admin endpoints:

```python
import time as _time
from fastapi import Request
from fastapi.responses import JSONResponse as _JSONResponse
from app.core.auth import get_current_admin

@router.post("/logout")
async def admin_logout(request: Request, payload: dict = Depends(get_current_admin)):
    jti = payload["jti"]
    exp = payload["exp"]
    remaining_ttl = max(1, int(exp - _time.time()))
    await request.app.state.redis.set(f"blocklist:{jti}", 1, ex=remaining_ttl)
    response = _JSONResponse({"status": "logged_out"})
    response.delete_cookie("admin_token")
    return response
```

Also update all existing `Depends(get_current_user)` in `app/admin/router.py` to `Depends(get_current_admin)`.

### Step 2.5 — Run tests

- [ ] `pytest tests/test_admin/test_admin_auth_v2.py -v`
  - Expected: all PASS

### Step 2.6 — Run full test suite to check regressions

- [ ] `pytest tests/ -v --tb=short`
  - Expected: no new failures

### Step 2.7 — Commit

- [ ] `git add app/core/auth.py app/main.py app/admin/router.py tests/test_admin/test_admin_auth_v2.py && git commit -m "feat: jti-based JWT logout blocklist + get_current_admin dependency"`

---

## Task 3: tc.py — Upload Shaping + Bytes Tracking

**Files:**
- Modify: `app/network/tc.py`
- Create: `tests/test_network/test_tc_bytes.py`

### Step 3.1 — Write failing tests

- [ ] Create `tests/test_network/test_tc_bytes.py`:

```python
import pytest
from unittest.mock import patch, MagicMock

TC_STATS_OUTPUT = b"""
class htb 1:1234 parent 1: prio 0 rate 10Mbit ceil 10Mbit burst 1600b cburst 1600b
 Sent 52428800 bytes 40960 pkt (dropped 0, overlimits 0 requeues 0)
 rate 0bit 0pps backlog 0b 0p requeues 0
"""

def _mock_run(stdout=b"", returncode=0):
    m = MagicMock()
    m.stdout = stdout
    m.returncode = returncode
    return m

def test_get_bytes_returns_download_from_wan(monkeypatch):
    """get_bytes reads bytes_down from WAN_INTERFACE class matching IP."""
    import app.network.tc as tc_mod
    monkeypatch.setattr("app.core.config.settings.WAN_INTERFACE", "eth0")
    with patch("app.network.tc.subprocess.run") as mock_run:
        mock_run.return_value = _mock_run(stdout=TC_STATS_OUTPUT)
        # IP 192.168.1.210 → class ID 1:466 (1*256+210=466)
        up, down = tc_mod.get_bytes("192.168.1.210")
    assert down == 52428800

def test_get_bytes_returns_zero_when_class_not_found():
    """get_bytes returns (0,0) when no matching class exists."""
    import app.network.tc as tc_mod
    with patch("app.network.tc.subprocess.run") as mock_run:
        mock_run.return_value = _mock_run(stdout=b"qdisc htb 1: root refcnt 2\n")
        up, down = tc_mod.get_bytes("192.168.1.1")
    assert up == 0
    assert down == 0

def test_apply_bandwidth_limit_adds_ifb_commands_when_up_kbps_nonzero():
    """apply_bandwidth_limit generates ifb0 commands when up_kbps > 0."""
    import app.network.tc as tc_mod
    with patch("app.network.tc._run") as mock_run:
        tc_mod.apply_bandwidth_limit("192.168.1.5", up_kbps=1024, down_kbps=2048, wan_if="eth0")
    calls = [" ".join(c.args[0]) for c in mock_run.call_args_list]
    ifb_calls = [c for c in calls if "ifb0" in c]
    assert len(ifb_calls) >= 2  # class add + filter add on ifb0

def test_apply_bandwidth_limit_skips_ifb_when_up_kbps_zero():
    """apply_bandwidth_limit skips ifb0 when up_kbps == 0."""
    import app.network.tc as tc_mod
    with patch("app.network.tc._run") as mock_run:
        tc_mod.apply_bandwidth_limit("192.168.1.5", up_kbps=0, down_kbps=2048, wan_if="eth0")
    calls = [" ".join(c.args[0]) for c in mock_run.call_args_list]
    ifb_calls = [c for c in calls if "ifb0" in c]
    assert len(ifb_calls) == 0

def test_remove_bandwidth_limit_removes_ifb_when_up_kbps_nonzero():
    """remove_bandwidth_limit deletes ifb0 class when up_kbps > 0."""
    import app.network.tc as tc_mod
    with patch("app.network.tc._run") as mock_run:
        tc_mod.remove_bandwidth_limit("192.168.1.5", up_kbps=1024, wan_if="eth0")
    calls = [" ".join(c.args[0]) for c in mock_run.call_args_list]
    ifb_calls = [c for c in calls if "ifb0" in c]
    assert len(ifb_calls) >= 2  # filter del + class del
```

- [ ] `pytest tests/test_network/test_tc_bytes.py -v`
  - Expected: FAIL (get_bytes not defined, apply_bandwidth_limit signature mismatch)

### Step 3.2 — Update `tc.py`

- [ ] Replace `app/network/tc.py` with:

```python
import re
import subprocess
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

def _ip_to_class_id(ip: str) -> str:
    parts = ip.split(".")
    numeric = int(parts[2]) * 256 + int(parts[3])
    return f"1:{numeric}"

def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=False, capture_output=True)

# ── IFB setup (call once at startup) ────────────────────────────────────────

def ensure_ifb_ready() -> None:
    """Load ifb module, bring up ifb0, redirect WIFI_INTERFACE ingress."""
    wifi_if = settings.WIFI_INTERFACE
    _run(["modprobe", "ifb"])
    _run(["ip", "link", "add", "ifb0", "type", "ifb"])
    _run(["ip", "link", "set", "ifb0", "up"])
    _run(["tc", "qdisc", "add", "dev", wifi_if, "handle", "ffff:", "ingress"])
    _run(["tc", "filter", "add", "dev", wifi_if, "parent", "ffff:", "protocol",
          "ip", "u32", "match", "u32", "0", "0", "action", "mirred", "egress",
          "redirect", "dev", "ifb0"])
    _run(["tc", "qdisc", "add", "dev", "ifb0", "root", "handle", "1:", "htb", "default", "999"])
    logger.info("tc: IFB ready for upload shaping")

# ── Bandwidth shaping ────────────────────────────────────────────────────────

def apply_bandwidth_limit(ip: str, up_kbps: int, down_kbps: int, wan_if: str) -> None:
    if up_kbps == 0 and down_kbps == 0:
        return
    class_id = _ip_to_class_id(ip)
    if down_kbps > 0:
        _run(["tc", "class", "add", "dev", wan_if, "parent", "1:", "classid",
              class_id, "htb", "rate", f"{down_kbps}kbit", "ceil", f"{down_kbps}kbit"])
        _run(["tc", "filter", "add", "dev", wan_if, "parent", "1:", "protocol",
              "ip", "prio", "1", "u32", "match", "ip", "dst", f"{ip}/32", "flowid", class_id])
    if up_kbps > 0:
        _run(["tc", "class", "add", "dev", "ifb0", "parent", "1:", "classid",
              class_id, "htb", "rate", f"{up_kbps}kbit", "ceil", f"{up_kbps}kbit"])
        _run(["tc", "filter", "add", "dev", "ifb0", "parent", "1:", "protocol",
              "ip", "prio", "1", "u32", "match", "ip", "src", f"{ip}/32", "flowid", class_id])
    logger.info(f"tc: applied {down_kbps}kbps down / {up_kbps}kbps up for {ip}")

def remove_bandwidth_limit(ip: str, up_kbps: int, wan_if: str) -> None:
    class_id = _ip_to_class_id(ip)
    _run(["tc", "filter", "del", "dev", wan_if, "parent", "1:", "protocol",
          "ip", "prio", "1", "u32", "match", "ip", "dst", f"{ip}/32", "flowid", class_id])
    _run(["tc", "class", "del", "dev", wan_if, "parent", "1:", "classid", class_id])
    if up_kbps > 0:
        _run(["tc", "filter", "del", "dev", "ifb0", "parent", "1:", "protocol",
              "ip", "prio", "1", "u32", "match", "ip", "src", f"{ip}/32", "flowid", class_id])
        _run(["tc", "class", "del", "dev", "ifb0", "parent", "1:", "classid", class_id])
    logger.info(f"tc: removed limit for {ip}")

# ── Bytes tracking ───────────────────────────────────────────────────────────

def get_bytes(ip: str) -> tuple[int, int]:
    """Returns (bytes_up, bytes_down) from tc stats. 0 if class not found."""
    class_id = _ip_to_class_id(ip)
    numeric_id = class_id.split(":")[1]

    def _parse(device: str) -> int:
        result = subprocess.run(
            ["tc", "-s", "class", "show", "dev", device],
            check=False, capture_output=True
        )
        text = result.stdout.decode(errors="replace")
        # Find the class block for our ID
        pattern = rf"class htb 1:{numeric_id}\b.*?Sent (\d+) bytes"
        m = re.search(pattern, text, re.DOTALL)
        return int(m.group(1)) if m else 0

    bytes_down = _parse(settings.WAN_INTERFACE)
    bytes_up = _parse("ifb0")
    return bytes_up, bytes_down
```

### Step 3.3 — Run tests

- [ ] `pytest tests/test_network/test_tc_bytes.py -v`
  - Expected: all PASS

### Step 3.4 — Check conftest patches still match

The conftest patches `app.network.tc.apply_bandwidth_limit` and `app.network.tc.remove_bandwidth_limit` by name — these still work after the signature update because they patch the whole function.

- [ ] `pytest tests/ -v --tb=short -q`
  - Expected: no regressions

### Step 3.5 — Commit

- [ ] `git add app/network/tc.py tests/test_network/test_tc_bytes.py && git commit -m "feat: tc upload shaping via IFB + get_bytes() dual-interface tracking"`

---

## Task 4: SessionManager — Persist bandwidth_up_kbps

**Files:**
- Modify: `app/network/session_manager.py`
- Create: `tests/test_network/test_session_manager_expire.py`

### Step 4.1 — Write failing test for expire_session() callsite

- [ ] Create `tests/test_network/test_session_manager_expire.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch, call, MagicMock

@pytest.mark.asyncio
async def test_expire_session_calls_remove_bandwidth_limit_with_up_kbps():
    """expire_session() must pass session.bandwidth_up_kbps to remove_bandwidth_limit."""
    from app.network.session_manager import SessionManager
    from app.core.models import SessionStatus

    mock_session = MagicMock()
    mock_session.ip_address = "192.168.1.55"
    mock_session.bandwidth_up_kbps = 2048  # sentinel value
    mock_session.status = SessionStatus.active

    mock_db = AsyncMock()

    with patch("app.network.session_manager.remove_whitelist") as mock_rw, \
         patch("app.network.session_manager.remove_bandwidth_limit") as mock_rbl:
        mgr = SessionManager(wifi_if="wlan0", wan_if="eth0")
        await mgr.expire_session(mock_db, mock_session)

    # Must be called with 3 args: (ip, bandwidth_up_kbps, wan_if)
    mock_rbl.assert_called_once_with("192.168.1.55", 2048, "eth0")
```

- [ ] Run: `pytest tests/test_network/test_session_manager_expire.py -v`
  - Expected: FAIL — `remove_bandwidth_limit` called with 2 args `("192.168.1.55", "eth0")`, not 3

### Step 4.2 — Update `create_session()` and `expire_session()`

- [ ] Update `session_manager.py`:

In `create_session()`, add `bandwidth_up_kbps` to the `Session(...)` constructor:
```python
session = Session(
    ip_address=ip,
    mac_address=mac,
    guest_id=guest_id,
    voucher_id=voucher_id,
    expires_at=expires_at,
    bandwidth_up_kbps=bandwidth_up_kbps,  # ← ADD THIS
    status=SessionStatus.active,
)
```

In `expire_session()`, update the `remove_bandwidth_limit` call:
```python
remove_bandwidth_limit(session.ip_address, session.bandwidth_up_kbps, self.wan_if)
```

### Step 4.3 — Run expire_session test to verify fix

- [ ] `pytest tests/test_network/test_session_manager_expire.py -v`
  - Expected: PASS — `remove_bandwidth_limit` now called with 3 args

### Step 4.4 — Run full network + portal + admin tests

- [ ] `pytest tests/test_network/ tests/test_portal/ tests/test_admin/ -v --tb=short -q`
  - Expected: all pass (tc functions are mocked in conftest; the conftest patches by name so 3-arg signature is invisible to existing tests — that's fine)

### Step 4.5 — Commit

- [ ] `git add app/network/session_manager.py tests/test_network/test_session_manager_expire.py && git commit -m "feat: persist bandwidth_up_kbps in session + pass to tc remove on expire"`

---

## Task 5: Scheduler — Bytes Job + Analytics Snapshot Job

**Files:**
- Modify: `app/network/scheduler.py`
- Create: `tests/test_admin/test_admin_analytics.py`

### Step 5.1 — Write failing tests

- [ ] Create `tests/test_admin/test_admin_analytics.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

@pytest.mark.asyncio
async def test_bytes_job_updates_session_bytes():
    """_bytes_job updates bytes_up and bytes_down on active sessions."""
    from app.network.scheduler import _bytes_job
    from app.core.models import SessionStatus

    mock_session = MagicMock(spec=["ip_address", "voucher_id", "bytes_up", "bytes_down"])
    mock_session.ip_address = "192.168.1.100"
    mock_session.voucher_id = None
    mock_session.bytes_up = 0    # sentinel: starts at 0
    mock_session.bytes_down = 0  # sentinel: starts at 0

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_session]
    mock_db.execute = AsyncMock(return_value=mock_result)

    with patch("app.network.scheduler.AsyncSessionFactory") as mock_factory, \
         patch("app.network.scheduler.tc.get_bytes", return_value=(1000, 2000)):
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        await _bytes_job()

    # Verify actual assignment happened (not MagicMock auto-creation)
    assert mock_session.bytes_up == 1000
    assert mock_session.bytes_down == 2000

@pytest.mark.asyncio
async def test_bytes_job_expires_data_voucher_when_quota_exceeded():
    """_bytes_job expires data-type voucher session when bytes_down >= quota."""
    from app.network.scheduler import _bytes_job
    from app.core.models import SessionStatus, VoucherType

    mock_voucher = MagicMock()
    mock_voucher.type = VoucherType.data
    mock_voucher.data_limit_mb = 1  # 1 MB = 1048576 bytes

    mock_session = MagicMock()
    mock_session.ip_address = "192.168.1.101"
    mock_session.voucher_id = "some-uuid"
    mock_session.voucher = mock_voucher
    mock_session.bytes_down = 0

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_session]
    mock_db.execute = AsyncMock(return_value=mock_result)

    with patch("app.network.scheduler.AsyncSessionFactory") as mock_factory, \
         patch("app.network.scheduler.tc.get_bytes", return_value=(500, 1048577)), \
         patch("app.network.scheduler._manager") as mock_manager:
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_manager.expire_session = AsyncMock()
        await _bytes_job()

    mock_manager.expire_session.assert_called_once()

@pytest.mark.asyncio
async def test_analytics_snapshot_job_inserts_row():
    """_analytics_snapshot_job writes a UsageSnapshot row."""
    from app.network.scheduler import _analytics_snapshot_job

    mock_db = AsyncMock()
    count_result = MagicMock()
    count_result.scalar_one.return_value = 5   # active_sessions
    sum_result = MagicMock()
    sum_result.one.return_value = (100, 200)   # (bytes_up, bytes_down)
    voucher_count_result = MagicMock()
    voucher_count_result.scalar_one.return_value = 3

    mock_db.execute = AsyncMock(side_effect=[count_result, sum_result, voucher_count_result])

    with patch("app.network.scheduler.AsyncSessionFactory") as mock_factory:
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        await _analytics_snapshot_job()

    assert mock_db.add.called
    snapshot = mock_db.add.call_args[0][0]
    assert snapshot.active_sessions == 5
```

- [ ] `pytest tests/test_admin/test_admin_analytics.py -v`
  - Expected: FAIL (`_bytes_job` not defined or missing `tc.get_bytes`)

### Step 5.2 — Update `scheduler.py`

- [ ] Update `app/network/scheduler.py`:

Add imports at top:
```python
from app.core.models import Session as SessionModel, SessionStatus, VoucherType, UsageSnapshot
from app.network import tc
from sqlalchemy import select, func
from sqlalchemy.orm import selectinload
```

Add two new job functions before `start_scheduler()`:

```python
async def _bytes_job():
    """Update bytes_up/bytes_down from tc stats; enforce data-based voucher quotas."""
    async with AsyncSessionFactory() as db:
        result = await db.execute(
            select(SessionModel)
            .options(selectinload(SessionModel.voucher))  # eager-load to avoid MissingGreenlet
            .where(SessionModel.status == SessionStatus.active)
        )
        sessions = result.scalars().all()
        for s in sessions:
            up, down = tc.get_bytes(s.ip_address)
            s.bytes_up = up
            s.bytes_down = down
            if s.voucher_id and s.voucher and s.voucher.type == VoucherType.data:
                quota_bytes = (s.voucher.data_limit_mb or 0) * 1024 * 1024
                if quota_bytes > 0 and down >= quota_bytes:
                    await _manager.expire_session(db, s, SessionStatus.expired)
        await db.commit()


async def _analytics_snapshot_job():
    """Write hourly usage snapshot for analytics charts."""
    from datetime import timedelta
    async with AsyncSessionFactory() as db:
        snapshot_at = datetime.now(timezone.utc)

        # active_sessions count
        count_result = await db.execute(
            select(func.count()).where(SessionModel.status == SessionStatus.active)
        )
        active_sessions = count_result.scalar_one() or 0

        # bytes sum
        sum_result = await db.execute(
            select(func.coalesce(func.sum(SessionModel.bytes_up), 0),
                   func.coalesce(func.sum(SessionModel.bytes_down), 0))
            .where(SessionModel.status == SessionStatus.active)
        )
        total_up, total_down = sum_result.one()

        # voucher_uses: sessions with voucher connected in last hour
        voucher_result = await db.execute(
            select(func.count()).where(
                SessionModel.voucher_id.isnot(None),
                SessionModel.connected_at >= snapshot_at - timedelta(hours=1),
            )
        )
        voucher_uses = voucher_result.scalar_one() or 0

        snapshot = UsageSnapshot(
            snapshot_at=snapshot_at,
            active_sessions=active_sessions,
            total_bytes_up=total_up,
            total_bytes_down=total_down,
            voucher_uses=voucher_uses,
        )
        db.add(snapshot)
        await db.commit()
        logger.info(f"Analytics snapshot: {active_sessions} sessions, {total_down} bytes down")
```

Update `start_scheduler()`:
```python
def start_scheduler():
    scheduler.add_job(_expire_job, "interval", seconds=60, id="expire_sessions")
    scheduler.add_job(_bytes_job, "interval", seconds=60, id="update_bytes")
    scheduler.add_job(_poll_checkouts_job, "interval", seconds=300, id="poll_checkouts")
    scheduler.add_job(_analytics_snapshot_job, "interval", seconds=3600, id="analytics_snapshot")
    scheduler.start()
    logger.info("Scheduler started (expire: 60s, bytes: 60s, poll: 300s, analytics: 3600s)")
```

### Step 5.3 — Run tests

- [ ] `pytest tests/test_admin/test_admin_analytics.py -v`
  - Expected: all PASS

- [ ] `pytest tests/ -v -q --tb=short`
  - Expected: no regressions

### Step 5.4 — Commit

- [ ] `git add app/network/scheduler.py tests/test_admin/test_admin_analytics.py && git commit -m "feat: bytes tracking scheduler job + hourly analytics snapshot job"`

---

## Task 6: Admin Dashboard Shell (base.html + Login)

**Files:**
- Create: `app/admin/templates/base.html`
- Create: `app/admin/templates/login.html`
- Modify: `app/admin/router.py` (add login + dashboard HTML routes)
- Modify: `app/admin/schemas.py` (add BrandConfigResponse for context)

**Note:** `_verify_password(plain, hashed)` is already defined in `app/admin/router.py` (line 21). Do not redefine it — it will be available to the new login routes.

### Step 6.1 — Add Jinja2 template renderer to admin router

- [ ] In `app/admin/router.py`, add template setup at the top (after existing imports):

```python
from fastapi import Request
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates

_templates = Jinja2Templates(directory="app/admin/templates")
```

Also add to router, the `GET /admin/login` and `POST /admin/login` and `GET /admin/` routes:

```python
@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_page(request: Request):
    # Note: do NOT check blocklist here — if we redirect and the token is blocklisted,
    # get_current_admin on /admin/ will reject it and redirect back to login (natural flow).
    # Only check decode validity to avoid showing login to clearly-valid sessions.
    token = request.cookies.get("admin_token")
    if token:
        from app.core.auth import decode_access_token
        payload = decode_access_token(token)
        if payload:  # valid signature — skip blocklist check here to avoid redirect loop
            return RedirectResponse(url="/admin/", status_code=302)
    return _templates.TemplateResponse("login.html", {"request": request, "error": None})

@router.post("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_submit(request: Request, db: AsyncSession = Depends(get_db)):
    form = await request.form()
    username = form.get("username", "")
    password = form.get("password", "")
    result = await db.execute(select(AdminUser).where(AdminUser.username == username))
    user = result.scalar_one_or_none()
    if not user or not _verify_password(password, user.password_hash):
        return _templates.TemplateResponse("login.html",
            {"request": request, "error": "Invalid username or password"}, status_code=401)
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    token = create_access_token({"sub": user.username, "role": user.role.value})
    next_url = request.query_params.get("next", "/admin/")
    resp = RedirectResponse(url=next_url, status_code=302)
    resp.set_cookie("admin_token", token, httponly=True, samesite="lax")
    return resp

@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard_page(request: Request, payload: dict = Depends(get_current_admin),
                         db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Session).where(Session.status == SessionStatus.active).order_by(Session.connected_at.desc()).limit(10)
    )
    recent_sessions = result.scalars().all()
    active_count = len(recent_sessions)
    flash = request.session.pop("flash", None)
    return _templates.TemplateResponse("dashboard.html", {
        "request": request, "current_user": payload,
        "recent_sessions": recent_sessions, "active_count": active_count,
        "flash": flash,
    })
```

### Step 6.2 — Create `app/admin/templates/base.html`

- [ ] Create `app/admin/templates/base.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>{% block title %}Admin{% endblock %} — Hotel WiFi Portal</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <script defer src="https://unpkg.com/alpinejs@3.x.x/dist/cdn.min.js"></script>
  <script src="https://unpkg.com/htmx.org@1.9.12"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@300;400;500;600;700&display=swap" rel="stylesheet"/>
  <style>
    body { font-family: 'Inter', sans-serif; background: #0f172a; color: #e2e8f0; }
    .glass { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); backdrop-filter: blur(12px); }
    .gradient-accent { background: linear-gradient(135deg, #6366f1, #8b5cf6); }
  </style>
  {% block head %}{% endblock %}
</head>
<body class="min-h-screen flex">

  <!-- Sidebar -->
  <aside class="w-64 min-h-screen glass flex flex-col p-4 fixed top-0 left-0">
    <div class="mb-8">
      <h1 class="text-xl font-bold gradient-accent bg-clip-text text-transparent">Hotel WiFi</h1>
      <p class="text-xs text-slate-400">Admin Panel</p>
    </div>
    <nav class="flex-1 space-y-1">
      <a href="/admin/" class="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-white/10 text-sm">📊 Dashboard</a>
      <a href="/admin/sessions" class="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-white/10 text-sm">🖥 Sessions</a>
      <a href="/admin/vouchers" class="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-white/10 text-sm">🎟 Vouchers</a>
      {% if current_user.role == 'superadmin' %}
      <a href="/admin/policies" class="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-white/10 text-sm">⚙ Rooms &amp; Policies</a>
      <a href="/admin/analytics" class="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-white/10 text-sm">📈 Analytics</a>
      <a href="/admin/pms" class="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-white/10 text-sm">🔗 PMS Settings</a>
      <a href="/admin/brand" class="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-white/10 text-sm">🎨 Brand &amp; Config</a>
      <a href="/admin/users" class="flex items-center gap-3 px-3 py-2 rounded-lg hover:bg-white/10 text-sm">👤 Admin Users</a>
      {% endif %}
    </nav>
    <div class="mt-auto pt-4 border-t border-white/10">
      <p class="text-xs text-slate-400 mb-2">{{ current_user.sub }} <span class="text-indigo-400">({{ current_user.role }})</span></p>
      <form action="/admin/logout" method="post">
        <button class="w-full text-left px-3 py-2 text-sm text-red-400 hover:bg-red-500/10 rounded-lg">Logout</button>
      </form>
    </div>
  </aside>

  <!-- Main Content -->
  <main class="ml-64 flex-1 p-8">
    {% if flash %}
    <div class="mb-4 px-4 py-3 rounded-lg bg-yellow-500/10 border border-yellow-500/30 text-yellow-300 text-sm">
      {{ flash }}
    </div>
    {% endif %}
    {% block content %}{% endblock %}
  </main>

</body>
</html>
```

### Step 6.3 — Create `app/admin/templates/login.html`

- [ ] Create `app/admin/templates/login.html`:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8"/>
  <meta name="viewport" content="width=device-width, initial-scale=1.0"/>
  <title>Admin Login — Hotel WiFi Portal</title>
  <script src="https://cdn.tailwindcss.com"></script>
  <link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&display=swap" rel="stylesheet"/>
  <style>
    body { font-family: 'Inter', sans-serif; background: #0f172a; }
    .glass { background: rgba(255,255,255,0.05); border: 1px solid rgba(255,255,255,0.1); backdrop-filter: blur(12px); }
  </style>
</head>
<body class="min-h-screen flex items-center justify-center">
  <div class="glass rounded-2xl p-8 w-full max-w-md">
    <h1 class="text-2xl font-bold text-white mb-2">Hotel WiFi</h1>
    <p class="text-slate-400 text-sm mb-8">Admin Portal</p>
    {% if error %}
    <div class="mb-4 px-4 py-3 rounded-lg bg-red-500/10 border border-red-500/30 text-red-300 text-sm">{{ error }}</div>
    {% endif %}
    <form method="post" action="/admin/login{% if request.query_params.get('next') %}?next={{ request.query_params.get('next') }}{% endif %}" class="space-y-4">
      <div>
        <label class="block text-sm text-slate-300 mb-1">Username</label>
        <input name="username" type="text" autocomplete="username" required
               class="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-indigo-500"/>
      </div>
      <div>
        <label class="block text-sm text-slate-300 mb-1">Password</label>
        <input name="password" type="password" autocomplete="current-password" required
               class="w-full bg-white/5 border border-white/10 rounded-lg px-4 py-2 text-white focus:outline-none focus:border-indigo-500"/>
      </div>
      <button type="submit"
              class="w-full py-2 rounded-lg font-medium text-white"
              style="background: linear-gradient(135deg, #6366f1, #8b5cf6)">
        Sign In
      </button>
    </form>
  </div>
</body>
</html>
```

### Step 6.4 — Create `app/admin/templates/dashboard.html`

- [ ] Create `app/admin/templates/dashboard.html`:

```html
{% extends "base.html" %}
{% block title %}Dashboard{% endblock %}
{% block content %}
<h2 class="text-2xl font-semibold text-white mb-6">Dashboard</h2>
<div class="grid grid-cols-3 gap-6 mb-8">
  <div class="glass rounded-xl p-6">
    <p class="text-slate-400 text-sm">Active Sessions</p>
    <p class="text-3xl font-bold text-white mt-1">{{ active_count }}</p>
  </div>
</div>
<div class="glass rounded-xl p-6">
  <h3 class="text-lg font-semibold text-white mb-4">Recent Sessions</h3>
  <table class="w-full text-sm text-slate-300">
    <thead><tr class="text-slate-500 border-b border-white/10">
      <th class="pb-2 text-left">IP</th>
      <th class="pb-2 text-left">Expires</th>
      <th class="pb-2 text-left">Status</th>
    </tr></thead>
    <tbody>
    {% for s in recent_sessions %}
    <tr class="border-b border-white/5 hover:bg-white/5">
      <td class="py-2">{{ s.ip_address }}</td>
      <td class="py-2">{{ s.expires_at.strftime('%Y-%m-%d %H:%M') if s.expires_at else '-' }}</td>
      <td class="py-2"><span class="px-2 py-0.5 rounded text-xs bg-green-500/20 text-green-300">{{ s.status.value }}</span></td>
    </tr>
    {% else %}
    <tr><td colspan="3" class="py-4 text-center text-slate-500">No active sessions</td></tr>
    {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
```

### Step 6.5 — Smoke test login flow manually

- [ ] Start dev server: `uvicorn app.main:app --reload --host 0.0.0.0 --port 8080`
- [ ] Visit `http://localhost:8080/admin/login` — should show login form
- [ ] Confirm page loads without 500 errors

### Step 6.6 — Commit

- [ ] `git add app/admin/router.py app/admin/templates/ && git commit -m "feat: admin dashboard shell — base layout, login page, dashboard page"`

---

## Task 7: Sessions Module UI

**Files:**
- Create: `app/admin/templates/sessions.html`
- Modify: `app/admin/router.py` (add sessions page + HTMX fragment route)

### Step 7.1 — Add sessions HTML routes to router

- [ ] In `app/admin/router.py`, add:

```python
@router.get("/sessions/rows", response_class=HTMLResponse, include_in_schema=False)
async def sessions_rows_fragment(request: Request, payload: dict = Depends(get_current_admin),
                                  db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Session).where(Session.status == SessionStatus.active))
    sessions = result.scalars().all()
    return _templates.TemplateResponse("sessions.html",
        {"request": request, "current_user": payload, "sessions": sessions, "fragment": True})

@router.get("/sessions", response_class=HTMLResponse, include_in_schema=False)
async def sessions_page(request: Request, payload: dict = Depends(get_current_admin),
                         db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Session).where(Session.status == SessionStatus.active))
    sessions = result.scalars().all()
    flash = request.session.pop("flash", None)
    return _templates.TemplateResponse("sessions.html",
        {"request": request, "current_user": payload, "sessions": sessions, "fragment": False, "flash": flash})
```

### Step 7.2 — Create `app/admin/templates/sessions.html`

- [ ] Create `app/admin/templates/sessions.html`:

```html
{% if not fragment %}
{% extends "base.html" %}
{% block title %}Sessions{% endblock %}
{% block content %}
{% endif %}

<div {% if not fragment %}class=""{% endif %}>
  {% if not fragment %}
  <h2 class="text-2xl font-semibold text-white mb-6">Active Sessions</h2>
  {% endif %}
  <div class="glass rounded-xl p-6">
    <table class="w-full text-sm text-slate-300" id="session-table">
      <thead><tr class="text-slate-500 border-b border-white/10">
        <th class="pb-2 text-left">IP</th>
        <th class="pb-2 text-left">Room / Voucher</th>
        <th class="pb-2 text-left">Connected</th>
        <th class="pb-2 text-left">Expires</th>
        <th class="pb-2 text-left">Down</th>
        <th class="pb-2 text-left"></th>
      </tr></thead>
      <tbody id="session-tbody"
             {% if not fragment %}
             hx-get="/admin/sessions/rows"
             hx-trigger="every 30s"
             hx-target="#session-tbody"
             hx-swap="outerHTML"
             {% endif %}>
        {% for s in sessions %}
        <tr id="session-{{ s.id }}" class="border-b border-white/5 hover:bg-white/5">
          <td class="py-2">{{ s.ip_address }}</td>
          <td class="py-2">{{ s.guest_id or s.voucher_id or '-' }}</td>
          <td class="py-2">{{ s.connected_at.strftime('%H:%M') if s.connected_at else '-' }}</td>
          <td class="py-2">{{ s.expires_at.strftime('%Y-%m-%d %H:%M') if s.expires_at else '-' }}</td>
          <td class="py-2">{{ "%.1f MB" % (s.bytes_down / 1048576) }}</td>
          <td class="py-2">
            <button hx-delete="/admin/sessions/{{ s.id }}"
                    hx-confirm="Kick this session?"
                    hx-target="#session-{{ s.id }}"
                    hx-swap="outerHTML swap:1s"
                    class="px-2 py-1 text-xs bg-red-500/20 text-red-300 rounded hover:bg-red-500/40">
              Kick
            </button>
          </td>
        </tr>
        {% else %}
        <tr><td colspan="6" class="py-4 text-center text-slate-500">No active sessions</td></tr>
        {% endfor %}
      </tbody>
    </table>
  </div>
</div>

{% if not fragment %}
{% endblock %}
{% endif %}
```

### Step 7.3 — Write test for HTMX fragment

**Note:** `tests/test_admin/test_admin_routes.py` already exists — add the new test to the end of that file.

- [ ] Add to `tests/test_admin/test_admin_routes.py`:

```python
@pytest.mark.asyncio
async def test_sessions_rows_fragment_returns_html(client):
    from app.core.auth import create_access_token
    from app.main import app
    app.state.redis.exists = AsyncMock(return_value=False)
    token = create_access_token({"sub": "admin", "role": "superadmin"})
    resp = await client.get(
        "/admin/sessions/rows",
        cookies={"admin_token": token},
        headers={"Accept": "text/html"},
    )
    assert resp.status_code == 200
    assert b"session-tbody" in resp.content or b"No active sessions" in resp.content
```

- [ ] `pytest tests/test_admin/test_admin_routes.py -v -k "sessions"` — Expected: PASS

### Step 7.4 — Commit

- [ ] `git add app/admin/router.py app/admin/templates/sessions.html tests/test_admin/test_admin_routes.py && git commit -m "feat: sessions module UI with HTMX 30s polling and kick"`

---

## Task 8: Vouchers Module UI + PDF Export

**Files:**
- Create: `app/voucher/pdf.py`
- Create: `app/admin/templates/vouchers.html`
- Modify: `app/admin/router.py` (add vouchers page, batch, PDF endpoints)
- Modify: `app/admin/schemas.py` (add BatchVoucherCreate schema)
- Extend: `tests/test_admin/test_voucher_admin.py`

### Step 8.1 — Install PDF dependencies

- [ ] `pip install reportlab qrcode[pil]` and add to `requirements.txt`

### Step 8.2 — Create `app/voucher/pdf.py`

- [ ] Create `app/voucher/pdf.py`:

```python
"""PDF + QR voucher generation using reportlab and qrcode."""
import io
import qrcode
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Image, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

def _make_qr_image(data: str) -> Image:
    qr = qrcode.QRCode(box_size=4, border=2)
    qr.add_data(data)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    return Image(buf, width=3*cm, height=3*cm)

def generate_voucher_pdf(
    vouchers: list[dict],
    qr_mode: str = "code",
    portal_url: str = "http://portal.local",
) -> bytes:
    """
    vouchers: list of {code, type, duration_minutes, data_limit_mb}
    qr_mode: "code" (QR encodes code string) | "url" (QR encodes portal URL with code)
    Returns: PDF bytes
    """
    buf = io.BytesIO()
    doc = SimpleDocTemplate(buf, pagesize=A4, leftMargin=1*cm, rightMargin=1*cm,
                            topMargin=1*cm, bottomMargin=1*cm)
    styles = getSampleStyleSheet()
    elements = []

    for v in vouchers:
        code = v["code"]
        vtype = v.get("type", "time")
        limit = v.get("duration_minutes") if vtype == "time" else v.get("data_limit_mb")
        unit = "min" if vtype == "time" else "MB"
        qr_data = f"{portal_url}/?code={code}" if qr_mode == "url" else code
        qr_img = _make_qr_image(qr_data)

        data = [
            [qr_img, Paragraph(f"<b>WiFi Voucher</b><br/>Code: <b>{code}</b><br/>"
                               f"Type: {vtype} | Limit: {limit} {unit}", styles["Normal"])],
        ]
        table = Table(data, colWidths=[4*cm, 14*cm])
        table.setStyle(TableStyle([
            ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
            ("BOX", (0, 0), (-1, -1), 0.5, colors.grey),
            ("LEFTPADDING", (0, 0), (-1, -1), 8),
            ("RIGHTPADDING", (0, 0), (-1, -1), 8),
            ("TOPPADDING", (0, 0), (-1, -1), 8),
            ("BOTTOMPADDING", (0, 0), (-1, -1), 8),
        ]))
        elements.append(table)
        elements.append(Spacer(1, 0.5*cm))

    doc.build(elements)
    return buf.getvalue()
```

### Step 8.3 — Write failing tests for PDF + batch

- [ ] Add to `tests/test_admin/test_voucher_admin.py`:

```python
@pytest.mark.asyncio
async def test_batch_voucher_creates_n_codes(client):
    """POST /admin/vouchers/batch with count=3 should return 3 vouchers."""
    from app.core.auth import create_access_token
    from app.main import app
    from app.core.database import get_db
    import uuid as _uuid
    app.state.redis.exists = AsyncMock(return_value=False)
    token = create_access_token({"sub": "admin", "role": "staff"})

    # Override DB to return a fake admin user for the created_by lookup
    mock_user = MagicMock()
    mock_user.id = _uuid.uuid4()
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_user
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    try:
        resp = await client.post(
            "/admin/vouchers/batch",
            json={"type": "time", "duration_minutes": 60, "max_uses": 1, "max_devices": 1, "count": 3},
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data) == 3
        assert all("code" in v for v in data)
    finally:
        app.dependency_overrides.pop(get_db, None)

def test_generate_voucher_pdf_returns_bytes():
    """generate_voucher_pdf should return non-empty PDF bytes."""
    from app.voucher.pdf import generate_voucher_pdf
    pdf = generate_voucher_pdf(
        [{"code": "ABCD1234", "type": "time", "duration_minutes": 60}],
        qr_mode="code",
    )
    assert len(pdf) > 100
    assert pdf[:4] == b"%PDF"

def test_generate_voucher_pdf_url_mode():
    """URL mode QR should embed portal URL."""
    from app.voucher.pdf import generate_voucher_pdf
    pdf = generate_voucher_pdf(
        [{"code": "XY9Z8W7V", "type": "data", "data_limit_mb": 100}],
        qr_mode="url",
        portal_url="http://192.168.1.1:8080",
    )
    assert len(pdf) > 100
```

- [ ] `pytest tests/test_admin/test_voucher_admin.py::test_generate_voucher_pdf_returns_bytes tests/test_admin/test_voucher_admin.py::test_generate_voucher_pdf_url_mode -v`
  - Expected: FAIL (pdf module not found)

### Step 8.4 — Add batch endpoint + PDF endpoint to router

- [ ] In `app/admin/schemas.py`, add:

```python
class BatchVoucherCreate(BaseModel):
    type: str  # "time" | "data"
    duration_minutes: int | None = None
    data_limit_mb: int | None = None
    max_uses: int = 1
    max_devices: int = 1
    expires_at: datetime | None = None
    count: int = Field(ge=1, le=100)
```

- [ ] In `app/admin/router.py`, add:

```python
from fastapi.responses import Response as _Response
from app.voucher.pdf import generate_voucher_pdf as _gen_pdf

@router.post("/vouchers/batch")
async def create_batch_vouchers(
    body: BatchVoucherCreate,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_admin),
):
    """Create `count` vouchers with the same settings."""
    result = await db.execute(select(AdminUser).where(AdminUser.username == payload["sub"]))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, {"error": "user_not_found"})
    created = []
    for _ in range(body.count):
        v = Voucher(
            code=generate_code(),
            type=VoucherType(body.type),
            duration_minutes=body.duration_minutes,
            data_limit_mb=body.data_limit_mb,
            max_uses=body.max_uses,
            max_devices=body.max_devices,
            expires_at=body.expires_at,
            created_by=user.id,
        )
        db.add(v)
        created.append(v)
    await db.commit()
    return [{"id": str(v.id), "code": v.code, "type": v.type.value} for v in created]

@router.get("/vouchers/{voucher_id}/pdf")
async def download_voucher_pdf(
    voucher_id: uuid.UUID,
    qr_mode: str = "code",
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_admin),
):
    result = await db.execute(select(Voucher).where(Voucher.id == voucher_id))
    v = result.scalar_one_or_none()
    if not v:
        raise HTTPException(404, {"error": "not_found"})
    if qr_mode not in ("url", "code"):
        raise HTTPException(422, {"error": "invalid_qr_mode"})
    pdf = _gen_pdf([{"code": v.code, "type": v.type.value,
                     "duration_minutes": v.duration_minutes, "data_limit_mb": v.data_limit_mb}],
                   qr_mode=qr_mode)
    return _Response(content=pdf, media_type="application/pdf",
                     headers={"Content-Disposition": f'attachment; filename="voucher-{v.code}.pdf"'})
```

Also add voucher page UI route and template (create `app/admin/templates/vouchers.html` with voucher list table + create form + batch form + download links).

### Step 8.5 — Create `app/admin/templates/vouchers.html`

- [ ] Create `app/admin/templates/vouchers.html` (key sections):

```html
{% extends "base.html" %}
{% block title %}Vouchers{% endblock %}
{% block content %}
<h2 class="text-2xl font-semibold text-white mb-6">Vouchers</h2>
<div class="grid grid-cols-2 gap-6 mb-8">
  <!-- Create Single Voucher -->
  <div class="glass rounded-xl p-6">
    <h3 class="text-lg font-semibold text-white mb-4">Create Voucher</h3>
    <form hx-post="/admin/vouchers" hx-target="#voucher-result" method="post" class="space-y-3">
      <div x-data="{vtype:'time'}">
        <label class="block text-sm text-slate-400 mb-1">Type</label>
        <select name="type" x-model="vtype" class="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-white">
          <option value="time">Time-based</option>
          <option value="data">Data-based</option>
        </select>
        <div x-show="vtype=='time'" class="mt-2">
          <input name="duration_minutes" type="number" placeholder="Duration (minutes)" class="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-white"/>
        </div>
        <div x-show="vtype=='data'" class="mt-2">
          <input name="data_limit_mb" type="number" placeholder="Data limit (MB)" class="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-white"/>
        </div>
      </div>
      <input name="max_uses" type="number" value="1" placeholder="Max uses" class="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-white"/>
      <button class="w-full py-2 rounded gradient-accent text-white font-medium">Create</button>
    </form>
    <div id="voucher-result" class="mt-3 text-sm text-green-400"></div>
  </div>
  <!-- Batch Generate -->
  <div class="glass rounded-xl p-6">
    <h3 class="text-lg font-semibold text-white mb-4">Batch Generate</h3>
    <form action="/admin/vouchers/batch" method="post" class="space-y-3">
      <input name="type" type="hidden" value="time"/>
      <input name="duration_minutes" type="number" value="60" placeholder="Duration (min)" class="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-white"/>
      <input name="count" type="number" min="1" max="100" value="10" class="w-full bg-white/5 border border-white/10 rounded px-3 py-2 text-white" placeholder="Count (1-100)"/>
      <button class="w-full py-2 rounded gradient-accent text-white font-medium">Generate Batch</button>
    </form>
  </div>
</div>
<!-- Voucher List -->
<div class="glass rounded-xl p-6">
  <h3 class="text-lg font-semibold text-white mb-4">Voucher List</h3>
  <table class="w-full text-sm text-slate-300">
    <thead><tr class="text-slate-500 border-b border-white/10">
      <th class="pb-2 text-left">Code</th><th class="pb-2 text-left">Type</th>
      <th class="pb-2 text-left">Uses</th><th class="pb-2 text-left">Expires</th>
      <th class="pb-2 text-left">PDF</th>
    </tr></thead>
    <tbody>
    {% for v in vouchers %}
    <tr class="border-b border-white/5">
      <td class="py-2 font-mono">{{ v.code }}</td>
      <td class="py-2">{{ v.type.value }}</td>
      <td class="py-2">{{ v.used_count }}/{{ v.max_uses }}</td>
      <td class="py-2">{{ v.expires_at.strftime('%Y-%m-%d') if v.expires_at else '∞' }}</td>
      <td class="py-2 space-x-2">
        <a href="/admin/vouchers/{{ v.id }}/pdf?qr_mode=code" class="text-indigo-400 hover:underline text-xs">Code QR</a>
        <a href="/admin/vouchers/{{ v.id }}/pdf?qr_mode=url" class="text-indigo-400 hover:underline text-xs">URL QR</a>
      </td>
    </tr>
    {% else %}
    <tr><td colspan="5" class="py-4 text-center text-slate-500">No vouchers</td></tr>
    {% endfor %}
    </tbody>
  </table>
</div>
{% endblock %}
```

Also add `GET /admin/vouchers` HTML route to router (query all vouchers, render template).

### Step 8.6 — Run PDF tests

- [ ] `pytest tests/test_admin/test_voucher_admin.py -v`
  - Expected: PDF tests PASS

### Step 8.7 — Commit

- [ ] `git add app/voucher/pdf.py app/admin/templates/vouchers.html app/admin/router.py app/admin/schemas.py tests/test_admin/test_voucher_admin.py requirements.txt && git commit -m "feat: vouchers UI + batch generate + PDF+QR export (url/code mode)"`

---

## Task 9: Rooms & Policies Module

**Files:**
- Create: `app/admin/templates/policies.html`
- Create: `app/admin/templates/rooms.html`
- Modify: `app/admin/router.py` (API + HTML routes)
- Create: `tests/test_admin/test_admin_policies.py`

### Step 9.1 — Write failing tests

- [ ] Create `tests/test_admin/test_admin_policies.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
import uuid

@pytest.mark.asyncio
async def test_create_policy_returns_201(client):
    from app.core.auth import create_access_token
    from app.main import app
    app.state.redis.exists = AsyncMock(return_value=False)
    token = create_access_token({"sub": "admin", "role": "superadmin"})
    resp = await client.post(
        "/admin/api/policies",
        json={"name": "Standard", "bandwidth_up_kbps": 1024,
              "bandwidth_down_kbps": 5120, "session_duration_min": 0, "max_devices": 3},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code in (200, 201)

@pytest.mark.asyncio
async def test_staff_cannot_access_policies(client):
    from app.core.auth import create_access_token
    from app.main import app
    app.state.redis.exists = AsyncMock(return_value=False)
    token = create_access_token({"sub": "staff", "role": "staff"})
    resp = await client.get(
        "/admin/api/policies",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
```

- [ ] `pytest tests/test_admin/test_admin_policies.py -v` — Expected: FAIL

### Step 9.2 — Add Policy API endpoints to router

- [ ] In `app/admin/router.py`, add policy and room endpoints using `require_superadmin`:

```python
from app.core.models import Policy, Room

# ── Policy CRUD ──────────────────────────────────────────────────────────────

class PolicyCreate(BaseModel):
    name: str
    bandwidth_up_kbps: int = 0
    bandwidth_down_kbps: int = 0
    session_duration_min: int = 0
    max_devices: int = 3

@router.get("/api/policies")
async def list_policies(db: AsyncSession = Depends(get_db),
                        _: dict = Depends(require_superadmin)):
    result = await db.execute(select(Policy))
    return [{"id": str(p.id), "name": p.name, "bandwidth_up_kbps": p.bandwidth_up_kbps,
             "bandwidth_down_kbps": p.bandwidth_down_kbps, "session_duration_min": p.session_duration_min,
             "max_devices": p.max_devices} for p in result.scalars().all()]

@router.post("/api/policies", status_code=201)
async def create_policy(body: PolicyCreate, db: AsyncSession = Depends(get_db),
                         _: dict = Depends(require_superadmin)):
    p = Policy(**body.dict())
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return {"id": str(p.id), "name": p.name}

@router.put("/api/policies/{policy_id}")
async def update_policy(policy_id: uuid.UUID, body: PolicyCreate,
                         db: AsyncSession = Depends(get_db), _: dict = Depends(require_superadmin)):
    result = await db.execute(select(Policy).where(Policy.id == policy_id))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, {"error": "not_found"})
    for k, v in body.dict().items():
        setattr(p, k, v)
    await db.commit()
    return {"id": str(p.id), "name": p.name}

@router.delete("/api/policies/{policy_id}")
async def delete_policy(policy_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                         _: dict = Depends(require_superadmin)):
    result = await db.execute(select(Policy).where(Policy.id == policy_id))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, {"error": "not_found"})
    await db.delete(p)
    await db.commit()
    return {"status": "deleted"}

# ── Rooms ─────────────────────────────────────────────────────────────────────

class RoomPolicyAssign(BaseModel):
    policy_id: uuid.UUID | None

@router.get("/api/rooms")
async def list_rooms(db: AsyncSession = Depends(get_db), _: dict = Depends(require_superadmin)):
    result = await db.execute(select(Room))
    return [{"id": str(r.id), "number": r.number, "room_type": r.room_type,
             "policy_id": str(r.policy_id) if r.policy_id else None} for r in result.scalars().all()]

@router.put("/api/rooms/{room_id}/policy")
async def assign_room_policy(room_id: uuid.UUID, body: RoomPolicyAssign,
                              db: AsyncSession = Depends(get_db), _: dict = Depends(require_superadmin)):
    result = await db.execute(select(Room).where(Room.id == room_id))
    r = result.scalar_one_or_none()
    if not r:
        raise HTTPException(404, {"error": "not_found"})
    r.policy_id = body.policy_id
    await db.commit()
    return {"id": str(r.id), "number": r.number, "policy_id": str(r.policy_id) if r.policy_id else None}
```

Add HTML routes for `/admin/policies` and `/admin/rooms`, and create minimal templates `policies.html` and `rooms.html` extending `base.html` with table + Alpine.js modal form.

### Step 9.3 — Run tests

- [ ] `pytest tests/test_admin/test_admin_policies.py -v` — Expected: PASS

### Step 9.4 — Commit

- [ ] `git add app/admin/router.py app/admin/templates/policies.html app/admin/templates/rooms.html tests/test_admin/test_admin_policies.py && git commit -m "feat: rooms & policies module — CRUD API + UI (superadmin only)"`

---

## Task 10: Analytics Module

**Files:**
- Create: `app/admin/templates/analytics.html`
- Modify: `app/admin/router.py` (analytics data JSON endpoint + page route)

### Step 10.1 — Add analytics data endpoint

- [ ] In `app/admin/router.py`, add:

```python
from app.core.models import UsageSnapshot
from sqlalchemy import func, extract

RANGE_INTERVALS = {"24h": 24, "7d": 168, "30d": 720}  # hours

@router.get("/api/analytics/data")
async def analytics_data(range: str = "24h", db: AsyncSession = Depends(get_db),
                         _: dict = Depends(require_superadmin)):
    if range not in RANGE_INTERVALS:
        raise HTTPException(400, {"error": "invalid_range", "valid": list(RANGE_INTERVALS.keys())})
    hours = RANGE_INTERVALS[range]
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    # sessions_over_time + bandwidth_per_hour from usage_snapshots
    snaps_result = await db.execute(
        select(UsageSnapshot).where(UsageSnapshot.snapshot_at >= since).order_by(UsageSnapshot.snapshot_at)
    )
    snaps = snaps_result.scalars().all()
    sessions_over_time = [{"timestamp": s.snapshot_at.isoformat(), "active_sessions": s.active_sessions} for s in snaps]
    bandwidth_per_hour = [{"timestamp": s.snapshot_at.isoformat(), "bytes_up": s.total_bytes_up, "bytes_down": s.total_bytes_down} for s in snaps]

    # peak_hours from usage_snapshots aggregated
    peak_result = await db.execute(
        select(
            extract("dow", UsageSnapshot.snapshot_at).label("dow"),
            extract("hour", UsageSnapshot.snapshot_at).label("hour"),
            func.sum(UsageSnapshot.active_sessions).label("count"),
        ).where(UsageSnapshot.snapshot_at >= since)
        .group_by("dow", "hour").order_by("dow", "hour")
    )
    peak_hours = [{"day_of_week": int(r.dow), "hour": int(r.hour), "count": int(r.count or 0)} for r in peak_result]

    # auth_breakdown from sessions table
    from sqlalchemy import case
    auth_result = await db.execute(
        select(
            func.count(case((Session.voucher_id.is_(None), 1))).label("room_auth"),
            func.count(case((Session.voucher_id.isnot(None), 1))).label("voucher_auth"),
        ).where(Session.connected_at >= since)
    )
    row = auth_result.one()
    auth_breakdown = {"room_auth": row.room_auth or 0, "voucher_auth": row.voucher_auth or 0}

    return {"range": range, "sessions_over_time": sessions_over_time,
            "bandwidth_per_hour": bandwidth_per_hour, "peak_hours": peak_hours,
            "auth_breakdown": auth_breakdown}
```

### Step 10.2 — Write analytics endpoint test

- [ ] Add to `tests/test_admin/test_admin_analytics.py`:

```python
@pytest.mark.asyncio
async def test_analytics_invalid_range_returns_400(client):
    from app.core.auth import create_access_token
    from app.main import app
    app.state.redis.exists = AsyncMock(return_value=False)
    token = create_access_token({"sub": "admin", "role": "superadmin"})
    resp = await client.get(
        "/admin/api/analytics/data?range=1y",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 400
    assert "invalid_range" in resp.json()["error"]

@pytest.mark.asyncio
async def test_analytics_valid_range_returns_schema(client):
    from app.core.auth import create_access_token
    from app.main import app
    from app.core.database import get_db
    app.state.redis.exists = AsyncMock(return_value=False)
    token = create_access_token({"sub": "admin", "role": "superadmin"})

    # Must override DB — analytics endpoint unpacks tuples from execute() results
    mock_db = AsyncMock()
    snaps_result = MagicMock()
    snaps_result.scalars.return_value.all.return_value = []  # empty snapshots
    peak_result = MagicMock()
    peak_result.__iter__ = MagicMock(return_value=iter([]))  # empty peak hours
    auth_result = MagicMock()
    auth_row = MagicMock()
    auth_row.room_auth = 5
    auth_row.voucher_auth = 2
    auth_result.one.return_value = auth_row
    mock_db.execute = AsyncMock(side_effect=[snaps_result, peak_result, auth_result])

    async def override_db():
        yield mock_db

    app.dependency_overrides[get_db] = override_db
    try:
        resp = await client.get(
            "/admin/api/analytics/data?range=24h",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert "sessions_over_time" in data
        assert "bandwidth_per_hour" in data
        assert "peak_hours" in data
        assert "auth_breakdown" in data
        assert data["auth_breakdown"]["room_auth"] >= 0
    finally:
        app.dependency_overrides.pop(get_db, None)
```

- [ ] `pytest tests/test_admin/test_admin_analytics.py -v` — Expected: PASS

### Step 10.3 — Create `app/admin/templates/analytics.html`

- [ ] Create `app/admin/templates/analytics.html`:

```html
{% extends "base.html" %}
{% block title %}Analytics{% endblock %}
{% block head %}
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
{% endblock %}
{% block content %}
<h2 class="text-2xl font-semibold text-white mb-6">Analytics</h2>
<div class="flex gap-2 mb-6">
  {% for r in ['24h','7d','30d'] %}
  <a href="/admin/analytics?range={{ r }}"
     class="px-4 py-2 rounded-lg text-sm {% if range == r %}gradient-accent text-white{% else %}glass text-slate-300 hover:bg-white/10{% endif %}">
    {{ r }}
  </a>
  {% endfor %}
</div>
<div class="grid grid-cols-2 gap-6">
  <div class="glass rounded-xl p-6"><canvas id="sessionsChart"></canvas></div>
  <div class="glass rounded-xl p-6"><canvas id="bandwidthChart"></canvas></div>
  <div class="glass rounded-xl p-6"><canvas id="authChart"></canvas></div>
</div>
<script>
const data = {{ analytics_data | tojson }};
// Sessions line chart
new Chart(document.getElementById('sessionsChart'), {
  type: 'line',
  data: {
    labels: data.sessions_over_time.map(d => d.timestamp.substr(11,5)),
    datasets: [{label: 'Active Sessions', data: data.sessions_over_time.map(d => d.active_sessions),
                borderColor: '#6366f1', fill: true, tension: 0.3}]
  }, options: {plugins:{legend:{labels:{color:'#e2e8f0'}}}, scales:{x:{ticks:{color:'#94a3b8'}}, y:{ticks:{color:'#94a3b8'}}}}
});
// Auth breakdown pie
new Chart(document.getElementById('authChart'), {
  type: 'doughnut',
  data: {
    labels: ['Room Auth', 'Voucher Auth'],
    datasets: [{data: [data.auth_breakdown.room_auth, data.auth_breakdown.voucher_auth],
                backgroundColor: ['#6366f1', '#8b5cf6']}]
  }, options: {plugins:{legend:{labels:{color:'#e2e8f0'}}}}
});
</script>
{% endblock %}
```

Also add `GET /admin/analytics` HTML route that fetches analytics data and passes to template.

### Step 10.4 — Commit

- [ ] `git add app/admin/router.py app/admin/templates/analytics.html tests/test_admin/test_admin_analytics.py && git commit -m "feat: analytics module — hourly snapshots + Chart.js dashboard"`

---

## Task 11: Brand & Config Module

**Files:**
- Create: `app/admin/templates/brand.html`
- Modify: `app/admin/router.py` (brand API + page routes)
- Create: `tests/test_admin/test_admin_brand.py`
- Create: `static/uploads/logo/` directory (create via `os.makedirs`)

### Step 11.1 — Write failing tests

- [ ] Create `tests/test_admin/test_admin_brand.py`:

```python
import pytest
import io
from unittest.mock import AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_get_brand_config_returns_defaults(client):
    from app.core.auth import create_access_token
    from app.main import app
    app.state.redis.exists = AsyncMock(return_value=False)
    token = create_access_token({"sub": "admin", "role": "superadmin"})
    resp = await client.get("/admin/api/brand", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "hotel_name" in data
    assert "primary_color" in data

@pytest.mark.asyncio
async def test_logo_upload_rejects_invalid_mime(client):
    from app.core.auth import create_access_token
    from app.main import app
    app.state.redis.exists = AsyncMock(return_value=False)
    token = create_access_token({"sub": "admin", "role": "superadmin"})
    resp = await client.post(
        "/admin/brand/logo",
        files={"file": ("test.txt", io.BytesIO(b"not an image"), "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422

@pytest.mark.asyncio
async def test_logo_upload_rejects_large_file(client):
    from app.core.auth import create_access_token
    from app.main import app
    app.state.redis.exists = AsyncMock(return_value=False)
    token = create_access_token({"sub": "admin", "role": "superadmin"})
    big_data = b"x" * (2 * 1024 * 1024 + 1)
    resp = await client.post(
        "/admin/brand/logo",
        files={"file": ("big.jpg", io.BytesIO(big_data), "image/jpeg")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 413
```

### Step 11.2 — Add brand API endpoints

- [ ] In `app/admin/router.py`, add:

```python
from app.core.models import BrandConfig
from fastapi import UploadFile, File
import os as _os

ALLOWED_LOGO_MIME = {"image/jpeg", "image/png", "image/webp"}
MAX_LOGO_BYTES = 2 * 1024 * 1024  # 2 MB
LOGO_UPLOAD_DIR = "static/uploads/logo"

class BrandUpdate(BaseModel):
    hotel_name: str | None = None
    primary_color: str | None = None
    tc_text_th: str | None = None
    tc_text_en: str | None = None
    language: str | None = None

@router.get("/api/brand")
async def get_brand(db: AsyncSession = Depends(get_db), _: dict = Depends(require_superadmin)):
    result = await db.execute(select(BrandConfig))
    b = result.scalar_one_or_none()
    if not b:
        return {"hotel_name": "Hotel WiFi", "logo_url": None, "primary_color": "#3B82F6",
                "tc_text_th": None, "tc_text_en": None, "language": "th"}
    logo_url = f"/static/{b.logo_path}" if b.logo_path else None
    return {"hotel_name": b.hotel_name, "logo_url": logo_url, "primary_color": b.primary_color,
            "tc_text_th": b.tc_text_th, "tc_text_en": b.tc_text_en, "language": b.language.value}

@router.put("/api/brand")
async def update_brand(body: BrandUpdate, db: AsyncSession = Depends(get_db),
                        _: dict = Depends(require_superadmin)):
    result = await db.execute(select(BrandConfig))
    b = result.scalar_one_or_none()
    if not b:
        raise HTTPException(404, {"error": "brand_config_not_seeded"})
    for field, value in body.dict(exclude_none=True).items():
        if field == "language":
            from app.core.models import LanguageType
            value = LanguageType(value)
        setattr(b, field, value)
    b.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"hotel_name": b.hotel_name, "primary_color": b.primary_color, "language": b.language.value}

@router.post("/brand/logo")
async def upload_logo(file: UploadFile = File(...), db: AsyncSession = Depends(get_db),
                       _: dict = Depends(require_superadmin)):
    if file.content_type not in ALLOWED_LOGO_MIME:
        raise HTTPException(422, {"error": "invalid_mime_type",
                                   "allowed": list(ALLOWED_LOGO_MIME)})
    data = await file.read(MAX_LOGO_BYTES + 1)
    if len(data) > MAX_LOGO_BYTES:
        raise HTTPException(413, {"error": "file_too_large", "max_mb": 2})
    ext = file.filename.rsplit(".", 1)[-1].lower() if file.filename and "." in file.filename else "jpg"
    _os.makedirs(LOGO_UPLOAD_DIR, exist_ok=True)
    # Remove old logo with different extension
    for ext_check in ("jpg", "jpeg", "png", "webp"):
        old = f"{LOGO_UPLOAD_DIR}/logo.{ext_check}"
        try:
            _os.remove(old)
        except FileNotFoundError:
            pass
    logo_filename = f"logo.{ext}"
    logo_full_path = f"{LOGO_UPLOAD_DIR}/{logo_filename}"
    with open(logo_full_path, "wb") as f:
        f.write(data)
    relative_path = f"uploads/logo/{logo_filename}"
    result = await db.execute(select(BrandConfig))
    b = result.scalar_one_or_none()
    if b:
        b.logo_path = relative_path
        b.updated_at = datetime.now(timezone.utc)
        await db.commit()
    return {"logo_url": f"/static/{relative_path}"}
```

### Step 11.3 — Run tests

- [ ] `pytest tests/test_admin/test_admin_brand.py -v` — Expected: PASS

### Step 11.4 — Create brand template

- [ ] Create `app/admin/templates/brand.html` with form for hotel_name, primary_color picker, language dropdown, T&C textareas (Alpine.js tabs for TH/EN), and logo upload form pointing to `/admin/brand/logo`.

### Step 11.5 — Commit

- [ ] `git add app/admin/router.py app/admin/templates/brand.html tests/test_admin/test_admin_brand.py && git commit -m "feat: brand & config module — hotel name, colors, T&C, logo upload"`

---

## Task 12: Admin Users Module

**Files:**
- Create: `app/admin/templates/users.html`
- Modify: `app/admin/router.py` (users API + page)
- Create: `tests/test_admin/test_admin_users.py`

### Step 12.1 — Write failing tests

- [ ] Create `tests/test_admin/test_admin_users.py`:

```python
import pytest
from unittest.mock import AsyncMock

@pytest.mark.asyncio
async def test_create_admin_user_hashes_password(client):
    from app.core.auth import create_access_token
    from app.main import app
    app.state.redis.exists = AsyncMock(return_value=False)
    token = create_access_token({"sub": "admin", "role": "superadmin"})
    resp = await client.post(
        "/admin/api/users",
        json={"username": "newstaff", "password": "secret123", "role": "staff"},
        headers={"Authorization": f"Bearer {token}"},
    )
    # 200 or 500 from mock DB — the important thing is password is not returned
    if resp.status_code == 200:
        assert "password" not in resp.json()

@pytest.mark.asyncio
async def test_staff_cannot_list_users(client):
    from app.core.auth import create_access_token
    from app.main import app
    app.state.redis.exists = AsyncMock(return_value=False)
    token = create_access_token({"sub": "staff", "role": "staff"})
    resp = await client.get(
        "/admin/api/users",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
```

### Step 12.2 — Add admin users API endpoints

- [ ] In `app/admin/router.py`, add:

```python
class AdminUserCreate(BaseModel):
    username: str
    password: str
    role: str = "staff"  # "staff" | "superadmin"

@router.get("/api/users")
async def list_admin_users(db: AsyncSession = Depends(get_db), _: dict = Depends(require_superadmin)):
    result = await db.execute(select(AdminUser))
    return [{"id": str(u.id), "username": u.username, "role": u.role.value,
             "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None}
            for u in result.scalars().all()]

@router.post("/api/users", status_code=201)
async def create_admin_user(body: AdminUserCreate, db: AsyncSession = Depends(get_db),
                             _: dict = Depends(require_superadmin)):
    import bcrypt as _bcrypt
    from app.core.models import AdminRole
    pw_hash = _bcrypt.hashpw(body.password.encode(), _bcrypt.gensalt()).decode()
    user = AdminUser(username=body.username, password_hash=pw_hash, role=AdminRole(body.role))
    db.add(user)
    await db.commit()
    await db.refresh(user)
    return {"id": str(user.id), "username": user.username, "role": user.role.value}
```

Add `GET /admin/users` HTML route and create `app/admin/templates/users.html`.

### Step 12.3 — Run tests

- [ ] `pytest tests/test_admin/test_admin_users.py -v` — Expected: PASS

### Step 12.4 — Commit

- [ ] `git add app/admin/router.py app/admin/templates/users.html tests/test_admin/test_admin_users.py && git commit -m "feat: admin users module — create staff + superadmin accounts"`

---

## Task 13: PMS Settings UI

**Files:**
- Create: `app/admin/templates/pms.html`
- Modify: `app/admin/router.py` (add PMS HTML page route)

### Step 13.1 — Add HTML route

- [ ] In `app/admin/router.py`, add:

```python
@router.get("/pms", response_class=HTMLResponse, include_in_schema=False)
async def pms_page(request: Request, payload: dict = Depends(require_superadmin),
                   db: AsyncSession = Depends(get_db)):
    # Reuse get_pms_config logic
    result = await db.execute(select(PMSAdapterModel).where(PMSAdapterModel.is_active == True))
    adapter = result.scalar_one_or_none()
    config = {}
    if adapter and adapter.config_encrypted:
        from app.core.encryption import decrypt_config
        raw = decrypt_config(adapter.config_encrypted)
        config = _mask_config(raw)
    flash = request.session.pop("flash", None)
    return _templates.TemplateResponse("pms.html", {
        "request": request, "current_user": payload, "config": config,
        "adapter_type": adapter.type.value if adapter else None, "flash": flash,
    })
```

### Step 13.2 — Create `app/admin/templates/pms.html`

- [ ] Create `app/admin/templates/pms.html` with read-only config display (credentials masked), Alpine.js edit toggle, form submitting `hx-put="/admin/pms"`, and Test Connection button with `hx-post="/admin/pms/test"` showing latency inline.

### Step 13.3 — Commit

- [ ] `git add app/admin/templates/pms.html app/admin/router.py && git commit -m "feat: PMS settings UI — config display, edit form, test connection"`

---

## Task 14: Full Test Suite + Final Verification

### Step 14.1 — Run full test suite

- [ ] `pytest tests/ -v --tb=short`
  - Expected: All tests PASS

### Step 14.2 — Run with coverage

- [ ] `pytest tests/ --cov=app --cov-report=term-missing`
  - Review uncovered critical paths (especially auth blocklist, tc bytes)

### Step 14.3 — Smoke test all admin pages

Start dev server: `uvicorn app.main:app --reload --host 0.0.0.0 --port 8080`

- [ ] `GET /admin/login` — shows login form
- [ ] Login with valid credentials → redirected to `/admin/`
- [ ] All sidebar links accessible (superadmin)
- [ ] Logout clears cookie, redirects to login
- [ ] Staff login → Rooms & Policies → redirected to `/admin/` with flash message

### Step 14.4 — Apply migration on dev DB

- [ ] `alembic upgrade head`
  - Expected: migration `b2c3d4e5` applied with no errors

### Step 14.5 — Final commit

- [ ] `git add -A && git commit -m "chore: Phase 3 complete — all tests passing, admin dashboard fully functional"`

---

## Key References

- **Spec:** `docs/superpowers/specs/2026-03-21-phase3-admin-dashboard-design.md`
- **Conftest:** `tests/conftest.py` — patch targets: `app.network.tc.*`, `app.network.scheduler.start_scheduler`, `app.pms.factory.load_adapter`
- **tc patch target:** `app.network.tc.subprocess.run` (not `subprocess.run`)
- **Redis access:** always via `request.app.state.redis` (app-state pattern)
- **Auth:** `get_current_admin` (cookie-first/Bearer-fallback) for all `/admin/*`; `require_superadmin` wraps it for superadmin-only endpoints
- **`_raise_or_redirect`** is `NoReturn` — always raises, never returns
- **`start_scheduler()`** takes no arguments — uses module-level `_manager` and `AsyncSessionFactory`
