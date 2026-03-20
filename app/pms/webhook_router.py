import uuid
import hmac
import hashlib
import logging
from fastapi import APIRouter, Depends, HTTPException, Header
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.models import PMSAdapter as PMSAdapterModel
from app.network.session_manager import SessionManager

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/internal/pms")
_manager = SessionManager()


async def expire_sessions_for_room(db: AsyncSession, room_number: str) -> int:
    """Thin wrapper so tests can mock it cleanly."""
    return await _manager.expire_sessions_for_room(db, room_number)


@router.post("/webhook/{adapter_id}")
async def pms_webhook(
    adapter_id: uuid.UUID,
    payload: dict,
    x_pms_secret: str = Header(alias="X-PMS-Secret", default=""),
    db: AsyncSession = Depends(get_db),
):
    result = await db.execute(
        select(PMSAdapterModel).where(PMSAdapterModel.id == adapter_id)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail={"error": "adapter_not_found"})

    expected = record.webhook_secret or ""
    incoming_hash = hashlib.sha256(x_pms_secret.encode()).hexdigest()
    if not hmac.compare_digest(incoming_hash, expected):
        raise HTTPException(status_code=401, detail={"error": "invalid_secret"})

    adapter_type = record.type.value
    room_number = None

    if adapter_type == "opera_cloud":
        if payload.get("eventType") == "CHECKED_OUT":
            room_number = payload.get("roomNumber")
            if room_number is None:
                logger.warning(f"Webhook opera_cloud: CHECKED_OUT event missing roomNumber — payload: {payload}")
    elif adapter_type == "mews":
        if payload.get("Type") == "ReservationUpdated" and payload.get("State") == "Checked_out":
            room_number = payload.get("RoomNumber")
            if room_number is None:
                logger.warning(f"Webhook mews: Checked_out event missing RoomNumber — payload: {payload}")

    if room_number:
        count = await expire_sessions_for_room(db, room_number)
        logger.info(f"Webhook checkout: room={room_number}, expired {count} sessions")

    return {"ok": True}
