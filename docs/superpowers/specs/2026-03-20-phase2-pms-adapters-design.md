# WiFi Captive Portal — Phase 2: PMS Adapters Design Specification

**Date:** 2026-03-20
**Status:** Approved
**Parent Spec:** `2026-03-20-wifi-captive-portal-design.md`
**Phase:** 2 — External PMS Integration

---

## 1. Overview

Phase 2 extends the existing captive portal (Phase 1: Foundation + StandaloneAdapter) with full external PMS integration. Guests at hotels running Opera 5/Suite8, Opera Cloud, Cloudbeds, or Mews can authenticate using their actual reservation data. A configurable CustomAdapter handles any REST-based PMS not covered by the above.

**Components added in Phase 2:**
1. Five new PMS adapters (opera_fias, opera_cloud, cloudbeds, mews, custom)
2. Factory update to instantiate correct adapter from DB config
3. Webhook endpoint for real-time checkout events (Opera Cloud, Mews)
4. Checkout polling scheduler (Cloudbeds, Custom, Opera FIAS)
5. Admin PMS management endpoints (configure, test connection)
6. Alembic migration to extend `PMSAdapterType` enum

---

## 2. Adapter Architecture

### Approach: Singleton Adapter + In-Memory Token Cache

`_active_adapter` is cached in `factory.py` (established in Phase 1). Each adapter instance:
- Receives a decrypted `config: dict` at construction time
- Maintains auth state (OAuth2 token, TCP socket) in instance variables
- Is a singleton for the lifetime of the process — reloaded only when admin changes PMS config

**Rationale:** Single-server hotel deployment. In-memory token cache is sufficient — token is simply re-fetched on restart. No Redis dependency needed in adapter layer.

---

## 3. DB Schema Update

Add two new values to the `PMSAdapterType` enum (Alembic migration required):

```
opera_fias | opera_cloud | cloudbeds | mews | custom | standalone
```

`opera_fias` = OPERA 5 / Suite8 via FIAS TCP socket
`opera_cloud` = OPERA Cloud via OHIP REST API

---

## 4. PMS Adapters

### 4.1 OperaCloudAdapter (`app/pms/opera_cloud.py`)

**Protocol:** HTTPS REST (Oracle OHIP)
**Auth:** OAuth2 Client Credentials

**Token cache strategy:**
- `self._token: str | None` and `self._token_expires_at: datetime | None`
- Before each API call: if token is None or expires within 60 seconds → fetch new token
- Token endpoint: `POST {api_url}/oauth/token` with `grant_type=client_credentials`

**Methods:**

| Method | Endpoint | Filter |
|--------|----------|--------|
| `verify_guest` | `GET /fof/v1/reservations` | `roomNumber`, `familyName`, status `DUE_IN\|IN_HOUSE` |
| `get_guest_by_room` | `GET /fof/v1/reservations` | `roomNumber`, status `IN_HOUSE` |
| `get_checkouts_since` | `GET /fof/v1/reservations` | `departureDate >= since`, status `CHECKED_OUT` |
| `health_check` | `GET /fof/v1/reservations` (limit 1) | — |

**Config keys:** `api_url`, `client_id`, `client_secret`, `hotel_id`

---

### 4.2 OperaFIASAdapter (`app/pms/opera_fias.py`)

**Protocol:** Persistent TCP socket (FIAS — Fidelio Interface Application Specification)
**Auth:** AuthKey exchange on login

FIAS uses a long-lived TCP connection, unlike REST adapters. All requests are serialized over the shared socket using `asyncio.Lock`.

**Connection lifecycle:**
```
factory.load_adapter() → OperaFIASAdapter(config) → await adapter.connect()
  → asyncio.open_connection(host, port)
  → send LR (Login Record) with AuthKey + VendorID
  → await LA (Login Acknowledge)
  → asyncio.create_task(_heartbeat_loop())  # KA every 30s
```

**Methods:**

