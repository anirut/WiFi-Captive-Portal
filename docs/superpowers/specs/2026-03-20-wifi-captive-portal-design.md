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

### Network Topology Assumption

The portal server acts as the **default gateway** for the guest WiFi network (bridge/router mode), meaning all guest traffic passes through the portal server at L2. This ensures the portal can read guest MAC addresses directly from the ARP table (`/proc/net/arp`). If deployed behind a separate L3 router, MAC-based enforcement is dropped and IP-only enforcement is used.

### Three Layers

**Network Layer (Ubuntu Linux)**
- `dnsmasq` — DHCP server + DNS redirect (all DNS queries → portal IP to trigger captive portal detection)
- `iptables` — intercept unauthenticated HTTP (port 80) only; whitelist authenticated IPs via FORWARD chain
- `tc` (Linux Traffic Control) — per-IP bandwidth shaping using HTB qdisc + filters
- Session Tracker — maps IP/MAC → session, handles expiry

**HTTPS Strategy:** Only HTTP (port 80) is intercepted. Modern OS captive portal detection uses known HTTP URLs (e.g., `connectivitycheck.gstatic.com`, `captive.apple.com`) which triggers the portal popup automatically. HTTPS traffic is **not** intercepted to avoid TLS errors. Nginx serves the portal on port 80 with optional HTTPS on a proper domain + Let's Encrypt for admin dashboard only.

**Application Layer (FastAPI Modular Monolith)**

| Module | Responsibility |
|--------|---------------|
| `portal/` | Guest-facing login pages, auth flow |
| `admin/` | Dashboard UI, management APIs |
| `network/` | iptables manager, tc bandwidth control, session expiry |
| `pms/` | PMS adapter interface + 5 implementations |
| `voucher/` | Voucher generation, validation, export |
| `core/` | DB models, auth, config, shared utilities |

**Data Layer**
- PostgreSQL — primary data store (native install, not containerized)
- Redis — active session cache, rate limiting, fast IP lookup (native install)
- PMS systems — external (Opera, Cloudbeds, Mews, Custom, Standalone)

**Deployment note:** PostgreSQL and Redis are installed natively on Ubuntu. `docker-compose.yml` is provided as an optional local development convenience only.

---

## 3. Portal API Contracts

### Guest Portal Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/` | Portal login page (redirect target for captive portal) |
| POST | `/auth/room` | Authenticate via room number + last name |
| POST | `/auth/voucher` | Authenticate via voucher code |
| GET | `/session` | Session status page (time remaining, usage) |
| POST | `/session/disconnect` | Guest-initiated disconnect |
| GET | `/success` | Post-auth success page |
| GET | `/expired` | Session expired page |

**POST /auth/room — Request:**
```json
{ "room_number": "101", "last_name": "Smith", "tc_accepted": true }
```
**Response (200):** `{ "session_id": "uuid", "expires_at": "ISO8601", "policy": {...} }`
**Response (401):** `{ "error": "room_not_found" | "guest_not_checked_in" | "pms_unavailable" }`

**POST /auth/voucher — Request:**
```json
{ "code": "VCH-XXXX", "tc_accepted": true }
```
**Response (200):** `{ "session_id": "uuid", "expires_at": "ISO8601", "type": "time|data" }`
**Response (401):** `{ "error": "invalid_code" | "expired" | "no_uses_remaining" }`

**Rate limiting:** Both auth endpoints limited to **5 attempts per IP per 10 minutes** via Redis. Returns HTTP 429 on breach.

### Admin API Endpoints (JWT-protected)

| Method | Path | Description |
|--------|------|-------------|
| POST | `/admin/auth/login` | Admin login → JWT access token |
| POST | `/admin/auth/logout` | Invalidate token (Redis blocklist) |
| GET | `/admin/sessions` | List active sessions |
| DELETE | `/admin/sessions/{id}` | Kick session |
| GET/POST | `/admin/vouchers` | List / create vouchers |
| GET | `/admin/analytics` | Usage analytics |
| GET/PUT | `/admin/pms` | PMS adapter config |
| POST | `/admin/pms/test` | Test PMS connection |
| GET/PUT | `/admin/brand` | Brand settings |
| GET/POST | `/admin/users` | Admin user management |

