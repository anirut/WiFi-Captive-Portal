from datetime import datetime, timezone
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.pms.base import PMSAdapter, GuestInfo
from app.core.models import Guest
import logging

logger = logging.getLogger(__name__)

class StandaloneAdapter(PMSAdapter):
    """Manages guests entirely in local DB. No external PMS."""

    async def verify_guest(self, room: str, last_name: str, db: AsyncSession = None, **kwargs) -> GuestInfo | None:
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(Guest).where(
                and_(
                    Guest.room_number == room,
                    Guest.last_name.ilike(last_name),
                    Guest.check_in <= now,
                    Guest.check_out >= now,
                )
            )
        )
        guest = result.scalar_one_or_none()
        if not guest:
            return None
        return GuestInfo(
            pms_id=str(guest.id),
            room_number=guest.room_number,
            last_name=guest.last_name,
            first_name=guest.first_name,
            check_in=guest.check_in,
            check_out=guest.check_out,
        )

    async def get_guest_by_room(self, room: str, db: AsyncSession = None, **kwargs) -> GuestInfo | None:
        now = datetime.now(timezone.utc)
        result = await db.execute(
            select(Guest).where(
                and_(Guest.room_number == room, Guest.check_in <= now, Guest.check_out >= now)
            )
        )
        guest = result.scalar_one_or_none()
        if not guest:
            return None
        return GuestInfo(
            pms_id=str(guest.id),
            room_number=guest.room_number,
            last_name=guest.last_name,
            first_name=guest.first_name,
            check_in=guest.check_in,
            check_out=guest.check_out,
        )

    async def health_check(self) -> bool:
        return True
