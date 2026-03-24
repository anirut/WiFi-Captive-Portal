import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timedelta, timezone
from app.pms.base import GuestInfo
from app.core.models import SessionStatus

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

@pytest.mark.asyncio
async def test_auth_room_max_devices_reached(client):
    """Returns 429 when guest already has max_devices active sessions."""
    guest_info = GuestInfo(
        pms_id="pms-2", room_number="102", last_name="Jones",
        check_in=datetime.now(timezone.utc) - timedelta(hours=1),
        check_out=datetime.now(timezone.utc) + timedelta(hours=23),
    )
    # Simulate an existing guest with max_devices=1 already at limit (1 active session)
    existing_guest = MagicMock()
    existing_guest.id = "guest-uuid"
    existing_guest.max_devices = 1

    with patch("app.portal.router.get_adapter") as mock_adapter_fn, \
         patch("app.portal.router.session_manager"):
        mock_adapter = AsyncMock()
        mock_adapter.verify_guest = AsyncMock(return_value=guest_info)
        mock_adapter_fn.return_value = mock_adapter

        # db.execute calls: (1) Room lookup, (2) Guest lookup → return existing_guest,
        # (3) active session count → return 1
        mock_results = [
            MagicMock(**{"scalar_one_or_none.return_value": None}),        # Room → None
            MagicMock(**{"scalar_one_or_none.return_value": existing_guest}),  # Guest → existing
            MagicMock(**{"scalar_one_or_none.return_value": 1}),           # count → 1
        ]
        from app.core.database import get_db
        from app.main import app
        call_count = 0

        async def mock_db_gen():
            mock_db = AsyncMock()
            nonlocal call_count
            def side_effect(*args, **kwargs):
                nonlocal call_count
                result = mock_results[min(call_count, len(mock_results) - 1)]
                call_count += 1
                import asyncio
                future = asyncio.get_event_loop().create_future()
                future.set_result(result)
                return future
            mock_db.execute = side_effect
            yield mock_db

        app.dependency_overrides[get_db] = mock_db_gen

        response = await client.post("/auth/room", json={
            "room_number": "102", "last_name": "Jones", "tc_accepted": True
        })
        app.dependency_overrides.pop(get_db, None)

        assert response.status_code == 429
        assert response.json()["detail"]["error"] == "max_devices_reached"


@pytest.mark.asyncio
async def test_portal_shows_disconnect_when_session_active(client):
    """When client has an active session, GET / should show disconnect page."""
    from datetime import datetime, timedelta, timezone
    from app.core.models import Session, SessionStatus
    from unittest.mock import patch, MagicMock

    # Create a mock active session
    mock_session = MagicMock()
    mock_session.id = "session-uuid"
    mock_session.expires_at = datetime.now(timezone.utc) + timedelta(hours=8)
    mock_session.status = SessionStatus.active

    # Mock get_mac_for_ip to return a MAC address
    with patch("app.portal.router.get_mac_for_ip", return_value="aa:bb:cc:dd:ee:ff"):
        # Override DB to return the mock session
        from app.core.database import get_db
        from app.main import app

        async def mock_db_gen():
            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_session
            mock_db.execute = AsyncMock(return_value=mock_result)
            yield mock_db

        app.dependency_overrides[get_db] = mock_db_gen

        response = await client.get("/")

        app.dependency_overrides.pop(get_db, None)

        assert response.status_code == 200
        # Check that we got the disconnect page, not login
        assert "Disconnect" in response.text
