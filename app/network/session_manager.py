import uuid
import logging
from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.models import Session, SessionStatus, Guest
from app.network.nftables import NftablesManager as nft
from app.network.tc import apply_bandwidth_limit, remove_bandwidth_limit
from app.network.arp import get_mac_for_ip
from app.core.config import settings

logger = logging.getLogger(__name__)

class SessionManager:
    def __init__(self, wifi_if: str = None, wan_if: str = None):
        self.wifi_if = wifi_if or settings.WIFI_INTERFACE
        self.wan_if = wan_if or settings.WAN_INTERFACE

    async def create_session(
        self, db: AsyncSession, ip: str,
        expires_at: datetime,
        bandwidth_up_kbps: int = 0,
        bandwidth_down_kbps: int = 0,
        guest_id: uuid.UUID | None = None,
        voucher_id: uuid.UUID | None = None,
    ) -> Session:
        mac = get_mac_for_ip(ip)
        session = Session(
            ip_address=ip,
            mac_address=mac,
            guest_id=guest_id,
            voucher_id=voucher_id,
            expires_at=expires_at,
            bandwidth_up_kbps=bandwidth_up_kbps,
            status=SessionStatus.active,
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        nft.create_session_rules(ip)
        apply_bandwidth_limit(ip, bandwidth_up_kbps, bandwidth_down_kbps, self.wan_if)
        logger.info(f"Session created: {session.id} for {ip}")
        return session

    async def expire_session(self, db: AsyncSession, session: Session, status: SessionStatus = SessionStatus.expired) -> None:
        nft.remove_session_rules(session.ip_address)
        remove_bandwidth_limit(session.ip_address, session.bandwidth_up_kbps, self.wan_if)
        session.status = status
        await db.commit()
        logger.info(f"Session {session.id} expired ({status.value})")

    async def expire_sessions_for_room(self, db: AsyncSession, room_number: str) -> int:
        """Expire all active sessions for guests in the given room number."""
        result = await db.execute(
            select(Session)
            .join(Guest, Session.guest_id == Guest.id)
            .where(
                Guest.room_number == room_number,
                Session.status == SessionStatus.active,
            )
        )
        sessions = result.scalars().all()
        for s in sessions:
            await self.expire_session(db, s)
        return len(sessions)

    async def expire_overdue_sessions(self, db: AsyncSession) -> int:
        result = await db.execute(
            select(Session).where(
                Session.status == SessionStatus.active,
                Session.expires_at <= datetime.now(timezone.utc)
            )
        )
        sessions = result.scalars().all()
        for s in sessions:
            await self.expire_session(db, s)
        return len(sessions)
