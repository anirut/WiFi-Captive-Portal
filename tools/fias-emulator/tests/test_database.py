"""
Tests for database layer of FIAS Emulator.
"""

import pytest
from datetime import date

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

# Import models
from emulator.models import (
    Base,
    Guest,
    Scenario,
    FailureRule,
    Connection,
    ActivityLog,
)


@pytest.mark.asyncio
async def test_database_connection(db_session: AsyncSession):
    """Test that we can connect to the database and create tables."""
    # Verify tables exist by querying them (should be empty)
    result = await db_session.execute(select(Guest))
    guests = result.scalars().all()
    assert guests == []

    result = await db_session.execute(select(Scenario))
    scenarios = result.scalars().all()
    assert scenarios == []


@pytest.mark.asyncio
async def test_create_guest(db_session: AsyncSession):
    """Test creating a guest record."""
    guest = Guest(
        room_number="101",
        last_name="Smith",
        first_name="John",
        reservation_number="RES-001",
        arrival_date=date(2024, 1, 15),
        departure_date=date(2024, 1, 20),
        is_active=True,
    )
    db_session.add(guest)
    await db_session.commit()

    # Query back
    result = await db_session.execute(select(Guest))
    guests = result.scalars().all()
    assert len(guests) == 1
    assert guests[0].room_number == "101"
    assert guests[0].last_name == "Smith"
    assert guests[0].reservation_number == "RES-001"


@pytest.mark.asyncio
async def test_create_scenario(db_session: AsyncSession):
    """Test creating a scenario record."""
    scenario = Scenario(
        name="happy_path",
        description="Normal guest login flow with no failures",
        is_active=True,
    )
    db_session.add(scenario)
    await db_session.commit()

    result = await db_session.execute(select(Scenario))
    scenarios = result.scalars().all()
    assert len(scenarios) == 1
    assert scenarios[0].name == "happy_path"
    assert scenarios[0].is_active is True


@pytest.mark.asyncio
async def test_create_failure_rule(db_session: AsyncSession):
    """Test creating a failure rule record."""
    # Create scenario first
    scenario = Scenario(
        name="connection_drops",
        description="Simulates connection drops",
    )
    db_session.add(scenario)
    await db_session.commit()

    # Create failure rule linked to scenario
    rule = FailureRule(
        scenario_id=scenario.id,
        trigger="on_login",
        action="drop_connection",
        probability=0.5,
    )
    db_session.add(rule)
    await db_session.commit()

    result = await db_session.execute(select(FailureRule))
    rules = result.scalars().all()
    assert len(rules) == 1
    assert rules[0].trigger == "on_login"
    assert rules[0].action == "drop_connection"
    assert rules[0].probability == 0.5


@pytest.mark.asyncio
async def test_create_connection(db_session: AsyncSession):
    """Test creating a connection record."""
    conn = Connection(
        client_host="192.168.1.100",
        client_port=54321,
        vendor_id="TEST_VENDOR",
        is_active=True,
    )
    db_session.add(conn)
    await db_session.commit()

    result = await db_session.execute(select(Connection))
    connections = result.scalars().all()
    assert len(connections) == 1
    assert connections[0].client_host == "192.168.1.100"
    assert connections[0].client_port == 54321
    assert connections[0].connected_at is not None


@pytest.mark.asyncio
async def test_create_activity_log(db_session: AsyncSession):
    """Test creating an activity log record."""
    # Create connection first
    conn = Connection(
        client_host="192.168.1.100",
        client_port=54321,
    )
    db_session.add(conn)
    await db_session.commit()
    await db_session.refresh(conn)

    # Create activity log
    log = ActivityLog(
        connection_id=conn.id,
        direction="in",
        record_type="LR",
        raw_content="<LR><RoomNumber>101</RoomNumber></LR>",
    )
    db_session.add(log)
    await db_session.commit()

    result = await db_session.execute(select(ActivityLog))
    logs = result.scalars().all()
    assert len(logs) == 1
    assert logs[0].direction == "in"
    assert logs[0].record_type == "LR"
    assert "RoomNumber" in logs[0].raw_content
    assert logs[0].timestamp is not None