| Method | FIAS Record | Notes |
|--------|-------------|-------|
| `verify_guest` | GI (Guest Information query) | Match room + last name + arrival/departure dates |
| `get_guest_by_room` | GI | Match room + currently in-house |
| `get_checkouts_since` | DR (Departure Record query) | Filter departure date >= since |
| `health_check` | — | `self._writer is not None and not self._writer.is_closing()` |
| `connect()` | LR → LA | Called by factory after instantiation (not part of ABC) |

**Reconnect:** Scheduler's health check loop calls `adapter.health_check()` every 60s. If False → `await adapter.connect()` to re-establish.

**Config keys:** `host`, `port`, `auth_key`, `vendor_id`

**Key implementation detail:**
```python
self._lock = asyncio.Lock()  # serialize all socket requests
```

---

### 4.3 CloudbedsAdapter (`app/pms/cloudbeds.py`)

**Protocol:** HTTPS REST (Cloudbeds API v1.1)
**Auth:** API Key in `Authorization: Bearer {api_key}` header (stateless — no token cache needed)

**Methods:**

| Method | Endpoint | Filter |
|--------|----------|--------|
| `verify_guest` | `GET /api/v1.1/getReservations` | `roomNumber`, `guestLastName`, `status=checked_in` |
| `get_guest_by_room` | `GET /api/v1.1/getReservations` | `roomNumber`, `status=checked_in` |
| `get_checkouts_since` | `GET /api/v1.1/getReservations` | `departureDate[gte]=since`, `status=checked_out` |
| `health_check` | `GET /api/v1.1/getHotels` | — |

**Config keys:** `api_url` (default: `https://api.cloudbeds.com`), `api_key`, `property_id`

---

### 4.4 MewsAdapter (`app/pms/mews.py`)

**Protocol:** HTTPS REST (Mews Connector API)
**Auth:** `ClientToken` + `AccessToken` embedded in every request body (no separate auth call)

**Methods:**

| Method | Endpoint | Filter |
|--------|----------|--------|
| `verify_guest` | `POST /api/connector/v1/reservations/getAll` | `SpaceIdentifiers` (room), `LastName`, `States: ["Started"]` |
| `get_guest_by_room` | `POST /api/connector/v1/reservations/getAll` | `SpaceIdentifiers`, `States: ["Started"]` |
| `get_checkouts_since` | `POST /api/connector/v1/reservations/getAll` | `EndUtc >= since`, `States: ["Processed"]` |
| `health_check` | `POST /api/connector/v1/configuration/get` | — |

**Config keys:** `api_url` (default: `https://www.mews.li`), `client_token`, `access_token`

---

### 4.5 CustomAdapter (`app/pms/custom.py`)

**Protocol:** HTTPS REST (any PMS with REST API)
**Auth:** Configurable — `bearer` (API key in Authorization header) or `basic` (username + password)

**Field mapping:** `field_map` config key maps PMS response JSON paths to `GuestInfo` fields using dot-notation.

**Config keys:**

| Key | Description |
|-----|-------------|
| `api_url` | Base URL |
| `auth_type` | `bearer` or `basic` |
| `token` | Bearer token (if `auth_type=bearer`) |
| `username` / `password` | Basic auth credentials (if `auth_type=basic`) |
| `verify_endpoint` | Path for `verify_guest` call (e.g., `/reservations/search`) |
| `guest_by_room_endpoint` | Path for `get_guest_by_room` |
| `checkouts_endpoint` | Path for `get_checkouts_since` |
| `health_endpoint` | Path for `health_check` |
| `field_map` | JSON object mapping PMS fields → GuestInfo fields |

**field_map example:**
```json
{
  "pms_id": "data.id",
  "room_number": "data.room",
  "last_name": "data.guest.surname",
  "first_name": "data.guest.given_name",
  "check_in": "data.arrival",
  "check_out": "data.departure"
}
```

---

## 5. Factory Update (`app/pms/factory.py`)

