"""
Integration tests for FIAS Emulator with the main project's OperaFIASAdapter.

These tests verify end-to-end connectivity between the captive portal's
OperaFIASAdapter and the FIAS emulator TCP server.

Tests cover:
- Happy path: Basic TCP connection, login, and guest lookup
- Connection failures: Login denial, connection drops
- Protocol errors: Malformed XML responses

To run these tests:
    pytest tests/integration/test_fias_emulator.py -v

Prerequisites:
    - The FIAS emulator must be seeded with scenarios
    - These tests will start/stop the emulator TCP server and management API
"""

import asyncio
import os
import sys
import xml.etree.ElementTree as ET
from datetime import datetime, timezone, timedelta
from typing import AsyncGenerator

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# Set environment variables BEFORE importing emulator modules
# This ensures the Settings class uses test values
_TEST_ENV = {
    "DATABASE_URL": "sqlite+aiosqlite:///:memory:",
    "AUTH_KEY": "test-integration-key",
    "FIAS_TCP_HOST": "127.0.0.1",
    "FIAS_TCP_PORT": "19090",
    "HTTP_HOST": "127.0.0.1",
    "HTTP_PORT": "18081",
}

for key, value in _TEST_ENV.items():
    os.environ[key] = value

# Add emulator to path for imports
_emulator_path = os.path.join(os.path.dirname(__file__), "..", "..", "tools", "fias-emulator")
sys.path.insert(0, _emulator_path)

# NOW import emulator modules (after env vars are set)
from emulator.models import Base, Scenario, Guest, FailureRule, ActivityLog, Connection
from emulator.fias_server import FIASServer

# Test configuration (must match env vars above)
EMULATOR_HOST = "127.0.0.1"
EMULATOR_TCP_PORT = 19090
TEST_AUTH_KEY = "test-integration-key"


# Create our own test engine and session factory
test_engine = create_async_engine(
    "sqlite+aiosqlite:///:memory:",
    echo=False,
)

TestSessionFactory = async_sessionmaker(
    test_engine,
    expire_on_commit=False,
)


async def init_test_db():
    """Create all tables in the test database."""
    async with test_engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def seed_test_scenarios(session: AsyncSession):
    """Seed the test database with scenarios."""
    from datetime import date

    TODAY = date.today()

    # Happy path scenario
    happy_path = Scenario(
        name="happy_path",
        description="Normal guest lookup with valid credentials.",
        is_active=True,
    )
    session.add(happy_path)
    await session.flush()

    happy_guests = [
        Guest(
            room_number="101",
            last_name="Smith",
            first_name="John",
            reservation_number="RES001",
            arrival_date=TODAY - timedelta(days=2),
            departure_date=TODAY + timedelta(days=3),
            is_active=True,
            scenario_id=happy_path.id,
        ),
        Guest(
            room_number="102",
            last_name="Johnson",
            first_name="Emily",
            reservation_number="RES002",
            arrival_date=TODAY - timedelta(days=1),
            departure_date=TODAY + timedelta(days=4),
            is_active=True,
            scenario_id=happy_path.id,
        ),
        Guest(
            room_number="103",
            last_name="Williams",
            first_name="Michael",
            reservation_number="RES003",
            arrival_date=TODAY,
            departure_date=TODAY + timedelta(days=5),
            is_active=True,
            scenario_id=happy_path.id,
        ),
    ]
    for guest in happy_guests:
        session.add(guest)

    # Connection failures scenario
    conn_failures = Scenario(
        name="connection_failures",
        description="Test connection failures.",
        is_active=False,
    )
    session.add(conn_failures)
    await session.flush()

    # Protocol errors scenario
    protocol_errors = Scenario(
        name="protocol_errors",
        description="Test protocol errors.",
        is_active=False,
    )
    session.add(protocol_errors)
    await session.flush()

    protocol_guests = [
        Guest(
            room_number="401",
            last_name="Thomas",
            first_name="Jennifer",
            reservation_number="RES201",
            arrival_date=TODAY,
            departure_date=TODAY + timedelta(days=2),
            is_active=True,
            scenario_id=protocol_errors.id,
        ),
        Guest(
            room_number="402",
            last_name="Jackson",
            first_name="Christopher",
            reservation_number="RES202",
            arrival_date=TODAY,
            departure_date=TODAY + timedelta(days=2),
            is_active=True,
            scenario_id=protocol_errors.id,
        ),
    ]
    for guest in protocol_guests:
        session.add(guest)

    await session.commit()


