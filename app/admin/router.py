import time
import uuid
import bcrypt as _bcrypt
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import JSONResponse, HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.models import Session, SessionStatus, PMSAdapter as PMSAdapterModel, PMSAdapterType, AdminUser, Voucher, VoucherType
from app.core.encryption import encrypt_config, decrypt_config
from app.core.auth import get_current_user, get_current_admin, create_access_token, decode_access_token
from app.network.session_manager import SessionManager
from app.pms.factory import load_adapter, ADAPTER_MAP
from app.admin.schemas import PMSConfigResponse, PMSConfigUpdate, PMSTestResult, VoucherCreate, VoucherResponse
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
    resp = RedirectResponse(url=next_url, status_code=302)
    resp.set_cookie("admin_token", token, httponly=True, samesite="lax")
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


@router.get("/sessions")
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


@router.get("/vouchers", response_model=list[VoucherResponse])
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
