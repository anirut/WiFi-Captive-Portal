# WiFi Captive Portal — Design Specification

**Date:** 2026-03-20
**Status:** Approved
**Project:** Hotel WiFi Captive Portal

---

## 1. Overview

A hotel WiFi captive portal system running on Ubuntu Linux. Guests connecting to WiFi are redirected to a login page where they authenticate using their room number + last name, or a voucher code. The system enforces network access via iptables and integrates with multiple Property Management Systems (PMS) through an adapter pattern.

**Key goals:**
- Fast, reliable guest authentication (room-based + voucher)
- Lightweight network control without RADIUS
- Extensible PMS integration via adapter pattern
- Full admin dashboard with analytics and brand customization
- Single hotel deployment (white-label)

---

## 2. Architecture

**Pattern:** Modular Monolith
**Runtime:** Python FastAPI on Ubuntu Linux
**Rationale:** Single-hotel deployment does not warrant microservices complexity. Modular structure enables future extraction if needed.

### Three Layers

**Network Layer (Ubuntu Linux)**
- `dnsmasq` — DHCP server + DNS redirect (all queries → portal IP)
- `iptables/nftables` — redirect unauthenticated HTTP/HTTPS to portal; whitelist authenticated IPs
- Session Tracker — maps IP/MAC → session, handles expiry

**Application Layer (FastAPI Modular Monolith)**

| Module | Responsibility |
|--------|---------------|
| `portal/` | Guest-facing login pages, auth flow |
| `admin/` | Dashboard UI, management APIs |
| `network/` | iptables manager, bandwidth control, session expiry |
| `pms/` | PMS adapter interface + 5 implementations |
| `voucher/` | Voucher generation, validation, export |
| `core/` | DB models, auth, config, shared utilities |

**Data Layer**
- PostgreSQL — primary data store
- Redis — active session cache, rate limiting, fast IP lookup
- PMS systems — external (Opera, Cloudbeds, Mews, Custom, Standalone)

---

## 3. Authentication Flows

### Flow A — Room Number + Last Name

1. Guest connects to WiFi → dnsmasq assigns IP
2. Guest opens browser → iptables redirects port 80/443 → FastAPI portal
3. Guest submits room number + last name + T&C acceptance
4. FastAPI calls active PMS adapter → `verify_guest(room, last_name)`
5. On success: fetch room policy → create session → record IP/MAC
6. `network.iptables.add_whitelist(ip)` + apply bandwidth limit via `tc`
7. Redirect to success page → internet access granted

### Flow B — Voucher Code

1. Guest connects to WiFi → redirect to portal
2. Guest selects "Voucher Code" tab → submits code
3. System validates: code exists, not expired, uses remaining
4. Create session → apply voucher policy (time-based or data-limited)
5. `network.iptables.add_whitelist(ip)` + bandwidth limit
6. Session expires when: time limit reached, data quota exceeded, or manual kick

### Session Expiry (Three Triggers)

| Trigger | Mechanism |
|---------|-----------|
| PMS check-out sync | PMS webhook/poll → expire all sessions for room → iptables REMOVE |
| Timer | APScheduler checks `expires_at` every 60s → REMOVE expired |
| Admin kick | Dashboard action → iptables REMOVE immediately → status = kicked |

---

## 4. PMS Adapter Layer

### Interface (Abstract Base Class)

```python
class PMSAdapter(ABC):
    async def verify_guest(self, room: str, last_name: str) -> GuestInfo | None
    async def get_guest_by_room(self, room: str) -> GuestInfo | None
    async def health_check(self) -> bool

@dataclass
class GuestInfo:
    pms_id: str
    room_number: str
    last_name: str
    check_in: datetime
    check_out: datetime
```

### Adapters

