# FIAS Emulator

A standalone Python application that emulates the Opera FIAS (Fidelio Interface Application Specification) TCP protocol for testing captive portal PMS integration.

## Overview

The FIAS Emulator simulates a hotel Property Management System (PMS) that speaks the FIAS TCP protocol. It allows you to test your captive portal's PMS integration without needing access to a real Opera PMS system.

### Features

- **TCP Protocol Server**: Implements the FIAS XML-based protocol over TCP
- **HTTP Management API**: RESTful API for managing test data
- **HTMX Dashboard**: Web UI for real-time monitoring and configuration
- **Pre-configured Scenarios**: Ready-to-use test scenarios for common cases
- **Failure Injection**: Simulate network issues, malformed responses, and timeouts
- **Activity Logging**: Track all FIAS messages for debugging

## Quick Start

### Prerequisites

- Python 3.10+
- Virtual environment (recommended)

### Running with the Main Portal

The easiest way to run the emulator is with the dev script from the project root:

```bash
# From the WiFi_Captive_Portal root directory
./scripts/dev-with-emulator.sh
```

This starts both the main captive portal and the FIAS emulator with proper configuration.

### Running Standalone

```bash
cd tools/fias-emulator

# Create and activate virtual environment
python -m venv .venv
source .venv/bin/activate

# Install dependencies
pip install -e .

# (Optional) Seed pre-configured scenarios
python -m emulator.seed_data

# Run the emulator
uvicorn emulator.main:app --host 0.0.0.0 --port 8081
```

## Services

| Service | Port | Purpose |
|---------|------|---------|
| HTTP Management API | 8081 | REST API + Dashboard UI |
| FIAS TCP Server | 9090 | FIAS protocol server |

When using `dev-with-emulator.sh`, an additional service runs:

| Service | Port | Purpose |
|---------|------|---------|
| Main Portal | 8080 | Captive portal application |

## Configuration

Configuration is loaded from environment variables:

| Variable | Default | Description |
|----------|---------|-------------|
| `FIAS_TCP_HOST` | `0.0.0.0` | TCP server bind address |
| `FIAS_TCP_PORT` | `9090` | TCP server port |
| `HTTP_HOST` | `0.0.0.0` | HTTP API bind address |
| `HTTP_PORT` | `8081` | HTTP API port |
| `DATABASE_URL` | `sqlite+aiosqlite:///./fias_emulator.db` | Database connection URL |
| `AUTH_KEY` | `""` | FIAS authentication key (optional) |
| `VENDOR_ID` | `FIAS_EMULATOR` | FIAS vendor identifier |

## Pre-configured Scenarios

The emulator includes five pre-configured test scenarios:

### happy_path
Normal guest lookup with valid credentials. All guests have proper check-in/check-out dates. No failures.

**Guests**: 5 (rooms 101-103, 201-202)
**Failure Rules**: 0

Use this for basic functionality testing.

### connection_failures
Test connection drops, login denials, and timeouts.

**Guests**: 3 (rooms 301-303)
**Failure Rules**: 3
- 30% chance of connection drop on login
- 20% chance of login denied
- 25% chance of timeout on query

### protocol_errors
Test malformed XML responses, missing fields, bad encoding, and delays.

**Guests**: 2 (rooms 401-402)
**Failure Rules**: 4
- 25% chance of missing field in response
- 25% chance of unknown XML tag
- 25% chance of bad encoding
- 100% chance of response delay

### edge_cases
Complex guest data: multi-guest rooms, same-day turnover, early check-ins.

**Guests**: 8 (rooms 501-503, 601-603)
**Failure Rules**: 0

Test cases include:
- Multi-guest room (room 501: Martinez family)
- Same-day turnover (room 502: Robinson checking out, Clark checking in)
- Early check-in (room 503)
- Long-term stay (room 601: 28 days)
- Short stay (room 602: 1 night)
- Future reservation (room 603)

### business_logic
Test mid-session checkout and room reassignment scenarios.

**Guests**: 4 (rooms 701-704)
**Failure Rules**: 2
- 50% chance of mid-session checkout
- 50% chance of room reassignment

