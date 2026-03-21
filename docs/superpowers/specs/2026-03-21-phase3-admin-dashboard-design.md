# WiFi Captive Portal — Phase 3: Admin Dashboard + Missing Features

**Date:** 2026-03-21
**Status:** Approved
**Parent Spec:** `2026-03-20-wifi-captive-portal-design.md`
**Phase:** 3 — Admin Dashboard UI + Missing Backend Features

---

## 1. Overview

Phase 3 completes the WiFi Captive Portal with a full Admin Dashboard UI and three missing backend features from Phase 1/2. The Admin Dashboard is built with Jinja2 + HTMX + Alpine.js + Tailwind CSS using the established Glassmorphism design system (dark navy, frosted glass cards, gradient accents).

**Components added in Phase 3:**
1. Missing backend features: JWT logout blocklist (jti-based), upload bandwidth shaping (IFB), bytes tracking + data-based voucher enforcement
2. Admin Dashboard shell: base layout, sidebar navigation, login page with cookie-based JWT
3. Eight UI modules: Dashboard, Sessions, Vouchers, Rooms & Policies, Analytics, PMS Settings, Brand & Config, Admin Users
4. Two new DB tables: `usage_snapshots`, `brand_config` (+ `bandwidth_up_kbps` column on sessions)
5. `policies` table migration — ORM model (`Policy`) already exists in `models.py`; Phase 3 migration creates the actual PostgreSQL table (checkfirst=True)
6. PDF + QR voucher export (URL mode and code mode selectable at generation time)
7. Analytics snapshot scheduler job (hourly)
8. PDF library: **reportlab** (chosen over weasyprint — no native dependency on Cairo/Pango, simpler QR integration)
9. Session middleware: `starlette.middleware.sessions.SessionMiddleware` added to `main.py` for flash messages

---

## 2. Implementation Order (Module-by-Module)

```
Module 1: Missing Backend Features (foundational)
  ├─ 1a. JWT logout + Redis token blocklist (jti-based, replaces existing raw-token blocklist)
  ├─ 1b. Upload bandwidth shaping (tc HTB on IFB device)
  └─ 1c. Bytes tracking (tc -s stats, dual-interface) + data-based voucher enforcement

Module 2: Admin Dashboard Shell
  └─ base.html layout (sidebar, topbar, content slot) + /admin/login page

Module 3: Sessions Module
  └─ Active sessions list + kick (HTMX polling every 30s)

Module 4: Vouchers Module
  ├─ Create single / batch generate
  ├─ List + filter
  └─ Export PDF + QR (URL mode / code mode selectable)

Module 5: Rooms & Policies Module
  ├─ Policy CRUD (bandwidth up/down, max devices, session duration)
  └─ Room list + assign policy dropdown

Module 6: Analytics Module
  ├─ DB table: usage_snapshots + hourly snapshot scheduler job
  └─ Chart.js charts: daily users, bandwidth per hour, peak hours heatmap, voucher usage

Module 7: Brand & Config Module
  ├─ DB table: brand_config (single row)
  └─ Logo upload (multipart), color picker, T&C textarea, language toggle (TH/EN)

Module 8: Admin Users Module
  └─ Create/list staff accounts + last login history
```

---

## 3. Database Schema Additions

### New Table: `usage_snapshots`

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK | |
| snapshot_at | TIMESTAMP TZ | NOT NULL | Hourly snapshot time (stored as-is from `datetime.now(timezone.utc)`) |
| active_sessions | INT | NOT NULL DEFAULT 0 | Active session count at snapshot time |
| total_bytes_up | BIGINT | NOT NULL DEFAULT 0 | Sum of bytes_up across all active sessions |
| total_bytes_down | BIGINT | NOT NULL DEFAULT 0 | Sum of bytes_down across all active sessions |
| voucher_uses | INT | NOT NULL DEFAULT 0 | Voucher sessions started in the hour preceding snapshot_at |

