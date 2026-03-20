# Phase 2: PMS Adapters Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Connect the captive portal to 5 external PMS systems (Opera Cloud, Opera FIAS, Cloudbeds, Mews, Custom) plus webhook checkout sync, polling scheduler, and admin PMS management endpoints.

**Architecture:** Singleton adapter pattern — factory decrypts config from DB, instantiates the correct adapter class, caches in `_active_adapter`. REST adapters use `httpx.AsyncClient` per call; OperaFIAS uses a persistent asyncio TCP socket. Checkout sync via webhook (Opera Cloud, Mews) or polling every 5 min (Cloudbeds, Custom, Opera FIAS). New `expire_sessions_for_room()` helper on `SessionManager` shared by both paths.

**Tech Stack:** FastAPI, SQLAlchemy async, httpx, asyncio TCP (stdlib), APScheduler, cryptography (Fernet), Alembic, pytest + pytest-asyncio

---

## File Map

```
app/core/models.py              MODIFY — add opera_fias, opera_cloud to PMSAdapterType enum
app/pms/opera_cloud.py          CREATE — OHIP REST adapter, OAuth2 token cache
app/pms/opera_fias.py           CREATE — FIAS TCP socket adapter, asyncio persistent connection
app/pms/cloudbeds.py            CREATE — Cloudbeds v1.1 REST adapter, API key
app/pms/mews.py                 CREATE — Mews Connector REST adapter, token in body
app/pms/custom.py               CREATE — configurable REST adapter, field_map JSON path
app/pms/factory.py              MODIFY — ADAPTER_MAP, decrypt config, retry, FIAS connect()
app/pms/webhook_router.py       CREATE — POST /internal/pms/webhook/{adapter_id}
app/network/session_manager.py  MODIFY — add expire_sessions_for_room()
app/network/scheduler.py        MODIFY — add poll_checkouts job (every 300s)
app/admin/router.py             MODIFY — GET/PUT /admin/pms, POST /admin/pms/test
app/admin/schemas.py            CREATE — PMSConfigResponse, PMSConfigUpdate, PMSTestResult
app/main.py                     MODIFY — include webhook_router
alembic/versions/               CREATE — migration: add opera_fias, opera_cloud enum values

tests/test_pms/test_opera_cloud.py   CREATE
tests/test_pms/test_opera_fias.py    CREATE
tests/test_pms/test_cloudbeds.py     CREATE
tests/test_pms/test_mews.py          CREATE
tests/test_pms/test_custom.py        CREATE
tests/test_pms/test_factory.py       CREATE
tests/test_pms/test_webhook.py       CREATE
tests/test_network/test_session_manager.py  MODIFY — add expire_sessions_for_room tests
tests/test_admin/test_pms_admin.py   CREATE
```

---

## Task 1: DB Migration — Extend PMSAdapterType Enum

**Files:**
- Modify: `app/core/models.py`
- Create: `alembic/versions/xxxx_add_opera_fias_opera_cloud_adapter_types.py`

- [ ] **Step 1: Add new values to Python enum in models.py**

In `app/core/models.py`, update `PMSAdapterType`:

```python
class PMSAdapterType(enum.Enum):
    opera = "opera"              # legacy — keep for DB compat, unused by adapters
    opera_fias = "opera_fias"   # NEW: OPERA 5/Suite8 via FIAS TCP
    opera_cloud = "opera_cloud" # NEW: OPERA Cloud via OHIP REST
    cloudbeds = "cloudbeds"
    mews = "mews"
    custom = "custom"
    standalone = "standalone"
```

- [ ] **Step 2: Create Alembic migration**

```bash
source .venv/bin/activate
alembic revision --autogenerate -m "add_opera_fias_opera_cloud_adapter_types"
```

