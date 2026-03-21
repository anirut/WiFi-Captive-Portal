import time
import uuid
import bcrypt as _bcrypt
from datetime import datetime, timezone
from urllib.parse import urlparse
from fastapi import APIRouter, Depends, HTTPException, Request, UploadFile, File
import os as _os
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, func, extract, case
from datetime import timedelta
from fastapi import Query
from app.core.database import get_db
from app.core.models import Session, SessionStatus, PMSAdapter as PMSAdapterModel, PMSAdapterType, AdminUser, Voucher, VoucherType, Policy, Room, UsageSnapshot, BrandConfig, LanguageType
from app.core.encryption import encrypt_config, decrypt_config
from app.core.auth import get_current_user, get_current_admin, create_access_token, decode_access_token, require_superadmin
from app.core.config import settings
from app.network.session_manager import SessionManager
from app.pms.factory import load_adapter, ADAPTER_MAP
from app.admin.schemas import PMSConfigResponse, PMSConfigUpdate, PMSTestResult, VoucherCreate, VoucherResponse, BatchVoucherCreate
from fastapi.responses import Response as _Response
from app.voucher.pdf import generate_voucher_pdf as _gen_pdf
from app.voucher.generator import generate_code

router = APIRouter(prefix="/admin")
session_manager = SessionManager()
_templates = Jinja2Templates(directory="app/admin/templates")

def _verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode() if isinstance(hashed, str) else hashed)


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.get("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_page(request: Request):
    token = request.cookies.get("admin_token")
    if token:
        payload = decode_access_token(token)
        if payload:
            return RedirectResponse(url="/admin/", status_code=302)
    return _templates.TemplateResponse("login.html", {"request": request, "error": None})


@router.post("/login", response_class=HTMLResponse, include_in_schema=False)
async def login_submit(request: Request, db: AsyncSession = Depends(get_db)):
    form = await request.form()
    username = form.get("username", "")
    password = form.get("password", "")
    result = await db.execute(select(AdminUser).where(AdminUser.username == username))
    user = result.scalar_one_or_none()
    if not user or not _verify_password(password, user.password_hash):
        return _templates.TemplateResponse("login.html",
            {"request": request, "error": "Invalid username or password"}, status_code=401)
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    token = create_access_token({"sub": user.username, "role": user.role.value})
    next_url = request.query_params.get("next", "/admin/")
    # Fix 1: Reject absolute URLs to prevent open redirect
    parsed = urlparse(next_url)
    if parsed.scheme or parsed.netloc:
        next_url = "/admin/"
    resp = RedirectResponse(url=next_url, status_code=302)
    # Fix 2: Set secure cookie flag based on environment
    _secure = settings.ENVIRONMENT.lower() == "production"
    resp.set_cookie("admin_token", token, httponly=True, samesite="lax", secure=_secure)
    return resp


@router.get("/", response_class=HTMLResponse, include_in_schema=False)
async def dashboard_page(request: Request, payload: dict = Depends(get_current_admin),
                         db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Session).where(Session.status == SessionStatus.active)
        .order_by(Session.connected_at.desc()).limit(10)
    )
    recent_sessions = result.scalars().all()
    active_count = len(recent_sessions)
    flash = request.session.pop("flash", None)
    return _templates.TemplateResponse("dashboard.html", {
        "request": request, "current_user": payload,
        "recent_sessions": recent_sessions, "active_count": active_count,
        "flash": flash,
    })


@router.post("/logout")
async def admin_logout(request: Request, payload: dict = Depends(get_current_admin)):
    jti = payload.get("jti", "")
    if not jti:
        raise HTTPException(status_code=400, detail={"error": "token_missing_jti"})
    exp = payload["exp"]
    remaining_ttl = max(1, int(exp - time.time()))
    await request.app.state.redis.set(f"blocklist:{jti}", 1, ex=remaining_ttl)
    response = JSONResponse({"status": "logged_out"})
    response.delete_cookie("admin_token", httponly=True, samesite="lax")
    return response