**Index:** `CREATE INDEX ON usage_snapshots (snapshot_at DESC)` — fast range queries.

### New Table: `brand_config`

Single-row table. Migration seeds the default row via `op.execute(INSERT ... ON CONFLICT DO NOTHING)`.

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK | Fixed: `00000000-0000-0000-0000-000000000001` |
| hotel_name | VARCHAR(200) | NOT NULL DEFAULT 'Hotel WiFi' | |
| logo_path | VARCHAR(500) | NULLABLE | Relative path from `static/`: e.g. `uploads/logo/logo.png`; NULL = no logo set |
| primary_color | VARCHAR(7) | NOT NULL DEFAULT '#3B82F6' | Hex color |
| tc_text_th | TEXT | NULLABLE | |
| tc_text_en | TEXT | NULLABLE | |
| language | language_type | NOT NULL DEFAULT 'th' | PostgreSQL enum named `language_type` |
| updated_at | TIMESTAMP TZ | NOT NULL, server_default=`now()` | Application sets `datetime.now(timezone.utc)` on every PUT; migration uses `server_default=sa.func.now()` |

**Migration order:** `CREATE TYPE language_type AS ENUM ('th', 'en')` before `CREATE TABLE brand_config`.
**Downgrade order:** `DROP TABLE brand_config` → `DROP TYPE language_type`.

### `policies` Table

`Policy` ORM model already exists in `models.py`. Migration uses `op.create_table(..., if_not_exists=True)` (or `checkfirst=True`). Columns match the model exactly:

| Column | Type | Constraints | Notes |
|--------|------|-------------|-------|
| id | UUID | PK | |
| name | VARCHAR(100) | NOT NULL | |
| bandwidth_up_kbps | INT | NOT NULL DEFAULT 0 | 0 = unlimited |
| bandwidth_down_kbps | INT | NOT NULL DEFAULT 0 | 0 = unlimited |
| session_duration_min | INT | NOT NULL DEFAULT 0 | 0 = until check-out |
| max_devices | INT | NOT NULL DEFAULT 3 | |

**Downgrade:** `op.drop_table("policies", if_exists=True)` only if created in this migration (use a flag or check existence).

### Modified Table: `sessions`

Add to `Session` ORM model in `models.py`:
```python
bandwidth_up_kbps: Mapped[int] = mapped_column(Integer, nullable=False, default=0, server_default="0")
```

Migration: `op.add_column("sessions", sa.Column("bandwidth_up_kbps", sa.Integer, nullable=False, server_default="0"))`.
Downgrade: `op.drop_column("sessions", "bandwidth_up_kbps")`.

---

## 4. Missing Backend Features

### 4a. JWT Logout + Token Blocklist

**Existing code to REMOVE from `auth.py`:**
- `revoke_token(token: str)` — stores raw token under `revoked:{token}`
- `is_token_revoked(token: str)` — checks `revoked:{token}`
- Remove both functions entirely; the existing `get_current_user` call to `is_token_revoked` must also be removed

**Updated `create_access_token()`:**
- Add `"jti": str(uuid4())` to the JWT payload

**New `get_current_admin(request: Request)` dependency** (replaces `get_current_user` on all admin routes):

```python
async def get_current_admin(request: Request) -> dict:
    token = request.cookies.get("admin_token")
    if not token:
        credentials = await HTTPBearer(auto_error=False)(request)
        if credentials:
            token = credentials.credentials
    if not token:
        _raise_or_redirect(request)          # always raises — execution stops here
    try:
        payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
    except JWTError:
        _raise_or_redirect(request)          # always raises — execution stops here
    redis = request.app.state.redis          # app-state pattern (same as portal router)
    if await redis.exists(f"blocklist:{payload['jti']}"):
        _raise_or_redirect(request)          # always raises — execution stops here
    return payload                           # {"sub": username, "role": role, "jti": jti, "exp": exp}
```

