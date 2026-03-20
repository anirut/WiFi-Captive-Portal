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
