import time
import uuid
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.models import Session, SessionStatus, PMSAdapter as PMSAdapterModel, PMSAdapterType
from app.core.encryption import encrypt_config, decrypt_config
from app.network.session_manager import SessionManager
from app.pms.factory import load_adapter, ADAPTER_MAP
from app.admin.schemas import PMSConfigResponse, PMSConfigUpdate, PMSTestResult

router = APIRouter(prefix="/admin")
session_manager = SessionManager()

@router.get("/sessions")
async def list_sessions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Session).where(Session.status == SessionStatus.active)
    )
    sessions = result.scalars().all()
    return [{"id": str(s.id), "ip": s.ip_address, "connected_at": s.connected_at, "expires_at": s.expires_at} for s in sessions]

@router.delete("/sessions/{session_id}")
async def kick_session(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        raise HTTPException(status_code=404, detail="not_found")
    await session_manager.expire_session(db, session, SessionStatus.kicked)
    return {"status": "kicked"}


_CREDENTIAL_KEYS = {"client_secret", "api_key", "token", "password", "access_token",
                    "client_token", "auth_key", "webhook_secret"}


def _mask_config(config: dict) -> dict:
    return {k: "***" if k in _CREDENTIAL_KEYS else v for k, v in config.items()}


@router.get("/pms", response_model=PMSConfigResponse)
async def get_pms_config(db: AsyncSession = Depends(get_db)):
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
async def update_pms_config(body: PMSConfigUpdate, db: AsyncSession = Depends(get_db)):
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
async def test_pms_config(body: PMSConfigUpdate):
    adapter_class = ADAPTER_MAP.get(body.type)
    if not adapter_class or body.type == PMSAdapterType.standalone:
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
