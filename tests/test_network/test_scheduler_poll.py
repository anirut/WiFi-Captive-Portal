import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timezone
from app.pms.standalone import StandaloneAdapter
from app.pms.cloudbeds import CloudbedsAdapter


@pytest.mark.asyncio
async def test_poll_checkouts_skips_standalone():
    with patch("app.network.scheduler.get_adapter", return_value=StandaloneAdapter()), \
         patch("app.network.scheduler.AsyncSessionFactory") as mock_factory:
        from app.network.scheduler import _poll_checkouts_job
        await _poll_checkouts_job()
    # No DB session opened for standalone
    mock_factory.assert_not_called()


@pytest.mark.asyncio
async def test_poll_checkouts_expires_rooms():
    mock_adapter = MagicMock(spec=CloudbedsAdapter)
    mock_adapter.get_checkouts_since = AsyncMock(return_value=["101", "202"])

    mock_record = MagicMock()
    mock_record.last_sync_at = None
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_record

    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.commit = AsyncMock()
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=None)

    with patch("app.network.scheduler.get_adapter", return_value=mock_adapter), \
         patch("app.network.scheduler.AsyncSessionFactory", return_value=mock_db), \
         patch("app.network.scheduler._manager") as mock_manager:
        mock_manager.expire_sessions_for_room = AsyncMock(return_value=1)
        from app.network import scheduler
        await scheduler._poll_checkouts_job()

    assert mock_manager.expire_sessions_for_room.call_count == 2


@pytest.mark.asyncio
async def test_poll_checkouts_does_not_update_sync_on_error():
    mock_adapter = MagicMock(spec=CloudbedsAdapter)
    mock_adapter.get_checkouts_since = AsyncMock(side_effect=Exception("timeout"))

    mock_record = MagicMock()
    mock_record.last_sync_at = datetime.now(timezone.utc)
    original_sync = mock_record.last_sync_at

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_record
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.__aenter__ = AsyncMock(return_value=mock_db)
    mock_db.__aexit__ = AsyncMock(return_value=None)

    with patch("app.network.scheduler.get_adapter", return_value=mock_adapter), \
         patch("app.network.scheduler.AsyncSessionFactory", return_value=mock_db):
        from app.network import scheduler
        await scheduler._poll_checkouts_job()

    # last_sync_at should not be updated
    assert mock_record.last_sync_at == original_sync
