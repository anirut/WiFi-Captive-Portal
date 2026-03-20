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
