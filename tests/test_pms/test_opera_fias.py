import inspect
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
from app.pms.opera_fias import OperaFIASAdapter
from app.pms.base import GuestInfo

CONFIG = {"host": "192.168.1.10", "port": 5010, "auth_key": "AUTHKEY1", "vendor_id": "WIFI01"}

@pytest.mark.asyncio
async def test_connect_sends_login_record():
    adapter = OperaFIASAdapter(CONFIG)
    mock_reader = AsyncMock()
    mock_writer = MagicMock()
    mock_writer.is_closing.return_value = False
    mock_writer.drain = AsyncMock()

    # LA response (Login Acknowledge)
    mock_reader.read = AsyncMock(return_value=b"<LA/>\r\n")

    with patch("app.pms.opera_fias.asyncio.open_connection", return_value=(mock_reader, mock_writer)), \
         patch.object(adapter, "_heartbeat_loop", new_callable=AsyncMock):
        await adapter.connect()

    # Should have written a login record
    mock_writer.write.assert_called()
    written = b"".join(call.args[0] for call in mock_writer.write.call_args_list)
    assert b"LR" in written
    assert b"AUTHKEY1" in written

@pytest.mark.asyncio
async def test_health_check_true_when_connected():
    adapter = OperaFIASAdapter(CONFIG)
    mock_writer = MagicMock()
    mock_writer.is_closing.return_value = False
    adapter._writer = mock_writer
    assert await adapter.health_check() is True

@pytest.mark.asyncio
async def test_health_check_false_when_not_connected():
    adapter = OperaFIASAdapter(CONFIG)
    assert await adapter.health_check() is False

@pytest.mark.asyncio
async def test_verify_guest_parses_gi_response():
    adapter = OperaFIASAdapter(CONFIG)
    mock_reader = AsyncMock()
    mock_writer = MagicMock()
    mock_writer.is_closing.return_value = False
    mock_writer.drain = AsyncMock()
    adapter._reader = mock_reader
    adapter._writer = mock_writer

    gi_response = (
        b'<GI RoomNumber="101" LastName="Smith" FirstName="John" '
        b'ArrivalDate="03-19-26" DepartureDate="03-22-26" '
        b'ReservationNumber="R999"/>\r\n'
    )
    mock_reader.read = AsyncMock(return_value=gi_response)

    result = await adapter.verify_guest("101", "Smith")

    assert isinstance(result, GuestInfo)
    assert result.room_number == "101"
    assert result.last_name == "Smith"

@pytest.mark.asyncio
async def test_verify_guest_not_found_returns_none():
    adapter = OperaFIASAdapter(CONFIG)
    mock_reader = AsyncMock()
    mock_writer = MagicMock()
    mock_writer.drain = AsyncMock()
    adapter._reader = mock_reader
    adapter._writer = mock_writer

    # GNA = Guest Not Available response
    mock_reader.read = AsyncMock(return_value=b"<GNA/>\r\n")

    result = await adapter.verify_guest("999", "Nobody")
    assert result is None


@pytest.mark.asyncio
async def test_connect_spawns_heartbeat_task():
    config = {"host": "10.0.0.1", "port": "5000", "auth_key": "key", "vendor_id": "vendor"}
    adapter = OperaFIASAdapter(config)

    mock_reader = AsyncMock()
    mock_writer = MagicMock()
    mock_writer.drain = AsyncMock()
    mock_reader.read = AsyncMock(return_value=b'<LA Status="0"/>')

    with patch("app.pms.opera_fias.asyncio.open_connection", return_value=(mock_reader, mock_writer)), \
         patch("app.pms.opera_fias.asyncio.create_task") as mock_create_task:
        await adapter.connect()

    mock_create_task.assert_called_once()
    call_arg = mock_create_task.call_args[0][0]
    assert inspect.isawaitable(call_arg) or inspect.iscoroutine(call_arg)
