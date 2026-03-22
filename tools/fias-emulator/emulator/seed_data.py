"""
Seed data script for FIAS Emulator.

Populates the database with pre-configured test scenarios.
"""

import asyncio
from datetime import date, timedelta
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from emulator.database import AsyncSessionFactory, init_db
from emulator.models import FailureRule, Guest, Scenario

# Reference date for scenarios (today)
TODAY = date.today()


# ============================================================================
# Scenario Definitions
# ============================================================================

def get_happy_path_scenario() -> tuple[Scenario, list[Guest], list[FailureRule]]:
    """
    Happy path scenario: 5 guests, 0 failures.

    Normal guest lookup with valid credentials.
    All guests have proper check-in/check-out dates.
    """
    scenario = Scenario(
        name="happy_path",
        description="Normal guest lookup with valid credentials. All guests have proper check-in/check-out dates. No failures.",
        is_active=False,
    )

    guests = [
        Guest(
            room_number="101",
            last_name="Smith",
            first_name="John",
            reservation_number="RES001",
            arrival_date=TODAY - timedelta(days=2),
            departure_date=TODAY + timedelta(days=3),
            is_active=True,
        ),
        Guest(
            room_number="102",
            last_name="Johnson",
            first_name="Emily",
            reservation_number="RES002",
            arrival_date=TODAY - timedelta(days=1),
            departure_date=TODAY + timedelta(days=4),
            is_active=True,
        ),
        Guest(
            room_number="103",
            last_name="Williams",
            first_name="Michael",
            reservation_number="RES003",
            arrival_date=TODAY,
            departure_date=TODAY + timedelta(days=5),
            is_active=True,
        ),
        Guest(
            room_number="201",
            last_name="Brown",
            first_name="Sarah",
            reservation_number="RES004",
            arrival_date=TODAY - timedelta(days=3),
            departure_date=TODAY + timedelta(days=2),
            is_active=True,
        ),
        Guest(
            room_number="202",
            last_name="Davis",
            first_name="Robert",
            reservation_number="RES005",
            arrival_date=TODAY + timedelta(days=1),
            departure_date=TODAY + timedelta(days=6),
            is_active=True,
        ),
    ]

    return scenario, guests, []


def get_connection_failures_scenario() -> tuple[Scenario, list[Guest], list[FailureRule]]:
    """
    Connection failures scenario: 3 guests, 3 failures.

    Test connection drops, login denials, timeouts.
    """
    scenario = Scenario(
        name="connection_failures",
        description="Test connection drops, login denials, and timeouts. 3 guests with 3 failure rules.",
        is_active=False,
    )

    guests = [
        Guest(
            room_number="301",
            last_name="Wilson",
            first_name="James",
            reservation_number="RES101",
            arrival_date=TODAY,
            departure_date=TODAY + timedelta(days=3),
            is_active=True,
        ),
        Guest(
            room_number="302",
            last_name="Taylor",
            first_name="Lisa",
            reservation_number="RES102",
            arrival_date=TODAY,
            departure_date=TODAY + timedelta(days=3),
            is_active=True,
        ),
        Guest(
            room_number="303",
            last_name="Anderson",
            first_name="David",
            reservation_number="RES103",
            arrival_date=TODAY,
            departure_date=TODAY + timedelta(days=3),
            is_active=True,
        ),
    ]

    failure_rules = [
        FailureRule(
            trigger="on_login",
            action="drop_connection",
            probability=0.3,
        ),
        FailureRule(
            trigger="on_login",
            action="login_denied",
            probability=0.2,
        ),
        FailureRule(
            trigger="on_query",
            action="timeout",
            probability=0.25,
        ),
    ]

    return scenario, guests, failure_rules


