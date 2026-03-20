from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

@dataclass
class GuestInfo:
    pms_id: str
    room_number: str
    last_name: str
    check_in: datetime
    check_out: datetime
    first_name: str | None = None

class PMSAdapter(ABC):
    @abstractmethod
    async def verify_guest(self, room: str, last_name: str, **kwargs) -> GuestInfo | None:
        """Verify guest is currently checked in. Returns GuestInfo or None."""

    @abstractmethod
    async def get_guest_by_room(self, room: str, **kwargs) -> GuestInfo | None:
        """Get current guest in room. Returns GuestInfo or None."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Check connectivity to PMS. Returns True if healthy."""

    async def get_checkouts_since(self, since: datetime, **kwargs) -> list[str]:
        """Return room numbers that checked out since given time. Override for PMS sync."""
        return []