@router.get("/sessions/rows", response_class=HTMLResponse, include_in_schema=False)
async def sessions_rows_fragment(request: Request, payload: dict = Depends(get_current_admin),
                                  db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Session).where(Session.status == SessionStatus.active))
    sessions = result.scalars().all()
    return _templates.TemplateResponse("sessions_rows.html",
        {"request": request, "current_user": payload, "sessions": sessions})

@router.get("/sessions", response_class=HTMLResponse, include_in_schema=False)
async def sessions_page(request: Request, payload: dict = Depends(get_current_admin),
                         db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Session).where(Session.status == SessionStatus.active))
    sessions = result.scalars().all()
    flash = request.session.pop("flash", None)
    return _templates.TemplateResponse("sessions.html",
        {"request": request, "current_user": payload, "sessions": sessions, "flash": flash})

@router.get("/api/sessions")
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_admin),
):
    result = await db.execute(
        select(Session).where(Session.status == SessionStatus.active)
    )
    sessions = result.scalars().all()
    return [{"id": str(s.id), "ip": s.ip_address, "connected_at": s.connected_at, "expires_at": s.expires_at} for s in sessions]

@router.delete("/sessions/{session_id}")
async def kick_session(
    session_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_admin),
):
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    await session_manager.expire_session(db, session, SessionStatus.kicked)
    return {"status": "kicked"}


_CREDENTIAL_KEYS = {"client_secret", "api_key", "token", "password", "access_token",
                    "client_token", "auth_key", "webhook_secret"}


def _mask_config(config: dict) -> dict:
    return {k: "***" if k in _CREDENTIAL_KEYS else v for k, v in config.items()}


@router.get("/pms", response_model=PMSConfigResponse)
async def get_pms_config(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_admin),
):
    result = await db.execute(
        select(PMSAdapterModel).where(PMSAdapterModel.is_active == True)
    )
    record = result.scalar_one_or_none()
    if not record:
        raise HTTPException(status_code=404, detail={"error": "no_active_adapter"})
    config = decrypt_config(record.config_encrypted) if record.config_encrypted else {}
    return PMSConfigResponse(
        id=record.id,
        type=PMSAdapterType(record.type.value),
        is_active=record.is_active,
        last_sync_at=record.last_sync_at,
        config=_mask_config(config),
    )


@router.put("/pms")
async def update_pms_config(
    body: PMSConfigUpdate,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_admin),
):
    result = await db.execute(
        select(PMSAdapterModel).where(PMSAdapterModel.is_active == True)
    )
    record = result.scalar_one_or_none()
    if not record:
        record = PMSAdapterModel(type=body.type, is_active=True)
        db.add(record)
    record.type = body.type
    record.config_encrypted = encrypt_config(body.config)
    if body.webhook_secret is not None:
        record.webhook_secret = body.webhook_secret
    await db.commit()
    await load_adapter(db)
    return {"ok": True}


@router.post("/pms/test", response_model=PMSTestResult)
async def test_pms_config(
    body: PMSConfigUpdate,
    _: dict = Depends(get_current_admin),
):
    adapter_class = ADAPTER_MAP.get(body.type)
    if not adapter_class:
        return PMSTestResult(ok=False, latency_ms=0.0, error="unsupported_adapter_type")
    if body.type == PMSAdapterType.standalone:
        return PMSTestResult(ok=True, latency_ms=0.0)
    adapter = adapter_class(body.config)
    start = time.monotonic()
    try:
        ok = await adapter.health_check()
        latency = (time.monotonic() - start) * 1000
        return PMSTestResult(ok=ok, latency_ms=round(latency, 1))
    except Exception as e:
        latency = (time.monotonic() - start) * 1000
        return PMSTestResult(ok=False, latency_ms=round(latency, 1), error=str(e))


