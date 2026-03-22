"""
Tests for FIAS TCP Server.
"""

import asyncio
import pytest
import pytest_asyncio
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from emulator.models import Guest, FailureRule, Scenario, Connection, ActivityLog
from emulator.fias_server import (
    FIASContext,
    FIASProtocolHandler,
    FIASServer,
    FailureActionResult,
)


@pytest_asyncio.fixture
async def context(db_session: AsyncSession) -> FIASContext:
    """Create a FIAS context for testing."""
    return FIASContext(
        client_host="127.0.0.1",
        client_port=12345,
    )


@pytest_asyncio.fixture
async def handler(db_session: AsyncSession, context: FIASContext) -> FIASProtocolHandler:
    """Create a FIAS protocol handler for testing."""
    return FIASProtocolHandler(db_session, context)


@pytest_asyncio.fixture
async def sample_guest(db_session: AsyncSession) -> Guest:
    """Create a sample guest in the database."""
    guest = Guest(
        room_number="101",
        last_name="Smith",
        first_name="John",
        reservation_number="RES001",
        arrival_date=date.today(),
        departure_date=date.today() + timedelta(days=3),
        is_active=True,
    )
    db_session.add(guest)
    await db_session.commit()
    await db_session.refresh(guest)
    return guest


@pytest_asyncio.fixture
async def sample_scenario(db_session: AsyncSession) -> Scenario:
    """Create a sample scenario in the database."""
    scenario = Scenario(
        name="test_scenario",
        description="Test scenario for failure injection",
        is_active=True,
    )
    db_session.add(scenario)
    await db_session.commit()
    await db_session.refresh(scenario)
    return scenario


class TestFIASProtocolHandler:
    """Tests for FIASProtocolHandler."""

    @pytest.mark.asyncio
    async def test_handle_lr_success(self, handler: FIASProtocolHandler, db_session: AsyncSession):
        """Test successful login."""
        # Create connection record
        conn = Connection(client_host="127.0.0.1", client_port=12345)
        db_session.add(conn)
        await db_session.commit()
        await db_session.refresh(conn)
        handler.context.connection_id = conn.id

        response = await handler.handle_data('<LR AuthKey="test-key" VendorID="TEST_VENDOR"/>')

        assert response == '<LA Result="OK"/>'
        assert handler.context.authenticated is True
        assert handler.context.vendor_id == "TEST_VENDOR"

    @pytest.mark.asyncio
    async def test_handle_lr_with_auth_key_validation(
        self, handler: FIASProtocolHandler, monkeypatch
    ):
        """Test login with auth key validation."""
        monkeypatch.setattr("emulator.fias_server.settings.auth_key", "secret-key")

        # Wrong key
        response = await handler.handle_data('<LR AuthKey="wrong-key" VendorID="TEST_VENDOR"/>')
        assert response == '<LA Result="DENIED"/>'
        assert handler.context.authenticated is False

    @pytest.mark.asyncio
    async def test_handle_ka(self, handler: FIASProtocolHandler):
        """Test keep-alive handling."""
        response = await handler.handle_data("<KA/>")
        assert response == "<KR/>"

    @pytest.mark.asyncio
    async def test_handle_giq_found(
        self, handler: FIASProtocolHandler, sample_guest: Guest
    ):
        """Test guest info query when guest is found."""
        response = await handler.handle_data(
            '<GIQ RoomNumber="101" LastName="Smith"/>'
        )

        assert response is not None
        assert '<GI ' in response
        assert 'RoomNumber="101"' in response
        assert 'LastName="Smith"' in response
        assert 'ReservationNumber="RES001"' in response
        assert 'FirstName="John"' in response

    @pytest.mark.asyncio
    async def test_handle_giq_not_found(self, handler: FIASProtocolHandler):
        """Test guest info query when guest is not found."""
        response = await handler.handle_data(
            '<GIQ RoomNumber="999" LastName="Nobody"/>'
        )

        assert response == '<GI Result="NOT_FOUND"/>'

    @pytest.mark.asyncio
    async def test_handle_giq_case_insensitive(
        self, handler: FIASProtocolHandler, sample_guest: Guest
    ):
        """Test guest info query with different case."""
        response = await handler.handle_data(
            '<GIQ RoomNumber="101" LastName="smith"/>'
        )

        assert response is not None
        assert '<GI ' in response
        assert 'RoomNumber="101"' in response

    @pytest.mark.asyncio
    async def test_handle_drq(
        self, handler: FIASProtocolHandler, db_session: AsyncSession
    ):
        """Test departure query."""
        # Create multiple guests
        today = date.today()
        guest1 = Guest(
            room_number="101",
            last_name="Smith",
            reservation_number="RES001",
            arrival_date=today - timedelta(days=3),
            departure_date=today,
            is_active=True,
        )
        guest2 = Guest(
            room_number="102",
            last_name="Jones",
            reservation_number="RES002",
            arrival_date=today - timedelta(days=2),
            departure_date=today,
            is_active=True,
        )
        guest3 = Guest(
            room_number="103",
            last_name="Brown",
            reservation_number="RES003",
            arrival_date=today - timedelta(days=1),
            departure_date=today + timedelta(days=1),  # Different date
            is_active=True,
        )
        db_session.add_all([guest1, guest2, guest3])
        await db_session.commit()

        date_str = today.strftime("%m-%d-%y")
        response = await handler.handle_data(f'<DRQ DepartureDate="{date_str}"/>')

        assert response is not None
        assert '<DR RoomNumber="101"/>' in response
        assert '<DR RoomNumber="102"/>' in response
        assert "103" not in response  # Not departing today

    @pytest.mark.asyncio
    async def test_handle_drq_no_departures(self, handler: FIASProtocolHandler):
        """Test departure query when no departures."""
        response = await handler.handle_data('<DRQ DepartureDate="12-31-99"/>')
        assert response == ""

    @pytest.mark.asyncio
    async def test_handle_ld(self, handler: FIASProtocolHandler, db_session: AsyncSession):
        """Test logout handling."""
        # Create connection record
        conn = Connection(client_host="127.0.0.1", client_port=12345, is_active=True)
        db_session.add(conn)
        await db_session.commit()
        await db_session.refresh(conn)
        handler.context.connection_id = conn.id
        handler.context.authenticated = True

        response = await handler.handle_data("<LD/>")

        assert response == ""  # LD has no response
        assert handler._running is False
        assert handler.context.authenticated is False

    @pytest.mark.asyncio
    async def test_date_format(self, handler: FIASProtocolHandler, sample_guest: Guest):
        """Test that dates are formatted correctly as %m-%d-%y."""
        response = await handler.handle_data(
            '<GIQ RoomNumber="101" LastName="Smith"/>'
        )

        # Date format should be MM-DD-YY
        assert "ArrivalDate=" in response
        assert "DepartureDate=" in response
        # Check format matches MM-DD-YY pattern
        import re
        assert re.search(r'ArrivalDate="\d{2}-\d{2}-\d{2}"', response)
        assert re.search(r'DepartureDate="\d{2}-\d{2}-\d{2}"', response)


