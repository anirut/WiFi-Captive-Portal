"""
Tests for the FIAS Emulator Management API.

These tests use an in-memory SQLite database for isolation.
"""

import os
import pytest
import pytest_asyncio
from datetime import date, datetime, timezone
from httpx import ASGITransport, AsyncClient
from unittest.mock import AsyncMock, patch, MagicMock

from sqlalchemy.ext.asyncio import (
    create_async_engine,
    async_sessionmaker,
    AsyncSession,
)

from emulator.main import app
from emulator.models import Base, Guest, Scenario, FailureRule, Connection, ActivityLog


@pytest.fixture(scope="module", autouse=True)
def set_test_env():
    """Set test environment variables before any app imports."""
    # Use in-memory SQLite for tests
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///:memory:"
    os.environ["AUTH_KEY"] = "test-key"
    yield
    # Cleanup
    os.environ.pop("DATABASE_URL", None)
    os.environ.pop("AUTH_KEY", None)


@pytest_asyncio.fixture(scope="function")
async def db_session():
    """Create a fresh database session for each test with isolated tables."""
    # Create a new engine for each test to ensure isolation
    engine = create_async_engine(
        "sqlite+aiosqlite:///:memory:",
        echo=False,
    )

    # Create all tables
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)

    # Create session factory
    session_factory = async_sessionmaker(
        engine,
        expire_on_commit=False,
    )

    session = session_factory()
    yield session

    # Cleanup
    await session.close()
    await engine.dispose()


@pytest.fixture
def mock_fias_server():
    """Mock FIAS server for testing."""
    with patch("emulator.main.FIASServer") as mock:
        server_instance = MagicMock()
        server_instance._running = True
        mock.return_value = server_instance
        yield mock


@pytest_asyncio.fixture(scope="function")
async def client(db_session, mock_fias_server):
    """Create an async test client with database override."""
    from emulator import database

    # Store original factory
    original_factory = database.AsyncSessionFactory

    # Create a factory that returns our test session
    test_factory = async_sessionmaker(
        bind=db_session.bind,
        expire_on_commit=False,
        class_=type(
            "TestSession",
            (AsyncSession,),
            {
                "__init__": lambda self, *args, **kwargs: super(type(self), self).__init__(
                    bind=db_session.bind, expire_on_commit=False
                )
            },
        ),
    )

    # Override the session factory globally
    database.AsyncSessionFactory = lambda: db_session

    with patch("emulator.main.init_db", new_callable=AsyncMock):
        with patch("emulator.main.close_db", new_callable=AsyncMock):
            with patch("emulator.database.get_db", return_value=iter([db_session])):
                transport = ASGITransport(app=app)
                async with AsyncClient(transport=transport, base_url="http://test") as test_client:
                    yield test_client

    # Restore original factory
    database.AsyncSessionFactory = original_factory