@router.post("/vouchers/batch")
async def create_batch_vouchers(
    body: BatchVoucherCreate,
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_admin),
):
    """Create `count` vouchers with the same settings."""
    result = await db.execute(select(AdminUser).where(AdminUser.username == payload["sub"]))
    user = result.scalar_one_or_none()
    if not user:
        raise HTTPException(404, {"error": "user_not_found"})
    created = []
    for _ in range(body.count):
        v = Voucher(
            code=generate_code(),
            type=VoucherType(body.type),
            duration_minutes=body.duration_minutes,
            data_limit_mb=body.data_limit_mb,
            max_uses=body.max_uses,
            max_devices=body.max_devices,
            expires_at=body.expires_at,
            created_by=user.id,
        )
        db.add(v)
        created.append(v)
    await db.commit()
    return [{"id": str(v.id), "code": v.code, "type": v.type.value} for v in created]


@router.post("/vouchers", response_model=VoucherResponse, status_code=201)
async def create_voucher(
    body: VoucherCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(get_current_admin),
):
    # Resolve admin user id from JWT sub (username)
    result = await db.execute(select(AdminUser).where(AdminUser.username == current_user["sub"]))
    admin = result.scalar_one_or_none()
    if not admin:
        raise HTTPException(status_code=401, detail={"error": "invalid_token"})
    # Generate a unique code (retry once on collision)
    code = generate_code()
    existing = await db.execute(select(Voucher).where(Voucher.code == code))
    if existing.scalar_one_or_none():
        code = generate_code()
    voucher = Voucher(
        code=code,
        type=body.type,
        duration_minutes=body.duration_minutes,
        data_limit_mb=body.data_limit_mb,
        max_devices=body.max_devices,
        max_uses=body.max_uses,
        expires_at=body.expires_at,
        used_count=0,
        created_by=admin.id,
    )
    db.add(voucher)
    await db.commit()
    await db.refresh(voucher)
    return VoucherResponse(
        id=voucher.id,
        code=voucher.code,
        type=voucher.type,
        duration_minutes=voucher.duration_minutes,
        data_limit_mb=voucher.data_limit_mb,
        max_devices=voucher.max_devices,
        max_uses=voucher.max_uses,
        used_count=voucher.used_count,
        expires_at=voucher.expires_at,
        created_by=voucher.created_by,
    )


@router.get("/api/vouchers", response_model=list[VoucherResponse])
async def list_vouchers(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_admin),
):
    result = await db.execute(select(Voucher))
    vouchers = result.scalars().all()
    return [
        VoucherResponse(
            id=v.id,
            code=v.code,
            type=v.type,
            duration_minutes=v.duration_minutes,
            data_limit_mb=v.data_limit_mb,
            max_devices=v.max_devices,
            max_uses=v.max_uses,
            used_count=v.used_count,
            expires_at=v.expires_at,
            created_by=v.created_by,
        )
        for v in vouchers
    ]


@router.get("/vouchers/{voucher_id}/pdf")
async def download_voucher_pdf(
    voucher_id: uuid.UUID,
    qr_mode: str = "code",
    db: AsyncSession = Depends(get_db),
    payload: dict = Depends(get_current_admin),
):
    result = await db.execute(select(Voucher).where(Voucher.id == voucher_id))
    v = result.scalar_one_or_none()
    if not v:
        raise HTTPException(404, {"error": "not_found"})
    if qr_mode not in ("url", "code"):
        raise HTTPException(422, {"error": "invalid_qr_mode"})
    portal_url = f"http://{settings.PORTAL_IP}:{settings.PORTAL_PORT}"
    pdf = _gen_pdf([{"code": v.code, "type": v.type.value,
                     "duration_minutes": v.duration_minutes, "data_limit_mb": v.data_limit_mb}],
                   qr_mode=qr_mode, portal_url=portal_url)
    return _Response(content=pdf, media_type="application/pdf",
                     headers={"Content-Disposition": f'attachment; filename="voucher-{v.code}.pdf"'})