---

## 4. Authentication Flows

### Flow A — Room Number + Last Name

1. Guest connects to WiFi → dnsmasq assigns IP (DHCP lease = 24h, aligned with max session)
2. Guest opens browser → OS captive portal detection hits HTTP URL → iptables redirects port 80 → FastAPI portal
3. Guest submits room number + last name + T&C acceptance
4. Rate limit check (Redis) → if exceeded return 429
5. FastAPI calls active PMS adapter → `verify_guest(room, last_name)`
6. On success: fetch room policy → create session (expires_at = min(check_out, now + policy.session_duration_min)) → record IP + MAC (from ARP table)
7. `network.iptables.add_whitelist(ip)` + `network.tc.apply_limit(ip, up_kbps, down_kbps)`
8. Redirect to `/success` → internet access granted

### Flow B — Voucher Code

1. Guest connects to WiFi → redirect to portal
2. Guest selects "Voucher Code" tab → submits code
3. Rate limit check (Redis) → validate: code exists, not expired, uses remaining
4. Increment `used_count` → create session → apply voucher policy
5. `network.iptables.add_whitelist(ip)` + `network.tc.apply_limit(ip, ...)`
6. Session expires when: time limit reached, data quota exceeded, or manual kick

### Session Expiry (Three Triggers)

| Trigger | Mechanism |
|---------|-----------|
| PMS check-out sync | Polling every 5 min (all adapters) + webhook where supported (Opera OHIP, Mews) → expire all sessions for room → iptables REMOVE + tc REMOVE |
| Timer | APScheduler checks `expires_at` every 60s → REMOVE expired |
| Admin kick | Dashboard action → iptables REMOVE + tc REMOVE immediately → status = kicked |

**DHCP/IP race condition:** DHCP lease duration (24h) is set longer than the maximum session duration. On session expiry, the iptables FORWARD rule for the IP is removed. If the IP is later reassigned (after a genuine lease expiry), the new client starts with no whitelist entry and must authenticate. This prevents unintended access inheritance.

---

## 5. PMS Adapter Layer

### Interface (Abstract Base Class)

```python
class PMSAdapter(ABC):
    async def verify_guest(self, room: str, last_name: str) -> GuestInfo | None
    async def get_guest_by_room(self, room: str) -> GuestInfo | None
    async def health_check(self) -> bool
    async def get_checkouts_since(self, since: datetime) -> list[str]  # room numbers

@dataclass
class GuestInfo:
    pms_id: str
    room_number: str
    last_name: str
    first_name: str | None   # nullable — not all PMS return this
    check_in: datetime
    check_out: datetime
```

### Adapters

| Adapter | PMS | Auth Method | Checkout Sync |
|---------|-----|-------------|--------------|
| `OperaAdapter` | Oracle OHIP | OAuth2 | Webhook (OHIP events) + poll fallback |
| `CloudbedsAdapter` | Cloudbeds v1 | API Key | Poll every 5 min |
| `MewsAdapter` | Mews Connector | Access Token | Webhook (Mews events) + poll fallback |
| `CustomAdapter` | Any REST API | Bearer/Basic + field mapping | Poll only |
| `StandaloneAdapter` | Local DB | None (admin-managed) | N/A |

**Factory:** On startup, load adapter from `pms_adapters` table where `is_active=true`.
**Fallback:** On PMS timeout/error → retry 2× (500ms backoff) → log error → return auth failure with `pms_unavailable` error (no silent fallback).
**Webhook endpoint:** `POST /internal/pms/webhook/{adapter_id}` — validated via shared secret header `X-PMS-Secret`.

---

## 6. Data Models

### `guests`
| Field | Type | Notes |
|-------|------|-------|
| id | UUID PK | |
| room_number | VARCHAR | |
| last_name | VARCHAR | |
| first_name | VARCHAR | nullable |
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
| mac_address | MACADDR | nullable (L3 topology = null) |
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

**Scope:** `rooms` table is always present. For PMS-connected modes, rooms are synced from PMS on startup + every 6 hours via `PMSAdapter.sync_rooms()` (optional method — not part of core interface). For standalone mode, admin manages rooms manually via dashboard.