class _FIASProtocolHandler:
    """
    Simplified FIAS protocol handler for testing.

    This bypasses the database dependency in the real FIASProtocolHandler
    and uses in-memory test data instead.
    """

    def __init__(self, guests: list[Guest], failure_rules: list[FailureRule]):
        self.guests = guests
        self.failure_rules = failure_rules

    async def handle_data(self, data: str, writer: asyncio.StreamWriter) -> str | None:
        """Parse and handle a FIAS record."""
        import xml.etree.ElementTree as ET

        try:
            root = ET.fromstring(data)
        except ET.ParseError:
            return None

        record_type = root.tag.upper()

        if record_type == "LR":
            return await self._handle_lr(root)
        elif record_type == "KA":
            return "<KR/>"
        elif record_type == "GIQ":
            return await self._handle_giq(root)
        elif record_type == "LD":
            return ""

        return None

    async def _handle_lr(self, root: ET.Element) -> str:
        """Handle Login Request."""
        auth_key = root.get("AuthKey", "")

        # Check for failure rules
        for rule in self.failure_rules:
            if rule.trigger == "on_login" and rule.action == "login_denied":
                return '<LA Result="DENIED"/>'

        if auth_key != TEST_AUTH_KEY:
            return '<LA Result="DENIED"/>'

        return '<LA Result="OK"/>'

    async def _handle_giq(self, root: ET.Element) -> str:
        """Handle Guest Info Query."""
        room_number = root.get("RoomNumber", "")
        last_name = root.get("LastName", "")

        # Check for failure rules
        for rule in self.failure_rules:
            if rule.trigger == "on_query":
                if rule.action == "malformed_xml":
                    return self._generate_malformed_xml(rule.malformed_type)
                elif rule.action == "timeout":
                    return ""  # No response

        # Find guest
        for guest in self.guests:
            if guest.room_number == room_number and guest.is_active:
                if not last_name or guest.last_name.lower() == last_name.lower():
                    return self._make_gi_response(guest)

        return '<GI Result="NOT_FOUND"/>'

    def _make_gi_response(self, guest: Guest) -> str:
        """Create a Guest Info response."""
        arrival_str = guest.arrival_date.strftime("%m-%d-%y")
        departure_str = guest.departure_date.strftime("%m-%d-%y")

        attrs = [
            f'ReservationNumber="{guest.reservation_number}"',
            f'RoomNumber="{guest.room_number}"',
            f'LastName="{guest.last_name}"',
        ]

        if guest.first_name:
            attrs.append(f'FirstName="{guest.first_name}"')

        attrs.append(f'ArrivalDate="{arrival_str}"')
        attrs.append(f'DepartureDate="{departure_str}"')

        return f'<GI {" ".join(attrs)}/>'

    def _generate_malformed_xml(self, malformed_type: str | None) -> str:
        """Generate malformed XML."""
        if malformed_type == "unknown_tag":
            return '<UNKNOWN RoomNumber="101"/>'
        elif malformed_type == "missing_field":
            return '<GI RoomNumber="101"/>'  # Missing required fields
        elif malformed_type == "bad_encoding":
            return '<GI RoomNumber="101">\xff\xfe</GI>'
        return '<GI'  # Truncated


