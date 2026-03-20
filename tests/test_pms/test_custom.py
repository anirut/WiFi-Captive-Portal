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

def test_field_map_resolves_nested_path():
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