Autogenerate will likely produce an empty migration (PostgreSQL enums aren't auto-detected for new values). Open the generated file and replace its `upgrade`/`downgrade` with:

```python
def upgrade() -> None:
    op.execute("ALTER TYPE pmsadaptertype ADD VALUE IF NOT EXISTS 'opera_fias'")
    op.execute("ALTER TYPE pmsadaptertype ADD VALUE IF NOT EXISTS 'opera_cloud'")

def downgrade() -> None:
    # PostgreSQL does not support removing enum values; downgrade is a no-op
    pass
```

> **Note on enum type name:** SQLAlchemy names the PG enum type from the Python class name, lowercased: `PMSAdapterType` → `pmsadaptertype`. If `alembic upgrade head` errors with "type does not exist", check the actual type name with: `SELECT typname FROM pg_type WHERE typtype='e';`

- [ ] **Step 3: Run migration**

```bash
alembic upgrade head
```

Expected: `Running upgrade ... -> xxxx, add_opera_fias_opera_cloud_adapter_types`

- [ ] **Step 4: Verify enum values in DB**

```bash
python -c "
from app.core.models import PMSAdapterType
print([e.value for e in PMSAdapterType])
"
```

Expected: `['opera', 'opera_fias', 'opera_cloud', 'cloudbeds', 'mews', 'custom', 'standalone']`

- [ ] **Step 5: Commit**

```bash
git add app/core/models.py alembic/versions/
git commit -m "feat: add opera_fias and opera_cloud to PMSAdapterType enum"
```

---

## Task 2: expire_sessions_for_room() Helper

Used by both webhook and polling scheduler. Joins `Session → Guest` since `Session` has no direct `room_number` field.

**Files:**
- Modify: `app/network/session_manager.py`
- Modify: `tests/test_network/test_session_manager.py`

- [ ] **Step 1: Write failing tests**

Add to `tests/test_network/test_session_manager.py`:

```python
@pytest.mark.asyncio
async def test_expire_sessions_for_room_expires_active_sessions(manager):
    from app.core.models import Guest, SessionStatus
    mock_session_1 = MagicMock()
    mock_session_1.ip_address = "192.168.1.10"
    mock_session_2 = MagicMock()
    mock_session_2.ip_address = "192.168.1.11"

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_session_1, mock_session_2]
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.commit = AsyncMock()

    with patch("app.network.session_manager.remove_whitelist") as mock_ipt, \
         patch("app.network.session_manager.remove_bandwidth_limit") as mock_tc:
        count = await manager.expire_sessions_for_room(mock_db, "101")

    assert count == 2
    assert mock_ipt.call_count == 2
    assert mock_tc.call_count == 2

@pytest.mark.asyncio
async def test_expire_sessions_for_room_returns_zero_when_no_sessions(manager):
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    count = await manager.expire_sessions_for_room(mock_db, "999")
    assert count == 0
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_network/test_session_manager.py::test_expire_sessions_for_room_expires_active_sessions -v
```

Expected: `FAILED` — `AttributeError: 'SessionManager' object has no attribute 'expire_sessions_for_room'`

- [ ] **Step 3: Implement expire_sessions_for_room**

Add to `SessionManager` class in `app/network/session_manager.py`:

```python
from sqlalchemy.orm import joinedload
from app.core.models import Guest

async def expire_sessions_for_room(self, db: AsyncSession, room_number: str) -> int:
    """Expire all active sessions for guests in the given room number."""
    result = await db.execute(
        select(Session)
        .join(Guest, Session.guest_id == Guest.id)
        .where(
            Guest.room_number == room_number,
            Session.status == SessionStatus.active,
        )
    )
    sessions = result.scalars().all()
    for s in sessions:
        await self.expire_session(db, s)
    return len(sessions)
```

Also add `Guest` to the existing import line at the top of session_manager.py:
```python
from app.core.models import Session, SessionStatus, Guest
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_network/test_session_manager.py -v
```

Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add app/network/session_manager.py tests/test_network/test_session_manager.py
git commit -m "feat: add expire_sessions_for_room to SessionManager"
```

---

## Task 3: OperaCloudAdapter

Oracle OHIP REST API. OAuth2 client credentials. Token cached in instance variables.

**Files:**
- Create: `app/pms/opera_cloud.py`
- Create: `tests/test_pms/test_opera_cloud.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_pms/test_opera_cloud.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta, timezone
from app.pms.opera_cloud import OperaCloudAdapter
from app.pms.base import GuestInfo

CONFIG = {
    "api_url": "https://opera.example.com",
    "client_id": "client123",
    "client_secret": "secret123",
    "hotel_id": "HOTEL1",
}

TOKEN_RESP = {"access_token": "tok123", "expires_in": 3600}

RESERVATION_RESP = {
    "reservations": [{
        "reservationId": "R001",
        "roomNumber": "101",
        "guest": {"surname": "Smith", "givenName": "John"},
        "arrivalDate": "2026-03-19T14:00:00Z",
        "departureDate": "2026-03-22T12:00:00Z",
    }]
}

def _make_mock_client(post_json=None, get_json=None):
    mock_resp = MagicMock()
    mock_resp.raise_for_status = MagicMock()
    mock_resp.json.side_effect = [post_json, get_json] if post_json else [get_json]
    mock_client = AsyncMock()
    mock_client.post = AsyncMock(return_value=mock_resp)
    mock_client.get = AsyncMock(return_value=mock_resp)
    return mock_client

@pytest.mark.asyncio
async def test_verify_guest_success():
    adapter = OperaCloudAdapter(CONFIG)
    with patch("app.pms.opera_cloud.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        token_mock = MagicMock()
        token_mock.raise_for_status = MagicMock()
        token_mock.json.return_value = TOKEN_RESP
        mock_client.post = AsyncMock(return_value=token_mock)

        guest_mock = MagicMock()
        guest_mock.raise_for_status = MagicMock()
        guest_mock.json.return_value = RESERVATION_RESP
        mock_client.get = AsyncMock(return_value=guest_mock)

        result = await adapter.verify_guest("101", "Smith")

    assert isinstance(result, GuestInfo)
    assert result.room_number == "101"
    assert result.last_name == "Smith"
    assert result.pms_id == "R001"

@pytest.mark.asyncio
async def test_verify_guest_not_found():
    adapter = OperaCloudAdapter(CONFIG)
    adapter._token = "cached_tok"
    adapter._token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    with patch("app.pms.opera_cloud.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)

        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"reservations": []}
        mock_client.get = AsyncMock(return_value=resp)

        result = await adapter.verify_guest("999", "Nobody")

    assert result is None

@pytest.mark.asyncio
async def test_health_check_returns_true():
    adapter = OperaCloudAdapter(CONFIG)
    adapter._token = "cached_tok"
    adapter._token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    with patch("app.pms.opera_cloud.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"reservations": []}
        mock_client.get = AsyncMock(return_value=resp)

        result = await adapter.health_check()
    assert result is True

@pytest.mark.asyncio
async def test_health_check_returns_false_on_error():
    adapter = OperaCloudAdapter(CONFIG)
    adapter._token = "cached_tok"
    adapter._token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    with patch("app.pms.opera_cloud.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(side_effect=Exception("connection refused"))

        result = await adapter.health_check()
    assert result is False

@pytest.mark.asyncio
async def test_token_cached_not_refetched():
    adapter = OperaCloudAdapter(CONFIG)
    adapter._token = "existing_tok"
    adapter._token_expires_at = datetime.now(timezone.utc) + timedelta(hours=1)

    with patch("app.pms.opera_cloud.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"reservations": []}
        mock_client.get = AsyncMock(return_value=resp)

        await adapter.verify_guest("101", "Smith")

    # post (token) should NOT have been called
    mock_client.post.assert_not_called()
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_pms/test_opera_cloud.py -v
```

Expected: `FAILED` — `ModuleNotFoundError: No module named 'app.pms.opera_cloud'`

- [ ] **Step 3: Implement OperaCloudAdapter**

Create `app/pms/opera_cloud.py`:

```python
import httpx
import logging
from datetime import datetime, timedelta, timezone
from app.pms.base import PMSAdapter, GuestInfo

logger = logging.getLogger(__name__)


class OperaCloudAdapter(PMSAdapter):
    """Oracle OHIP REST adapter. OAuth2 client credentials with in-memory token cache."""

    def __init__(self, config: dict):
        self._config = config
        self._token: str | None = None
        self._token_expires_at: datetime | None = None

    async def _get_token(self) -> str:
        now = datetime.now(timezone.utc)
        if self._token and self._token_expires_at and self._token_expires_at > now + timedelta(seconds=60):
            return self._token
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._config['api_url']}/oauth/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._config["client_id"],
                    "client_secret": self._config["client_secret"],
                },
                timeout=10.0,
            )
            resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expires_at = now + timedelta(seconds=data["expires_in"])
        return self._token

    def _parse_reservation(self, res: dict) -> GuestInfo:
        guest = res.get("guest", {})
        return GuestInfo(
            pms_id=res["reservationId"],
            room_number=res["roomNumber"],
            last_name=guest.get("surname", ""),
            first_name=guest.get("givenName"),
            check_in=datetime.fromisoformat(res["arrivalDate"].replace("Z", "+00:00")),
            check_out=datetime.fromisoformat(res["departureDate"].replace("Z", "+00:00")),
        )

    async def verify_guest(self, room: str, last_name: str, **kwargs) -> GuestInfo | None:
        token = await self._get_token()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._config['api_url']}/fof/v1/reservations",
                headers={
                    "Authorization": f"Bearer {token}",
                    "x-hotel-id": self._config["hotel_id"],
                },
                params={"roomNumber": room, "familyName": last_name, "reservationStatus": "DUE_IN|IN_HOUSE"},
                timeout=10.0,
            )
            resp.raise_for_status()
        reservations = resp.json().get("reservations", [])
        if not reservations:
            return None
        return self._parse_reservation(reservations[0])

    async def get_guest_by_room(self, room: str, **kwargs) -> GuestInfo | None:
        token = await self._get_token()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._config['api_url']}/fof/v1/reservations",
                headers={
                    "Authorization": f"Bearer {token}",
                    "x-hotel-id": self._config["hotel_id"],
                },
                params={"roomNumber": room, "reservationStatus": "IN_HOUSE"},
                timeout=10.0,
            )
            resp.raise_for_status()
        reservations = resp.json().get("reservations", [])
        if not reservations:
            return None
        return self._parse_reservation(reservations[0])

    async def get_checkouts_since(self, since: datetime, **kwargs) -> list[str]:
        token = await self._get_token()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._config['api_url']}/fof/v1/reservations",
                headers={
                    "Authorization": f"Bearer {token}",
                    "x-hotel-id": self._config["hotel_id"],
                },
                params={
                    "departureDate": since.strftime("%Y-%m-%d"),
                    "reservationStatus": "CHECKED_OUT",
                },
                timeout=10.0,
            )
            resp.raise_for_status()
        return [r["roomNumber"] for r in resp.json().get("reservations", [])]

    async def health_check(self) -> bool:
        try:
            token = await self._get_token()
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self._config['api_url']}/fof/v1/reservations",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "x-hotel-id": self._config["hotel_id"],
                    },
                    params={"limit": "1"},
                    timeout=5.0,
                )
                resp.raise_for_status()
            return True
        except Exception as e:
            logger.warning(f"OperaCloud health check failed: {e}")
            return False
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_pms/test_opera_cloud.py -v
```

Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add app/pms/opera_cloud.py tests/test_pms/test_opera_cloud.py
git commit -m "feat: OperaCloudAdapter — OHIP REST + OAuth2 token cache"
```

---

## Task 4: CloudbedsAdapter