@router.get("/vouchers", response_class=HTMLResponse, include_in_schema=False)
async def vouchers_page(request: Request, payload: dict = Depends(get_current_admin),
                         db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Voucher).order_by(Voucher.created_at.desc()).limit(100))
    vouchers = result.scalars().all()
    flash = request.session.pop("flash", None)
    return _templates.TemplateResponse("vouchers.html", {
        "request": request, "current_user": payload, "vouchers": vouchers, "flash": flash,
    })


@router.delete("/vouchers/{voucher_id}", status_code=204)
async def delete_voucher(
    voucher_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_admin),
):
    result = await db.execute(select(Voucher).where(Voucher.id == voucher_id))
    voucher = result.scalar_one_or_none()
    if not voucher:
        raise HTTPException(status_code=404, detail={"error": "not_found"})
    await db.delete(voucher)
    await db.commit()


# ── Policy CRUD ──────────────────────────────────────────────────────────────

class PolicyCreate(BaseModel):
    name: str
    bandwidth_up_kbps: int = 0
    bandwidth_down_kbps: int = 0
    session_duration_min: int = 0
    max_devices: int = 3


@router.get("/api/policies")
async def list_policies(db: AsyncSession = Depends(get_db),
                        _: dict = Depends(require_superadmin)):
    result = await db.execute(select(Policy))
    return [{"id": str(p.id), "name": p.name, "bandwidth_up_kbps": p.bandwidth_up_kbps,
             "bandwidth_down_kbps": p.bandwidth_down_kbps, "session_duration_min": p.session_duration_min,
             "max_devices": p.max_devices} for p in result.scalars().all()]


@router.post("/api/policies", status_code=201)
async def create_policy(body: PolicyCreate, db: AsyncSession = Depends(get_db),
                         _: dict = Depends(require_superadmin)):
    p = Policy(**body.dict())
    db.add(p)
    await db.commit()
    await db.refresh(p)
    return {"id": str(p.id), "name": p.name}


@router.put("/api/policies/{policy_id}")
async def update_policy(policy_id: uuid.UUID, body: PolicyCreate,
                         db: AsyncSession = Depends(get_db), _: dict = Depends(require_superadmin)):
    result = await db.execute(select(Policy).where(Policy.id == policy_id))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, {"error": "not_found"})
    for k, v in body.dict().items():
        setattr(p, k, v)
    await db.commit()
    return {"id": str(p.id), "name": p.name}


@router.delete("/api/policies/{policy_id}")
async def delete_policy(policy_id: uuid.UUID, db: AsyncSession = Depends(get_db),
                         _: dict = Depends(require_superadmin)):
    result = await db.execute(select(Policy).where(Policy.id == policy_id))
    p = result.scalar_one_or_none()
    if not p:
        raise HTTPException(404, {"error": "not_found"})
    await db.delete(p)
    await db.commit()
    return {"status": "deleted"}


# ── Rooms ─────────────────────────────────────────────────────────────────────

class RoomPolicyAssign(BaseModel):
    policy_id: uuid.UUID | None = None


@router.get("/api/rooms")
async def list_rooms(db: AsyncSession = Depends(get_db), _: dict = Depends(require_superadmin)):
    result = await db.execute(select(Room))
    return [{"id": str(r.id), "number": r.number, "room_type": r.room_type,
             "policy_id": str(r.policy_id) if r.policy_id else None} for r in result.scalars().all()]


@router.put("/api/rooms/{room_id}/policy")
async def assign_room_policy(room_id: uuid.UUID, body: RoomPolicyAssign,
                              db: AsyncSession = Depends(get_db), _: dict = Depends(require_superadmin)):
    result = await db.execute(select(Room).where(Room.id == room_id))
    r = result.scalar_one_or_none()
    if not r:
        raise HTTPException(404, {"error": "not_found"})
    r.policy_id = body.policy_id
    await db.commit()
    return {"id": str(r.id), "number": r.number, "policy_id": str(r.policy_id) if r.policy_id else None}