### `policies`
| Field | Type | Notes |
|-------|------|-------|
| id | UUID PK | |
| name | VARCHAR | |
| bandwidth_up_kbps | INT | 0 = unlimited |
| bandwidth_down_kbps | INT | 0 = unlimited |
| session_duration_min | INT | 0 = until check-out |
| max_devices | INT | |

### `pms_adapters`
| Field | Type | Notes |
|-------|------|-------|
| id | UUID PK | |
| type | ENUM | opera / cloudbeds / mews / custom / standalone |
| config_encrypted | BYTEA | Fernet-encrypted JSON (api_url, credentials, field_map) |
| is_active | BOOLEAN | |
| last_sync_at | TIMESTAMP | |
| webhook_secret | VARCHAR | hashed, for webhook validation |

**Security:** `config_encrypted` stores PMS credentials encrypted with Fernet (symmetric key stored in `ENCRYPTION_KEY` env var, not in DB). Decrypted only in-memory at runtime.

### `admin_users`
| Field | Type | Notes |
|-------|------|-------|
| id | UUID PK | |
| username | VARCHAR UNIQUE | |
| password_hash | VARCHAR | bcrypt |
| role | ENUM | superadmin / staff |
| last_login_at | TIMESTAMP | |

---

## 7. Admin Authentication (JWT)

- **Access token TTL:** 8 hours (front desk shift duration)
- **No refresh token** — staff re-login after shift; simpler than refresh flow for this use case
- **Logout:** Token added to Redis blocklist with TTL = remaining token lifetime
- **All admin routes:** Validate JWT + check Redis blocklist on each request

---

## 8. Network Control (iptables + tc)

### iptables Rules

```bash
# Redirect unauthenticated HTTP to portal (port 80 only)
iptables -t nat -A PREROUTING -i wlan0 -p tcp --dport 80 \
  -m conntrack ! --ctstate ESTABLISHED -j DNAT --to 192.168.1.1:8080

# Drop unauthenticated forwarding (default)
iptables -A FORWARD -i wlan0 -j DROP

# Allow authenticated IP (added per session by network.iptables module)
iptables -I FORWARD -s <guest_ip> -j ACCEPT

# Remove on expire/kick
iptables -D FORWARD -s <guest_ip> -j ACCEPT
```

### Bandwidth Control (tc HTB)

```bash
# Root qdisc on WAN interface
tc qdisc add dev eth0 root handle 1: htb default 999

# Per-session class (added on auth)
tc class add dev eth0 parent 1: classid 1:<id> htb \
  rate <down_kbps>kbit ceil <down_kbps>kbit
tc filter add dev eth0 parent 1: protocol ip prio 1 \
  u32 match ip dst <guest_ip>/32 flowid 1:<id>

# Remove on expire/kick
tc class del dev eth0 parent 1: classid 1:<id>
tc filter del dev eth0 parent 1: ...
```

`network/tc.py` manages these operations. Class IDs are derived from the last two octets of the guest IP.

---

## 9. Admin Dashboard

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

## 10. Guest Portal

**UI Style:** Split layout — left panel branding, right panel form
**Theme:** Glassmorphism (dark, matches admin)
**Tech:** FastAPI + Jinja2 + Tailwind CSS
**Primary device:** Mobile (responsive — stacks to single column on mobile)

### Pages
1. **Login** — split: left = hotel logo + WiFi info, right = Room+Name form / Voucher tab
2. **Success** — connected confirmation + session info (time remaining, disconnect button)
3. **Expired** — session expired, prompt to reconnect
4. **Error** — auth failed with clear message (wrong room, PMS unavailable, rate limited, etc.)

### Customizable via Admin
- Hotel logo
- Hotel name
- Primary color
- T&C text
- Language (TH / EN)

---