`_raise_or_redirect(request: Request) -> NoReturn`: always raises — never returns.
- If `Accept` header contains `text/html`: `raise HTTPException(302, headers={"Location": f"/admin/login?next={request.url.path}"})`
- Otherwise: `raise HTTPException(401, {"error": "unauthorized"})`

**`require_superadmin` dependency:**
```python
async def require_superadmin(payload: dict = Depends(get_current_admin)) -> dict:
    if payload.get("role") != "superadmin":
        raise HTTPException(403, {"error": "forbidden"})
    return payload
```

**403 handling for HTML routes** — register a `@app.exception_handler(403)` in `main.py`:
```python
@app.exception_handler(403)
async def forbidden_handler(request: Request, exc: HTTPException):
    if "text/html" in request.headers.get("accept", ""):
        request.session["flash"] = "Access denied: superadmin required"
        return RedirectResponse(url="/admin/", status_code=302)
    return JSONResponse({"error": "forbidden"}, status_code=403)
```
This single handler covers all superadmin-only HTML routes uniformly. No try/except in individual route handlers. `SessionMiddleware` (added to `main.py`) makes `request.session` available. Key: `settings.SECRET_KEY` (consistent with rest of `main.py`).

**`POST /admin/logout` endpoint:**
```python
@router.post("/logout")
async def admin_logout(request: Request, payload: dict = Depends(get_current_admin)):
    # request: Request — no default (FastAPI injects automatically)
    jti = payload["jti"]
    exp = payload["exp"]
    remaining_ttl = max(1, exp - int(time.time()))
    await request.app.state.redis.set(f"blocklist:{jti}", 1, ex=remaining_ttl)
    response = JSONResponse({"status": "logged_out"})
    response.delete_cookie("admin_token")
    return response
```

### 4b. Upload Bandwidth Shaping (IFB device)

**`tc.ensure_ifb_ready()` — called once in `main.py` lifespan startup:**

```bash
modprobe ifb
ip link add ifb0 type ifb 2>/dev/null || true
ip link set ifb0 up
tc qdisc add dev {WIFI_INTERFACE} handle ffff: ingress 2>/dev/null || true
tc filter add dev {WIFI_INTERFACE} parent ffff: protocol ip u32 match u32 0 0 \
  action mirred egress redirect dev ifb0 2>/dev/null || true
tc qdisc add dev ifb0 root handle 1: htb default 999 2>/dev/null || true
```

All commands use `_run()` (existing wrapper, `check=False`, errors logged but not raised).

**Updated `apply_bandwidth_limit(ip, down_kbps, up_kbps, wan_if)` signature:**
- New `up_kbps: int = 0` parameter added
- Download shaping on `wan_if` unchanged
- If `up_kbps > 0`: add class + filter on `ifb0` (src IP match)

```bash
tc class add dev ifb0 parent 1: classid 1:<id> htb rate <up_kbps>kbit ceil <up_kbps>kbit
tc filter add dev ifb0 parent 1: protocol ip prio 1 u32 match ip src <guest_ip>/32 flowid 1:<id>
```

**Updated `remove_bandwidth_limit(ip, up_kbps, wan_if)` signature:**
- New `up_kbps: int = 0` parameter added
- Download cleanup on `wan_if` unchanged
- If `up_kbps > 0`: delete filter + class on `ifb0`

```bash
tc filter del dev ifb0 parent 1: protocol ip prio 1 u32 match ip src <guest_ip>/32 flowid 1:<id>
tc class del dev ifb0 parent 1: classid 1:<id>
```

**Updated `SessionManager.create_session()`:**
- Add `bandwidth_up_kbps: int = 0` parameter
- Pass to `tc.apply_bandwidth_limit(ip, down_kbps, up_kbps, wan_if)`
- Set `session.bandwidth_up_kbps = bandwidth_up_kbps` on the `Session(...)` constructor call