`load_adapter()` updated to instantiate the correct adapter class, with retry:

```python
ADAPTER_MAP = {
    PMSAdapterType.opera_cloud: OperaCloudAdapter,
    PMSAdapterType.opera_fias: OperaFIASAdapter,
    PMSAdapterType.cloudbeds: CloudbedsAdapter,
    PMSAdapterType.mews: MewsAdapter,
    PMSAdapterType.custom: CustomAdapter,
    PMSAdapterType.standalone: StandaloneAdapter,
}
```

**Load flow:**
1. Query `pms_adapters` where `is_active=True`
2. Decrypt `config_encrypted` with Fernet → `config: dict`
3. Instantiate adapter from `ADAPTER_MAP`
4. If `OperaFIASAdapter` → `await adapter.connect()`
5. Health check with retry: up to 3 attempts, 500ms backoff
6. If all attempts fail → log error, store adapter anyway (portal returns `pms_unavailable`)
7. Cache in `_active_adapter`

**Reload trigger:** `PUT /admin/pms` calls `load_adapter(db)` after saving new config.

---

## 6. Webhook Endpoint (`app/pms/webhook_router.py`)

**Path:** `POST /internal/pms/webhook/{adapter_id}`

**Validation:** `X-PMS-Secret` header compared against `pms_adapters.webhook_secret` using `hmac.compare_digest` (timing-safe).

**Flow:**
1. Load `pms_adapters` record by `adapter_id` → 404 if not found
2. Validate secret → 401 if mismatch
3. Parse event body by adapter type:

| PMS | Checkout signal |
|-----|----------------|
| Opera Cloud (OHIP) | `eventType == "CHECKED_OUT"` → extract `roomNumber` |
| Mews | `Type == "ReservationUpdated"` + `State == "Checked_out"` → extract room identifier |

4. For each matched checkout event:
   - Call `session_manager.expire_sessions_for_room(db, room_number)` (see below)
5. Update `pms_adapters.last_sync_at = now`

**`expire_sessions_for_room(db, room_number)`** — new helper added to `app/network/session_manager.py`:
- Query `Session` JOIN `Guest` WHERE `Guest.room_number == room_number` AND `Session.status == active`
- For each session: `iptables.remove_whitelist(session.ip_address)` + `tc.remove_bandwidth_limit(session.ip_address)` + `session.status = expired`
- `await db.commit()`

**Supported adapters:** Opera Cloud, Mews only (Cloudbeds and Custom use polling; FIAS pushes events natively via socket)

---

## 7. Checkout Polling Scheduler

Added as a second APScheduler job in `network/scheduler.py`. Runs every 5 minutes, independent of the existing session expiry job (which runs every 60s).

**Target adapters:** Cloudbeds, Custom, OperaFIAS (FIAS can also receive push events but poll is used as fallback)
**Skip:** OperaCloud, Mews (use webhook)

**Job logic:**
```python
async def poll_checkouts(db):
    adapter = get_adapter()
    if isinstance(adapter, (OperaCloudAdapter, MewsAdapter)):
        return  # webhook-based, no polling needed

    record = await db.scalar(select(PMSAdapterModel).where(PMSAdapterModel.is_active == True))
    last_sync = record.last_sync_at or (datetime.now(timezone.utc) - timedelta(minutes=10))

    try:
        checkouts = await adapter.get_checkouts_since(last_sync)
    except Exception as e:
        logger.error(f"Checkout poll failed: {e}")
        return  # do NOT update last_sync_at — retry with same range next run

    for room in checkouts:
        await expire_sessions_for_room(db, room)
        # expire_sessions_for_room joins Session→Guest by guest_id,
        # filters Guest.room_number == room + Session.status == active,
        # then removes iptables/tc rules and sets status = expired

    record.last_sync_at = datetime.now(timezone.utc)
    await db.commit()
```

**Error handling:** On poll failure, `last_sync_at` is not updated → next poll window automatically covers the missed interval.

