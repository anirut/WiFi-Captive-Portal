import httpx
import logging
from datetime import datetime, timedelta, timezone
from app.pms.base import PMSAdapter, GuestInfo

logger = logging.getLogger(__name__)


class OperaCloudAdapter(PMSAdapter):
    """Oracle OHIP REST adapter. OAuth2 client credentials with in-memory token cache."""

    def __init__(self, config: dict):
        self._config = config
        self._token: str | None = None
        self._token_expires_at: datetime | None = None

    async def _get_token(self) -> str:
        now = datetime.now(timezone.utc)
        if self._token and self._token_expires_at and self._token_expires_at > now + timedelta(seconds=60):
            return self._token
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._config['api_url']}/oauth/token",
                data={
                    "grant_type": "client_credentials",
                    "client_id": self._config["client_id"],
                    "client_secret": self._config["client_secret"],
                },
                timeout=10.0,
            )
            resp.raise_for_status()
        data = resp.json()
        self._token = data["access_token"]
        self._token_expires_at = now + timedelta(seconds=data["expires_in"])
        return self._token

    def _parse_reservation(self, res: dict) -> GuestInfo:
        guest = res.get("guest", {})
        return GuestInfo(
            pms_id=res["reservationId"],
            room_number=res["roomNumber"],
            last_name=guest.get("surname", ""),
            first_name=guest.get("givenName"),
            check_in=datetime.fromisoformat(res["arrivalDate"].replace("Z", "+00:00")),
            check_out=datetime.fromisoformat(res["departureDate"].replace("Z", "+00:00")),
        )

    async def verify_guest(self, room: str, last_name: str, **kwargs) -> GuestInfo | None:
        token = await self._get_token()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._config['api_url']}/fof/v1/reservations",
                headers={
                    "Authorization": f"Bearer {token}",
                    "x-hotel-id": self._config["hotel_id"],
                },
                params={"roomNumber": room, "familyName": last_name, "reservationStatus": "DUE_IN|IN_HOUSE"},
                timeout=10.0,
            )
            resp.raise_for_status()
        reservations = resp.json().get("reservations", [])
        if not reservations:
            return None
        return self._parse_reservation(reservations[0])

    async def get_guest_by_room(self, room: str, **kwargs) -> GuestInfo | None:
        token = await self._get_token()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._config['api_url']}/fof/v1/reservations",
                headers={
                    "Authorization": f"Bearer {token}",
                    "x-hotel-id": self._config["hotel_id"],
                },
                params={"roomNumber": room, "reservationStatus": "IN_HOUSE"},
                timeout=10.0,
            )
            resp.raise_for_status()
        reservations = resp.json().get("reservations", [])
        if not reservations:
            return None
        return self._parse_reservation(reservations[0])

    async def get_checkouts_since(self, since: datetime, **kwargs) -> list[str]:
        token = await self._get_token()
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._config['api_url']}/fof/v1/reservations",
                headers={
                    "Authorization": f"Bearer {token}",
                    "x-hotel-id": self._config["hotel_id"],
                },
                params={
                    "departureDate": since.strftime("%Y-%m-%d"),
                    "reservationStatus": "CHECKED_OUT",
                },
                timeout=10.0,
            )
            resp.raise_for_status()
        return [r["roomNumber"] for r in resp.json().get("reservations", [])]

    async def health_check(self) -> bool:
        try:
            token = await self._get_token()
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self._config['api_url']}/fof/v1/reservations",
                    headers={
                        "Authorization": f"Bearer {token}",
                        "x-hotel-id": self._config["hotel_id"],
                    },
                    params={"limit": "1"},
                    timeout=5.0,
                )
                resp.raise_for_status()
            return True
        except Exception as e:
            logger.warning(f"OperaCloud health check failed: {e}")
            return False
