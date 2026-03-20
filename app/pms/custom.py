import httpx
import logging
from datetime import datetime, timezone
from app.pms.base import PMSAdapter, GuestInfo

logger = logging.getLogger(__name__)


class CustomAdapter(PMSAdapter):
    """Configurable REST adapter. Supports bearer or basic auth with JSON field mapping."""

    def __init__(self, config: dict):
        self._config = config

    def _auth_kwargs(self) -> dict:
        auth_type = self._config.get("auth_type", "bearer")
        if auth_type == "basic":
            return {"auth": (self._config["username"], self._config["password"])}
        return {"headers": {"Authorization": f"Bearer {self._config['token']}"}}

    def _resolve(self, path: str, data: dict):
        """Resolve dot-notation path in nested dict. E.g. 'data.guest.surname'"""
        parts = path.split(".")
        val = data
        for p in parts:
            if not isinstance(val, dict):
                return None
            val = val.get(p)
        return val

    def _parse(self, data: dict) -> GuestInfo:
        fm = self._config["field_map"]

        def get(key):
            return self._resolve(fm[key], data) if key in fm else None

        check_in_raw = get("check_in")
        check_out_raw = get("check_out")
        return GuestInfo(
            pms_id=str(get("pms_id") or ""),
            room_number=str(get("room_number") or ""),
            last_name=str(get("last_name") or ""),
            first_name=get("first_name"),
            check_in=datetime.fromisoformat(check_in_raw) if check_in_raw else datetime.now(timezone.utc),
            check_out=datetime.fromisoformat(check_out_raw) if check_out_raw else datetime.now(timezone.utc),
        )

    async def verify_guest(self, room: str, last_name: str, **kwargs) -> GuestInfo | None:
        endpoint = self._config["verify_endpoint"]
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._config['api_url']}{endpoint}",
                params={"room": room, "last_name": last_name},
                timeout=10.0,
                **self._auth_kwargs(),
            )
            resp.raise_for_status()
        data = resp.json()
        room_number = self._resolve(self._config["field_map"].get("room_number", ""), data)
        if not room_number:
            return None
        return self._parse(data)

    async def get_guest_by_room(self, room: str, **kwargs) -> GuestInfo | None:
        endpoint = self._config.get("guest_by_room_endpoint", self._config["verify_endpoint"])
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._config['api_url']}{endpoint}",
                params={"room": room},
                timeout=10.0,
                **self._auth_kwargs(),
            )
            resp.raise_for_status()
        data = resp.json()
        room_number = self._resolve(self._config["field_map"].get("room_number", ""), data)
        if not room_number:
            return None
        return self._parse(data)

    async def get_checkouts_since(self, since: datetime, **kwargs) -> list[str]:
        endpoint = self._config.get("checkouts_endpoint")
        if not endpoint:
            return []
        async with httpx.AsyncClient() as client:
            resp = await client.get(
                f"{self._config['api_url']}{endpoint}",
                params={"since": since.isoformat()},
                timeout=10.0,
                **self._auth_kwargs(),
            )
            resp.raise_for_status()
        items = resp.json() if isinstance(resp.json(), list) else resp.json().get("data", [])
        room_key = self._config["field_map"].get("room_number", "room_number")
        return [self._resolve(room_key, item) for item in items if self._resolve(room_key, item)]

    async def health_check(self) -> bool:
        endpoint = self._config.get("health_endpoint", "/")
        try:
            async with httpx.AsyncClient() as client:
                resp = await client.get(
                    f"{self._config['api_url']}{endpoint}",
                    timeout=5.0,
                    **self._auth_kwargs(),
                )
                resp.raise_for_status()
            return True
        except Exception as e:
            logger.warning(f"Custom adapter health check failed: {e}")
            return False
