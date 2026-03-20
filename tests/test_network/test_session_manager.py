import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
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
            expires_at=datetime.utcnow() + timedelta(hours=24),
            bandwidth_up_kbps=0,
            bandwidth_down_kbps=0,
        )
        mock_ipt.assert_called_once_with("192.168.1.45")

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