**Files:**
- Create: `app/pms/cloudbeds.py`
- Create: `tests/test_pms/test_cloudbeds.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_pms/test_cloudbeds.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.pms.cloudbeds import CloudbedsAdapter
from app.pms.base import GuestInfo

CONFIG = {"api_url": "https://api.cloudbeds.com", "api_key": "key123", "property_id": "P1"}

RESERVATION_RESP = {
    "success": True,
    "data": [{
        "reservationID": "CB001",
        "roomID": "101",
        "guestLastName": "Smith",
        "guestFirstName": "John",
        "startDate": "2026-03-19",
        "endDate": "2026-03-22",
    }]
}

@pytest.mark.asyncio
async def test_verify_guest_success():
    adapter = CloudbedsAdapter(CONFIG)
    with patch("app.pms.cloudbeds.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = RESERVATION_RESP
        mock_client.get = AsyncMock(return_value=resp)

        result = await adapter.verify_guest("101", "Smith")

    assert isinstance(result, GuestInfo)
    assert result.room_number == "101"
    assert result.last_name == "Smith"

@pytest.mark.asyncio
async def test_verify_guest_not_found():
    adapter = CloudbedsAdapter(CONFIG)
    with patch("app.pms.cloudbeds.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"success": True, "data": []}
        mock_client.get = AsyncMock(return_value=resp)

        result = await adapter.verify_guest("999", "Nobody")
    assert result is None

@pytest.mark.asyncio
async def test_health_check_true():
    adapter = CloudbedsAdapter(CONFIG)
    with patch("app.pms.cloudbeds.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"success": True}
        mock_client.get = AsyncMock(return_value=resp)

        result = await adapter.health_check()
    assert result is True

@pytest.mark.asyncio
async def test_health_check_false_on_error():
    adapter = CloudbedsAdapter(CONFIG)
    with patch("app.pms.cloudbeds.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        mock_client.get = AsyncMock(side_effect=Exception("timeout"))

        result = await adapter.health_check()
    assert result is False
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_pms/test_cloudbeds.py -v
```

Expected: `FAILED` — `ModuleNotFoundError`

- [ ] **Step 3: Implement CloudbedsAdapter**

Create `app/pms/cloudbeds.py`:

```python
import httpx
import logging
from datetime import datetime, timezone
from app.pms.base import PMSAdapter, GuestInfo

logger = logging.getLogger(__name__)


class CloudbedsAdapter(PMSAdapter):
    """Cloudbeds v1.1 REST adapter. API key in Authorization header."""

    def __init__(self, config: dict):
        self._config = config
        self._headers = {"Authorization": f"Bearer {config['api_key']}"}

    def _base_url(self) -> str:
        return self._config.get("api_url", "https://api.cloudbeds.com")

    def _parse(self, r: dict) -> GuestInfo:
        return GuestInfo(
            pms_id=r["reservationID"],
            room_number=r["roomID"],
            last_name=r["guestLastName"],
            first_name=r.get("guestFirstName"),
            check_in=datetime.fromisoformat(r["startDate"]).replace(tzinfo=timezone.utc),
            check_out=datetime.fromisoformat(r["endDate"]).replace(tzinfo=timezone.utc),
        )

    async def verify_guest(self, room: str, last_name: str, **kwargs) -> GuestInfo | None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url()}/api/v1.1/getReservations",
                headers=self._headers,
                params={
                    "propertyID": self._config["property_id"],
                    "roomID": room,
                    "guestLastName": last_name,
                    "status": "checked_in",
                },
                timeout=10.0,
            )
            resp.raise_for_status()
        data = resp.json().get("data", [])
        if not data:
            return None
        return self._parse(data[0])

    async def get_guest_by_room(self, room: str, **kwargs) -> GuestInfo | None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url()}/api/v1.1/getReservations",
                headers=self._headers,
                params={
                    "propertyID": self._config["property_id"],
                    "roomID": room,
                    "status": "checked_in",
                },
                timeout=10.0,
            )
            resp.raise_for_status()
        data = resp.json().get("data", [])
        if not data:
            return None
        return self._parse(data[0])

    async def get_checkouts_since(self, since: datetime, **kwargs) -> list[str]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url()}/api/v1.1/getReservations",
                headers=self._headers,
                params={
                    "propertyID": self._config["property_id"],
                    "departureFrom": since.strftime("%m/%d/%Y"),
                    "status": "checked_out",
                },
                timeout=10.0,
            )
            resp.raise_for_status()
        return [r["roomID"] for r in resp.json().get("data", [])]

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self._base_url()}/api/v1.1/getHotels",
                    headers=self._headers,
                    timeout=5.0,
                )
                resp.raise_for_status()
            return True
        except Exception as e:
            logger.warning(f"Cloudbeds health check failed: {e}")
            return False
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_pms/test_cloudbeds.py -v
```

Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add app/pms/cloudbeds.py tests/test_pms/test_cloudbeds.py
git commit -m "feat: CloudbedsAdapter — REST API + API key"
```

---

## Task 5: MewsAdapter

**Files:**
- Create: `app/pms/mews.py`
- Create: `tests/test_pms/test_mews.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_pms/test_mews.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from app.pms.mews import MewsAdapter
from app.pms.base import GuestInfo

CONFIG = {
    "api_url": "https://www.mews.li",
    "client_token": "ct123",
    "access_token": "at456",
}

RESERVATIONS_RESP = {
    "Reservations": [{
        "Id": "M001",
        "AssignedSpaceId": "ROOM101",
        "LastName": "Smith",
        "FirstName": "John",
        "StartUtc": "2026-03-19T14:00:00Z",
        "EndUtc": "2026-03-22T12:00:00Z",
    }],
    "Spaces": [{"Id": "ROOM101", "Number": "101"}],
}

