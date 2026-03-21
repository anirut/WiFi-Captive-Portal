import uuid
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select as sa_select
from app.core.database import get_db
from app.core.config import settings
from app.core.rate_limit import check_rate_limit, RateLimitExceeded
from app.pms.factory import get_adapter
from app.network.session_manager import SessionManager
from app.voucher.generator import validate_voucher, VoucherValidationError
from app.portal.schemas import RoomAuthRequest, VoucherAuthRequest, SessionResponse
from app.core.models import Guest, Room, Policy, Session, SessionStatus
import logging

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="app/portal/templates")
session_manager = SessionManager()

async def _get_redis(request: Request):
    return request.app.state.redis

@router.get("/", response_class=HTMLResponse)
async def portal_login(request: Request):
    return templates.TemplateResponse(request, "login.html")

@router.post("/auth/room")
async def auth_room(
    request: Request,
    body: RoomAuthRequest,
    db: AsyncSession = Depends(get_db),
):
    redis = await _get_redis(request)
    try:
        await check_rate_limit(
            request.client.host, redis,
            max_attempts=settings.AUTH_RATE_LIMIT_ATTEMPTS,
            window_seconds=settings.AUTH_RATE_LIMIT_WINDOW_SECONDS,
        )
    except RateLimitExceeded:
        raise HTTPException(status_code=429, detail={"error": "rate_limited"})

    adapter = get_adapter()
    guest_info = await adapter.verify_guest(body.room_number, body.last_name, db=db)
    if not guest_info:
        raise HTTPException(status_code=401, detail={"error": "guest_not_checked_in"})

    # Look up room policy for session duration + bandwidth limits
    room_result = await db.execute(sa_select(Room).where(Room.number == body.room_number))
    room = room_result.scalar_one_or_none()
    policy = None
    if room and room.policy_id:
        policy_result = await db.execute(sa_select(Policy).where(Policy.id == room.policy_id))
        policy = policy_result.scalar_one_or_none()

    if policy and policy.session_duration_min > 0:
        expires_at = min(guest_info.check_out, datetime.now(timezone.utc) + timedelta(minutes=policy.session_duration_min))
    else:
        expires_at = guest_info.check_out

    up_kbps = policy.bandwidth_up_kbps if policy else 0
    down_kbps = policy.bandwidth_down_kbps if policy else 0

    # Upsert local Guest record so sessions can be linked and expired by room
    if guest_info.pms_id:
        guest_result = await db.execute(sa_select(Guest).where(Guest.pms_guest_id == guest_info.pms_id))
    else:
        guest_result = await db.execute(sa_select(Guest).where(Guest.room_number == guest_info.room_number))
    guest = guest_result.scalar_one_or_none()
    if guest is None:
        guest = Guest(
            id=uuid.uuid4(),
            room_number=guest_info.room_number,
            last_name=guest_info.last_name,
            first_name=guest_info.first_name,
            pms_guest_id=guest_info.pms_id,
            check_in=guest_info.check_in,
            check_out=guest_info.check_out,
        )
        db.add(guest)
        await db.flush()
    else:
        guest.check_in = guest_info.check_in
        guest.check_out = guest_info.check_out
        guest.last_name = guest_info.last_name

    session = await session_manager.create_session(
        db=db, ip=request.client.host,
        guest_id=guest.id,
        expires_at=expires_at,
        bandwidth_up_kbps=up_kbps,
        bandwidth_down_kbps=down_kbps,
    )
    return SessionResponse(session_id=str(session.id), expires_at=session.expires_at)

@router.post("/auth/voucher")
async def auth_voucher(
    request: Request,
    body: VoucherAuthRequest,
    db: AsyncSession = Depends(get_db),
):
    redis = await _get_redis(request)
    try:
        await check_rate_limit(
            request.client.host, redis,
            max_attempts=settings.AUTH_RATE_LIMIT_ATTEMPTS,
            window_seconds=settings.AUTH_RATE_LIMIT_WINDOW_SECONDS,
        )
    except RateLimitExceeded:
        raise HTTPException(status_code=429, detail={"error": "rate_limited"})

    try:
        voucher = await validate_voucher(body.code, db=db)
    except VoucherValidationError as e:
        raise HTTPException(status_code=401, detail={"error": e.reason})

    if voucher.duration_minutes:
        expires_at = datetime.now(timezone.utc) + timedelta(minutes=voucher.duration_minutes)
    else:
        expires_at = datetime.now(timezone.utc) + timedelta(hours=24)

    session = await session_manager.create_session(
        db=db, ip=request.client.host,
        voucher_id=voucher.id,
        expires_at=expires_at,
    )
    voucher.used_count += 1
    await db.commit()
    return SessionResponse(session_id=str(session.id), expires_at=session.expires_at)

@router.get("/success", response_class=HTMLResponse)
async def portal_success(request: Request):
    return templates.TemplateResponse(request, "success.html")

@router.get("/expired", response_class=HTMLResponse)
async def portal_expired(request: Request):
    return templates.TemplateResponse(request, "expired.html")

@router.post("/session/disconnect")
async def disconnect(request: Request, db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        sa_select(Session).where(
            Session.ip_address == request.client.host,
            Session.status == SessionStatus.active
        )
    )
    session = result.scalar_one_or_none()
    if session:
        await session_manager.expire_session(db, session, SessionStatus.kicked)
    return {"status": "disconnected"}
