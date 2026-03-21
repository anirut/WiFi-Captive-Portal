import pytest
from unittest.mock import AsyncMock, patch, MagicMock

@pytest.mark.asyncio
async def test_expire_session_calls_remove_bandwidth_limit_with_up_kbps():
    """expire_session() must pass session.bandwidth_up_kbps to remove_bandwidth_limit."""
    from app.network.session_manager import SessionManager
    from app.core.models import SessionStatus

    mock_session = MagicMock()
    mock_session.ip_address = "192.168.1.55"
    mock_session.bandwidth_up_kbps = 2048  # sentinel value
    mock_session.status = SessionStatus.active

    mock_db = AsyncMock()

    with patch("app.network.session_manager.remove_whitelist") as mock_rw, \
         patch("app.network.session_manager.remove_bandwidth_limit") as mock_rbl:
        mgr = SessionManager(wifi_if="wlan0", wan_if="eth0")
        await mgr.expire_session(mock_db, mock_session)

    # Must be called with 3 args: (ip, bandwidth_up_kbps, wan_if)
    mock_rbl.assert_called_once_with("192.168.1.55", 2048, "eth0")