@pytest.mark.asyncio
async def test_guest_scenario_relationship(db_session: AsyncSession):
    """Test the relationship between Guest and Scenario."""
    scenario = Scenario(
        name="test_scenario_rel",
        description="Test scenario",
    )
    db_session.add(scenario)
    await db_session.commit()
    await db_session.refresh(scenario)

    guest = Guest(
        room_number="102",
        last_name="Doe",
        reservation_number="RES-REL-001",
        arrival_date=date(2024, 2, 1),
        departure_date=date(2024, 2, 5),
        scenario_id=scenario.id,
    )
    db_session.add(guest)
    await db_session.commit()
    await db_session.refresh(guest)

    # Verify relationship
    result = await db_session.execute(
        select(Guest).where(Guest.reservation_number == "RES-REL-001")
    )
    guest_check = result.scalar_one_or_none()
    assert guest_check is not None
    assert guest_check.scenario_id == scenario.id


@pytest.mark.asyncio
async def test_connection_activity_log_relationship(db_session: AsyncSession):
    """Test the relationship between Connection and ActivityLog."""
    conn = Connection(
        client_host="10.0.0.1",
        client_port=12345,
    )
    db_session.add(conn)
    await db_session.commit()
    await db_session.refresh(conn)

    # Create multiple logs
    for i, record_type in enumerate(["LR", "GIQ", "GI"]):
        log = ActivityLog(
            connection_id=conn.id,
            direction="in" if i % 2 == 0 else "out",
            record_type=record_type,
            raw_content=f"<{record_type}>test</{record_type}>",
        )
        db_session.add(log)
    await db_session.commit()

    # Verify logs exist
    result = await db_session.execute(
        select(ActivityLog).where(ActivityLog.connection_id == conn.id)
    )
    logs = result.scalars().all()
    assert len(logs) == 3


@pytest.mark.asyncio
async def test_unique_reservation_number(db_session: AsyncSession):
    """Test that reservation numbers must be unique."""
    guest1 = Guest(
        room_number="101",
        last_name="Smith",
        reservation_number="RES-UNIQUE",
        arrival_date=date(2024, 1, 1),
        departure_date=date(2024, 1, 5),
    )
    db_session.add(guest1)
    await db_session.commit()

    guest2 = Guest(
        room_number="102",
        last_name="Jones",
        reservation_number="RES-UNIQUE",  # Same reservation number
        arrival_date=date(2024, 1, 1),
        departure_date=date(2024, 1, 5),
    )
    db_session.add(guest2)

    with pytest.raises(Exception):  # IntegrityError
        await db_session.commit()


@pytest.mark.asyncio
async def test_unique_scenario_name(db_session: AsyncSession):
    """Test that scenario names must be unique."""
    scenario1 = Scenario(
        name="unique_scenario",
        description="First",
    )
    db_session.add(scenario1)
    await db_session.commit()

    scenario2 = Scenario(
        name="unique_scenario",  # Same name
        description="Second",
    )
    db_session.add(scenario2)

    with pytest.raises(Exception):  # IntegrityError
        await db_session.commit()


@pytest.mark.asyncio
async def test_global_failure_rule(db_session: AsyncSession):
    """Test creating a global failure rule (no scenario)."""
    rule = FailureRule(
        scenario_id=None,  # Global rule
        trigger="on_query",
        action="delay:5s",
        probability=1.0,
    )
    db_session.add(rule)
    await db_session.commit()

    result = await db_session.execute(select(FailureRule))
    rules = result.scalars().all()
    assert len(rules) == 1
    assert rules[0].scenario_id is None
    assert rules[0].trigger == "on_query"


@pytest.mark.asyncio
async def test_malformed_type_failure_rule(db_session: AsyncSession):
    """Test failure rule with malformed_type."""
    rule = FailureRule(
        trigger="on_login",
        action="malformed_xml",
        malformed_type="missing_field",
        probability=1.0,
    )
    db_session.add(rule)
    await db_session.commit()

    result = await db_session.execute(select(FailureRule))
    rules = result.scalars().all()
    assert len(rules) == 1
    assert rules[0].malformed_type == "missing_field"


@pytest.mark.asyncio
async def test_business_rule_failure_rule(db_session: AsyncSession):
    """Test failure rule with business_rule."""
    rule = FailureRule(
        trigger="on_room:101",
        action="checkout_mid_session",
        business_rule="checkout_mid_session",
        probability=1.0,
    )
    db_session.add(rule)
    await db_session.commit()

    result = await db_session.execute(select(FailureRule))
    rules = result.scalars().all()
    assert len(rules) == 1
    assert rules[0].business_rule == "checkout_mid_session"