| Adapter | PMS | Auth Method |
|---------|-----|-------------|
| `OperaAdapter` | Oracle OHIP | OAuth2 |
| `CloudbedsAdapter` | Cloudbeds v1 | API Key |
| `MewsAdapter` | Mews Connector | Access Token |
| `CustomAdapter` | Any REST API | Configurable (Bearer/Basic) + field mapping |
| `StandaloneAdapter` | Local DB only | None (admin-managed guests) |

**Factory:** On startup, load adapter from `pms_adapters` table where `is_active=true`.
**Fallback:** On PMS timeout/error → retry 2× → log error → return auth failure (no silent fallback).

---

## 5. Data Models

### `guests`
| Field | Type | Notes |
|-------|------|-------|
| id | UUID PK | |
| room_number | VARCHAR | |
| last_name | VARCHAR | |
| pms_guest_id | VARCHAR | nullable |
| check_in | TIMESTAMP | |
| check_out | TIMESTAMP | |
| max_devices | INT | default 3 |
| created_at | TIMESTAMP | |

### `sessions`
| Field | Type | Notes |
|-------|------|-------|
| id | UUID PK | |
| guest_id | FK → guests | nullable |
| voucher_id | FK → vouchers | nullable |
| ip_address | INET | |
| mac_address | MACADDR | |
| connected_at | TIMESTAMP | |
| expires_at | TIMESTAMP | |
| bytes_up | BIGINT | |
| bytes_down | BIGINT | |
| status | ENUM | active / expired / kicked |

### `vouchers`
| Field | Type | Notes |
|-------|------|-------|
| id | UUID PK | |
| code | VARCHAR UNIQUE | |
| type | ENUM | time / data |
| duration_minutes | INT | nullable |
| data_limit_mb | INT | nullable |
| max_devices | INT | default 1 |
| created_by | FK → admin_users | |
| expires_at | TIMESTAMP | nullable |
| used_count | INT | |
| max_uses | INT | |

### `rooms`
| Field | Type | Notes |
|-------|------|-------|
| id | UUID PK | |
| number | VARCHAR | |
| room_type | VARCHAR | standard / deluxe / suite |
| policy_id | FK → policies | |
| pms_room_id | VARCHAR | nullable |

### `policies`
| Field | Type | Notes |
|-------|------|-------|
| id | UUID PK | |
| name | VARCHAR | |
| bandwidth_up_kbps | INT | |
| bandwidth_down_kbps | INT | |
| session_duration_min | INT | |
| max_devices | INT | |

### `pms_adapters`
| Field | Type | Notes |
|-------|------|-------|
| id | UUID PK | |
| type | ENUM | opera / cloudbeds / mews / custom / standalone |
| config | JSONB | api_url, credentials, field_map |
| is_active | BOOLEAN | |
| last_sync_at | TIMESTAMP | |

### `admin_users`
| Field | Type | Notes |
|-------|------|-------|
| id | UUID PK | |
| username | VARCHAR UNIQUE | |
| password_hash | VARCHAR | |
| role | ENUM | superadmin / staff |
| last_login_at | TIMESTAMP | |

---

## 6. Admin Dashboard

**UI Style:** Glassmorphism — dark navy background, frosted glass cards, gradient accents
**Tech:** FastAPI + Jinja2 + HTMX + Alpine.js + Tailwind CSS

### Navigation Modules

| Module | Access | Features |
|--------|--------|----------|
| Dashboard | All | Stats overview, active session list |
| Active Sessions | All | Real-time list, kick button, bandwidth usage |
| Guests | superadmin | View/manage guests (standalone mode) |
| Vouchers | All | Create single/batch, set policy, export PDF+QR |
| Rooms & Policies | superadmin | Bandwidth limits per room type, max devices |
| Analytics | superadmin | Daily/weekly users, bandwidth per room, peak hours, voucher reports |
| PMS Settings | superadmin | Select adapter, configure credentials, test connection |
| Brand & Config | superadmin | Logo, hotel name, T&C text, primary color, language (TH/EN) |
| Admin Users | superadmin | Create staff accounts, view login log |