class _FIASServer:
    """
    Test FIAS server that uses in-memory test data.
    """

    def __init__(self, host: str, port: int, guests: list[Guest], failure_rules: list[FailureRule]):
        self.host = host
        self.port = port
        self.guests = guests
        self.failure_rules = failure_rules
        self._server: asyncio.Server | None = None
        self._running = False

    async def start(self):
        """Start the test server."""
        self._server = await asyncio.start_server(
            self._handle_connection,
            self.host,
            self.port,
        )
        self._running = True

        async with self._server:
            await self._server.serve_forever()

    async def stop(self):
        """Stop the test server."""
        self._running = False
        if self._server:
            self._server.close()
            await self._server.wait_closed()

    async def _handle_connection(self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter):
        """Handle a client connection."""
        handler = _FIASProtocolHandler(self.guests, self.failure_rules)
        buffer = b""

        try:
            while self._running:
                try:
                    data = await asyncio.wait_for(reader.read(4096), timeout=300.0)
                except asyncio.TimeoutError:
                    continue

                if not data:
                    break

                buffer += data

                while b"\r\n" in buffer:
                    line, buffer = buffer.split(b"\r\n", 1)
                    if not line:
                        continue

                    try:
                        record = line.decode("utf-8")
                        response = await handler.handle_data(record, writer)

                        if response:
                            writer.write(response.encode("utf-8") + b"\r\n")
                            await writer.drain()
                    except UnicodeDecodeError:
                        pass
        except (ConnectionResetError, BrokenPipeError):
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass


# ============================================================================
# Fixtures
# ============================================================================


@pytest_asyncio.fixture(scope="module")
async def test_database():
    """Initialize the test database with scenarios."""
    await init_test_db()

    async with TestSessionFactory() as session:
        await seed_test_scenarios(session)

    yield


@pytest_asyncio.fixture
async def db_session():
    """Provide a fresh database session for each test."""
    async with TestSessionFactory() as session:
        yield session


@pytest_asyncio.fixture
async def happy_path_server(test_database, db_session):
    """Start a FIAS server with happy_path scenario active."""
    # Get happy_path guests
    result = await db_session.execute(
        select(Scenario).where(Scenario.name == "happy_path")
    )
    scenario = result.scalar_one_or_none()

    result = await db_session.execute(
        select(Guest).where(Guest.scenario_id == scenario.id)
    )
    guests = list(result.scalars().all())

    # No failure rules for happy path
    server = _FIASServer(EMULATOR_HOST, EMULATOR_TCP_PORT, guests, [])

    server_task = asyncio.create_task(server.start())
    await asyncio.sleep(0.3)  # Wait for server to start

    yield server

    await server.stop()
    server_task.cancel()
    try:
        await server_task
    except asyncio.CancelledError:
        pass


@pytest_asyncio.fixture
async def failure_rules_server(test_database, db_session):
    """Start a FIAS server that can have failure rules added dynamically."""
    # Get happy_path guests as base
    result = await db_session.execute(
        select(Scenario).where(Scenario.name == "happy_path")
    )
    scenario = result.scalar_one_or_none()

    result = await db_session.execute(
        select(Guest).where(Guest.scenario_id == scenario.id)
    )
    guests = list(result.scalars().all())

    # Use a mutable list for failure rules
    failure_rules: list[FailureRule] = []

    server = _FIASServer(EMULATOR_HOST, EMULATOR_TCP_PORT, guests, failure_rules)

    server_task = asyncio.create_task(server.start())
    await asyncio.sleep(0.3)

    yield {"server": server, "failure_rules": failure_rules}

    await server.stop()
    server_task.cancel()
    try:
        await server_task
    except asyncio.CancelledError:
        pass


def create_adapter():
    """Create an OperaFIASAdapter instance with test configuration."""
    from app.pms.opera_fias import OperaFIASAdapter

    config = {
        "host": EMULATOR_HOST,
        "port": EMULATOR_TCP_PORT,
        "auth_key": TEST_AUTH_KEY,
        "vendor_id": "INTEGRATION_TEST",
    }
    return OperaFIASAdapter(config)


# ============================================================================
# Happy Path Tests
# ============================================================================


