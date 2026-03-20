from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.models import Session, SessionStatus
from app.network.session_manager import SessionManager
import uuid

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