def get_protocol_errors_scenario() -> tuple[Scenario, list[Guest], list[FailureRule]]:
    """
    Protocol errors scenario: 2 guests, 4 failures.

    Malformed XML, missing fields, bad encoding.
    """
    scenario = Scenario(
        name="protocol_errors",
        description="Test malformed XML responses, missing fields, bad encoding, and delays. 2 guests with 4 failure rules.",
        is_active=False,
    )

    guests = [
        Guest(
            room_number="401",
            last_name="Thomas",
            first_name="Jennifer",
            reservation_number="RES201",
            arrival_date=TODAY,
            departure_date=TODAY + timedelta(days=2),
            is_active=True,
        ),
        Guest(
            room_number="402",
            last_name="Jackson",
            first_name="Christopher",
            reservation_number="RES202",
            arrival_date=TODAY,
            departure_date=TODAY + timedelta(days=2),
            is_active=True,
        ),
    ]

    failure_rules = [
        FailureRule(
            trigger="on_query",
            action="malformed_xml",
            probability=0.25,
            malformed_type="missing_field",
        ),
        FailureRule(
            trigger="on_query",
            action="malformed_xml",
            probability=0.25,
            malformed_type="unknown_tag",
        ),
        FailureRule(
            trigger="on_query",
            action="malformed_xml",
            probability=0.25,
            malformed_type="bad_encoding",
        ),
        FailureRule(
            trigger="on_query",
            action="delay",
            probability=1.0,
        ),
    ]

    return scenario, guests, failure_rules


def get_edge_cases_scenario() -> tuple[Scenario, list[Guest], list[FailureRule]]:
    """
    Edge cases scenario: 8 guests, 0 failures.

    Multi-guest rooms, same-day turnover, early check-in.
    No failures, just complex guest data.
    """
    scenario = Scenario(
        name="edge_cases",
        description="Complex guest data: multi-guest rooms, same-day turnover, early check-ins. 8 guests, no failures.",
        is_active=False,
    )

    guests = [
        # Multi-guest room 501
        Guest(
            room_number="501",
            last_name="Martinez",
            first_name="Carlos",
            reservation_number="RES301",
            arrival_date=TODAY,
            departure_date=TODAY + timedelta(days=4),
            is_active=True,
        ),
        Guest(
            room_number="501",
            last_name="Martinez",
            first_name="Maria",
            reservation_number="RES302",
            arrival_date=TODAY,
            departure_date=TODAY + timedelta(days=4),
            is_active=True,
        ),
        # Same-day turnover - previous guest checking out today
        Guest(
            room_number="502",
            last_name="Robinson",
            first_name="Kevin",
            reservation_number="RES303",
            arrival_date=TODAY - timedelta(days=3),
            departure_date=TODAY,
            is_active=True,
        ),
        # Same-day turnover - new guest checking in today
        Guest(
            room_number="502",
            last_name="Clark",
            first_name="Amanda",
            reservation_number="RES304",
            arrival_date=TODAY,
            departure_date=TODAY + timedelta(days=2),
            is_active=True,
        ),
        # Early check-in (arrival yesterday, departure tomorrow)
        Guest(
            room_number="503",
            last_name="Lewis",
            first_name="Steven",
            reservation_number="RES305",
            arrival_date=TODAY - timedelta(days=1),
            departure_date=TODAY + timedelta(days=1),
            is_active=True,
        ),
        # Long-term stay
        Guest(
            room_number="601",
            last_name="Walker",
            first_name="Patricia",
            reservation_number="RES306",
            arrival_date=TODAY - timedelta(days=14),
            departure_date=TODAY + timedelta(days=14),
            is_active=True,
        ),
        # Short stay (1 night)
        Guest(
            room_number="602",
            last_name="Hall",
            first_name="Daniel",
            reservation_number="RES307",
            arrival_date=TODAY,
            departure_date=TODAY + timedelta(days=1),
            is_active=True,
        ),
        # Future reservation (not yet checked in)
        Guest(
            room_number="603",
            last_name="Young",
            first_name="Michelle",
            reservation_number="RES308",
            arrival_date=TODAY + timedelta(days=3),
            departure_date=TODAY + timedelta(days=7),
            is_active=True,
        ),
    ]

    return scenario, guests, []