class TestFailureInjection:
    """Tests for failure injection logic."""

    @pytest.mark.asyncio
    async def test_login_denied_failure(
        self,
        handler: FIASProtocolHandler,
        db_session: AsyncSession,
        sample_scenario: Scenario,
    ):
        """Test login_denied failure injection."""
        rule = FailureRule(
            scenario_id=sample_scenario.id,
            trigger="on_login",
            action="login_denied",
            probability=1.0,
        )
        db_session.add(rule)
        await db_session.commit()

        response = await handler.handle_data(
            '<LR AuthKey="test-key" VendorID="TEST_VENDOR"/>'
        )

        assert response == '<LA Result="DENIED"/>'

    @pytest.mark.asyncio
    async def test_delay_failure(
        self,
        handler: FIASProtocolHandler,
        db_session: AsyncSession,
        sample_scenario: Scenario,
    ):
        """Test delay failure injection."""
        rule = FailureRule(
            scenario_id=sample_scenario.id,
            trigger="on_heartbeat",
            action="delay:0.1s",
            probability=1.0,
        )
        db_session.add(rule)
        await db_session.commit()

        import time
        start = time.time()
        response = await handler.handle_data("<KA/>")
        elapsed = time.time() - start

        assert response == "<KR/>"
        assert elapsed >= 0.1

    @pytest.mark.asyncio
    async def test_room_specific_failure(
        self,
        handler: FIASProtocolHandler,
        db_session: AsyncSession,
        sample_scenario: Scenario,
        sample_guest: Guest,
    ):
        """Test room-specific failure injection."""
        rule = FailureRule(
            scenario_id=sample_scenario.id,
            trigger="on_room:101",
            action="malformed_xml",  # Will cause malformed response
            probability=1.0,
            malformed_type="unknown_tag",
        )
        db_session.add(rule)
        await db_session.commit()

        response = await handler.handle_data(
            '<GIQ RoomNumber="101" LastName="Smith"/>'
        )

        # Room 101 should trigger failure, returning malformed XML
        assert response is not None
        assert "<UNKNOWN" in response  # unknown_tag malformation

    @pytest.mark.asyncio
    async def test_global_failure_rule(
        self,
        handler: FIASProtocolHandler,
        db_session: AsyncSession,
    ):
        """Test global failure rule (no scenario)."""
        rule = FailureRule(
            scenario_id=None,  # Global rule
            trigger="on_login",
            action="login_denied",
            probability=1.0,
        )
        db_session.add(rule)
        await db_session.commit()

        response = await handler.handle_data(
            '<LR AuthKey="test-key" VendorID="TEST_VENDOR"/>'
        )

        assert response == '<LA Result="DENIED"/>'

    @pytest.mark.asyncio
    async def test_probability_skip(
        self,
        handler: FIASProtocolHandler,
        db_session: AsyncSession,
        sample_scenario: Scenario,
    ):
        """Test that low probability rules may not fire."""
        rule = FailureRule(
            scenario_id=sample_scenario.id,
            trigger="on_login",
            action="login_denied",
            probability=0.0,  # Never fires
        )
        db_session.add(rule)
        await db_session.commit()

        # With probability 0, should always succeed
        for _ in range(5):
            new_handler = FIASProtocolHandler(
                db_session, FIASContext(client_host="127.0.0.1", client_port=12345)
            )
            response = await new_handler.handle_data(
                '<LR AuthKey="test-key" VendorID="TEST_VENDOR"/>'
            )
            assert response == '<LA Result="OK"/>'


