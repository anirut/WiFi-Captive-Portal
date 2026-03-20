import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from app.pms.factory import load_adapter, get_adapter
from app.pms.standalone import StandaloneAdapter
from app.pms.cloudbeds import CloudbedsAdapter
from app.core.models import PMSAdapterType
from app.core.encryption import encrypt_config


def _make_db_mock(adapter_type, config_dict):
    record = MagicMock()
    record.type = adapter_type
    record.config_encrypted = encrypt_config(config_dict)
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = record
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    return mock_db


@pytest.mark.asyncio
async def test_load_adapter_standalone_when_no_record():
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    adapter = await load_adapter(mock_db)
    assert isinstance(adapter, StandaloneAdapter)


@pytest.mark.asyncio
async def test_load_adapter_cloudbeds():
    config = {"api_url": "https://api.cloudbeds.com", "api_key": "k", "property_id": "P1"}
    mock_db = _make_db_mock(PMSAdapterType.cloudbeds, config)

    with patch.object(CloudbedsAdapter, "health_check", new_callable=AsyncMock, return_value=True):
        adapter = await load_adapter(mock_db)

    assert isinstance(adapter, CloudbedsAdapter)


@pytest.mark.asyncio
async def test_load_adapter_retries_on_health_check_fail():
    config = {"api_url": "https://api.cloudbeds.com", "api_key": "k", "property_id": "P1"}
    mock_db = _make_db_mock(PMSAdapterType.cloudbeds, config)

    with patch.object(CloudbedsAdapter, "health_check", new_callable=AsyncMock, return_value=False), \
         patch("app.pms.factory.asyncio.sleep", new_callable=AsyncMock) as mock_sleep:
        adapter = await load_adapter(mock_db)

    # 3 attempts, 2 sleeps between them
    assert mock_sleep.call_count == 2
    # Still returns the adapter even after all retries fail
    assert isinstance(adapter, CloudbedsAdapter)


@pytest.mark.asyncio
async def test_get_adapter_returns_standalone_if_never_loaded():
    import app.pms.factory as factory_mod
    factory_mod._active_adapter = None
    adapter = get_adapter()
    assert isinstance(adapter, StandaloneAdapter)