## API Reference

### Guests

#### `GET /api/guests`
List all test guests.

**Query Parameters**:
- `is_active` (bool, optional): Filter by active status
- `scenario_id` (int, optional): Filter by scenario

**Response**: `list[GuestResponse]`

```json
[
  {
    "id": 1,
    "room_number": "101",
    "last_name": "Smith",
    "first_name": "John",
    "reservation_number": "RES001",
    "arrival_date": "2024-03-20",
    "departure_date": "2024-03-25",
    "is_active": true,
    "scenario_id": 1
  }
]
```

#### `POST /api/guests`
Create a new test guest.

**Request Body**: `GuestCreate`

```json
{
  "room_number": "101",
  "last_name": "Smith",
  "first_name": "John",
  "reservation_number": "RES001",
  "arrival_date": "2024-03-20",
  "departure_date": "2024-03-25",
  "is_active": true,
  "scenario_id": null
}
```

**Response**: `GuestResponse` (201 Created)

#### `GET /api/guests/{guest_id}`
Get a specific guest by ID.

**Response**: `GuestResponse`

#### `PUT /api/guests/{guest_id}`
Update a guest. All fields are optional.

**Request Body**: `GuestUpdate`

**Response**: `GuestResponse`

#### `DELETE /api/guests/{guest_id}`
Delete a guest.

**Response**: `{"message": "Guest deleted", "id": 1}`

### Scenarios

#### `GET /api/scenarios`
List all scenarios with guest and failure rule counts.

**Response**: `list[ScenarioResponse]`

```json
[
  {
    "id": 1,
    "name": "happy_path",
    "description": "Normal guest lookup...",
    "is_active": true,
    "guest_count": 5,
    "failure_rule_count": 0
  }
]
```

#### `POST /api/scenarios/{scenario_id}/activate`
Activate a scenario (deactivates all others).

**Response**: `{"message": "Scenario 'happy_path' activated", "id": 1}`

### Failure Rules

#### `GET /api/failure-rules`
List all failure rules.

**Query Parameters**:
- `scenario_id` (int, optional): Filter by scenario

**Response**: `list[FailureRuleResponse]`

```json
[
  {
    "id": 1,
    "scenario_id": 2,
    "trigger": "on_login",
    "action": "drop_connection",
    "probability": 0.3,
    "malformed_type": null,
    "business_rule": null
  }
]
```

#### `POST /api/failure-rules`
Create a new failure rule.

**Request Body**: `FailureRuleCreate`

```json
{
  "scenario_id": 1,
  "trigger": "on_query",
  "action": "delay:5s",
  "probability": 0.5,
  "malformed_type": null,
  "business_rule": null
}
```

**Response**: `FailureRuleResponse` (201 Created)

**Trigger Types**:
- `on_login` - Fires on FIAS login request
- `on_query` - Fires on guest info query
- `on_heartbeat` - Fires on keep-alive
- `on_room:{number}` - Fires on query for specific room (e.g., `on_room:101`)

**Action Types**:
- `drop_connection` - Close the TCP connection
- `login_denied` - Return login denied response
- `timeout` - Never respond
- `delay:{seconds}s` - Delay response (e.g., `delay:5s`)
- `malformed_xml` - Return malformed XML response

**Malformed Types** (for `malformed_xml` action):
- `missing_field` - Remove a random attribute
- `bad_encoding` - Insert invalid bytes
- `unknown_tag` - Change tag name to unknown

#### `DELETE /api/failure-rules/{rule_id}`
Delete a failure rule.

**Response**: `{"message": "Failure rule deleted", "id": 1}`

#### `POST /api/failure-rules/{rule_id}/trigger`
Manually trigger a failure rule for testing.

**Response**: Information about the triggered rule

### Connections

#### `GET /api/connections`
List FIAS TCP connections.

**Query Parameters**:
- `is_active` (bool, optional): Filter by active status
- `limit` (int, default 100): Maximum results

**Response**: `list[ConnectionResponse]`

