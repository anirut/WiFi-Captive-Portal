"""
Management API routes for FIAS Emulator.

Provides REST endpoints for managing test guests, scenarios, failure rules,
connections, and activity logs.
"""

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import delete, func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from emulator.database import get_db
from emulator.models import ActivityLog, Connection, FailureRule, Guest, Scenario
from emulator.schemas import (
    ActivityLogResponse,
    ConnectionResponse,
    FailureRuleCreate,
    FailureRuleResponse,
    GuestCreate,
    GuestResponse,
    GuestUpdate,
    ResetResponse,
    ScenarioResponse,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api", tags=["management"])


# ============ Guest endpoints ============


@router.get("/guests", response_model=list[GuestResponse])
async def list_guests(
    is_active: Optional[bool] = None,
    scenario_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """List all test guests, optionally filtered."""
    stmt = select(Guest)

    if is_active is not None:
        stmt = stmt.where(Guest.is_active == is_active)
    if scenario_id is not None:
        stmt = stmt.where(Guest.scenario_id == scenario_id)

    stmt = stmt.order_by(Guest.id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("/guests", response_model=GuestResponse, status_code=201)
async def create_guest(guest_data: GuestCreate, db: AsyncSession = Depends(get_db)):
    """Create a new test guest."""
    # Check for duplicate reservation number
    stmt = select(Guest).where(Guest.reservation_number == guest_data.reservation_number)
    result = await db.execute(stmt)
    if result.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail={"error": f"Reservation number '{guest_data.reservation_number}' already exists"},
        )

    guest = Guest(**guest_data.model_dump())
    db.add(guest)
    await db.commit()
    await db.refresh(guest)
    return guest


@router.get("/guests/{guest_id}", response_model=GuestResponse)
async def get_guest(guest_id: int, db: AsyncSession = Depends(get_db)):
    """Get a specific guest by ID."""
    stmt = select(Guest).where(Guest.id == guest_id)
    result = await db.execute(stmt)
    guest = result.scalar_one_or_none()

    if guest is None:
        raise HTTPException(status_code=404, detail={"error": "Guest not found"})

    return guest


@router.put("/guests/{guest_id}", response_model=GuestResponse)
async def update_guest(
    guest_id: int,
    guest_data: GuestUpdate,
    db: AsyncSession = Depends(get_db),
):
    """Update a guest."""
    stmt = select(Guest).where(Guest.id == guest_id)
    result = await db.execute(stmt)
    guest = result.scalar_one_or_none()

    if guest is None:
        raise HTTPException(status_code=404, detail={"error": "Guest not found"})

    # Check for duplicate reservation number if changing
    if guest_data.reservation_number and guest_data.reservation_number != guest.reservation_number:
        stmt = select(Guest).where(Guest.reservation_number == guest_data.reservation_number)
        result = await db.execute(stmt)
        if result.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail={"error": f"Reservation number '{guest_data.reservation_number}' already exists"},
            )

    # Update only provided fields
    update_data = guest_data.model_dump(exclude_unset=True)
    for field, value in update_data.items():
        setattr(guest, field, value)

    await db.commit()
    await db.refresh(guest)
    return guest


@router.delete("/guests/{guest_id}")
async def delete_guest(guest_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a guest."""
    stmt = select(Guest).where(Guest.id == guest_id)
    result = await db.execute(stmt)
    guest = result.scalar_one_or_none()

    if guest is None:
        raise HTTPException(status_code=404, detail={"error": "Guest not found"})

    await db.delete(guest)
    await db.commit()
    return {"message": "Guest deleted", "id": guest_id}


# ============ Scenario endpoints ============


@router.get("/scenarios", response_model=list[ScenarioResponse])
async def list_scenarios(db: AsyncSession = Depends(get_db)):
    """List all scenarios with guest and failure rule counts."""
    # Query scenarios with counts
    stmt = select(Scenario).order_by(Scenario.id)
    result = await db.execute(stmt)
    scenarios = list(result.scalars().all())

    # Build response with counts
    response = []
    for scenario in scenarios:
        # Count guests
        guest_count_stmt = select(func.count()).select_from(Guest).where(Guest.scenario_id == scenario.id)
        guest_result = await db.execute(guest_count_stmt)
        guest_count = guest_result.scalar() or 0

        # Count failure rules
        rule_count_stmt = select(func.count()).select_from(FailureRule).where(
            FailureRule.scenario_id == scenario.id
        )
        rule_result = await db.execute(rule_count_stmt)
        rule_count = rule_result.scalar() or 0

        response.append(
            ScenarioResponse(
                id=scenario.id,
                name=scenario.name,
                description=scenario.description,
                is_active=scenario.is_active,
                guest_count=guest_count,
                failure_rule_count=rule_count,
            )
        )

    return response


@router.post("/scenarios/{scenario_id}/activate")
async def activate_scenario(scenario_id: int, db: AsyncSession = Depends(get_db)):
    """Activate a scenario (deactivates all others)."""
    stmt = select(Scenario).where(Scenario.id == scenario_id)
    result = await db.execute(stmt)
    scenario = result.scalar_one_or_none()

    if scenario is None:
        raise HTTPException(status_code=404, detail={"error": "Scenario not found"})

    # Deactivate all scenarios
    await db.execute(update(Scenario).values(is_active=False))

    # Activate the selected scenario
    scenario.is_active = True
    await db.commit()

    return {"message": f"Scenario '{scenario.name}' activated", "id": scenario_id}


# ============ Failure Rule endpoints ============


@router.get("/failure-rules", response_model=list[FailureRuleResponse])
async def list_failure_rules(
    scenario_id: Optional[int] = None,
    db: AsyncSession = Depends(get_db),
):
    """List all failure rules, optionally filtered by scenario."""
    stmt = select(FailureRule)

    if scenario_id is not None:
        stmt = stmt.where(FailureRule.scenario_id == scenario_id)

    stmt = stmt.order_by(FailureRule.id)
    result = await db.execute(stmt)
    return list(result.scalars().all())


@router.post("/failure-rules", response_model=FailureRuleResponse, status_code=201)
async def create_failure_rule(rule_data: FailureRuleCreate, db: AsyncSession = Depends(get_db)):
    """Create a new failure rule."""
    # Validate scenario exists if specified
    if rule_data.scenario_id is not None:
        stmt = select(Scenario).where(Scenario.id == rule_data.scenario_id)
        result = await db.execute(stmt)
        if result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=400,
                detail={"error": f"Scenario {rule_data.scenario_id} not found"},
            )

    rule = FailureRule(**rule_data.model_dump())
    db.add(rule)
    await db.commit()
    await db.refresh(rule)
    return rule


@router.delete("/failure-rules/{rule_id}")
async def delete_failure_rule(rule_id: int, db: AsyncSession = Depends(get_db)):
    """Delete a failure rule."""
    stmt = select(FailureRule).where(FailureRule.id == rule_id)
    result = await db.execute(stmt)
    rule = result.scalar_one_or_none()

    if rule is None:
        raise HTTPException(status_code=404, detail={"error": "Failure rule not found"})

    await db.delete(rule)
    await db.commit()
    return {"message": "Failure rule deleted", "id": rule_id}


@router.post("/failure-rules/{rule_id}/trigger")
async def trigger_failure_rule(rule_id: int, db: AsyncSession = Depends(get_db)):
    """
    Manually trigger a failure rule for testing.

    This endpoint doesn't actually inject a failure but returns information
    about what the rule would do when triggered.
    """
    stmt = select(FailureRule).where(FailureRule.id == rule_id)
    result = await db.execute(stmt)
    rule = result.scalar_one_or_none()

    if rule is None:
        raise HTTPException(status_code=404, detail={"error": "Failure rule not found"})

    # Log the manual trigger
    log = ActivityLog(
        connection_id=None,
        direction="out",
        record_type="MANUAL_TRIGGER",
        raw_content=f"Rule {rule_id} ({rule.trigger} -> {rule.action}) manually triggered",
    )
    db.add(log)
    await db.commit()

    return {
        "message": "Failure rule triggered",
        "rule": {
            "id": rule.id,
            "trigger": rule.trigger,
            "action": rule.action,
            "probability": rule.probability,
            "malformed_type": rule.malformed_type,
        },
    }


# ============ Connection endpoints ============


@router.get("/connections", response_model=list[ConnectionResponse])
async def list_connections(
    is_active: Optional[bool] = None,
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """List FIAS connections, optionally filtered by active status."""
    stmt = select(Connection)

    if is_active is not None:
        stmt = stmt.where(Connection.is_active == is_active)

    stmt = stmt.order_by(Connection.connected_at.desc()).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ============ Activity Log endpoints ============


@router.get("/activity", response_model=list[ActivityLogResponse])
async def list_activity(
    connection_id: Optional[int] = None,
    direction: Optional[str] = None,
    record_type: Optional[str] = None,
    limit: int = Query(100, ge=1, le=1000),
    db: AsyncSession = Depends(get_db),
):
    """List recent activity log entries."""
    stmt = select(ActivityLog)

    if connection_id is not None:
        stmt = stmt.where(ActivityLog.connection_id == connection_id)
    if direction is not None:
        stmt = stmt.where(ActivityLog.direction == direction)
    if record_type is not None:
        stmt = stmt.where(ActivityLog.record_type == record_type)

    stmt = stmt.order_by(ActivityLog.timestamp.desc()).limit(limit)
    result = await db.execute(stmt)
    return list(result.scalars().all())


# ============ Reset endpoint ============


@router.post("/reset", response_model=ResetResponse)
async def reset_all_data(db: AsyncSession = Depends(get_db)):
    """
    Clear all data and reset to defaults.

    This deletes all guests, connections, activity logs, and failure rules,
    then deactivates all scenarios.
    """
    # Count items before deletion
    guest_count = await db.scalar(select(func.count()).select_from(Guest)) or 0
    connection_count = await db.scalar(select(func.count()).select_from(Connection)) or 0
    activity_count = await db.scalar(select(func.count()).select_from(ActivityLog)) or 0

    # Delete all data
    await db.execute(delete(ActivityLog))
    await db.execute(delete(Connection))
    await db.execute(delete(Guest))
    await db.execute(delete(FailureRule))

    # Deactivate all scenarios
    await db.execute(update(Scenario).values(is_active=False))

    await db.commit()

    logger.info(
        f"Reset completed: cleared {guest_count} guests, "
        f"{connection_count} connections, {activity_count} activity logs"
    )

    return ResetResponse(
        guests_cleared=guest_count,
        connections_cleared=connection_count,
        activity_logs_cleared=activity_count,
    )
