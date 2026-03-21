# WiFi Captive Portal — Phase 3: Admin Dashboard + Missing Features

**Date:** 2026-03-21
**Status:** Approved
**Parent Spec:** `2026-03-20-wifi-captive-portal-design.md`
**Phase:** 3 — Admin Dashboard UI + Missing Backend Features

---

## 1. Overview

Phase 3 completes the WiFi Captive Portal with a full Admin Dashboard UI and three missing backend features from Phase 1/2. The Admin Dashboard is built with Jinja2 + HTMX + Alpine.js + Tailwind CSS using the established Glassmorphism design system (dark navy, frosted glass cards, gradient accents).

**Components added in Phase 3:**
1. Missing backend features: JWT logout blocklist, upload bandwidth shaping, bytes tracking + data-based voucher enforcement
2. Admin Dashboard shell: base layout, sidebar navigation, login page with cookie-based JWT
3. Eight UI modules: Dashboard, Sessions, Vouchers, Rooms & Policies, Analytics, PMS Settings, Brand & Config, Admin Users
4. Three new DB tables: `usage_snapshots`, `brand_config`, `policies` (+ `bandwidth_up_kbps` column on sessions)
5. PDF + QR voucher export (URL mode and code mode selectable)
6. Analytics snapshot scheduler job (hourly)

---

## 2. Implementation Order (Module-by-Module)

Phase 3 is implemented module-by-module so each piece is testable before moving on:

```
Module 1: Missing Backend Features (foundational)
  ├─ 1a. JWT logout + Redis token blocklist
  ├─ 1b. Upload bandwidth shaping (tc HTB on WIFI_INTERFACE)
  └─ 1c. Bytes tracking (tc -s stats) + data-based voucher enforcement

Module 2: Admin Dashboard Shell
  └─ base.html layout (sidebar, topbar, content slot) + /admin/login page

Module 3: Sessions Module
  └─ Active sessions list + kick (HTMX polling every 30s)

Module 4: Vouchers Module
  ├─ Create single / batch generate
  ├─ List + filter
  └─ Export PDF + QR (URL mode / code mode selectable at generate time)

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

Stores hourly snapshots for analytics charts.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| snapshot_at | TIMESTAMP TZ | Hourly snapshot time |
| active_sessions | INT | Active session count at snapshot time |
| total_bytes_up | BIGINT | Sum of bytes_up across all active sessions |
| total_bytes_down | BIGINT | Sum of bytes_down across all active sessions |
| voucher_uses | INT | Voucher-authenticated sessions started in this hour |

**Index:** `snapshot_at DESC` for fast analytics queries.

### New Table: `brand_config`

Single-row table (always exactly one row, seeded on first migration).

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| hotel_name | VARCHAR(200) | Default: "Hotel WiFi" |
| logo_path | VARCHAR(500) | Server file path to uploaded logo |
| primary_color | VARCHAR(7) | Hex color, default: #3B82F6 |
| tc_text_th | TEXT | T&C text in Thai |
| tc_text_en | TEXT | T&C text in English |
| language | ENUM | `th` / `en`, default: `th` |
| updated_at | TIMESTAMP TZ | |

### New Table: `policies`

Per design spec — already referenced by `rooms.policy_id` FK but not yet created.

| Column | Type | Notes |
|--------|------|-------|
| id | UUID PK | |
| name | VARCHAR(100) | |
| bandwidth_up_kbps | INT | 0 = unlimited |
| bandwidth_down_kbps | INT | 0 = unlimited |
| session_duration_min | INT | 0 = until check-out |
| max_devices | INT | Default: 3 |

### Modified Table: `sessions`

Add 1 column:

| Column | Type | Notes |
|--------|------|-------|
| bandwidth_up_kbps | INT | Upload limit applied at session creation (needed for tc remove) |

---

## 4. Missing Backend Features

### 4a. JWT Logout + Token Blocklist

**Endpoint:** `POST /admin/logout` (JWT-protected)

- Extract `jti` claim from current token
- Store in Redis: `SET blocklist:{jti} 1 EX {remaining_ttl_seconds}`
- `get_current_user` dependency: after JWT decode, check `EXISTS blocklist:{jti}` — if found, return 401

**Required change to `create_access_token()`:**
- Add `jti` = `str(uuid4())` claim to every issued token

### 4b. Upload Bandwidth Shaping

`tc.py` currently shapes download on `WAN_INTERFACE` only. Phase 3 adds upload shaping on `WIFI_INTERFACE`:

```bash
# Upload shaping (egress from portal's perspective = ingress on wifi interface)
# Uses IFB (Intermediate Functional Block) device for ingress shaping
tc qdisc add dev ifb0 root handle 1: htb default 999
tc class add dev ifb0 parent 1: classid 1:<id> htb rate <up_kbps>kbit
tc filter add dev ifb0 parent 1: protocol ip prio 1 u32 match ip src <guest_ip>/32 flowid 1:<id>
```

`SessionManager.create_session()` passes `bandwidth_up_kbps` from policy → `tc.apply_bandwidth_limit()`. Session stores `bandwidth_up_kbps` for cleanup on expire/kick.

### 4c. Bytes Tracking + Data-based Voucher Enforcement

**`tc.get_bytes(ip: str) -> tuple[int, int]`** — parses output of `tc -s class show dev {WAN_INTERFACE}`, returns `(bytes_up, bytes_down)` for the class matching the IP.

**Scheduler (every 60 seconds, same loop as expiry job):**
1. For each active session: call `tc.get_bytes(ip)` → update `session.bytes_up`, `session.bytes_down`
2. For voucher sessions where `voucher.type == data`: if `bytes_down >= voucher.data_limit_mb * 1024 * 1024` → call `session_manager.expire_session()`

---

## 5. Admin Dashboard UI

### Stack
- **Templates:** Jinja2 (server-side rendered)
- **Interactivity:** HTMX (partial page updates, polling) + Alpine.js (client-side state)
- **Styling:** Tailwind CSS + custom Glassmorphism utilities
- **Charts:** Chart.js (analytics module only)
- **Auth:** JWT stored in httpOnly cookie (`admin_token`); middleware reads cookie on all `/admin/*` GET routes

### Design System
- Background: `#0f172a` (dark navy)
- Cards: frosted glass (`backdrop-blur`, semi-transparent white border)
- Accent: gradient indigo→purple
- Typography: Inter font

### Layout: `base.html`

```
┌─────────────────────────────────────────────┐
│  Sidebar (fixed left, collapsible)          │
│  ├─ Logo + Hotel Name                       │
│  ├─ Dashboard                               │
│  ├─ Sessions                                │
│  ├─ Vouchers                                │
│  ├─ Rooms & Policies  [superadmin only]     │
│  ├─ Analytics         [superadmin only]     │
│  ├─ PMS Settings      [superadmin only]     │
│  ├─ Brand & Config    [superadmin only]     │
│  └─ Admin Users       [superadmin only]     │
│                                             │
│  Top Bar (fixed top)                        │
│  ├─ Page title                              │
│  └─ User info + Logout button               │
│                                             │
│  Content Area                               │
│  └─ {% block content %}{% endblock %}       │
└─────────────────────────────────────────────┘
```

### Module Details

#### Login Page (`GET/POST /admin/login`)
- Username + password form
- On success: set `admin_token` httpOnly cookie, redirect to `/admin/`
- On failure: show error message inline
- Auto-redirect to login if cookie missing or expired

#### Dashboard (`GET /admin/`)
- Stats cards: Active Sessions count, Vouchers used today, Total bandwidth today
- Recent sessions table (last 10, with kick button)
- Quick links to each module

#### Sessions (`GET /admin/sessions`)
- Full table: IP, Room/Voucher, Connected At, Expires At, Bytes Down, Status
- HTMX auto-refresh every 30 seconds (`hx-trigger="every 30s"`)
- Kick button: `DELETE /admin/sessions/{id}` → HTMX removes row

#### Vouchers (`GET /admin/vouchers`)
- Create form: type (time/data), duration/limit, max_uses, max_devices, expires_at
- Batch generate: count field (1–100), same policy applied to all
- QR export selector: "URL mode" (encodes portal URL with code) or "Code mode" (encodes code string only)
- List table with filter (type, status, date range)
- Download PDF button per voucher or bulk

#### Rooms & Policies (`GET /admin/rooms`, `GET /admin/policies`)
- Policy list + Create/Edit modal (Alpine.js)
- Room list: number, type, current policy (dropdown to reassign)
- `PUT /admin/rooms/{id}/policy` → assign policy

#### Analytics (`GET /admin/analytics`)
- Time range selector: 24h / 7d / 30d
- Line chart: active sessions over time
- Bar chart: hourly bandwidth (up + down stacked)
- Heatmap: peak hours (day-of-week × hour)
- Pie chart: room auth vs voucher auth breakdown

#### PMS Settings (`GET /admin/pms`)
- Existing API UI-wrapped: show config (masked), edit form, Test Connection button
- Test result shows latency + success/error inline via HTMX

#### Brand & Config (`GET /admin/brand`)
- Logo upload (multipart `POST /admin/brand/logo`)
- Hotel name, primary color (color picker), language dropdown
- T&C text: tabbed editor (TH / EN)
- Live preview panel

#### Admin Users (`GET /admin/users`)
- List: username, role, last login
- Create form: username, password, role (staff/superadmin)
- No delete (deactivation only — future scope)

---

## 6. API Endpoints Added in Phase 3

### Admin (JWT-protected, cookie or Bearer)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/admin/logout` | Invalidate current JWT (Redis blocklist) |
| GET/POST | `/admin/policies` | List / create policies |
| GET/PUT/DELETE | `/admin/policies/{id}` | Get / update / delete policy |
| GET | `/admin/rooms` | List rooms |
| PUT | `/admin/rooms/{id}/policy` | Assign policy to room |
| GET | `/admin/analytics` | Analytics data (JSON for Chart.js) |
| GET/PUT | `/admin/brand` | Get / update brand config |
| POST | `/admin/brand/logo` | Upload logo file |
| GET/POST | `/admin/users` | List / create admin users |
| GET | `/admin/vouchers/{id}/pdf` | Download voucher PDF+QR |
| GET | `/admin/vouchers/batch-pdf` | Download batch PDF |

### UI Routes (HTML responses, cookie auth)

| Method | Path | Description |
|--------|------|-------------|
| GET/POST | `/admin/login` | Login page |
| GET | `/admin/` | Dashboard page |
| GET | `/admin/sessions` | Sessions page |
| GET | `/admin/vouchers` | Vouchers page |
| GET | `/admin/rooms` | Rooms page |
| GET | `/admin/policies` | Policies page |
| GET | `/admin/analytics` | Analytics page |
| GET | `/admin/pms` | PMS Settings page |
| GET | `/admin/brand` | Brand & Config page |
| GET | `/admin/users` | Admin Users page |

---

## 7. Testing Strategy

### Backend (pytest)

| Test File | Coverage |
|-----------|----------|
| `test_admin_auth.py` | Logout blocklist, expired/blocked token rejected, jti in token |
| `test_tc_bytes.py` | `get_bytes()` parses tc stats output (mocked subprocess) |
| `test_voucher_data_enforcement.py` | Scheduler expires session when bytes_down ≥ data quota |
| `test_admin_sessions.py` | List + kick (extend existing) |
| `test_admin_vouchers.py` | Create single/batch, validate fields, PDF endpoint returns bytes |
| `test_admin_policies.py` | CRUD policies, assign to room |
| `test_admin_brand.py` | Get/update brand config, logo upload |
| `test_admin_users.py` | Create staff, list users |
| `test_admin_analytics.py` | Snapshot job writes correct data, analytics endpoint returns expected shape |

### UI Testing
- Manual smoke test each page in browser
- HTMX fragment endpoints tested via httpx TestClient (check HTML response content)

### Migration Testing
- `alembic upgrade head` on test DB produces no errors for all 3 new tables + sessions column

---

## 8. File Structure Changes

```
app/
├── admin/
│   ├── router.py          # extend with new endpoints
│   ├── schemas.py         # extend with new schemas
│   └── templates/
│       ├── base.html      # NEW: sidebar + layout shell
│       ├── login.html     # NEW: admin login page
│       ├── dashboard.html # NEW
│       ├── sessions.html  # NEW
│       ├── vouchers.html  # NEW
│       ├── policies.html  # NEW
│       ├── rooms.html     # NEW
│       ├── analytics.html # NEW
│       ├── pms.html       # NEW
│       ├── brand.html     # NEW
│       └── users.html     # NEW
├── core/
│   ├── models.py          # Add UsageSnapshot, BrandConfig, Policy models + sessions column
│   └── auth.py            # Add jti to token, add blocklist check
├── network/
│   ├── tc.py              # Add get_bytes(), upload shaping
│   └── scheduler.py       # Add bytes update job + analytics snapshot job
└── voucher/
    └── pdf.py             # NEW: PDF+QR generation (reportlab or weasyprint)

alembic/versions/
└── xxxx_phase3_tables.py  # usage_snapshots, brand_config, policies + sessions.bandwidth_up_kbps

tests/
├── test_admin_auth.py     # NEW
├── test_tc_bytes.py       # NEW
├── test_voucher_data_enforcement.py  # NEW
├── test_admin_vouchers.py # extend
├── test_admin_policies.py # NEW
├── test_admin_brand.py    # NEW
├── test_admin_users.py    # NEW
└── test_admin_analytics.py # NEW
```
