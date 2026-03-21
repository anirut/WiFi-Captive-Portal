import time
import uuid
import bcrypt as _bcrypt
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.models import Session, SessionStatus, PMSAdapter as PMSAdapterModel, PMSAdapterType, AdminUser
from app.core.encryption import encrypt_config, decrypt_config
from app.core.auth import get_current_user, create_access_token
from app.network.session_manager import SessionManager
from app.pms.factory import load_adapter, ADAPTER_MAP
from app.admin.schemas import PMSConfigResponse, PMSConfigUpdate, PMSTestResult

router = APIRouter(prefix="/admin")
session_manager = SessionManager()

def _verify_password(plain: str, hashed: str) -> bool:
    return _bcrypt.checkpw(plain.encode(), hashed.encode() if isinstance(hashed, str) else hashed)


class AdminLoginRequest(BaseModel):
    username: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


@router.post("/login", response_model=TokenResponse)
async def admin_login(body: AdminLoginRequest, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(AdminUser).where(AdminUser.username == body.username))
    user = result.scalar_one_or_none()
    if not user or not _verify_password(body.password, user.password_hash):
        raise HTTPException(status_code=401, detail={"error": "invalid_credentials"})
    user.last_login_at = datetime.now(timezone.utc)
    await db.commit()
    token = create_access_token({"sub": user.username, "role": user.role.value})
    return TokenResponse(access_token=token)

@router.get("/sessions")
async def list_sessions(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(get_current_user),
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
    _: dict = Depends(get_current_user),
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
    _: dict = Depends(get_current_user),
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
    _: dict = Depends(get_current_user),
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
    await db.commit()
    await load_adapter(db)
    return {"ok": True}


@router.post("/pms/test", response_model=PMSTestResult)
async def test_pms_config(
    body: PMSConfigUpdate,
    _: dict = Depends(get_current_user),
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
