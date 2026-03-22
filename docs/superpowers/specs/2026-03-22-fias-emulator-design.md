# Opera FIAS Emulator Design Specification

**Date:** 2026-03-22
**Status:** Draft
**Purpose:** Development/testing tool for simulating Opera FIAS PMS interface

---

## 1. Overview

The FIAS Emulator is a standalone development tool that simulates the Opera FIAS (Fidelio Interface Application Specification) TCP protocol. It allows the main WiFi Captive Portal project to connect to a realistic FIAS server during development and testing without requiring access to a real Opera PMS.

**Key features:**
- Full FIAS TCP protocol implementation
- Web-based dashboard for managing test data
- Predefined test scenarios (happy path, errors, edge cases)
- Failure injection for testing error handling
- SQLite database for persistence

---

## 2. Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                    fias-emulator (FastAPI app)                  │
├─────────────────────────────────────────────────────────────────┤
│  ┌─────────────────┐    ┌─────────────────────────────────────┐│
│  │  FIAS TCP Server│    │     Management API (HTTP)           ││
│  │  (asyncio)      │    │  ┌─────────┐  ┌─────────────────┐  ││
│  │  Port: 9090     │    │  │ REST API│  │ HTMX Dashboard  │  ││
│  │                 │    │  │ /api/*  │  │ Templates/Jinja2│  ││
│  │  - LR/LA login  │    │  └─────────┘  └─────────────────┘  ││
│  │  - KA/KR heart  │    │           Port: 8081               ││
│  │  - GIQ/GI query │    └─────────────────────────────────────┘│
│  │  - DRQ/DR dept  │                                            │
│  │  - LD logout    │                                            │
│  └────────┬────────┘                                            │
│           │                                                     │
│           ▼                                                     │
│  ┌─────────────────────────────────────────────────────────────┐│
│  │              SQLite Database (emulator.db)                  ││
│  │  - guests       - scenarios       - failure_rules           ││
│  │  - connections  - activity_log    - settings                ││
│  └─────────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────────┘
         ▲
         │ TCP FIAS Protocol
         │
┌────────┴────────┐
│  Main Project   │
│  OperaFIASAdapter│
│  (port 9090)    │
└─────────────────┘
```

**Design decisions:**
- Single async process runs both TCP server and HTTP server
- SQLite with `aiosqlite` for async database access
- FIAS server runs as background task on FastAPI startup
- FastAPI + HTMX for lightweight interactive UI

---

## 3. FIAS Protocol

### 3.1 Record Types

| Record | Direction | Format |
|--------|-----------|--------|
| **LR** (Login Request) | IN | `<LR AuthKey="..." VendorID="..."/>` |
| **LA** (Login Acknowledge) | OUT | `<LA Result="OK"/>` or `<LA Result="DENIED"/>` |
| **KA** (Keep-Alive) | IN | `<KA/>` |
| **KR** (Keep-Alive Response) | OUT | `<KR/>` |
| **GIQ** (Guest Info Query) | IN | `<GIQ RoomNumber="101" LastName="Smith"/>` |
| **GI** (Guest Info) | OUT | `<GI ReservationNumber="..." RoomNumber="..." LastName="..." FirstName="..." ArrivalDate="..." DepartureDate="..."/>` |
| **DRQ** (Departure Query) | IN | `<DRQ DepartureDate="03-22-26"/>` |
| **DR** (Departure Record) | OUT | `<DR RoomNumber="101"/>` (multiple records delimited by CRLF) |
| **LD** (Logout) | IN | `<LD/>` |

### 3.2 Protocol Details

- **Transport:** TCP socket
- **Terminator:** `\r\n` (CRLF)
- **Date format:** `%m-%d-%y` (e.g., `03-22-26`)
- **Heartbeat:** Client sends KA every 30 seconds, server responds KR

### 3.3 Guest Not Found Response

When GIQ finds no matching guest:
```xml
<GI Result="NOT_FOUND"/>
```

---

## 4. Database Models

### 4.1 Guest

```python
class Guest(Base):
    __tablename__ = "guests"

    id: int                      # Primary key
    room_number: str             # e.g., "101", "A-205"
    last_name: str               # Required for lookup
    first_name: str | None       # Optional
    reservation_number: str      # PMS reservation ID
    arrival_date: date           # Check-in date
    departure_date: date         # Check-out date
    is_active: bool = True       # Soft delete for "checked out"
    scenario_id: int | None      # Optional scenario grouping
```

### 4.2 Scenario

```python
class Scenario(Base):
    __tablename__ = "scenarios"

    id: int
    name: str                    # "happy_path", "connection_drops", etc.
    description: str
    is_active: bool = False      # Only one active at a time
```

### 4.3 FailureRule

```python
class FailureRule(Base):
    __tablename__ = "failure_rules"

    id: int
    scenario_id: int | None      # Null = global rule

    # When to trigger
    trigger: str                 # "on_login", "on_query", "on_room:101"
    probability: float = 1.0     # 0.0-1.0, chance of firing

    # What action to take
    action: str                  # "drop_connection", "delay:5s", "malformed_xml"

    # Protocol-level failure details
    malformed_type: str | None   # "missing_field", "bad_encoding", "unknown_tag"

    # Business logic failure details
    business_rule: str | None    # "checkout_mid_session", "room_reassign"
```

### 4.4 Connection

```python
class Connection(Base):
    __tablename__ = "connections"

    id: int
    client_host: str
    client_port: int
    connected_at: datetime
    vendor_id: str | None
    is_active: bool = True
```

### 4.5 ActivityLog

```python
class ActivityLog(Base):
    __tablename__ = "activity_log"

    id: int
    connection_id: int
    timestamp: datetime
    direction: str               # "in" or "out"
    record_type: str             # "LR", "GIQ", "GI", etc.
    raw_content: str             # Full XML record
```

---

## 5. Management API

### 5.1 Guest Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/guests` | List all test guests |
| POST | `/api/guests` | Create new test guest |
| PUT | `/api/guests/{id}` | Update guest |
| DELETE | `/api/guests/{id}` | Delete guest |

### 5.2 Scenario Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/scenarios` | List scenarios |
| POST | `/api/scenarios/{id}/activate` | Switch active scenario |

### 5.3 Failure Rule Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/failure-rules` | List failure rules |
| POST | `/api/failure-rules` | Create failure rule |
| DELETE | `/api/failure-rules/{id}` | Delete rule |
| POST | `/api/failure-rules/{id}/trigger` | Manually trigger a failure |

### 5.4 System Endpoints

| Method | Path | Description |
|--------|------|-------------|
| GET | `/api/connections` | List active FIAS connections |
| GET | `/api/activity` | Recent activity log |
| POST | `/api/reset` | Clear all data, reset to defaults |

---

## 6. HTMX Dashboard

### 6.1 Pages

| Path | Page | Description |
|------|------|-------------|
| `/` | Dashboard | Server status, connections, activity feed |
| `/guests` | Guests | Guest management table with add/edit |
| `/scenarios` | Scenarios | Scenario cards with activate buttons |
| `/failures` | Failures | Failure rule editor with trigger buttons |
| `/activity` | Activity | Full activity log with filters |

### 6.2 UI Components

- **Dashboard:** Status cards (server, connections), quick actions, real-time activity feed
- **Guests:** Data table with inline edit, status badges, add/edit forms
- **Scenarios:** Card grid with activate buttons, active scenario highlighted
- **Failures:** Rule list with manual trigger buttons, add/edit form
- **Activity:** Filterable log table with pagination, export to CSV

### 6.3 Styling

- Tailwind CSS for styling
- Dark theme matching main project admin dashboard
- HTMX for dynamic updates without page reload
- Server-Sent Events (SSE) for real-time activity feed

---

## 7. Failure Injection

### 7.1 Trigger Types

| Trigger | Description |
|---------|-------------|
| `on_login` | Fires when LR record received |
| `on_query` | Fires when GIQ record received |
| `on_heartbeat` | Fires when KA record received |
| `on_logout` | Fires when LD record received |
| `on_room:XXX` | Fires only for specific room number |

### 7.2 Action Types

**Connection-level:**
| Action | Description |
|--------|-------------|
| `drop_connection` | Close TCP connection immediately |
| `login_denied` | Return `<LA Result="DENIED"/>` |
| `delay:Xs` | Delay response by X seconds |
| `timeout` | Never respond (client timeout) |

**Protocol-level:**
| Action | Description |
|--------|-------------|
| `malformed_xml:missing_field` | Omit required field from response |
| `malformed_xml:unknown_tag` | Use invalid XML tag name |
| `malformed_xml:bad_encoding` | Send invalid UTF-8 bytes |

**Business-logic:**
| Action | Description |
|--------|-------------|
| `checkout_mid_session` | Mark guest as checked out during active session |
| `room_reassign` | Change guest room number mid-stay |
| `duplicate_reservation` | Return multiple GI records for same query |

---

## 8. Pre-configured Scenarios

| Scenario | Guests | Failures | Purpose |
|----------|--------|----------|---------|
| **Happy Path** | 5 | 0 | Normal guest lookup, all valid credentials |
| **Connection Failures** | 3 | 3 | Drop connection, login denied, timeout |
| **Protocol Errors** | 2 | 4 | Malformed XML, missing fields, bad encoding |
| **Edge Cases** | 8 | 0 | Multi-guest room, same-day turnover, early check-in |
| **Business Logic** | 4 | 2 | Mid-session checkout, room reassignment |

---

## 9. Dev Script Integration

```bash
# scripts/dev-with-emulator.sh

#!/bin/bash
# Starts both main portal and FIAS emulator for development

# Kill existing processes
pkill -f "uvicorn app.main:app" 2>/dev/null
pkill -f "uvicorn emulator.main:app" 2>/dev/null

# Start FIAS emulator
cd tools/fias-emulator
source .venv/bin/activate
export FIAS_TCP_PORT=9090
export FIAS_HTTP_PORT=8081
uvicorn emulator.main:app --host 0.0.0.0 --port 8081 &
EMULATOR_PID=$!
cd ../..

# Start main portal
source .venv/bin/activate
export PMS_TYPE=opera_fias
export PMS_HOST=localhost
export PMS_PORT=9090
export PMS_AUTH_KEY=dev-test-key
export PMS_VENDOR_ID=wifi-portal-dev
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080

# Cleanup
trap "kill $EMULATOR_PID 2>/dev/null" EXIT
```

**Services:**
| Service | Port | Purpose |
|---------|------|---------|
| Main Portal | 8080 | Captive portal app |
| FIAS Emulator HTTP | 8081 | Management UI + API |
| FIAS Emulator TCP | 9090 | FIAS protocol server |

---

## 10. File Structure

```
tools/fias-emulator/
├── pyproject.toml
├── emulator/
│   ├── __init__.py
│   ├── config.py
│   ├── database.py
│   ├── models.py
│   ├── fias_server.py
│   ├── management.py
│   ├── templates/
│   │   ├── base.html
│   │   ├── dashboard.html
│   │   ├── guests.html
│   │   ├── scenarios.html
│   │   ├── failures.html
│   │   └── activity.html
│   └── static/
│       └── css/
├── data/
│   └── emulator.db
├── tests/
│   ├── __init__.py
│   ├── test_fias_server.py
│   ├── test_management_api.py
│   └── test_failure_injection.py
└── README.md
```

---

## 11. Dependencies

```
# pyproject.toml dependencies
fastapi
uvicorn
jinja2
python-multipart
sqlalchemy
aiosqlite
pydantic
httpx  # for testing
pytest
pytest-asyncio
```

---

## 12. Testing Strategy

### 12.1 Unit Tests

- **FIAS Server:** Mock TCP connections, test record parsing and response generation
- **Management API:** Test CRUD operations for guests, scenarios, failure rules
- **Failure Injection:** Test each failure type triggers correctly

### 12.2 Integration Tests

- **End-to-end:** Main project's `OperaFIASAdapter` connects to emulator
- **Scenario switching:** Verify scenario activation loads correct guest data
- **Failure scenarios:** Verify main project handles failures gracefully

---

## 13. Future Enhancements (Out of Scope)

- Real-time connection visualization
- FIAS message recording/playback
- Multiple concurrent client support with isolation
- Export/import scenario configurations