@pytest.mark.asyncio
async def test_verify_guest_success():
    adapter = MewsAdapter(CONFIG)
    with patch("app.pms.mews.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = RESERVATIONS_RESP
        mock_client.post = AsyncMock(return_value=resp)

        result = await adapter.verify_guest("101", "Smith")

    assert isinstance(result, GuestInfo)
    assert result.room_number == "101"
    assert result.last_name == "Smith"

@pytest.mark.asyncio
async def test_verify_guest_not_found():
    adapter = MewsAdapter(CONFIG)
    with patch("app.pms.mews.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {"Reservations": [], "Spaces": []}
        mock_client.post = AsyncMock(return_value=resp)

        result = await adapter.verify_guest("999", "Nobody")
    assert result is None

@pytest.mark.asyncio
async def test_health_check_true():
    adapter = MewsAdapter(CONFIG)
    with patch("app.pms.mews.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = {}
        mock_client.post = AsyncMock(return_value=resp)

        result = await adapter.health_check()
    assert result is True
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_pms/test_mews.py -v
```

Expected: `FAILED` — `ModuleNotFoundError`

- [ ] **Step 3: Implement MewsAdapter**

Create `app/pms/mews.py`:

```python
import httpx
import logging
from datetime import datetime, timezone
from app.pms.base import PMSAdapter, GuestInfo

logger = logging.getLogger(__name__)


class MewsAdapter(PMSAdapter):
    """Mews Connector REST adapter. ClientToken + AccessToken embedded in every request body."""

    def __init__(self, config: dict):
        self._config = config

    def _base_url(self) -> str:
        return self._config.get("api_url", "https://www.mews.li")

    def _auth(self) -> dict:
        return {
            "ClientToken": self._config["client_token"],
            "AccessToken": self._config["access_token"],
        }

    def _parse(self, res: dict, spaces: list[dict]) -> GuestInfo:
        space_map = {s["Id"]: s["Number"] for s in spaces}
        return GuestInfo(
            pms_id=res["Id"],
            room_number=space_map.get(res.get("AssignedSpaceId", ""), ""),
            last_name=res.get("LastName", ""),
            first_name=res.get("FirstName"),
            check_in=datetime.fromisoformat(res["StartUtc"].replace("Z", "+00:00")),
            check_out=datetime.fromisoformat(res["EndUtc"].replace("Z", "+00:00")),
        )

    async def verify_guest(self, room: str, last_name: str, **kwargs) -> GuestInfo | None:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base_url()}/api/connector/v1/reservations/getAll",
                json={**self._auth(), "States": ["Started"], "Extent": {"Reservations": True, "Spaces": True}},
                timeout=10.0,
            )
            resp.raise_for_status()
        data = resp.json()
        spaces = data.get("Spaces", [])
        space_map = {s["Number"]: s["Id"] for s in spaces}
        room_id = space_map.get(room)
        reservations = [
            r for r in data.get("Reservations", [])
            if r.get("AssignedSpaceId") == room_id
            and r.get("LastName", "").lower() == last_name.lower()
        ]
        if not reservations:
            return None
        return self._parse(reservations[0], spaces)

    async def get_guest_by_room(self, room: str, **kwargs) -> GuestInfo | None:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base_url()}/api/connector/v1/reservations/getAll",
                json={**self._auth(), "States": ["Started"], "Extent": {"Reservations": True, "Spaces": True}},
                timeout=10.0,
            )
            resp.raise_for_status()
        data = resp.json()
        spaces = data.get("Spaces", [])
        space_map = {s["Number"]: s["Id"] for s in spaces}
        room_id = space_map.get(room)
        reservations = [r for r in data.get("Reservations", []) if r.get("AssignedSpaceId") == room_id]
        if not reservations:
            return None
        return self._parse(reservations[0], spaces)

    async def get_checkouts_since(self, since: datetime, **kwargs) -> list[str]:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base_url()}/api/connector/v1/reservations/getAll",
                json={
                    **self._auth(),
                    "States": ["Processed"],
                    "EndUtc": {"StartUtc": since.isoformat()},
                    "Extent": {"Reservations": True, "Spaces": True},
                },
                timeout=10.0,
            )
            resp.raise_for_status()
        data = resp.json()
        spaces = {s["Id"]: s["Number"] for s in data.get("Spaces", [])}
        return [spaces.get(r.get("AssignedSpaceId", ""), "") for r in data.get("Reservations", [])]

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self._base_url()}/api/connector/v1/configuration/get",
                    json=self._auth(),
                    timeout=5.0,
                )
                resp.raise_for_status()
            return True
        except Exception as e:
            logger.warning(f"Mews health check failed: {e}")
            return False
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_pms/test_mews.py -v
```

Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add app/pms/mews.py tests/test_pms/test_mews.py
git commit -m "feat: MewsAdapter — Connector REST + token-in-body auth"
```

---

## Task 6: CustomAdapter

**Files:**
- Create: `app/pms/custom.py`
- Create: `tests/test_pms/test_custom.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_pms/test_custom.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.pms.custom import CustomAdapter
from app.pms.base import GuestInfo

CONFIG_BEARER = {
    "api_url": "https://pms.example.com",
    "auth_type": "bearer",
    "token": "tok999",
    "verify_endpoint": "/reservations/search",
    "guest_by_room_endpoint": "/reservations/room",
    "checkouts_endpoint": "/reservations/checkouts",
    "health_endpoint": "/status",
    "field_map": {
        "pms_id": "data.id",
        "room_number": "data.room",
        "last_name": "data.guest.surname",
        "first_name": "data.guest.given_name",
        "check_in": "data.arrival",
        "check_out": "data.departure",
    },
}

PMS_RESP = {
    "data": {
        "id": "C001",
        "room": "101",
        "guest": {"surname": "Smith", "given_name": "John"},
        "arrival": "2026-03-19T14:00:00+00:00",
        "departure": "2026-03-22T12:00:00+00:00",
    }
}

@pytest.mark.asyncio
async def test_verify_guest_bearer_success():
    adapter = CustomAdapter(CONFIG_BEARER)
    with patch("app.pms.custom.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = PMS_RESP
        mock_client.get = AsyncMock(return_value=resp)

        result = await adapter.verify_guest("101", "Smith")

    assert isinstance(result, GuestInfo)
    assert result.room_number == "101"
    assert result.last_name == "Smith"
    assert result.pms_id == "C001"

@pytest.mark.asyncio
async def test_verify_guest_basic_auth():
    config = {**CONFIG_BEARER, "auth_type": "basic", "username": "user", "password": "pass"}
    del config["token"]
    adapter = CustomAdapter(config)
    with patch("app.pms.custom.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        resp.json.return_value = PMS_RESP
        mock_client.get = AsyncMock(return_value=resp)

        result = await adapter.verify_guest("101", "Smith")
    assert result is not None

@pytest.mark.asyncio
async def test_field_map_resolves_nested_path():
    adapter = CustomAdapter(CONFIG_BEARER)
    result = adapter._resolve("data.guest.surname", PMS_RESP)
    assert result == "Smith"

@pytest.mark.asyncio
async def test_health_check_true():
    adapter = CustomAdapter(CONFIG_BEARER)
    with patch("app.pms.custom.httpx.AsyncClient") as mock_cls:
        mock_client = AsyncMock()
        mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
        mock_cls.return_value.__aexit__ = AsyncMock(return_value=None)
        resp = MagicMock()
        resp.raise_for_status = MagicMock()
        mock_client.get = AsyncMock(return_value=resp)

        result = await adapter.health_check()
    assert result is True
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_pms/test_custom.py -v
```

Expected: `FAILED` — `ModuleNotFoundError`

- [ ] **Step 3: Implement CustomAdapter**

Create `app/pms/custom.py`:

```python
import httpx
import logging
from datetime import datetime, timezone
from app.pms.base import PMSAdapter, GuestInfo

logger = logging.getLogger(__name__)


class CustomAdapter(PMSAdapter):
    """Configurable REST adapter. Supports bearer or basic auth with JSON field mapping."""

    def __init__(self, config: dict):
        self._config = config

    def _auth_kwargs(self) -> dict:
        auth_type = self._config.get("auth_type", "bearer")
        if auth_type == "basic":
            return {"auth": (self._config["username"], self._config["password"])}
        return {"headers": {"Authorization": f"Bearer {self._config['token']}"}}

    def _resolve(self, path: str, data: dict):
        """Resolve dot-notation path in nested dict. E.g. 'data.guest.surname'"""
        parts = path.split(".")
        val = data
        for p in parts:
            if not isinstance(val, dict):
                return None
            val = val.get(p)
        return val

    def _parse(self, data: dict) -> GuestInfo:
        fm = self._config["field_map"]

        def get(key):
            return self._resolve(fm[key], data) if key in fm else None

        check_in_raw = get("check_in")
        check_out_raw = get("check_out")
        return GuestInfo(
            pms_id=str(get("pms_id") or ""),
            room_number=str(get("room_number") or ""),
            last_name=str(get("last_name") or ""),
            first_name=get("first_name"),
            check_in=datetime.fromisoformat(check_in_raw) if check_in_raw else datetime.now(timezone.utc),
            check_out=datetime.fromisoformat(check_out_raw) if check_out_raw else datetime.now(timezone.utc),
        )

    async def verify_guest(self, room: str, last_name: str, **kwargs) -> GuestInfo | None:
        endpoint = self._config["verify_endpoint"]
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._config['api_url']}{endpoint}",
                params={"room": room, "last_name": last_name},
                timeout=10.0,
                **self._auth_kwargs(),
            )
            resp.raise_for_status()
        data = resp.json()
        room_number = self._resolve(self._config["field_map"].get("room_number", ""), data)
        if not room_number:
            return None
        return self._parse(data)

    async def get_guest_by_room(self, room: str, **kwargs) -> GuestInfo | None:
        endpoint = self._config.get("guest_by_room_endpoint", self._config["verify_endpoint"])
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._config['api_url']}{endpoint}",
                params={"room": room},
                timeout=10.0,
                **self._auth_kwargs(),
            )
            resp.raise_for_status()
        data = resp.json()
        room_number = self._resolve(self._config["field_map"].get("room_number", ""), data)
        if not room_number:
            return None
        return self._parse(data)

    async def get_checkouts_since(self, since: datetime, **kwargs) -> list[str]:
        endpoint = self._config.get("checkouts_endpoint")
        if not endpoint:
            return []
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._config['api_url']}{endpoint}",
                params={"since": since.isoformat()},
                timeout=10.0,
                **self._auth_kwargs(),
            )
            resp.raise_for_status()
        items = resp.json() if isinstance(resp.json(), list) else resp.json().get("data", [])
        room_key = self._config["field_map"].get("room_number", "room_number")
        return [self._resolve(room_key, item) for item in items if self._resolve(room_key, item)]

    async def health_check(self) -> bool:
        endpoint = self._config.get("health_endpoint", "/")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self._config['api_url']}{endpoint}",
                    timeout=5.0,
                    **self._auth_kwargs(),
                )
                resp.raise_for_status()
            return True
        except Exception as e:
            logger.warning(f"Custom adapter health check failed: {e}")
            return False
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_pms/test_custom.py -v
```

Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add app/pms/custom.py tests/test_pms/test_custom.py
git commit -m "feat: CustomAdapter — configurable REST + JSON field_map"
```

---

## Task 7: OperaFIASAdapter

FIAS TCP socket over asyncio. Persistent connection with heartbeat. All requests serialized via asyncio.Lock.

> **Note:** FIAS XML record format is per Oracle's "Opera FIAS Specification" document (v2.x). The XML structure below matches the publicly documented FIAS standard for vendor login and guest info queries. Obtain the full FIAS spec from Oracle support for production deployment.

**Files:**
- Create: `app/pms/opera_fias.py`
- Create: `tests/test_pms/test_opera_fias.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_pms/test_opera_fias.py`:

```python
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from app.pms.opera_fias import OperaFIASAdapter
from app.pms.base import GuestInfo