def get_business_logic_scenario() -> tuple[Scenario, list[Guest], list[FailureRule]]:
    """
    Business logic scenario: 4 guests, 2 failures.

    Mid-session checkout, room reassignment.
    """
    scenario = Scenario(
        name="business_logic",
        description="Test mid-session checkout and room reassignment scenarios. 4 guests with 2 failure rules.",
        is_active=False,
    )

    guests = [
        # Guest who will check out mid-session
        Guest(
            room_number="701",
            last_name="Allen",
            first_name="Nancy",
            reservation_number="RES401",
            arrival_date=TODAY - timedelta(days=2),
            departure_date=TODAY + timedelta(days=3),
            is_active=True,
        ),
        # Guest whose room will be reassigned
        Guest(
            room_number="702",
            last_name="Wright",
            first_name="Kenneth",
            reservation_number="RES402",
            arrival_date=TODAY - timedelta(days=1),
            departure_date=TODAY + timedelta(days=4),
            is_active=True,
        ),
        # Normal active guest
        Guest(
            room_number="703",
            last_name="King",
            first_name="Sandra",
            reservation_number="RES403",
            arrival_date=TODAY,
            departure_date=TODAY + timedelta(days=5),
            is_active=True,
        ),
        # Another normal active guest
        Guest(
            room_number="704",
            last_name="Scott",
            first_name="Brandon",
            reservation_number="RES404",
            arrival_date=TODAY,
            departure_date=TODAY + timedelta(days=2),
            is_active=True,
        ),
    ]

    failure_rules = [
        FailureRule(
            trigger="on_query",
            action="business_rule",
            probability=0.5,
            business_rule="checkout_mid_session",
        ),
        FailureRule(
            trigger="on_query",
            action="business_rule",
            probability=0.5,
            business_rule="room_reassign",
        ),
    ]

    return scenario, guests, failure_rules


# List of all scenario generators
SCENARIO_GENERATORS = [
    get_happy_path_scenario,
    get_connection_failures_scenario,
    get_protocol_errors_scenario,
    get_edge_cases_scenario,
    get_business_logic_scenario,
]


# ============================================================================
# Seed Functions
# ============================================================================

async def clear_existing_data(session: AsyncSession) -> None:
    """Clear existing scenarios, guests, and failure rules."""
    # Delete in order to respect foreign key constraints
    await session.execute(FailureRule.__table__.delete())
    await session.execute(Guest.__table__.delete())
    await session.execute(Scenario.__table__.delete())
    await session.commit()
    print("Cleared existing data.")


async def seed_scenario(
    session: AsyncSession,
    scenario: Scenario,
    guests: list[Guest],
    failure_rules: list[FailureRule],
) -> None:
    """Add a single scenario with its guests and failure rules."""
    # Check if scenario already exists
    existing = await session.execute(
        select(Scenario).where(Scenario.name == scenario.name)
    )
    if existing.scalar_one_or_none() is not None:
        print(f"  Scenario '{scenario.name}' already exists, skipping...")
        return

    # Add scenario first
    session.add(scenario)
    await session.flush()  # Get the scenario ID

    # Add guests with scenario reference
    for guest in guests:
        guest.scenario_id = scenario.id
        session.add(guest)

    # Add failure rules with scenario reference
    for rule in failure_rules:
        rule.scenario_id = scenario.id
        session.add(rule)

    await session.commit()
    print(
        f"  Added scenario '{scenario.name}': "
        f"{len(guests)} guests, {len(failure_rules)} failure rules"
    )