---

## 8. Admin PMS Endpoints

Added to `app/admin/router.py`. All endpoints require valid JWT (existing middleware).

### `GET /admin/pms`

Returns current adapter config with credentials masked (`***`).

**Response schema (`PMSConfigResponse`):**
```python
class PMSConfigResponse(BaseModel):
    id: uuid.UUID
    type: PMSAdapterType
    is_active: bool
    last_sync_at: datetime | None
    config: dict  # credentials replaced with "***"
```

---

### `PUT /admin/pms`

Accepts plaintext config → encrypts with Fernet → upserts `pms_adapters` → reloads `_active_adapter`.

**Request schema (`PMSConfigUpdate`):**
```python
class PMSConfigUpdate(BaseModel):
    type: PMSAdapterType
    config: dict  # plaintext credentials — encrypted before DB write
```

**Reload:** Calls `load_adapter(db)` immediately after saving. For `opera_fias`: calls `await adapter.connect()` to establish TCP socket.

---

### `POST /admin/pms/test`

Instantiates a temporary adapter from the provided config (not saved to DB) and calls `health_check()`. Returns result with latency.

**Request:** Same as `PMSConfigUpdate`

**Response schema (`PMSTestResult`):**
```python
class PMSTestResult(BaseModel):
    ok: bool
    latency_ms: float | None = None
    error: str | None = None
```

Returns HTTP 200 always — `ok: false` with `error` string on connection failure (not a 4xx, since the error is in the remote system, not the request).

---

## 9. File Map

```
app/pms/
├── base.py              # unchanged
├── standalone.py        # unchanged
├── opera_cloud.py       # NEW — OHIP REST + OAuth2 token cache
├── opera_fias.py        # NEW — FIAS TCP socket + asyncio.Lock
├── cloudbeds.py         # NEW — Cloudbeds v1.1 REST + API Key
├── mews.py              # NEW — Mews Connector REST + token body
├── custom.py            # NEW — configurable REST + field_map
├── factory.py           # UPDATED — ADAPTER_MAP, retry, FIAS connect
└── webhook_router.py    # NEW — POST /internal/pms/webhook/{adapter_id}

app/admin/
├── router.py            # UPDATED — GET/PUT /admin/pms, POST /admin/pms/test
└── schemas.py           # UPDATED — PMSConfigResponse, PMSConfigUpdate, PMSTestResult

app/network/
├── session_manager.py   # UPDATED — add expire_sessions_for_room(db, room_number)
└── scheduler.py         # UPDATED — add poll_checkouts job (5 min interval)

alembic/versions/
└── xxxx_add_opera_fias_opera_cloud_adapter_types.py  # NEW migration

tests/test_pms/
├── test_opera_cloud.py  # NEW
├── test_opera_fias.py   # NEW
├── test_cloudbeds.py    # NEW
├── test_mews.py         # NEW
├── test_custom.py       # NEW
├── test_factory.py      # UPDATED
└── test_webhook.py      # NEW
```

---

## 10. Testing Strategy

- **All external HTTP adapters:** Mock `httpx.AsyncClient` — test verify_guest success, guest not found, PMS error (500), timeout
- **OperaFIASAdapter:** Mock `asyncio.open_connection` — test login handshake, GI query/response parsing, heartbeat task creation, reconnect on socket close
- **Webhook:** Mock DB + session expiry functions — test valid secret, invalid secret (401), unknown adapter (404), checkout event parsing for each PMS
- **Polling scheduler:** Mock `get_adapter()` + DB — test rooms expire correctly, last_sync_at updates, no update on poll failure
- **Admin endpoints:** Mock factory `load_adapter` + encryption — test credential masking on GET, encryption on PUT, test endpoint returns ok/fail

---

## 11. Dependencies

No new Python packages required — all adapters use `httpx` (already in requirements). `OperaFIASAdapter` uses Python stdlib `asyncio` for TCP.