class TestMalformedXML:
    """Tests for malformed XML generation."""

    def test_missing_field_malformation(self, handler: FIASProtocolHandler):
        """Test missing_field malformed type."""
        original = '<GI RoomNumber="101" LastName="Smith"/>'
        result = handler._generate_malformed_xml("missing_field", original)
        # Should have removed one attribute
        assert 'RoomNumber="101" LastName="Smith"' not in result
        assert "<GI " in result

    def test_unknown_tag_malformation(self, handler: FIASProtocolHandler):
        """Test unknown_tag malformed type."""
        original = '<GI RoomNumber="101" LastName="Smith"/>'
        result = handler._generate_malformed_xml("unknown_tag", original)
        assert "<UNKNOWN" in result

    def test_default_malformation(self, handler: FIASProtocolHandler):
        """Test default (truncated) malformed type."""
        original = '<GI RoomNumber="101" LastName="Smith"/>'
        result = handler._generate_malformed_xml(None, original)
        # Should be truncated
        assert len(result) < len(original)


class TestActivityLogging:
    """Tests for activity logging."""

    @pytest.mark.asyncio
    async def test_activity_logged(
        self, handler: FIASProtocolHandler, db_session: AsyncSession
    ):
        """Test that activities are logged to database."""
        # Create connection record
        conn = Connection(client_host="127.0.0.1", client_port=12345)
        db_session.add(conn)
        await db_session.commit()
        await db_session.refresh(conn)
        handler.context.connection_id = conn.id

        await handler.handle_data("<KA/>")

        # Check activity log
        stmt = select(ActivityLog).where(ActivityLog.connection_id == conn.id)
        result = await db_session.execute(stmt)
        logs = result.scalars().all()

        assert len(logs) >= 1
        # Should have incoming KA and outgoing KR
        record_types = [log.record_type for log in logs]
        assert "KA" in record_types


class TestFIASServer:
    """Tests for FIASServer class."""

    def test_server_initialization(self):
        """Test server initialization."""
        server = FIASServer(host="127.0.0.1", port=9999)
        assert server.host == "127.0.0.1"
        assert server.port == 9999
        assert server._server is None
        assert server._running is False

    @pytest.mark.asyncio
    async def test_server_start_stop(self):
        """Test server start and stop."""
        server = FIASServer(host="127.0.0.1", port=19090)  # Use non-standard port

        # Start server in background
        task = asyncio.create_task(server.start())

        # Give it time to start
        await asyncio.sleep(0.1)

        assert server._running is True
        assert server._server is not None

        # Stop server
        task.cancel()
        try:
            await task
        except asyncio.CancelledError:
            pass

        await server.stop()


class TestMockConnection:
    """Tests using mock TCP connections."""

    @pytest.mark.asyncio
    async def test_full_connection_flow(self, db_session: AsyncSession):
        """Test a complete connection flow with mock reader/writer."""
        # This test simulates a full connection scenario
        context = FIASContext(client_host="127.0.0.1", client_port=12345)
        handler = FIASProtocolHandler(db_session, context)

        # Create connection record
        conn = Connection(client_host="127.0.0.1", client_port=12345)
        db_session.add(conn)
        await db_session.commit()
        await db_session.refresh(conn)
        context.connection_id = conn.id

        # Create a test guest
        guest = Guest(
            room_number="201",
            last_name="Test",
            first_name="User",
            reservation_number="TEST001",
            arrival_date=date.today(),
            departure_date=date.today() + timedelta(days=1),
            is_active=True,
        )
        db_session.add(guest)
        await db_session.commit()

        # Simulate login
        response = await handler.handle_data(
            '<LR AuthKey="" VendorID="TEST_CLIENT"/>'
        )
        assert response == '<LA Result="OK"/>'

        # Simulate keep-alive
        response = await handler.handle_data("<KA/>")
        assert response == "<KR/>"

        # Simulate guest query
        response = await handler.handle_data(
            '<GIQ RoomNumber="201" LastName="Test"/>'
        )
        assert '<GI ' in response
        assert 'RoomNumber="201"' in response

        # Simulate logout
        response = await handler.handle_data("<LD/>")
        assert response == ""