# ── Analytics ─────────────────────────────────────────────────────────────────

RANGE_INTERVALS = {"24h": 24, "7d": 168, "30d": 720}  # hours


@router.get("/api/analytics/data")
async def analytics_data(
    range_param: str = Query("24h", alias="range"),
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_superadmin),
):
    if range_param not in RANGE_INTERVALS:
        return JSONResponse(status_code=400, content={"error": "invalid_range", "valid": list(RANGE_INTERVALS.keys())})
    hours = RANGE_INTERVALS[range_param]
    since = datetime.now(timezone.utc) - timedelta(hours=hours)

    snaps_result = await db.execute(
        select(UsageSnapshot).where(UsageSnapshot.snapshot_at >= since).order_by(UsageSnapshot.snapshot_at)
    )
    snaps = snaps_result.scalars().all()
    sessions_over_time = [{"timestamp": s.snapshot_at.isoformat(), "active_sessions": s.active_sessions} for s in snaps]
    bandwidth_per_hour = [{"timestamp": s.snapshot_at.isoformat(), "bytes_up": s.total_bytes_up, "bytes_down": s.total_bytes_down} for s in snaps]

    peak_result = await db.execute(
        select(
            extract("dow", UsageSnapshot.snapshot_at).label("dow"),
            extract("hour", UsageSnapshot.snapshot_at).label("hour"),
            func.sum(UsageSnapshot.active_sessions).label("count"),
        ).where(UsageSnapshot.snapshot_at >= since)
        .group_by("dow", "hour").order_by("dow", "hour")
    )
    peak_hours = [{"day_of_week": int(r.dow), "hour": int(r.hour), "count": int(r.count or 0)} for r in peak_result]

    auth_result = await db.execute(
        select(
            func.count(case((Session.voucher_id.is_(None), 1))).label("room_auth"),
            func.count(case((Session.voucher_id.isnot(None), 1))).label("voucher_auth"),
        ).where(Session.connected_at >= since)
    )
    row = auth_result.one()
    auth_breakdown = {"room_auth": row.room_auth or 0, "voucher_auth": row.voucher_auth or 0}

    return {"range": range_param, "sessions_over_time": sessions_over_time,
            "bandwidth_per_hour": bandwidth_per_hour, "peak_hours": peak_hours,
            "auth_breakdown": auth_breakdown}


@router.get("/analytics", response_class=HTMLResponse, include_in_schema=False)
async def analytics_page(
    request: Request,
    payload: dict = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
    range_param: str = Query("24h", alias="range"),
):
    if range_param not in RANGE_INTERVALS:
        range_param = "24h"
    hours = RANGE_INTERVALS[range_param]
    since = datetime.now(timezone.utc) - timedelta(hours=hours)
    snaps_result = await db.execute(
        select(UsageSnapshot).where(UsageSnapshot.snapshot_at >= since).order_by(UsageSnapshot.snapshot_at)
    )
    snaps = snaps_result.scalars().all()
    sessions_over_time = [{"timestamp": s.snapshot_at.isoformat(), "active_sessions": s.active_sessions} for s in snaps]
    bandwidth_per_hour = [{"timestamp": s.snapshot_at.isoformat(), "bytes_up": s.total_bytes_up, "bytes_down": s.total_bytes_down} for s in snaps]
    auth_result = await db.execute(
        select(
            func.count(case((Session.voucher_id.is_(None), 1))).label("room_auth"),
            func.count(case((Session.voucher_id.isnot(None), 1))).label("voucher_auth"),
        ).where(Session.connected_at >= since)
    )
    row = auth_result.one()
    auth_breakdown = {"room_auth": row.room_auth or 0, "voucher_auth": row.voucher_auth or 0}
    analytics_data_val = {
        "range": range_param, "sessions_over_time": sessions_over_time,
        "bandwidth_per_hour": bandwidth_per_hour, "auth_breakdown": auth_breakdown,
    }
    flash = request.session.pop("flash", None)
    return _templates.TemplateResponse("analytics.html", {
        "request": request, "current_user": payload,
        "analytics_data": analytics_data_val, "range": range_param, "flash": flash,
    })