```json
[
  {
    "id": 1,
    "client_host": "127.0.0.1",
    "client_port": 54321,
    "connected_at": "2024-03-22T10:30:00Z",
    "vendor_id": "wifi-portal-dev",
    "is_active": true
  }
]
```

### Activity Logs

#### `GET /api/activity`
List recent FIAS activity log entries.

**Query Parameters**:
- `connection_id` (int, optional): Filter by connection
- `direction` (str, optional): Filter by direction (`in` or `out`)
- `record_type` (str, optional): Filter by record type (`LR`, `GIQ`, `GI`, etc.)
- `limit` (int, default 100): Maximum results

**Response**: `list[ActivityLogResponse]`

```json
[
  {
    "id": 1,
    "connection_id": 1,
    "timestamp": "2024-03-22T10:30:01Z",
    "direction": "in",
    "record_type": "LR",
    "raw_content": "<LR AuthKey=\"test\" VendorID=\"dev\"/>"
  }
]
```

#### `GET /api/activity/stream`
Server-Sent Events endpoint for real-time activity feed.

Connect to receive real-time updates about FIAS activity.

### Reset

#### `POST /api/reset`
Clear all data and reset to defaults.

Deletes all guests, connections, activity logs, and failure rules, then deactivates all scenarios.

**Response**: `ResetResponse`

```json
{
  "message": "All data cleared and reset to defaults",
  "guests_cleared": 22,
  "connections_cleared": 5,
  "activity_logs_cleared": 150
}
```

### Health Check

#### `GET /health`
Health check endpoint.

**Response**:
```json
{
  "status": "healthy",
  "fias_server_running": true,
  "tcp_port": 9090,
  "http_port": 8081
}
```

## FIAS Protocol Support

The emulator supports the following FIAS record types:

| Record | Direction | Description |
|--------|-----------|-------------|
| `LR` | In | Login Request |
| `LA` | Out | Login Acknowledgment |
| `KA` | In | Keep-Alive |
| `KR` | Out | Keep-Alive Response |
| `GIQ` | In | Guest Info Query |
| `GI` | Out | Guest Info Response |
| `DRQ` | In | Departure Query |
| `DR` | Out | Departure Response |
| `LD` | In | Logout |

### Example FIAS Exchange

```
Client -> Server:  <LR AuthKey="dev-test-key" VendorID="wifi-portal"/>
Server -> Client:  <LA Result="OK"/>

Client -> Server:  <GIQ RoomNumber="101" LastName="Smith"/>
Server -> Client:  <GI ReservationNumber="RES001" RoomNumber="101" LastName="Smith" FirstName="John" ArrivalDate="03-20-24" DepartureDate="03-25-24"/>

Client -> Server:  <KA/>
Server -> Client:  <KR/>

Client -> Server:  <LD/>
```

## Development

### Running Tests

```bash
# Activate virtual environment
source .venv/bin/activate

# Run all tests
pytest tests/ -v

# Run with coverage
pytest tests/ --cov=emulator --cov-report=term-missing
```

### Project Structure

```
tools/fias-emulator/
  emulator/
    __init__.py
    config.py        # Pydantic settings
    database.py      # SQLAlchemy async setup
    models.py        # ORM models
    schemas.py       # Pydantic schemas
    fias_server.py   # TCP protocol handler
    management.py    # REST API routes
    main.py          # FastAPI app entry point
    seed_data.py     # Pre-configured scenarios
    templates/       # HTMX dashboard templates
  tests/
    test_*.py
  fias_emulator.db   # SQLite database
  pyproject.toml
  README.md
```

## Troubleshooting

### Port Already in Use

If ports 8081 or 9090 are already in use:

```bash
# Find and kill processes using the ports
lsof -ti:8081 | xargs kill
lsof -ti:9090 | xargs kill
```

### Database Issues

To reset the database:

```bash
# Delete the database file
rm fias_emulator.db

# Re-seed the data
python -m emulator.seed_data
```

### Connection Refused

Ensure the emulator is running before starting the main portal:

```bash
# Check emulator health
curl http://localhost:8081/health
```
