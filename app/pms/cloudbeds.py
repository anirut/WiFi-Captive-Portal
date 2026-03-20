import httpx
import logging
from datetime import datetime, timezone
from app.pms.base import PMSAdapter, GuestInfo

logger = logging.getLogger(__name__)


class CloudbedsAdapter(PMSAdapter):
    """Cloudbeds v1.1 REST adapter. API key in Authorization header."""

    def __init__(self, config: dict):
        self._config = config
        self._headers = {"Authorization": f"Bearer {config['api_key']}"}

    def _base_url(self) -> str:
        return self._config.get("api_url", "https://api.cloudbeds.com")

    def _parse(self, r: dict) -> GuestInfo:
        return GuestInfo(
            pms_id=r["reservationID"],
            room_number=r["roomID"],
            last_name=r["guestLastName"],
            first_name=r.get("guestFirstName"),
            check_in=datetime.fromisoformat(r["startDate"]).replace(tzinfo=timezone.utc),
            check_out=datetime.fromisoformat(r["endDate"]).replace(tzinfo=timezone.utc),
        )

    async def verify_guest(self, room: str, last_name: str, **kwargs) -> GuestInfo | None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url()}/api/v1.1/getReservations",
                headers=self._headers,
                params={
                    "propertyID": self._config["property_id"],
                    "roomID": room,
                    "guestLastName": last_name,
                    "status": "checked_in",
                },
                timeout=10.0,
            )
            resp.raise_for_status()
        data = resp.json().get("data", [])
        if not data:
            return None
        return self._parse(data[0])

    async def get_guest_by_room(self, room: str, **kwargs) -> GuestInfo | None:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url()}/api/v1.1/getReservations",
                headers=self._headers,
                params={
                    "propertyID": self._config["property_id"],
                    "roomID": room,
                    "status": "checked_in",
                },
                timeout=10.0,
            )
            resp.raise_for_status()
        data = resp.json().get("data", [])
        if not data:
            return None
        return self._parse(data[0])

    async def get_checkouts_since(self, since: datetime, **kwargs) -> list[str]:
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._base_url()}/api/v1.1/getReservations",
                headers=self._headers,
                params={
                    "propertyID": self._config["property_id"],
                    "departureFrom": since.strftime("%m/%d/%Y"),
                    "status": "checked_out",
                },
                timeout=10.0,
            )
            resp.raise_for_status()
        return [r["roomID"] for r in resp.json().get("data", [])]

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self._base_url()}/api/v1.1/getHotels",
                    headers=self._headers,
                    timeout=5.0,
                )
                resp.raise_for_status()
            return True
        except Exception as e:
            logger.warning(f"Cloudbeds health check failed: {e}")
            return False
