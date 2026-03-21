import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone

@pytest.mark.asyncio
async def test_bytes_job_updates_session_bytes():
    """_bytes_job updates bytes_up and bytes_down on active sessions."""
    from app.network.scheduler import _bytes_job
    from app.core.models import SessionStatus

    mock_session = MagicMock(spec=["ip_address", "voucher_id", "bytes_up", "bytes_down"])
    mock_session.ip_address = "192.168.1.100"
    mock_session.voucher_id = None
    mock_session.bytes_up = 0    # sentinel: starts at 0
    mock_session.bytes_down = 0  # sentinel: starts at 0

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_session]
    mock_db.execute = AsyncMock(return_value=mock_result)

    with patch("app.network.scheduler.AsyncSessionFactory") as mock_factory, \
         patch("app.network.scheduler.tc.get_bytes", return_value=(1000, 2000)):
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        await _bytes_job()

    # Verify actual assignment happened (not MagicMock auto-creation)
    assert mock_session.bytes_up == 1000
    assert mock_session.bytes_down == 2000

@pytest.mark.asyncio
async def test_bytes_job_expires_data_voucher_when_quota_exceeded():
    """_bytes_job expires data-type voucher session when bytes_down >= quota."""
    from app.network.scheduler import _bytes_job
    from app.core.models import SessionStatus, VoucherType

    mock_voucher = MagicMock()
    mock_voucher.type = VoucherType.data
    mock_voucher.data_limit_mb = 1  # 1 MB = 1048576 bytes

    mock_session = MagicMock()
    mock_session.ip_address = "192.168.1.101"
    mock_session.voucher_id = "some-uuid"
    mock_session.voucher = mock_voucher
    mock_session.bytes_down = 0

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = [mock_session]
    mock_db.execute = AsyncMock(return_value=mock_result)

    with patch("app.network.scheduler.AsyncSessionFactory") as mock_factory, \
         patch("app.network.scheduler.tc.get_bytes", return_value=(500, 1048577)), \
         patch("app.network.scheduler._manager") as mock_manager:
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        mock_manager.expire_session = AsyncMock()
        await _bytes_job()

    mock_manager.expire_session.assert_called_once()

@pytest.mark.asyncio
async def test_analytics_snapshot_job_inserts_row():
    """_analytics_snapshot_job writes a UsageSnapshot row."""
    from app.network.scheduler import _analytics_snapshot_job

    mock_db = AsyncMock()
    count_result = MagicMock()
    count_result.scalar_one.return_value = 5   # active_sessions
    sum_result = MagicMock()
    sum_result.one.return_value = (100, 200)   # (bytes_up, bytes_down)
    voucher_count_result = MagicMock()
    voucher_count_result.scalar_one.return_value = 3

    mock_db.execute = AsyncMock(side_effect=[count_result, sum_result, voucher_count_result])

    with patch("app.network.scheduler.AsyncSessionFactory") as mock_factory:
        mock_factory.return_value.__aenter__ = AsyncMock(return_value=mock_db)
        mock_factory.return_value.__aexit__ = AsyncMock(return_value=False)
        await _analytics_snapshot_job()

    assert mock_db.add.called
    snapshot = mock_db.add.call_args[0][0]
    assert snapshot.active_sessions == 5
