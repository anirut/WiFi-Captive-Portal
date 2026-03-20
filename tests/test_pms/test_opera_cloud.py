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