CONFIG = {"host": "192.168.1.10", "port": 5010, "auth_key": "AUTHKEY1", "vendor_id": "WIFI01"}

@pytest.mark.asyncio
async def test_connect_sends_login_record():
    adapter = OperaFIASAdapter(CONFIG)
    mock_reader = AsyncMock()
    mock_writer = MagicMock()
    mock_writer.is_closing.return_value = False

    # LA response (Login Acknowledge)
    mock_reader.read = AsyncMock(return_value=b"<LA/>\r\n")

    with patch("app.pms.opera_fias.asyncio.open_connection", return_value=(mock_reader, mock_writer)), \
         patch.object(adapter, "_heartbeat_loop", new_callable=AsyncMock):
        await adapter.connect()

    # Should have written a login record
    mock_writer.write.assert_called()
    written = b"".join(call.args[0] for call in mock_writer.write.call_args_list)
    assert b"LR" in written
    assert b"AUTHKEY1" in written

@pytest.mark.asyncio
async def test_health_check_true_when_connected():
    adapter = OperaFIASAdapter(CONFIG)
    mock_writer = MagicMock()
    mock_writer.is_closing.return_value = False
    adapter._writer = mock_writer
    assert await adapter.health_check() is True

@pytest.mark.asyncio
async def test_health_check_false_when_not_connected():
    adapter = OperaFIASAdapter(CONFIG)
    assert await adapter.health_check() is False

@pytest.mark.asyncio
async def test_verify_guest_parses_gi_response():
    adapter = OperaFIASAdapter(CONFIG)
    mock_reader = AsyncMock()
    mock_writer = MagicMock()
    mock_writer.is_closing.return_value = False
    adapter._reader = mock_reader
    adapter._writer = mock_writer

    gi_response = (
        b'<GI RoomNumber="101" LastName="Smith" FirstName="John" '
        b'ArrivalDate="03-19-26" DepartureDate="03-22-26" '
        b'ReservationNumber="R999"/>\r\n'
    )
    mock_reader.read = AsyncMock(return_value=gi_response)

    result = await adapter.verify_guest("101", "Smith")

    assert isinstance(result, GuestInfo)
    assert result.room_number == "101"
    assert result.last_name == "Smith"

@pytest.mark.asyncio
async def test_verify_guest_not_found_returns_none():
    adapter = OperaFIASAdapter(CONFIG)
    mock_reader = AsyncMock()
    mock_writer = MagicMock()
    adapter._reader = mock_reader
    adapter._writer = mock_writer

    # GNA = Guest Not Available response
    mock_reader.read = AsyncMock(return_value=b"<GNA/>\r\n")

    result = await adapter.verify_guest("999", "Nobody")
    assert result is None
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_pms/test_opera_fias.py -v
```

Expected: `FAILED` — `ModuleNotFoundError`

- [ ] **Step 3: Implement OperaFIASAdapter**

Create `app/pms/opera_fias.py`:

```python
import asyncio
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from app.pms.base import PMSAdapter, GuestInfo

logger = logging.getLogger(__name__)

# FIAS XML record terminator
_CRLF = b"\r\n"