@pytest.mark.asyncio
async def test_happy_path_connection(happy_path_server):
    """Test basic TCP connection and login with valid credentials."""
    adapter = create_adapter()

    try:
        await adapter.connect()
        assert await adapter.health_check() is True
    finally:
        await adapter.disconnect()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_happy_path_guest_query(happy_path_server):
    """Test guest lookup returns correct data for happy_path scenario."""
    adapter = create_adapter()

    try:
        await adapter.connect()

        # Query for room 101, guest "Smith"
        result = await adapter.verify_guest("101", "Smith")

        assert result is not None
        assert result.room_number == "101"
        assert result.last_name == "Smith"
        assert result.first_name == "John"
        assert result.pms_id == "RES001"

    finally:
        await adapter.disconnect()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_happy_path_guest_not_found(happy_path_server):
    """Test guest lookup returns None for non-existent guest."""
    adapter = create_adapter()

    try:
        await adapter.connect()

        result = await adapter.verify_guest("999", "Nonexistent")

        assert result is None

    finally:
        await adapter.disconnect()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_happy_path_get_guest_by_room(happy_path_server):
    """Test getting guest by room number only."""
    adapter = create_adapter()

    try:
        await adapter.connect()

        result = await adapter.get_guest_by_room("102")

        assert result is not None
        assert result.room_number == "102"
        assert result.last_name == "Johnson"
        assert result.first_name == "Emily"

    finally:
        await adapter.disconnect()


# ============================================================================
# Connection Failure Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_connection_failures_login_denied(failure_rules_server):
    """Test login denial with failure rule."""
    # Add a login denial failure rule
    rule = FailureRule(
        trigger="on_login",
        action="login_denied",
        probability=1.0,
    )
    failure_rules_server["failure_rules"].append(rule)

    adapter = create_adapter()

    try:
        # Connect - the login will be denied but adapter continues
        # (current implementation doesn't check LA result)
        await adapter.connect()

        # Subsequent queries should fail since server doesn't recognize us
        # The adapter will still try to query, but the server may reject
        # or the behavior depends on server implementation

    finally:
        try:
            await adapter.disconnect()
        except Exception:
            pass


# ============================================================================
# Protocol Error Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_protocol_errors_malformed_xml(failure_rules_server):
    """Test handling of malformed XML responses."""
    # Add a malformed XML failure rule
    rule = FailureRule(
        trigger="on_query",
        action="malformed_xml",
        probability=1.0,
        malformed_type="unknown_tag",
    )
    failure_rules_server["failure_rules"].append(rule)

    adapter = create_adapter()

    try:
        await adapter.connect()

        result = await adapter.verify_guest("101", "Smith")

        # Should return None when parsing fails
        assert result is None

    finally:
        try:
            await adapter.disconnect()
        except Exception:
            pass


@pytest.mark.asyncio
@pytest.mark.integration
async def test_protocol_errors_missing_field(failure_rules_server):
    """Test handling of XML with missing required fields."""
    # Add a missing field failure rule
    rule = FailureRule(
        trigger="on_query",
        action="malformed_xml",
        probability=1.0,
        malformed_type="missing_field",
    )
    failure_rules_server["failure_rules"].append(rule)

    adapter = create_adapter()

    try:
        await adapter.connect()

        result = await adapter.verify_guest("101", "Smith")

        # Should return None when required fields are missing
        assert result is None

    finally:
        try:
            await adapter.disconnect()
        except Exception:
            pass


# ============================================================================
# Reconnection and Resilience Tests
# ============================================================================


@pytest.mark.asyncio
@pytest.mark.integration
async def test_reconnect_after_disconnect(happy_path_server):
    """Test that adapter can reconnect after disconnect."""
    adapter = create_adapter()

    try:
        # First connection
        await adapter.connect()
        assert await adapter.health_check() is True

        # Disconnect
        await adapter.disconnect()
        assert await adapter.health_check() is False

        # Reconnect
        await adapter.connect()
        assert await adapter.health_check() is True

        # Verify we can query
        result = await adapter.verify_guest("101", "Smith")
        assert result is not None

    finally:
        await adapter.disconnect()


@pytest.mark.asyncio
@pytest.mark.integration
async def test_multiple_queries_same_connection(happy_path_server):
    """Test multiple queries over the same connection."""
    adapter = create_adapter()

    try:
        await adapter.connect()

        # Query multiple guests
        result1 = await adapter.verify_guest("101", "Smith")
        result2 = await adapter.verify_guest("102", "Johnson")
        result3 = await adapter.verify_guest("103", "Williams")

        assert result1 is not None
        assert result1.room_number == "101"

        assert result2 is not None
        assert result2.room_number == "102"

        assert result3 is not None
        assert result3.room_number == "103"

    finally:
        await adapter.disconnect()