**Updated `SessionManager.expire_session()` (and kick):**
- Call `tc.remove_bandwidth_limit(ip, session.bandwidth_up_kbps, wan_if)` — reads `bandwidth_up_kbps` from the session row

### 4c. Bytes Tracking + Data-based Voucher Enforcement

**`tc.get_bytes(ip: str) -> tuple[int, int]`** returns `(bytes_up, bytes_down)`:
- `bytes_down`: `subprocess.run(["tc", "-s", "class", "show", "dev", WAN_INTERFACE])` → find class ID matching IP → extract `Sent X bytes`
- `bytes_up`: same command on `ifb0` — returns 0 if `ifb0` not configured or class not found
- Returns `(0, 0)` if class not found on either device
- Patch target in tests: `patch("app.network.tc.subprocess.run")`

**Updated `start_scheduler()` in `scheduler.py`** — keep no-argument signature (existing pattern; jobs use module-level `_manager` and `AsyncSessionFactory`); add two new `add_job` calls:

```python
def start_scheduler():
    scheduler.add_job(_expire_job, "interval", seconds=60, id="expire_sessions")
    scheduler.add_job(_bytes_job, "interval", seconds=60, id="update_bytes")
    scheduler.add_job(_poll_checkouts_job, "interval", seconds=300, id="poll_checkouts")
    scheduler.add_job(_analytics_snapshot_job, "interval", seconds=3600, id="analytics_snapshot")
    scheduler.start()
    logger.info("Scheduler started (expire: 60s, bytes: 60s, poll: 300s, analytics: 3600s)")
```

`main.py` callsite is unchanged — `start_scheduler()` still takes no arguments.

**`_bytes_job()`** — runs every 60 seconds, independent from `_expire_job`. Uses module-level `_manager = SessionManager()` (same pattern as `_expire_job`):

```python
async def _bytes_job():
    async with AsyncSessionFactory() as db:
        # 1. Query all active sessions (eager-load voucher)
        # 2. For each session: (up, down) = tc.get_bytes(session.ip_address)
        #    → session.bytes_up = up; session.bytes_down = down
        # 3. For voucher sessions (type=data):
        #    if session.bytes_down >= voucher.data_limit_mb * 1024 * 1024:
        #        await _manager.expire_session(db, session, SessionStatus.expired)
        # 4. await db.commit()
```

`session.bandwidth_up_kbps` accessed in `expire_session()` defaults to `0` (via `server_default="0"`) for all rows — including rows created before the migration. No `AttributeError` risk after `alembic upgrade head` runs.

**`_analytics_snapshot_job()`** — runs every 3600 seconds:

```python
async def _analytics_snapshot_job():
    async with AsyncSessionFactory() as db:
        snapshot_at = datetime.now(timezone.utc)   # stored as-is (not hour-truncated)
        # 1. Count active sessions
        # 2. Sum bytes_up, bytes_down from active sessions (default 0 if none)
        # 3. Count voucher_uses: sessions with voucher_id IS NOT NULL
        #    and connected_at >= snapshot_at - timedelta(hours=1)
        # 4. Insert UsageSnapshot(snapshot_at, active_sessions, total_bytes_up,
        #                         total_bytes_down, voucher_uses)
        # 5. await db.commit()
```

---

## 5. Admin Dashboard UI

### Auth Architecture

**`get_current_admin`** reads token cookie-first, then Bearer header; checks JWT validity and Redis blocklist; redirects to login (HTML) or returns 401 (JSON). Accesses Redis via `request.app.state.redis`.

**`require_superadmin`** — wraps `get_current_admin`, raises 403 if role != superadmin.

**Flash messages** — `SessionMiddleware` added to `main.py` (`starlette.middleware.sessions.SessionMiddleware`, `secret_key=SECRET_KEY`). Flash stored as `request.session["flash"]` string; rendered in `base.html`; cleared after display.