class OperaFIASAdapter(PMSAdapter):
    """
    OPERA 5 / Suite8 FIAS TCP socket adapter.

    FIAS (Fidelio Interface Application Specification) uses a persistent TCP
    connection with XML record exchange. All requests are serialized via asyncio.Lock
    since the socket is shared. Heartbeat (KA/KR) sent every 30 seconds.

    Reference: Oracle Hospitality FIAS Specification v2.25
    """

    def __init__(self, config: dict):
        self._config = config
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        """Open TCP connection and perform FIAS login handshake. Call after __init__."""
        self._reader, self._writer = await asyncio.open_connection(
            self._config["host"], int(self._config["port"])
        )
        # Send LR (Login Record)
        lr = f'<LR AuthKey="{self._config["auth_key"]}" VendorID="{self._config["vendor_id"]}"/>'
        self._writer.write(lr.encode() + _CRLF)
        await self._writer.drain()
        # Wait for LA (Login Acknowledge)
        await self._reader.read(256)
        asyncio.create_task(self._heartbeat_loop())
        logger.info(f"FIAS connected to {self._config['host']}:{self._config['port']}")

    async def _heartbeat_loop(self) -> None:
        while self._writer and not self._writer.is_closing():
            await asyncio.sleep(30)
            try:
                async with self._lock:
                    self._writer.write(b"<KA/>" + _CRLF)
                    await self._writer.drain()
                    await self._reader.read(64)
            except Exception as e:
                logger.warning(f"FIAS heartbeat failed: {e}")
                break

    async def _send_recv(self, xml: str) -> str:
        """Send XML record and return response string (thread-safe)."""
        async with self._lock:
            self._writer.write(xml.encode() + _CRLF)
            await self._writer.drain()
            data = await self._reader.read(4096)
        return data.decode(errors="replace").strip()

    def _parse_gi(self, xml_str: str) -> GuestInfo | None:
        """Parse GI (Guest Information) response record."""
        try:
            root = ET.fromstring(xml_str)
            if root.tag != "GI":
                return None
            return GuestInfo(
                pms_id=root.attrib.get("ReservationNumber", ""),
                room_number=root.attrib.get("RoomNumber", ""),
                last_name=root.attrib.get("LastName", ""),
                first_name=root.attrib.get("FirstName"),
                check_in=datetime.strptime(root.attrib["ArrivalDate"], "%m-%d-%y").replace(tzinfo=timezone.utc),
                check_out=datetime.strptime(root.attrib["DepartureDate"], "%m-%d-%y").replace(tzinfo=timezone.utc),
            )
        except Exception as e:
            logger.warning(f"FIAS GI parse error: {e} — raw: {xml_str!r}")
            return None

    async def verify_guest(self, room: str, last_name: str, **kwargs) -> GuestInfo | None:
        xml = f'<GIQ RoomNumber="{room}" LastName="{last_name}"/>'
        response = await self._send_recv(xml)
        return self._parse_gi(response)

    async def get_guest_by_room(self, room: str, **kwargs) -> GuestInfo | None:
        xml = f'<GIQ RoomNumber="{room}"/>'
        response = await self._send_recv(xml)
        return self._parse_gi(response)

    async def get_checkouts_since(self, since: datetime, **kwargs) -> list[str]:
        date_str = since.strftime("%m-%d-%y")
        xml = f'<DRQ DepartureDate="{date_str}"/>'
        response = await self._send_recv(xml)
        rooms = []
        # DR responses may return multiple records delimited by CRLF
        for line in response.splitlines():
            try:
                root = ET.fromstring(line.strip())
                if root.tag == "DR":
                    room_num = root.attrib.get("RoomNumber", "")
                    if room_num:
                        rooms.append(room_num)
            except ET.ParseError:
                continue
        return rooms

    async def health_check(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def disconnect(self) -> None:
        if self._writer:
            try:
                self._writer.write(b"<LD/>" + _CRLF)
                await self._writer.drain()
                self._writer.close()
            except Exception:
                pass
            self._writer = None
            self._reader = None
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_pms/test_opera_fias.py -v
```

Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add app/pms/opera_fias.py tests/test_pms/test_opera_fias.py
git commit -m "feat: OperaFIASAdapter — TCP socket + FIAS XML protocol"
```

---

## Task 8: Factory Update

Replace the fallback-only factory with ADAPTER_MAP + retry + FIAS connect.

**Files:**
- Modify: `app/pms/factory.py`
- Create: `tests/test_pms/test_factory.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_pms/test_factory.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.pms.factory import load_adapter, get_adapter
from app.pms.standalone import StandaloneAdapter
from app.pms.cloudbeds import CloudbedsAdapter
from app.core.models import PMSAdapterType
from app.core.encryption import encrypt_config
import json

def _make_db_mock(adapter_type, config_dict):
    record = MagicMock()
    record.type = adapter_type
    record.config_encrypted = encrypt_config(config_dict)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = record
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    return mock_db

@pytest.mark.asyncio
async def test_load_adapter_standalone_when_no_record():
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    adapter = await load_adapter(mock_db)
    assert isinstance(adapter, StandaloneAdapter)

@pytest.mark.asyncio
async def test_load_adapter_cloudbeds():
    config = {"api_url": "https://api.cloudbeds.com", "api_key": "k", "property_id": "P1"}
    mock_db = _make_db_mock(PMSAdapterType.cloudbeds, config)

    with patch.object(CloudbedsAdapter, "health_check", new_callable=AsyncMock, return_value=True):
        adapter = await load_adapter(mock_db)

    assert isinstance(adapter, CloudbedsAdapter)

@pytest.mark.asyncio
async def test_load_adapter_retries_on_health_check_fail():
    config = {"api_url": "https://api.cloudbeds.com", "api_key": "k", "property_id": "P1"}
    mock_db = _make_db_mock(PMSAdapterType.cloudbeds, config)

    with patch.object(CloudbedsAdapter, "health_check", new_callable=AsyncMock, return_value=False), \
         patch("app.pms.factory.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        adapter = await load_adapter(mock_db)

    # 3 attempts, 2 sleeps between them
    assert mock_sleep.call_count == 2
    # Still returns the adapter even after all retries fail
    assert isinstance(adapter, CloudbedsAdapter)

@pytest.mark.asyncio
async def test_get_adapter_returns_standalone_if_never_loaded():
    import app.pms.factory as factory_mod
    factory_mod._active_adapter = None
    adapter = get_adapter()
    assert isinstance(adapter, StandaloneAdapter)
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_pms/test_factory.py -v
```

Expected: some tests FAIL (retry logic not implemented yet)

- [ ] **Step 3: Rewrite factory.py**

Replace `app/pms/factory.py` entirely:

```python
import asyncio
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.models import PMSAdapter as PMSAdapterModel, PMSAdapterType
from app.core.encryption import decrypt_config
from app.pms.base import PMSAdapter
from app.pms.standalone import StandaloneAdapter
from app.pms.opera_cloud import OperaCloudAdapter
from app.pms.opera_fias import OperaFIASAdapter
from app.pms.cloudbeds import CloudbedsAdapter
from app.pms.mews import MewsAdapter
from app.pms.custom import CustomAdapter

logger = logging.getLogger(__name__)

_active_adapter: PMSAdapter | None = None

ADAPTER_MAP = {
    PMSAdapterType.opera_cloud: OperaCloudAdapter,
    PMSAdapterType.opera_fias: OperaFIASAdapter,
    PMSAdapterType.cloudbeds: CloudbedsAdapter,
    PMSAdapterType.mews: MewsAdapter,
    PMSAdapterType.custom: CustomAdapter,
    PMSAdapterType.standalone: StandaloneAdapter,
}


async def load_adapter(db: AsyncSession) -> PMSAdapter:
    global _active_adapter
    result = await db.execute(
        select(PMSAdapterModel).where(PMSAdapterModel.is_active == True)
    )
    record = result.scalar_one_or_none()

    if not record or record.type == PMSAdapterType.standalone or record.type not in ADAPTER_MAP:
        _active_adapter = StandaloneAdapter()
        return _active_adapter

    config = decrypt_config(record.config_encrypted) if record.config_encrypted else {}
    adapter_class = ADAPTER_MAP[record.type]
    adapter = adapter_class(config)

    # FIAS needs TCP connection established before health check
    if isinstance(adapter, OperaFIASAdapter):
        try:
            await adapter.connect()
        except Exception as e:
            logger.error(f"FIAS connect failed: {e}")

    # Health check with retry (3 attempts, 500ms backoff)
    for attempt in range(3):
        if await adapter.health_check():
            break
        if attempt < 2:
            logger.warning(f"Adapter health check failed (attempt {attempt + 1}/3), retrying...")
            await asyncio.sleep(0.5)
    else:
        logger.error(f"Adapter {record.type.value} health check failed after 3 attempts — portal will return pms_unavailable")

    _active_adapter = adapter
    return _active_adapter


def get_adapter() -> PMSAdapter:
    if _active_adapter is None:
        return StandaloneAdapter()
    return _active_adapter
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_pms/test_factory.py -v
```

Expected: all PASSED

- [ ] **Step 5: Run all PMS tests to confirm no regressions**

```bash
pytest tests/test_pms/ -v
```

Expected: all PASSED

- [ ] **Step 6: Commit**

```bash
git add app/pms/factory.py tests/test_pms/test_factory.py
git commit -m "feat: factory ADAPTER_MAP — route to correct adapter class with retry"
```

---

## Task 9: Webhook Router

**Files:**
- Create: `app/pms/webhook_router.py`
- Create: `tests/test_pms/test_webhook.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_pms/test_webhook.py`:

```python
import pytest
import hmac
import hashlib
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

# Set env vars before importing app
import os
os.environ.setdefault("SECRET_KEY", "test_secret_key_32_chars_long_xxx")
os.environ.setdefault("ENCRYPTION_KEY", "AF7LzGfwqzgX6h8uF89ph9XUwy-_GilZDJp0zv2y0hs=")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

SECRET = "webhook_secret_123"
SECRET_HASH = hashlib.sha256(SECRET.encode()).hexdigest()

def _make_db_with_adapter(adapter_type_value, webhook_secret_hash):
    record = MagicMock()
    record.type.value = adapter_type_value
    record.webhook_secret = webhook_secret_hash
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = record
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    return mock_db

@pytest.mark.asyncio
async def test_webhook_opera_cloud_checkout():
    with patch("app.network.scheduler.start_scheduler"), \
         patch("app.pms.factory.load_adapter"):
        from app.main import app
        from app.core.database import get_db

        mock_db = _make_db_with_adapter("opera_cloud", SECRET_HASH)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        app.state.redis = AsyncMock()

        import uuid
        adapter_id = str(uuid.uuid4())

        with patch("app.pms.webhook_router.expire_sessions_for_room", new_callable=AsyncMock) as mock_expire:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post(
                    f"/internal/pms/webhook/{adapter_id}",
                    json={"eventType": "CHECKED_OUT", "roomNumber": "101"},
                    headers={"X-PMS-Secret": SECRET},
                )

        assert resp.status_code == 200
        mock_expire.assert_called_once()
        app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_webhook_invalid_secret_returns_401():
    with patch("app.network.scheduler.start_scheduler"), \
         patch("app.pms.factory.load_adapter"):
        from app.main import app
        from app.core.database import get_db

        mock_db = _make_db_with_adapter("opera_cloud", SECRET_HASH)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        app.state.redis = AsyncMock()

        import uuid
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                f"/internal/pms/webhook/{uuid.uuid4()}",
                json={"eventType": "CHECKED_OUT", "roomNumber": "101"},
                headers={"X-PMS-Secret": "wrong_secret"},
            )

        assert resp.status_code == 401
        app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_webhook_unknown_adapter_returns_404():
    with patch("app.network.scheduler.start_scheduler"), \
         patch("app.pms.factory.load_adapter"):
        from app.main import app
        from app.core.database import get_db

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        app.state.redis = AsyncMock()

        import uuid
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                f"/internal/pms/webhook/{uuid.uuid4()}",
                json={},
                headers={"X-PMS-Secret": "x"},
            )

        assert resp.status_code == 404
        app.dependency_overrides.clear()
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_pms/test_webhook.py -v
```

Expected: FAILED

- [ ] **Step 3: Implement webhook_router.py**

Create `app/pms/webhook_router.py`:

```python
import uuid
import hmac
import hashlib
import logging
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.models import PMSAdapter as PMSAdapterModel
from app.network.session_manager import SessionManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/internal/pms")
_manager = SessionManager()


async def expire_sessions_for_room(db: AsyncSession, room_number: str) -> int:
    """Thin wrapper so tests can mock it cleanly."""
    return await _manager.expire_sessions_for_room(db, room_number)


@router.post("/webhook/{adapter_id}")
async def pms_webhook(
    adapter_id: uuid.UUID,
    payload: dict,
    x_pms_secret: str = Header(alias="X-PMS-Secret", default=""),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PMSAdapterModel).where(PMSAdapterModel.id == adapter_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail={"error": "adapter_not_found"})

    expected = record.webhook_secret or ""
    incoming_hash = hashlib.sha256(x_pms_secret.encode()).hexdigest()
    if not hmac.compare_digest(incoming_hash, expected):
        raise HTTPException(status_code=401, detail={"error": "invalid_secret"})

    adapter_type = record.type.value
    room_number = None

    if adapter_type == "opera_cloud":
        if payload.get("eventType") == "CHECKED_OUT":
            room_number = payload.get("roomNumber")
    elif adapter_type == "mews":
        if payload.get("Type") == "ReservationUpdated" and payload.get("State") == "Checked_out":
            room_number = payload.get("RoomNumber")

    if room_number:
        count = await expire_sessions_for_room(db, room_number)
        logger.info(f"Webhook checkout: room={room_number}, expired {count} sessions")

    return {"ok": True}
```

- [ ] **Step 4: Register webhook router in main.py**

Add to `app/main.py`:

```python
from app.pms.webhook_router import router as webhook_router
# ...
app.include_router(webhook_router)
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_pms/test_webhook.py -v
```

Expected: all PASSED

- [ ] **Step 6: Commit**

```bash
git add app/pms/webhook_router.py app/main.py tests/test_pms/test_webhook.py
git commit -m "feat: PMS webhook endpoint — Opera Cloud + Mews checkout events"
```

---

## Task 10: Checkout Polling Scheduler

**Files:**
- Modify: `app/network/scheduler.py`

- [ ] **Step 1: Write failing tests**

Add to a new file `tests/test_network/test_scheduler_poll.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from app.pms.standalone import StandaloneAdapter
from app.pms.cloudbeds import CloudbedsAdapter


@pytest.mark.asyncio
async def test_poll_checkouts_skips_standalone():
    with patch("app.network.scheduler.get_adapter", return_value=StandaloneAdapter()), \
         patch("app.network.scheduler.AsyncSessionFactory") as mock_factory:
        from app.network.scheduler import _poll_checkouts_job
        await _poll_checkouts_job()
    # No DB session opened for standalone
    mock_factory.assert_not_called()


@pytest.mark.asyncio
async def test_poll_checkouts_expires_rooms():
    mock_adapter = MagicMock(spec=CloudbedsAdapter)
    mock_adapter.get_checkouts_since = AsyncMock(return_value=["101", "202"])

    mock_record = MagicMock()
    mock_record.last_sync_at = None
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_record

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.commit = AsyncMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=None)

    with patch("app.network.scheduler.get_adapter", return_value=mock_adapter), \
         patch("app.network.scheduler.AsyncSessionFactory", return_value=mock_db), \
         patch("app.network.scheduler._manager") as mock_manager:
        mock_manager.expire_sessions_for_room = AsyncMock(return_value=1)
        from app.network import scheduler
        # Reload to pick up patches
        await scheduler._poll_checkouts_job()

    assert mock_manager.expire_sessions_for_room.call_count == 2


@pytest.mark.asyncio
async def test_poll_checkouts_does_not_update_sync_on_error():
    mock_adapter = MagicMock(spec=CloudbedsAdapter)
    mock_adapter.get_checkouts_since = AsyncMock(side_effect=Exception("timeout"))

    mock_record = MagicMock()
    mock_record.last_sync_at = datetime.now(timezone.utc)
    original_sync = mock_record.last_sync_at

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_record
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=None)

    with patch("app.network.scheduler.get_adapter", return_value=mock_adapter), \
         patch("app.network.scheduler.AsyncSessionFactory", return_value=mock_db):
        from app.network import scheduler
        await scheduler._poll_checkouts_job()

    # last_sync_at should not be updated
    assert mock_record.last_sync_at == original_sync
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_network/test_scheduler_poll.py -v
```

Expected: FAILED — `cannot import name '_poll_checkouts_job'`

- [ ] **Step 3: Add poll job to scheduler.py**

Replace `app/network/scheduler.py`:

```python
from datetime import datetime, timedelta, timezone
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.core.database import AsyncSessionFactory
from app.core.models import PMSAdapter as PMSAdapterModel
from app.network.session_manager import SessionManager
from app.pms.factory import get_adapter
from app.pms.opera_cloud import OperaCloudAdapter
from app.pms.mews import MewsAdapter
from sqlalchemy import select
import logging

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()
_manager = SessionManager()


async def _expire_job():
    async with AsyncSessionFactory() as db:
        count = await _manager.expire_overdue_sessions(db)
        if count:
            logger.info(f"Scheduler expired {count} sessions")


async def _poll_checkouts_job():
    adapter = get_adapter()
    # Opera Cloud and Mews use webhooks — no polling needed
    if isinstance(adapter, (OperaCloudAdapter, MewsAdapter)):
        return

    async with AsyncSessionFactory() as db:
        result = await db.execute(
            select(PMSAdapterModel).where(PMSAdapterModel.is_active == True)
        )
        record = result.scalar_one_or_none()
        last_sync = (record.last_sync_at if record and record.last_sync_at
                     else datetime.now(timezone.utc) - timedelta(minutes=10))

        try:
            checkouts = await adapter.get_checkouts_since(last_sync)
        except Exception as e:
            logger.error(f"Checkout poll failed: {e} — skipping last_sync_at update")
            return

        for room in checkouts:
            count = await _manager.expire_sessions_for_room(db, room)
            if count:
                logger.info(f"Poll checkout: room={room}, expired {count} sessions")

        if record:
            record.last_sync_at = datetime.now(timezone.utc)
        await db.commit()


def start_scheduler():
    scheduler.add_job(_expire_job, "interval", seconds=60, id="expire_sessions")
    scheduler.add_job(_poll_checkouts_job, "interval", seconds=300, id="poll_checkouts")
    scheduler.start()
    logger.info("Scheduler started (expire: 60s, poll_checkouts: 300s)")


def stop_scheduler():
    scheduler.shutdown(wait=False)
```

- [ ] **Step 4: Run tests to verify they pass**

```bash
pytest tests/test_network/test_scheduler_poll.py -v
```

Expected: all PASSED

- [ ] **Step 5: Commit**

```bash
git add app/network/scheduler.py tests/test_network/test_scheduler_poll.py
git commit -m "feat: checkout polling scheduler — poll PMS every 5 min, expire sessions on checkout"
```

---

## Task 11: Admin PMS Endpoints

**Files:**
- Create: `app/admin/schemas.py`
- Modify: `app/admin/router.py`
- Create: `tests/test_admin/test_pms_admin.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_admin/test_pms_admin.py`:

```python
import pytest
import pytest_asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
from app.core.encryption import encrypt_config

@pytest_asyncio.fixture
async def admin_client():
    with patch("app.network.scheduler.start_scheduler"), \
         patch("app.pms.factory.load_adapter"):
        from app.main import app
        from app.core.database import get_db

        record = MagicMock()
        record.id = uuid.uuid4()
        record.type = MagicMock()
        record.type.value = "cloudbeds"
        record.is_active = True
        record.last_sync_at = None
        record.config_encrypted = encrypt_config(
            {"api_url": "https://api.cloudbeds.com", "api_key": "k", "property_id": "P1"}
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = record
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        app.state.redis = AsyncMock()

        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c, mock_db

        app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_get_pms_returns_config_with_masked_credentials(admin_client):
    # Note: add JWT auth header in real deployment; mocked here via dependency override
    client, _ = admin_client
    resp = await client.get("/admin/pms")
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "cloudbeds"
    # Credentials should be masked
    assert data["config"].get("api_key") == "***"

@pytest.mark.asyncio
async def test_put_pms_updates_config(admin_client):
    client, mock_db = admin_client
    with patch("app.admin.router.load_adapter", new_callable=AsyncMock):
        resp = await client.put("/admin/pms", json={
            "type": "cloudbeds",
            "config": {"api_url": "https://api.cloudbeds.com", "api_key": "new_key", "property_id": "P2"},
        })
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

@pytest.mark.asyncio
async def test_post_pms_test_returns_ok_true(admin_client):
    client, _ = admin_client
    with patch("app.pms.cloudbeds.CloudbedsAdapter.health_check", new_callable=AsyncMock, return_value=True):
        resp = await client.post("/admin/pms/test", json={
            "type": "cloudbeds",
            "config": {"api_url": "https://api.cloudbeds.com", "api_key": "k", "property_id": "P1"},
        })
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

@pytest.mark.asyncio
async def test_post_pms_test_returns_ok_false_on_error(admin_client):
    client, _ = admin_client
    with patch("app.pms.cloudbeds.CloudbedsAdapter.health_check", new_callable=AsyncMock, return_value=False):
        resp = await client.post("/admin/pms/test", json={
            "type": "cloudbeds",
            "config": {"api_url": "https://api.cloudbeds.com", "api_key": "bad", "property_id": "P1"},
        })
    assert resp.status_code == 200
    assert resp.json()["ok"] is False
```

- [ ] **Step 2: Run to verify failure**

```bash
pytest tests/test_admin/test_pms_admin.py -v
```

Expected: FAILED

- [ ] **Step 3: Create app/admin/schemas.py**

Create `app/admin/schemas.py`:

```python
import uuid
from datetime import datetime
from pydantic import BaseModel
from app.core.models import PMSAdapterType


class PMSConfigResponse(BaseModel):
    id: uuid.UUID
    type: PMSAdapterType
    is_active: bool
    last_sync_at: datetime | None
    config: dict  # credentials replaced with "***"


class PMSConfigUpdate(BaseModel):
    type: PMSAdapterType
    config: dict  # plaintext — encrypted before DB write


class PMSTestResult(BaseModel):
    ok: bool
    latency_ms: float | None = None
    error: str | None = None
```

- [ ] **Step 4: Add PMS endpoints to admin/router.py**

Add imports and endpoints to `app/admin/router.py`:

```python
# Add to imports at top:
import time
from sqlalchemy import select
from app.core.models import PMSAdapter as PMSAdapterModel, PMSAdapterType
from app.core.encryption import encrypt_config, decrypt_config
from app.pms.factory import load_adapter, ADAPTER_MAP
from app.admin.schemas import PMSConfigResponse, PMSConfigUpdate, PMSTestResult

_CREDENTIAL_KEYS = {"client_secret", "api_key", "token", "password", "access_token",
                    "client_token", "auth_key", "webhook_secret"}


def _mask_config(config: dict) -> dict:
    return {k: "***" if k in _CREDENTIAL_KEYS else v for k, v in config.items()}


@router.get("/pms", response_model=PMSConfigResponse)
async def get_pms_config(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PMSAdapterModel).where(PMSAdapterModel.is_active == True)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail={"error": "no_active_adapter"})
    config = decrypt_config(record.config_encrypted) if record.config_encrypted else {}
    return PMSConfigResponse(
        id=record.id,
        type=record.type,
        is_active=record.is_active,
        last_sync_at=record.last_sync_at,
        config=_mask_config(config),
    )


@router.put("/pms")
async def update_pms_config(body: PMSConfigUpdate, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(PMSAdapterModel).where(PMSAdapterModel.is_active == True)
    )
    record = result.scalar_one_or_none()
    if not record:
        record = PMSAdapterModel(type=body.type, is_active=True)
        db.add(record)
    record.type = body.type
    record.config_encrypted = encrypt_config(body.config)
    await db.commit()
    await load_adapter(db)
    return {"ok": True}


@router.post("/pms/test", response_model=PMSTestResult)
async def test_pms_config(body: PMSConfigUpdate):
    adapter_class = ADAPTER_MAP.get(body.type)
    if not adapter_class or body.type == PMSAdapterType.standalone:
        return PMSTestResult(ok=True, latency_ms=0.0)
    adapter = adapter_class(body.config)
    start = time.monotonic()
    try:
        ok = await adapter.health_check()
        latency = (time.monotonic() - start) * 1000
        return PMSTestResult(ok=ok, latency_ms=round(latency, 1))
    except Exception as e:
        latency = (time.monotonic() - start) * 1000
        return PMSTestResult(ok=False, latency_ms=round(latency, 1), error=str(e))
```

- [ ] **Step 5: Run tests to verify they pass**

```bash
pytest tests/test_admin/test_pms_admin.py -v
```

Expected: all PASSED

- [ ] **Step 6: Commit**

```bash
git add app/admin/schemas.py app/admin/router.py tests/test_admin/test_pms_admin.py
git commit -m "feat: admin PMS endpoints — GET/PUT /admin/pms, POST /admin/pms/test"
```

---

## Task 12: Final Integration — Run Full Test Suite

- [ ] **Step 1: Run all tests**

```bash
pytest tests/ -v --tb=short
```

Expected: all tests PASS. If any fail, fix before continuing.

- [ ] **Step 2: Run with coverage**

```bash
pytest tests/ --cov=app --cov-report=term-missing
```

Target: >80% coverage on `app/pms/` and `app/network/`

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat: Phase 2 complete — PMS adapters, webhook, polling scheduler, admin PMS endpoints"
```
