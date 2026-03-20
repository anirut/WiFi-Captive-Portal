import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timedelta, timezone
from app.pms.base import GuestInfo

@pytest.mark.asyncio
async def test_get_portal_login_page(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

@pytest.mark.asyncio
async def test_auth_room_success(client):
    guest_info = GuestInfo(
        pms_id="pms-1", room_number="101", last_name="Smith",
        check_in=datetime.now(timezone.utc) - timedelta(hours=1),
        check_out=datetime.now(timezone.utc) + timedelta(hours=23),
    )
    with patch("app.portal.router.get_adapter") as mock_adapter_fn, \
         patch("app.portal.router.session_manager") as mock_sm:
        mock_adapter = AsyncMock()
        mock_adapter.verify_guest = AsyncMock(return_value=guest_info)
        mock_adapter_fn.return_value = mock_adapter
        mock_session = MagicMock()
        mock_session.id = "sess-1"
        mock_session.expires_at = datetime.now(timezone.utc) + timedelta(hours=8)
        mock_sm.create_session = AsyncMock(return_value=mock_session)

        response = await client.post("/auth/room", json={
            "room_number": "101", "last_name": "Smith", "tc_accepted": True
        })
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data

@pytest.mark.asyncio
async def test_auth_room_wrong_credentials(client):
    with patch("app.portal.router.get_adapter") as mock_adapter_fn:
        mock_adapter = AsyncMock()
        mock_adapter.verify_guest = AsyncMock(return_value=None)
        mock_adapter_fn.return_value = mock_adapter

        response = await client.post("/auth/room", json={
            "room_number": "101", "last_name": "Wrong", "tc_accepted": True
        })
        assert response.status_code == 401
        assert response.json()["detail"]["error"] == "guest_not_checked_in"

@pytest.mark.asyncio
async def test_auth_room_tc_not_accepted(client):
    response = await client.post("/auth/room", json={
        "room_number": "101", "last_name": "Smith", "tc_accepted": False
    })
    assert response.status_code == 422