**Route disambiguation** — HTML page routes and JSON API routes share the same URL prefix `/admin/` but are disambiguated by response type. To avoid FastAPI route conflicts, JSON API endpoints that share a path with an HTML route are served at `/admin/api/*`:

| HTML route | JSON API equivalent |
|-----------|-------------------|
| `GET /admin/policies` | `GET /admin/api/policies` |
| `GET /admin/rooms` | `GET /admin/api/rooms` |
| `GET /admin/brand` | `GET /admin/api/brand` |
| `GET /admin/analytics` | `GET /admin/api/analytics/data` |

All other JSON-only endpoints remain at `/admin/*` (no HTML counterpart at same path).

### Stack
- **Templates:** Jinja2, `app/admin/templates/`
- **Interactivity:** HTMX + Alpine.js
- **Styling:** Tailwind CSS (CDN), Glassmorphism utilities
- **Charts:** Chart.js (analytics only, CDN)
- **Session middleware:** `SessionMiddleware` (for flash messages)

### Design System
- Background: `#0f172a`
- Cards: `backdrop-blur`, semi-transparent white border
- Accent: gradient indigo→purple
- Typography: Inter (Google Fonts CDN)

### Layout: `base.html`

```
┌─────────────────────────────────────────────┐
│  Sidebar (fixed left, collapsible)          │
│  ├─ Logo + Hotel Name                       │
│  ├─ Dashboard          [staff + superadmin] │
│  ├─ Sessions           [staff + superadmin] │
│  ├─ Vouchers           [staff + superadmin] │
│  ├─ Rooms & Policies   [superadmin only]    │
│  ├─ Analytics          [superadmin only]    │
│  ├─ PMS Settings       [superadmin only]    │
│  ├─ Brand & Config     [superadmin only]    │
│  └─ Admin Users        [superadmin only]    │
│                                             │
│  Top Bar (fixed top)                        │
│  ├─ Page title + flash message area         │
│  └─ Username + role badge + Logout button   │
│                                             │
│  Content Area                               │
│  └─ {% block content %}{% endblock %}       │
└─────────────────────────────────────────────┘
```

Superadmin-only sidebar items hidden when `current_user.role == "staff"`. Jinja2 context variable `current_user` injected from `get_current_admin` payload.

### Module Details

#### Login Page (`GET/POST /admin/login`)
- No `base.html` — standalone page
- `POST`: validate credentials → set `admin_token` httpOnly cookie (SameSite=Lax) → redirect to `?next` param or `/admin/`
- Failure: re-render with inline error (no redirect)
- If already authenticated: redirect to `/admin/`

#### Dashboard (`GET /admin/`)
- Stats cards: Active Sessions, Vouchers used today, Total bytes down today
- Recent 10 active sessions with kick button
- Role: staff + superadmin

#### Sessions (`GET /admin/sessions`)
- Table: IP, Room/Voucher, Connected At, Expires At, Bytes Down (human-readable), Status
- HTMX polling: `hx-get="/admin/sessions/rows" hx-trigger="every 30s" hx-target="#session-tbody"`
- `GET /admin/sessions/rows` → HTML fragment (tbody rows only)
- Kick: `hx-delete="/admin/sessions/{id}"` → HTMX removes row
- Role: staff + superadmin

#### Vouchers (`GET /admin/vouchers`)
- Create form: type, duration_minutes OR data_limit_mb, max_uses, max_devices, expires_at
- Batch generate: count (1–100) + same settings → `POST /admin/vouchers/batch`
- QR mode radio: "URL" or "Code" (sent as `?qr_mode=url|code` to PDF endpoint)
- List table with client-side Alpine.js filter
- Role: staff + superadmin

#### Rooms & Policies (`GET /admin/rooms`, `GET /admin/policies`)
- Policy CRUD with Alpine.js modal + HTMX submit
- Room list with inline policy dropdown → `hx-put="/admin/rooms/{id}/policy"`
- Role: superadmin only