# ── Admin Users ───────────────────────────────────────────────────────────────

class AdminUserCreate(BaseModel):
    username: str
    password: str = Field(min_length=8)
    role: str = "staff"  # "staff" | "superadmin"


@router.get("/api/users")
async def list_admin_users(db: AsyncSession = Depends(get_db), _: dict = Depends(require_superadmin)):
    result = await db.execute(select(AdminUser))
    return [{"id": str(u.id), "username": u.username, "role": u.role.value,
             "last_login_at": u.last_login_at.isoformat() if u.last_login_at else None}
            for u in result.scalars().all()]


@router.post("/api/users", status_code=201)
async def create_admin_user(body: AdminUserCreate, db: AsyncSession = Depends(get_db),
                             _: dict = Depends(require_superadmin)):
    from app.core.models import AdminRole
    try:
        role = AdminRole(body.role)
    except ValueError:
        raise HTTPException(422, {"error": "invalid_role", "allowed": ["staff", "superadmin"]})
    pw_hash = _bcrypt.hashpw(body.password.encode(), _bcrypt.gensalt()).decode()
    user = AdminUser(username=body.username, password_hash=pw_hash, role=role)
    db.add(user)
    try:
        await db.commit()
    except Exception as e:
        await db.rollback()
        if "unique" in str(e).lower() or "duplicate" in str(e).lower():
            raise HTTPException(409, {"error": "username_already_exists"})
        raise
    await db.refresh(user)
    return {"id": str(user.id), "username": user.username, "role": user.role.value}


@router.get("/users", response_class=HTMLResponse, include_in_schema=False)
async def users_page(request: Request, payload: dict = Depends(require_superadmin),
                     db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AdminUser))
    users = result.scalars().all()
    flash = request.session.pop("flash", None)
    return _templates.TemplateResponse("users.html", {
        "request": request, "current_user": payload, "users": users, "flash": flash,
    })


# ── Brand & Config ────────────────────────────────────────────────────────────

ALLOWED_LOGO_MIME = {"image/jpeg", "image/png", "image/webp"}
MIME_TO_EXT = {"image/jpeg": "jpg", "image/png": "png", "image/webp": "webp"}
MAX_LOGO_BYTES = 2 * 1024 * 1024  # 2 MB
LOGO_UPLOAD_DIR = "static/uploads/logo"


class BrandUpdate(BaseModel):
    hotel_name: str | None = None
    primary_color: str | None = None
    tc_text_th: str | None = None
    tc_text_en: str | None = None
    language: str | None = None


@router.get("/api/brand")
async def get_brand(db: AsyncSession = Depends(get_db), _: dict = Depends(require_superadmin)):
    result = await db.execute(select(BrandConfig))
    b = result.scalar_one_or_none()
    if not b:
        return {"hotel_name": "Hotel WiFi", "logo_url": None, "primary_color": "#3B82F6",
                "tc_text_th": None, "tc_text_en": None, "language": "th"}
    logo_url = f"/static/{b.logo_path}" if b.logo_path else None
    return {"hotel_name": b.hotel_name, "logo_url": logo_url, "primary_color": b.primary_color,
            "tc_text_th": b.tc_text_th, "tc_text_en": b.tc_text_en, "language": b.language.value}