async def seed_all_scenarios(
    session: AsyncSession,
    clear_first: bool = True,
    activate: Optional[str] = None,
) -> dict[str, int]:
    """
    Seed all pre-configured scenarios.

    Args:
        session: Database session
        clear_first: Whether to clear existing data first
        activate: Optional scenario name to activate after seeding

    Returns:
        Dictionary with counts of scenarios, guests, and failure rules created
    """
    if clear_first:
        await clear_existing_data(session)

    counts = {"scenarios": 0, "guests": 0, "failure_rules": 0}

    print("\nSeeding scenarios...")

    for generator in SCENARIO_GENERATORS:
        scenario, guests, failure_rules = generator()

        # Check if scenario exists (in case we didn't clear)
        existing = await session.execute(
            select(Scenario).where(Scenario.name == scenario.name)
        )
        if existing.scalar_one_or_none() is not None:
            print(f"  Scenario '{scenario.name}' already exists, skipping...")
            continue

        # Add scenario
        session.add(scenario)
        await session.flush()

        # Add guests
        for guest in guests:
            guest.scenario_id = scenario.id
            session.add(guest)

        # Add failure rules
        for rule in failure_rules:
            rule.scenario_id = scenario.id
            session.add(rule)

        await session.commit()

        counts["scenarios"] += 1
        counts["guests"] += len(guests)
        counts["failure_rules"] += len(failure_rules)

        print(
            f"  Created '{scenario.name}': "
            f"{len(guests)} guests, {len(failure_rules)} failure rules"
        )

    # Activate a specific scenario if requested
    if activate:
        await activate_scenario(session, activate)

    print(
        f"\nSeeding complete: {counts['scenarios']} scenarios, "
        f"{counts['guests']} guests, {counts['failure_rules']} failure rules"
    )

    return counts


async def activate_scenario(session: AsyncSession, name: str) -> bool:
    """
    Activate a specific scenario by name.

    Deactivates all other scenarios first.

    Args:
        session: Database session
        name: Scenario name to activate

    Returns:
        True if scenario was found and activated, False otherwise
    """
    # Deactivate all scenarios
    await session.execute(
        Scenario.__table__.update().values(is_active=False)
    )

    # Find and activate the target scenario
    result = await session.execute(
        select(Scenario).where(Scenario.name == name)
    )
    scenario = result.scalar_one_or_none()

    if scenario is None:
        print(f"  Warning: Scenario '{name}' not found.")
        return False

    scenario.is_active = True
    await session.commit()
    print(f"  Activated scenario '{name}'.")
    return True


async def list_scenarios(session: AsyncSession) -> list[dict]:
    """
    List all scenarios with their guest and failure rule counts.

    Args:
        session: Database session

    Returns:
        List of scenario info dictionaries
    """
    result = await session.execute(select(Scenario))
    scenarios = result.scalars().all()

    scenario_list = []
    for scenario in scenarios:
        # Count guests
        guest_result = await session.execute(
            select(Guest).where(Guest.scenario_id == scenario.id)
        )
        guest_count = len(guest_result.scalars().all())

        # Count failure rules
        rule_result = await session.execute(
            select(FailureRule).where(FailureRule.scenario_id == scenario.id)
        )
        rule_count = len(rule_result.scalars().all())

        scenario_list.append(
            {
                "name": scenario.name,
                "description": scenario.description,
                "is_active": scenario.is_active,
                "guest_count": guest_count,
                "failure_rule_count": rule_count,
            }
        )

    return scenario_list


async def main() -> None:
    """Main entry point for seeding the database."""
    print("FIAS Emulator - Database Seeding")
    print("=" * 40)

    # Initialize database (create tables if needed)
    await init_db()

    # Seed all scenarios
    async with AsyncSessionFactory() as session:
        await seed_all_scenarios(session, clear_first=True)

        # List all scenarios
        print("\nAvailable scenarios:")
        scenarios = await list_scenarios(session)
        for s in scenarios:
            status = "[ACTIVE]" if s["is_active"] else "[inactive]"
            print(f"  {status} {s['name']}: {s['guest_count']} guests, {s['failure_rule_count']} rules")
            print(f"          {s['description']}")


if __name__ == "__main__":
    asyncio.run(main())