#### Analytics (`GET /admin/analytics`)
- Time range selector: `?range=24h|7d|30d` (invalid values → 400)
- Chart.js rendered from `GET /admin/api/analytics/data?range=...` JSON
- Four charts: sessions line, bandwidth bar (up+down stacked), peak hours heatmap, auth breakdown pie
- Role: superadmin only

#### PMS Settings (`GET /admin/pms`)
- Wraps existing API with UI; edit form + HTMX submit; Test Connection inline
- Role: superadmin only

#### Brand & Config (`GET /admin/brand`)
- Form: hotel name, primary color picker, language dropdown, T&C textareas (TH/EN tabs)
- Logo: separate `<form>` posting multipart to `POST /admin/brand/logo`
- Live preview panel
- Role: superadmin only

#### Admin Users (`GET /admin/users`)
- List: username, role, last login
- Create form: username, password, role dropdown
- Role: superadmin only

---

## 6. API Endpoints Added in Phase 3

### Auth Note
- All `/admin/*` endpoints (except `/admin/login`): `get_current_admin` dependency
- Superadmin-only: additionally `require_superadmin`
- JSON API at `/admin/api/*` where path conflicts with HTML route; elsewhere at `/admin/*`

### JSON API Endpoints

| Method | Path | Role | Request Body | Response |
|--------|------|------|-------------|----------|
| POST | `/admin/logout` | any | — | `{"status": "logged_out"}` + clears cookie |
| GET | `/admin/api/policies` | superadmin | — | `[{id, name, bandwidth_up_kbps, bandwidth_down_kbps, session_duration_min, max_devices}]` |
| POST | `/admin/api/policies` | superadmin | `{name, bandwidth_up_kbps, bandwidth_down_kbps, session_duration_min, max_devices}` | created policy object |
| PUT | `/admin/api/policies/{id}` | superadmin | partial fields | updated policy object |
| DELETE | `/admin/api/policies/{id}` | superadmin | — | `{"status": "deleted"}` |
| GET | `/admin/api/rooms` | superadmin | — | `[{id, number, room_type, policy_id, policy_name}]` |
| PUT | `/admin/api/rooms/{id}/policy` | superadmin | `{policy_id: uuid \| null}` | `{id, number, policy_id}` |
| GET | `/admin/api/analytics/data` | superadmin | `?range=24h\|7d\|30d` | analytics JSON (see schema below) |
| GET | `/admin/api/brand` | superadmin | — | `{hotel_name, logo_url, primary_color, tc_text_th, tc_text_en, language}` |
| PUT | `/admin/api/brand` | superadmin | `{hotel_name?: str, primary_color?: str (7-char hex), tc_text_th?: str\|null, tc_text_en?: str\|null, language?: "th"\|"en"}` — all fields optional (Pydantic model with all Optional) | updated brand object |
| POST | `/admin/brand/logo` | superadmin | multipart `file` | `{logo_url: "/static/uploads/logo/logo.png"}` |
| GET | `/admin/api/users` | superadmin | — | `[{id, username, role, last_login_at}]` |
| POST | `/admin/api/users` | superadmin | `{username, password, role}` | `{id, username, role}` |
| POST | `/admin/vouchers/batch` | any | `{type, duration_minutes?, data_limit_mb?, max_uses, max_devices, expires_at?, count}` (count: 1–100) | `[{id, code, type, ...}]` |
| GET | `/admin/vouchers/{id}/pdf` | any | `?qr_mode=url\|code` | PDF binary (`application/pdf`) |
| GET | `/admin/vouchers/batch-pdf` | any | `?ids=uuid,uuid,...&qr_mode=url\|code` (`ids` is comma-delimited string, split server-side) | PDF binary |

### Analytics Response Schema

