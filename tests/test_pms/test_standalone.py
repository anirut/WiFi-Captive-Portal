import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta, timezone
import uuid
from app.pms.standalone import StandaloneAdapter
from app.pms.base import GuestInfo

@pytest.fixture
def adapter():
    return StandaloneAdapter()

@pytest.mark.asyncio
async def test_verify_guest_found(adapter):
    mock_guest = MagicMock()
    mock_guest.pms_guest_id = str(uuid.uuid4())
    mock_guest.room_number = "101"
    mock_guest.last_name = "Smith"
    mock_guest.first_name = "John"
    mock_guest.check_in = datetime.now(timezone.utc) - timedelta(hours=2)
    mock_guest.check_out = datetime.now(timezone.utc) + timedelta(hours=22)

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_guest
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await adapter.verify_guest("101", "Smith", db=mock_db)
    assert isinstance(result, GuestInfo)
    assert result.room_number == "101"

@pytest.mark.asyncio
async def test_verify_guest_not_found(adapter):
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await adapter.verify_guest("999", "Nobody", db=mock_db)
    assert result is None

@pytest.mark.asyncio
async def test_health_check_returns_true(adapter):
    assert await adapter.health_check() is True
