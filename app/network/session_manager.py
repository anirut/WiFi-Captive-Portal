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
        logger.info(f"create_session: starting for IP {ip}")
        mac = get_mac_for_ip(ip)

        # Check if this MAC address already has an active session
        if mac:
            result = await db.execute(
                select(Session).where(
                    Session.mac_address == mac,
                    Session.status == SessionStatus.active,
                    Session.expires_at > datetime.now(timezone.utc),
                )
            )
            existing_session = result.scalar_one_or_none()

            if existing_session:
                old_ip = str(existing_session.ip_address)
                # MAC reconnected with a different IP - update the session
                if old_ip != ip:
                    logger.info(f"MAC {mac} reconnected with new IP: {old_ip} → {ip}")
                    # Remove old nftables rules and apply new ones
                    nft.remove_session_rules(old_ip)
                    remove_bandwidth_limit(old_ip, existing_session.bandwidth_up_kbps, self.wan_if)
                    # Apply new IP rules
                    existing_session.ip_address = ip
                    await db.commit()
                    nft.create_session_rules(ip)
                    apply_bandwidth_limit(ip, existing_session.bandwidth_up_kbps, existing_session.bandwidth_down_kbps, self.wan_if)
                    logger.info(f"Session {existing_session.id} updated with new IP {ip}")
                else:
                    logger.info(f"MAC {mac} reconnected with same IP {ip} - reusing session")
                return existing_session

        # No existing session for this MAC - create new session
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
        logger.info(f"create_session: DB record created for {ip}, calling nft.create_session_rules()")
        nft.create_session_rules(ip)
        logger.info(f"create_session: nft rules created, applying bandwidth limits")
        apply_bandwidth_limit(ip, bandwidth_up_kbps, bandwidth_down_kbps, self.wan_if)
        logger.info(f"Session created: {session.id} for {ip}")
        return session

    async def expire_session(self, db: AsyncSession, session: Session, status: SessionStatus = SessionStatus.expired) -> None:
        ip_str = str(session.ip_address)  # INET column returns IPv4Address via asyncpg
        nft.remove_session_rules(ip_str)
        remove_bandwidth_limit(ip_str, session.bandwidth_up_kbps, self.wan_if)
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