```json
{
  "range": "24h",
  "sessions_over_time": [
    {"timestamp": "2026-03-21T10:00:00+00:00", "active_sessions": 12}
  ],
  "bandwidth_per_hour": [
    {"timestamp": "2026-03-21T10:00:00+00:00", "bytes_up": 104857600, "bytes_down": 524288000}
  ],
  "peak_hours": [
    {"day_of_week": 0, "hour": 14, "count": 25}
  ],
  "auth_breakdown": {
    "room_auth": 150,
    "voucher_auth": 42
  }
}
```

- `sessions_over_time` + `bandwidth_per_hour`: from `usage_snapshots` where `snapshot_at >= now() - interval`
- `peak_hours`: `GROUP BY EXTRACT(DOW FROM snapshot_at), EXTRACT(HOUR FROM snapshot_at)`, aggregate `SUM(active_sessions)`; `day_of_week` 0=Sunday (PostgreSQL convention)
- `auth_breakdown`: from `sessions` where `connected_at >= now() - interval`; `voucher_id IS NULL` = room_auth; `voucher_id IS NOT NULL` = voucher_auth
- Invalid `range` value → `400 {"error": "invalid_range", "valid": ["24h", "7d", "30d"]}`

### Logo Upload Constraints (`POST /admin/brand/logo`)
- Accepted MIME types: `image/jpeg`, `image/png`, `image/webp`
- Max file size: 2 MB (read up to 2MB+1 byte; if exceeded → 413 `{"error": "file_too_large"}`)
- Storage path: `static/uploads/logo/` (relative to project root; `os.makedirs(..., exist_ok=True)`)
- Filename: `logo.{ext}` — replaces previous logo; old file deleted via `os.remove()` if extension differs; wrap deletion in `try/except FileNotFoundError: pass` to handle missing files gracefully
- `brand_config.logo_path`: relative path from `static/`, e.g. `uploads/logo/logo.png`
- `logo_url` in response: `/static/uploads/logo/logo.png`

### HTML Routes

| Method | Path | Role | Description |
|--------|------|------|-------------|
| GET/POST | `/admin/login` | public | Login page |
| GET | `/admin/` | any | Dashboard page |
| GET | `/admin/sessions` | any | Sessions page |
| GET | `/admin/sessions/rows` | any | HTMX fragment: tbody only |
| GET | `/admin/vouchers` | any | Vouchers page |
| GET | `/admin/rooms` | superadmin | Rooms page |
| GET | `/admin/policies` | superadmin | Policies page |
| GET | `/admin/analytics` | superadmin | Analytics page |
| GET | `/admin/pms` | superadmin | PMS Settings page |
| GET | `/admin/brand` | superadmin | Brand & Config page |
| GET | `/admin/users` | superadmin | Admin Users page |

---

## 7. Testing Strategy

### Backend (pytest)

| Test File | Coverage |
|-----------|----------|
| `test_admin_auth.py` | jti in issued tokens; logout sets blocklist key; blocklisted token returns 401; old `revoke_token`/`is_token_revoked` functions removed; cookie auth works; Bearer auth works |
| `test_tc_bytes.py` | `get_bytes()` parses WAN_INTERFACE output for download; parses ifb0 for upload; returns `(0, 0)` when class not found; patch target: `app.network.tc.subprocess.run` |
| `test_tc_upload_shaping.py` | `apply_bandwidth_limit()` generates ifb0 commands when `up_kbps > 0`; skips ifb0 when `up_kbps == 0`; `remove_bandwidth_limit()` deletes ifb0 class when `up_kbps > 0` |
| `test_voucher_data_enforcement.py` | `_bytes_job` expires voucher session when `bytes_down >= quota`; does not expire if below quota; does not expire time-type voucher sessions |
| `test_admin_sessions.py` | List active sessions; kick → status = kicked; HTMX `/sessions/rows` returns HTML fragment |
| `test_admin_vouchers.py` | Create single voucher; batch count=5 creates 5 rows; batch count=101 returns 422; PDF endpoint returns bytes with correct Content-Type; `qr_mode=url` and `qr_mode=code` both accepted |
| `test_admin_policies.py` | CRUD policies; assign policy to room; staff user gets 403 on all policy endpoints |
| `test_admin_brand.py` | GET/PUT brand config; valid PNG logo stored; invalid MIME → 422; file >2MB → 413 |
| `test_admin_users.py` | Create staff (bcrypt stored); list users; staff cannot access `/admin/api/users` (403) |
| `test_admin_analytics.py` | Snapshot job inserts correct `usage_snapshots` row; `/admin/api/analytics/data` returns valid schema for each range; invalid range → 400; `auth_breakdown` values non-negative |