@router.put("/api/brand")
async def update_brand(body: BrandUpdate, db: AsyncSession = Depends(get_db),
                        _: dict = Depends(require_superadmin)):
    result = await db.execute(select(BrandConfig))
    b = result.scalar_one_or_none()
    if not b:
        raise HTTPException(404, {"error": "brand_config_not_seeded"})
    for field, value in body.dict(exclude_none=True).items():
        if field == "language":
            try:
                value = LanguageType(value)
            except ValueError:
                raise HTTPException(422, {"error": "invalid_language", "allowed": ["th", "en"]})
        setattr(b, field, value)
    b.updated_at = datetime.now(timezone.utc)
    await db.commit()
    return {"hotel_name": b.hotel_name, "primary_color": b.primary_color, "language": b.language.value}


@router.post("/brand/logo")
async def upload_logo(file: UploadFile = File(...), db: AsyncSession = Depends(get_db),
                       _: dict = Depends(require_superadmin)):
    if file.content_type not in ALLOWED_LOGO_MIME:
        raise HTTPException(422, {"error": "invalid_mime_type", "allowed": list(ALLOWED_LOGO_MIME)})
    data = await file.read(MAX_LOGO_BYTES + 1)
    if len(data) > MAX_LOGO_BYTES:
        raise HTTPException(413, {"error": "file_too_large", "max_mb": 2})
    ext = MIME_TO_EXT[file.content_type]
    _os.makedirs(LOGO_UPLOAD_DIR, exist_ok=True)
    for ext_check in ("jpg", "jpeg", "png", "webp"):
        old = f"{LOGO_UPLOAD_DIR}/logo.{ext_check}"
        try:
            _os.remove(old)
        except FileNotFoundError:
            pass
    logo_filename = f"logo.{ext}"
    logo_full_path = f"{LOGO_UPLOAD_DIR}/{logo_filename}"
    with open(logo_full_path, "wb") as fh:
        fh.write(data)
    relative_path = f"uploads/logo/{logo_filename}"
    result = await db.execute(select(BrandConfig))
    b = result.scalar_one_or_none()
    if b:
        b.logo_path = relative_path
        b.updated_at = datetime.now(timezone.utc)
        await db.commit()
    return {"logo_url": f"/static/{relative_path}"}


@router.get("/brand", response_class=HTMLResponse, include_in_schema=False)
async def brand_page(request: Request, payload: dict = Depends(require_superadmin),
                     db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(BrandConfig))
    b = result.scalar_one_or_none()
    brand = None
    if b:
        brand = {"hotel_name": b.hotel_name, "logo_url": f"/static/{b.logo_path}" if b.logo_path else None,
                 "primary_color": b.primary_color, "tc_text_th": b.tc_text_th,
                 "tc_text_en": b.tc_text_en, "language": b.language.value}
    flash = request.session.pop("flash", None)
    return _templates.TemplateResponse("brand.html", {
        "request": request, "current_user": payload, "brand": brand, "flash": flash,
    })


# ── HTML pages ────────────────────────────────────────────────────────────────

@router.get("/policies", response_class=HTMLResponse, include_in_schema=False)
async def policies_page(request: Request, payload: dict = Depends(require_superadmin),
                         db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Policy))
    policies = result.scalars().all()
    flash = request.session.pop("flash", None)
    return _templates.TemplateResponse("policies.html", {
        "request": request, "current_user": payload, "policies": policies, "flash": flash,
    })


@router.get("/rooms", response_class=HTMLResponse, include_in_schema=False)
async def rooms_page(request: Request, payload: dict = Depends(require_superadmin),
                      db: AsyncSession = Depends(get_db)):
    result_rooms = await db.execute(select(Room))
    result_policies = await db.execute(select(Policy))
    rooms = result_rooms.scalars().all()
    policies = result_policies.scalars().all()
    flash = request.session.pop("flash", None)
    return _templates.TemplateResponse("rooms.html", {
        "request": request, "current_user": payload,
        "rooms": rooms, "policies": policies, "flash": flash,
    })
