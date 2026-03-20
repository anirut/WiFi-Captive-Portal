import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta, timezone
import uuid
from app.network.session_manager import SessionManager

@pytest.fixture
def manager():
    return SessionManager(wifi_if="wlan0", wan_if="eth0")

@pytest.mark.asyncio
async def test_create_session_adds_whitelist(manager):
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()

    with patch("app.network.session_manager.add_whitelist") as mock_ipt, \
         patch("app.network.session_manager.apply_bandwidth_limit") as mock_tc, \
         patch("app.network.session_manager.get_mac_for_ip", return_value="aa:bb:cc:dd:ee:ff"):

        await manager.create_session(
            db=mock_db,
            ip="192.168.1.45",
            guest_id=uuid.uuid4(),
            expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
            bandwidth_up_kbps=0,
            bandwidth_down_kbps=0,
        )
        mock_ipt.assert_called_once_with("192.168.1.45")
        mock_tc.assert_called_once_with("192.168.1.45", 0, 0, "eth0")

@pytest.mark.asyncio
async def test_expire_session_removes_whitelist(manager):
    mock_db = AsyncMock()
    mock_session = MagicMock()
    mock_session.ip_address = "192.168.1.45"
    mock_session.status.value = "active"

    with patch("app.network.session_manager.remove_whitelist") as mock_ipt, \
         patch("app.network.session_manager.remove_bandwidth_limit") as mock_tc:
        await manager.expire_session(db=mock_db, session=mock_session)
        mock_ipt.assert_called_once_with("192.168.1.45")
        mock_tc.assert_called_once_with("192.168.1.45", "eth0")

@pytest.mark.asyncio
async def test_expire_overdue_sessions_returns_count(manager):
    mock_session_1 = MagicMock()
    mock_session_1.ip_address = "192.168.1.10"
    mock_session_1.status = MagicMock()
    mock_session_2 = MagicMock()
    mock_session_2.ip_address = "192.168.1.11"
    mock_session_2.status = MagicMock()

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_session_1, mock_session_2]

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.commit = AsyncMock()

    with patch("app.network.session_manager.remove_whitelist"), \
         patch("app.network.session_manager.remove_bandwidth_limit"):
        count = await manager.expire_overdue_sessions(db=mock_db)

    assert count == 2
