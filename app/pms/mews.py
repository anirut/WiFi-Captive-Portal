import httpx
import logging
from datetime import datetime, timezone
from app.pms.base import PMSAdapter, GuestInfo

logger = logging.getLogger(__name__)


class MewsAdapter(PMSAdapter):
    """Mews Connector REST adapter. ClientToken + AccessToken embedded in every request body."""

    def __init__(self, config: dict):
        self._config = config

    def _base_url(self) -> str:
        return self._config.get("api_url", "https://www.mews.li")

    def _auth(self) -> dict:
        return {
            "ClientToken": self._config["client_token"],
            "AccessToken": self._config["access_token"],
        }

    def _parse(self, res: dict, spaces: list[dict]) -> GuestInfo:
        space_map = {s["Id"]: s["Number"] for s in spaces}
        return GuestInfo(
            pms_id=res["Id"],
            room_number=space_map.get(res.get("AssignedSpaceId", ""), ""),
            last_name=res.get("LastName", ""),
            first_name=res.get("FirstName"),
            check_in=datetime.fromisoformat(res["StartUtc"].replace("Z", "+00:00")),
            check_out=datetime.fromisoformat(res["EndUtc"].replace("Z", "+00:00")),
        )

    async def verify_guest(self, room: str, last_name: str, **kwargs) -> GuestInfo | None:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base_url()}/api/connector/v1/reservations/getAll",
                json={**self._auth(), "States": ["Started"], "Extent": {"Reservations": True, "Spaces": True}},
                timeout=10.0,
            )
            resp.raise_for_status()
        data = resp.json()
        spaces = data.get("Spaces", [])
        space_map = {s["Number"]: s["Id"] for s in spaces}
        room_id = space_map.get(room)
        reservations = [
            r for r in data.get("Reservations", [])
            if r.get("AssignedSpaceId") == room_id
            and r.get("LastName", "").lower() == last_name.lower()
        ]
        if not reservations:
            return None
        return self._parse(reservations[0], spaces)

    async def get_guest_by_room(self, room: str, **kwargs) -> GuestInfo | None:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base_url()}/api/connector/v1/reservations/getAll",
                json={**self._auth(), "States": ["Started"], "Extent": {"Reservations": True, "Spaces": True}},
                timeout=10.0,
            )
            resp.raise_for_status()
        data = resp.json()
        spaces = data.get("Spaces", [])
        space_map = {s["Number"]: s["Id"] for s in spaces}
        room_id = space_map.get(room)
        reservations = [r for r in data.get("Reservations", []) if r.get("AssignedSpaceId") == room_id]
        if not reservations:
            return None
        return self._parse(reservations[0], spaces)

    async def get_checkouts_since(self, since: datetime, **kwargs) -> list[str]:
        async with httpx.AsyncClient() as client:
            resp = await client.post(
                f"{self._base_url()}/api/connector/v1/reservations/getAll",
                json={
                    **self._auth(),
                    "States": ["Processed"],
                    "EndUtc": {"StartUtc": since.isoformat()},
                    "Extent": {"Reservations": True, "Spaces": True},
                },
                timeout=10.0,
            )
            resp.raise_for_status()
        data = resp.json()
        spaces = {s["Id"]: s["Number"] for s in data.get("Spaces", [])}
        return [spaces.get(r.get("AssignedSpaceId", ""), "") for r in data.get("Reservations", [])]

    async def health_check(self) -> bool:
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.post(
                    f"{self._base_url()}/api/connector/v1/configuration/get",
                    json=self._auth(),
                    timeout=5.0,
                )
                resp.raise_for_status()
            return True
        except Exception as e:
            logger.warning(f"Mews health check failed: {e}")
            return False