### Roles
- **superadmin** — full access
- **staff** — sessions + vouchers only (front desk use)

---

## 7. Guest Portal

**UI Style:** Split layout — left panel branding, right panel form
**Theme:** Glassmorphism (dark, matches admin)
**Tech:** FastAPI + Jinja2 + Tailwind CSS
**Primary device:** Mobile (responsive)

### Pages
1. **Login** — split: left = hotel logo + WiFi info, right = Room+Name form / Voucher tab
2. **Success** — connected confirmation + session info (time remaining, disconnect button)
3. **Expired** — session expired, prompt to reconnect
4. **Error** — auth failed with clear message (wrong room, PMS unavailable, etc.)

### Customizable via Admin
- Hotel logo
- Hotel name
- Primary color
- T&C text
- Language (TH / EN)

---

## 8. Project Structure

```
wifi-captive-portal/
├── app/
│   ├── portal/
│   │   ├── router.py
│   │   ├── schemas.py
│   │   └── templates/
│   ├── admin/
│   │   ├── router.py
│   │   ├── schemas.py
│   │   └── templates/
│   ├── network/
│   │   ├── iptables.py
│   │   ├── session_manager.py
│   │   └── scheduler.py
│   ├── pms/
│   │   ├── base.py
│   │   ├── opera.py
│   │   ├── cloudbeds.py
│   │   ├── mews.py
│   │   ├── custom.py
│   │   ├── standalone.py
│   │   └── factory.py
│   ├── voucher/
│   │   ├── router.py
│   │   └── generator.py
│   ├── core/
│   │   ├── models.py
│   │   ├── database.py
│   │   ├── auth.py
│   │   └── config.py
│   └── main.py
├── static/
│   └── css/ js/ img/
├── tests/
│   ├── test_portal.py
│   ├── test_pms/
│   └── test_network.py
├── alembic/
├── scripts/          # iptables setup scripts
├── docker-compose.yml
├── .env.example
└── requirements.txt
```

---

## 9. Tech Stack

| Layer | Technology |
|-------|-----------|
| Web Framework | FastAPI |
| ORM | SQLAlchemy |
| Migrations | Alembic |
| Background Jobs | APScheduler |
| HTTP Client | httpx (async) |
| Admin Auth | JWT (python-jose) |
| Frontend | Jinja2 + HTMX + Alpine.js + Tailwind CSS |
| Charts | Chart.js |
| Database | PostgreSQL |
| Cache | Redis |
| Network | iptables / nftables + tc (bandwidth) |
| DNS/DHCP | dnsmasq |
| Reverse Proxy | Nginx |
| ASGI Server | Uvicorn |
| Testing | pytest + pytest-asyncio + httpx + pytest-cov |
| Deployment | systemd + docker-compose + iptables-persistent |

---

## 10. Testing Strategy

- **Unit tests** — PMS adapters (mocked HTTP), voucher generator, session expiry logic
- **Integration tests** — FastAPI routes via httpx TestClient, PostgreSQL test DB
- **Network tests** — iptables manager (requires sudo, run in CI with elevated permissions)
- **Mock adapters** — all PMS adapters have mock implementations for testing without live PMS

---

## 11. Deployment (Ubuntu)

1. Install: Python 3.11+, PostgreSQL, Redis, dnsmasq, Nginx
2. Configure dnsmasq: DHCP range + DNS redirect to portal IP
3. Run `scripts/setup-iptables.sh` — creates redirect + forward chains
4. Install `iptables-persistent` — rules survive reboot
5. Configure `.env` — DB URL, Redis URL, secret keys, PMS credentials
6. Run `docker-compose up -d` — PostgreSQL + Redis
7. Run `alembic upgrade head` — apply DB migrations
8. Configure Nginx — reverse proxy to Uvicorn on port 8000
9. Enable systemd service — auto-start FastAPI on boot