### UI Testing
- Manual smoke test each page in browser
- HTMX fragment routes tested via TestClient (assert expected HTML elements present)

### Migration Testing
- `alembic upgrade head`: creates `usage_snapshots`, `brand_config` (with seeded row), `language_type` enum, `policies` (checkfirst), `sessions.bandwidth_up_kbps`
- `alembic downgrade -1`: drops `sessions.bandwidth_up_kbps`, `usage_snapshots`, `brand_config`, then `language_type` enum (in that order); `policies` dropped only if created in this migration

---

## 8. File Structure Changes

```
app/
├── admin/
│   ├── router.py          # extend with all new endpoints (api + html routes)
│   ├── schemas.py         # extend with new schemas
│   └── templates/
│       ├── base.html      # NEW: sidebar + layout shell + flash display
│       ├── login.html     # NEW: standalone login page
│       ├── dashboard.html # NEW
│       ├── sessions.html  # NEW (includes HTMX polling + rows fragment)
│       ├── vouchers.html  # NEW
│       ├── policies.html  # NEW
│       ├── rooms.html     # NEW
│       ├── analytics.html # NEW (includes Chart.js init)
│       ├── pms.html       # NEW
│       ├── brand.html     # NEW
│       └── users.html     # NEW
├── core/
│   ├── models.py          # Add UsageSnapshot, BrandConfig ORM models;
│   │                      # add bandwidth_up_kbps to Session model
│   └── auth.py            # Replace raw-token blocklist with jti-based;
│                          # add get_current_admin (cookie+Bearer, Redis blocklist);
│                          # add require_superadmin;
│                          # remove revoke_token(), is_token_revoked()
├── network/
│   ├── tc.py              # Add ensure_ifb_ready(); get_bytes() (dual-interface);
│   │                      # update apply_bandwidth_limit() + remove_bandwidth_limit()
│   │                      # signatures to include up_kbps parameter
│   ├── session_manager.py # Update create_session() to persist bandwidth_up_kbps;
│   │                      # update expire_session()/kick callsite signature for tc
│   └── scheduler.py       # Add _bytes_job (60s) + _analytics_snapshot_job (3600s);
│                          # update start_scheduler() to register both
├── voucher/
│   └── pdf.py             # NEW: PDF+QR generation via reportlab + qrcode library
└── main.py                # Add SessionMiddleware; call ensure_ifb_ready() in lifespan

static/
└── uploads/
    └── logo/              # Created at runtime for logo uploads

alembic/versions/
└── xxxx_phase3_tables.py  # Creates: language_type enum, usage_snapshots, brand_config
                           #          (seeds default row), policies (checkfirst),
                           #          sessions.bandwidth_up_kbps column
                           # Downgrade: reverse order, drop language_type enum last

tests/
├── test_admin_auth.py                # NEW
├── test_tc_bytes.py                  # NEW
├── test_tc_upload_shaping.py         # NEW
├── test_voucher_data_enforcement.py  # NEW
├── test_admin_sessions.py            # extend existing
├── test_admin_vouchers.py            # extend existing
├── test_admin_policies.py            # NEW
├── test_admin_brand.py               # NEW
├── test_admin_users.py               # NEW
└── test_admin_analytics.py           # NEW
```