## 11. Project Structure

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
│   │   ├── iptables.py       # add/remove whitelist rules
│   │   ├── tc.py             # bandwidth shaping via tc HTB
│   │   ├── session_manager.py
│   │   └── scheduler.py      # APScheduler expiry jobs
│   ├── pms/
│   │   ├── base.py           # PMSAdapter ABC + GuestInfo
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
│   │   ├── models.py         # SQLAlchemy models
│   │   ├── database.py
│   │   ├── auth.py           # JWT + Redis blocklist
│   │   ├── encryption.py     # Fernet for pms config
│   │   └── config.py         # env var loading
│   └── main.py
├── static/
│   └── css/ js/ img/
├── tests/
│   ├── test_portal.py
│   ├── test_pms/
│   └── test_network.py
├── alembic/
├── scripts/
│   ├── setup-iptables.sh     # initial iptables chain setup
│   └── setup-tc.sh           # initial tc qdisc setup
├── docker-compose.yml        # local dev only (PostgreSQL + Redis)
├── .env.example
└── requirements.txt
```

---

## 12. Environment Configuration

```bash
# .env.example

# Application
SECRET_KEY=<random 32 bytes hex>
ENCRYPTION_KEY=<Fernet key for PMS config encryption>
ENVIRONMENT=production

# Database (native PostgreSQL)
DATABASE_URL=postgresql+asyncpg://user:pass@localhost:5432/captive_portal

# Redis (native)
REDIS_URL=redis://localhost:6379/0

# Network interface names
WIFI_INTERFACE=wlan0       # guest WiFi interface
WAN_INTERFACE=eth0         # internet-facing interface
PORTAL_IP=192.168.1.1      # portal server IP on guest network
PORTAL_PORT=8080           # FastAPI port

# JWT
JWT_ALGORITHM=HS256
JWT_EXPIRE_HOURS=8

# Rate limiting
AUTH_RATE_LIMIT_ATTEMPTS=5
AUTH_RATE_LIMIT_WINDOW_SECONDS=600

# Admin
ADMIN_DEFAULT_USERNAME=admin
ADMIN_DEFAULT_PASSWORD=<set on first run>
```

---

## 13. Tech Stack

| Layer | Technology |
|-------|-----------|
| Web Framework | FastAPI |
| ORM | SQLAlchemy (async) |
| Migrations | Alembic |
| Background Jobs | APScheduler |
| HTTP Client | httpx (async) |
| Admin Auth | JWT (python-jose) + Redis blocklist |
| Credential Encryption | cryptography (Fernet) |
| Password Hashing | bcrypt (passlib) |
| Frontend | Jinja2 + HTMX + Alpine.js + Tailwind CSS |
| Charts | Chart.js |
| Database | PostgreSQL (native) |
| Cache | Redis (native) |
| Network | iptables + tc HTB (bandwidth) |
| DNS/DHCP | dnsmasq |
| Reverse Proxy | Nginx |
| ASGI Server | Uvicorn |
| Testing | pytest + pytest-asyncio + httpx + pytest-cov |
| Deployment | systemd + iptables-persistent + logrotate |

---

## 14. Testing Strategy

- **Unit tests** — PMS adapters (mocked HTTP), voucher generator, session expiry logic, Fernet encryption
- **Integration tests** — FastAPI routes via httpx TestClient, PostgreSQL test DB
- **Network tests** — iptables/tc manager (requires sudo, skipped in CI by default, run manually)
- **Mock adapters** — all PMS adapters have mock implementations for testing without live PMS
- **Rate limit tests** — Redis mock for testing 429 responses

---

## 15. Deployment (Ubuntu)

1. Install: Python 3.11+, PostgreSQL, Redis, dnsmasq, Nginx, iptables-persistent
2. Configure dnsmasq: DHCP range + DNS redirect to portal IP; set lease time = 24h
3. Run `scripts/setup-iptables.sh` — creates FORWARD drop default + nat redirect chain
4. Run `scripts/setup-tc.sh` — creates root HTB qdisc on WAN interface
5. Install `iptables-persistent` — rules survive reboot
6. Configure `.env` from `.env.example`
7. Run `alembic upgrade head` — apply DB migrations
8. Configure Nginx — port 80 → Uvicorn:8080; admin dashboard on HTTPS with Let's Encrypt
9. Enable systemd service — auto-start FastAPI on boot
10. Configure logrotate for `/var/log/captive-portal/`