@pytest.mark.asyncio
class TestGuestEndpoints:
    """Tests for guest management endpoints."""

    async def test_list_guests_empty(self, client, db_session):
        """Test listing guests when empty."""
        response = await client.get("/api/guests")

        assert response.status_code == 200
        assert response.json() == []

    async def test_create_guest(self, client, db_session):
        """Test creating a guest."""
        response = await client.post(
            "/api/guests",
            json={
                "room_number": "101",
                "last_name": "Smith",
                "first_name": "John",
                "reservation_number": "RES001",
                "arrival_date": "2024-01-15",
                "departure_date": "2024-01-20",
                "is_active": True,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["room_number"] == "101"
        assert data["last_name"] == "Smith"
        assert data["reservation_number"] == "RES001"
        assert data["id"] == 1

    async def test_create_guest_duplicate_reservation(self, client, db_session):
        """Test creating a guest with duplicate reservation number."""
        # First create a guest
        await client.post(
            "/api/guests",
            json={
                "room_number": "101",
                "last_name": "Smith",
                "reservation_number": "RES001",
                "arrival_date": "2024-01-15",
                "departure_date": "2024-01-20",
            },
        )

        # Try to create another with same reservation number
        response = await client.post(
            "/api/guests",
            json={
                "room_number": "102",
                "last_name": "Jones",
                "reservation_number": "RES001",  # Duplicate
                "arrival_date": "2024-01-15",
                "departure_date": "2024-01-20",
            },
        )

        assert response.status_code == 400
        assert "error" in response.json()["detail"]

    async def test_get_guest(self, client, db_session):
        """Test getting a guest by ID."""
        # Create a guest
        create_response = await client.post(
            "/api/guests",
            json={
                "room_number": "101",
                "last_name": "Smith",
                "reservation_number": "RES001",
                "arrival_date": "2024-01-15",
                "departure_date": "2024-01-20",
            },
        )
        guest_id = create_response.json()["id"]

        # Get the guest
        response = await client.get(f"/api/guests/{guest_id}")

        assert response.status_code == 200
        data = response.json()
        assert data["room_number"] == "101"
        assert data["last_name"] == "Smith"

    async def test_get_guest_not_found(self, client, db_session):
        """Test getting a non-existent guest."""
        response = await client.get("/api/guests/999")

        assert response.status_code == 404

    async def test_update_guest(self, client, db_session):
        """Test updating a guest."""
        # Create a guest
        create_response = await client.post(
            "/api/guests",
            json={
                "room_number": "101",
                "last_name": "Smith",
                "reservation_number": "RES001",
                "arrival_date": "2024-01-15",
                "departure_date": "2024-01-20",
            },
        )
        guest_id = create_response.json()["id"]

        # Update the guest
        response = await client.put(
            f"/api/guests/{guest_id}",
            json={"room_number": "102"},
        )

        assert response.status_code == 200
        data = response.json()
        assert data["room_number"] == "102"
        assert data["last_name"] == "Smith"  # Unchanged

    async def test_delete_guest(self, client, db_session):
        """Test deleting a guest."""
        # Create a guest
        create_response = await client.post(
            "/api/guests",
            json={
                "room_number": "101",
                "last_name": "Smith",
                "reservation_number": "RES001",
                "arrival_date": "2024-01-15",
                "departure_date": "2024-01-20",
            },
        )
        guest_id = create_response.json()["id"]

        # Delete the guest
        response = await client.delete(f"/api/guests/{guest_id}")

        assert response.status_code == 200
        assert response.json()["message"] == "Guest deleted"

        # Verify it's gone
        get_response = await client.get(f"/api/guests/{guest_id}")
        assert get_response.status_code == 404


@pytest.mark.asyncio
class TestScenarioEndpoints:
    """Tests for scenario management endpoints."""

    async def test_list_scenarios_empty(self, client, db_session):
        """Test listing scenarios when empty."""
        response = await client.get("/api/scenarios")

        assert response.status_code == 200
        assert response.json() == []

    async def test_activate_scenario_not_found(self, client, db_session):
        """Test activating a non-existent scenario."""
        response = await client.post("/api/scenarios/999/activate")

        assert response.status_code == 404

    async def test_activate_scenario(self, client, db_session):
        """Test activating a scenario."""
        # Create a scenario directly in DB
        scenario = Scenario(
            name="Test Scenario",
            description="A test scenario",
            is_active=False,
        )
        db_session.add(scenario)
        await db_session.commit()
        await db_session.refresh(scenario)

        # Activate it
        response = await client.post(f"/api/scenarios/{scenario.id}/activate")

        assert response.status_code == 200
        assert "activated" in response.json()["message"]


@pytest.mark.asyncio
class TestFailureRuleEndpoints:
    """Tests for failure rule management endpoints."""

    async def test_list_failure_rules_empty(self, client, db_session):
        """Test listing failure rules when empty."""
        response = await client.get("/api/failure-rules")

        assert response.status_code == 200
        assert response.json() == []

    async def test_create_failure_rule(self, client, db_session):
        """Test creating a failure rule."""
        response = await client.post(
            "/api/failure-rules",
            json={
                "trigger": "on_login",
                "action": "login_denied",
                "probability": 1.0,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["trigger"] == "on_login"
        assert data["action"] == "login_denied"

    async def test_create_failure_rule_with_scenario(self, client, db_session):
        """Test creating a failure rule with a scenario."""
        # Create a scenario
        scenario = Scenario(
            name="Test Scenario",
            description="A test scenario",
        )
        db_session.add(scenario)
        await db_session.commit()
        await db_session.refresh(scenario)

        response = await client.post(
            "/api/failure-rules",
            json={
                "scenario_id": scenario.id,
                "trigger": "on_query",
                "action": "delay:5s",
                "probability": 0.5,
            },
        )

        assert response.status_code == 201
        data = response.json()
        assert data["scenario_id"] == scenario.id
        assert data["trigger"] == "on_query"

    async def test_create_failure_rule_invalid_scenario(self, client, db_session):
        """Test creating a failure rule with non-existent scenario."""
        response = await client.post(
            "/api/failure-rules",
            json={
                "scenario_id": 999,
                "trigger": "on_query",
                "action": "delay:5s",
            },
        )

        assert response.status_code == 400

    async def test_delete_failure_rule(self, client, db_session):
        """Test deleting a failure rule."""
        # Create a rule
        create_response = await client.post(
            "/api/failure-rules",
            json={
                "trigger": "on_login",
                "action": "login_denied",
            },
        )
        rule_id = create_response.json()["id"]

        # Delete it
        response = await client.delete(f"/api/failure-rules/{rule_id}")

        assert response.status_code == 200
        assert response.json()["message"] == "Failure rule deleted"

    async def test_trigger_failure_rule_not_found(self, client, db_session):
        """Test triggering a non-existent failure rule."""
        response = await client.post("/api/failure-rules/999/trigger")

        assert response.status_code == 404

    async def test_trigger_failure_rule(self, client, db_session):
        """Test triggering a failure rule."""
        # Create a rule
        create_response = await client.post(
            "/api/failure-rules",
            json={
                "trigger": "on_login",
                "action": "login_denied",
            },
        )
        rule_id = create_response.json()["id"]

        # Trigger it
        response = await client.post(f"/api/failure-rules/{rule_id}/trigger")

        assert response.status_code == 200
        data = response.json()
        assert data["message"] == "Failure rule triggered"
        assert data["rule"]["id"] == rule_id


@pytest.mark.asyncio
class TestConnectionEndpoints:
    """Tests for connection endpoints."""

    async def test_list_connections_empty(self, client, db_session):
        """Test listing connections when empty."""
        response = await client.get("/api/connections")

        assert response.status_code == 200
        assert response.json() == []

    async def test_list_connections_with_data(self, client, db_session):
        """Test listing connections with data."""
        # Create a connection directly in DB
        conn = Connection(
            client_host="192.168.1.100",
            client_port=54321,
            vendor_id="TEST",
            is_active=True,
        )
        db_session.add(conn)
        await db_session.commit()

        response = await client.get("/api/connections")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["client_host"] == "192.168.1.100"


@pytest.mark.asyncio
class TestActivityEndpoints:
    """Tests for activity log endpoints."""

    async def test_list_activity_empty(self, client, db_session):
        """Test listing activity when empty."""
        response = await client.get("/api/activity")

        assert response.status_code == 200
        assert response.json() == []

    async def test_list_activity_with_data(self, client, db_session):
        """Test listing activity with data."""
        # Create an activity log directly in DB
        log = ActivityLog(
            direction="in",
            record_type="LR",
            raw_content='<LR VendorID="test"/>',
        )
        db_session.add(log)
        await db_session.commit()

        response = await client.get("/api/activity")

        assert response.status_code == 200
        data = response.json()
        assert len(data) == 1
        assert data[0]["direction"] == "in"
        assert data[0]["record_type"] == "LR"


@pytest.mark.asyncio
class TestResetEndpoint:
    """Tests for reset endpoint."""

    async def test_reset(self, client, db_session):
        """Test reset endpoint clears data."""
        # Create some data
        guest = Guest(
            room_number="101",
            last_name="Smith",
            reservation_number="RES001",
            arrival_date=date(2024, 1, 15),
            departure_date=date(2024, 1, 20),
        )
        db_session.add(guest)

        conn = Connection(
            client_host="192.168.1.100",
            client_port=54321,
        )
        db_session.add(conn)

        log = ActivityLog(
            direction="in",
            record_type="LR",
            raw_content="<LR/>",
        )
        db_session.add(log)
        await db_session.commit()

        # Reset
        response = await client.post("/api/reset")

        assert response.status_code == 200
        data = response.json()
        assert data["guests_cleared"] == 1
        assert data["connections_cleared"] == 1
        assert data["activity_logs_cleared"] == 1

        # Verify data is gone
        guests_response = await client.get("/api/guests")
        assert guests_response.json() == []


@pytest.mark.asyncio
class TestHealthEndpoint:
    """Tests for health check endpoint."""

    async def test_health_check(self, client):
        """Test health check endpoint."""
        response = await client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "healthy"
        assert "fias_server_running" in data


@pytest.mark.asyncio
class TestPageRoutes:
    """Tests for page routes (HTMX templates)."""

    async def test_dashboard_page(self, client):
        """Test dashboard page route."""
        response = await client.get("/")

        assert response.status_code == 200
        assert "FIAS Emulator" in response.text

    async def test_guests_page(self, client):
        """Test guests page route."""
        response = await client.get("/pages/guests")

        assert response.status_code == 200

    async def test_scenarios_page(self, client):
        """Test scenarios page route."""
        response = await client.get("/pages/scenarios")

        assert response.status_code == 200

    async def test_failure_rules_page(self, client):
        """Test failure rules page route."""
        response = await client.get("/pages/failure-rules")

        assert response.status_code == 200

    async def test_connections_page(self, client):
        """Test connections page route."""
        response = await client.get("/pages/connections")

        assert response.status_code == 200

    async def test_activity_page(self, client):
        """Test activity page route."""
        response = await client.get("/pages/activity")

        assert response.status_code == 200
