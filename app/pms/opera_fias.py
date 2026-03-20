import asyncio
import logging
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from app.pms.base import PMSAdapter, GuestInfo

logger = logging.getLogger(__name__)

# FIAS XML record terminator
_CRLF = b"\r\n"


class OperaFIASAdapter(PMSAdapter):
    """
    OPERA 5 / Suite8 FIAS TCP socket adapter.

    FIAS (Fidelio Interface Application Specification) uses a persistent TCP
    connection with XML record exchange. All requests are serialized via asyncio.Lock
    since the socket is shared. Heartbeat (KA/KR) sent every 30 seconds.

    Reference: Oracle Hospitality FIAS Specification v2.25
    """

    def __init__(self, config: dict):
        self._config = config
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._lock = asyncio.Lock()

    async def connect(self) -> None:
        """Open TCP connection and perform FIAS login handshake. Call after __init__."""
        self._reader, self._writer = await asyncio.open_connection(
            self._config["host"], int(self._config["port"])
        )
        # Send LR (Login Record)
        lr = f'<LR AuthKey="{self._config["auth_key"]}" VendorID="{self._config["vendor_id"]}"/>'
        self._writer.write(lr.encode() + _CRLF)
        await self._writer.drain()
        # Wait for LA (Login Acknowledge)
        await self._reader.read(256)
        asyncio.create_task(self._heartbeat_loop())
        logger.info(f"FIAS connected to {self._config['host']}:{self._config['port']}")

    async def _heartbeat_loop(self) -> None:
        while self._writer and not self._writer.is_closing():
            await asyncio.sleep(30)
            try:
                async with self._lock:
                    self._writer.write(b"<KA/>" + _CRLF)
                    await self._writer.drain()
                    await self._reader.read(64)
            except Exception as e:
                logger.warning(f"FIAS heartbeat failed: {e}")
                break

    async def _send_recv(self, xml: str) -> str:
        """Send XML record and return response string (thread-safe)."""
        async with self._lock:
            self._writer.write(xml.encode() + _CRLF)
            await self._writer.drain()
            data = await self._reader.read(4096)
        return data.decode(errors="replace").strip()

    def _parse_gi(self, xml_str: str) -> GuestInfo | None:
        """Parse GI (Guest Information) response record."""
        try:
            root = ET.fromstring(xml_str)
            if root.tag != "GI":
                return None
            return GuestInfo(
                pms_id=root.attrib.get("ReservationNumber", ""),
                room_number=root.attrib.get("RoomNumber", ""),
                last_name=root.attrib.get("LastName", ""),
                first_name=root.attrib.get("FirstName"),
                check_in=datetime.strptime(root.attrib["ArrivalDate"], "%m-%d-%y").replace(tzinfo=timezone.utc),
                check_out=datetime.strptime(root.attrib["DepartureDate"], "%m-%d-%y").replace(tzinfo=timezone.utc),
            )
        except Exception as e:
            logger.warning(f"FIAS GI parse error: {e} — raw: {xml_str!r}")
            return None

    async def verify_guest(self, room: str, last_name: str, **kwargs) -> GuestInfo | None:
        xml = f'<GIQ RoomNumber="{room}" LastName="{last_name}"/>'
        response = await self._send_recv(xml)
        return self._parse_gi(response)

    async def get_guest_by_room(self, room: str, **kwargs) -> GuestInfo | None:
        xml = f'<GIQ RoomNumber="{room}"/>'
        response = await self._send_recv(xml)
        return self._parse_gi(response)

    async def get_checkouts_since(self, since: datetime, **kwargs) -> list[str]:
        date_str = since.strftime("%m-%d-%y")
        xml = f'<DRQ DepartureDate="{date_str}"/>'
        response = await self._send_recv(xml)
        rooms = []
        # DR responses may return multiple records delimited by CRLF
        for line in response.splitlines():
            try:
                root = ET.fromstring(line.strip())
                if root.tag == "DR":
                    room_num = root.attrib.get("RoomNumber", "")
                    if room_num:
                        rooms.append(room_num)
            except ET.ParseError:
                continue
        return rooms

    async def health_check(self) -> bool:
        return self._writer is not None and not self._writer.is_closing()

    async def disconnect(self) -> None:
        if self._writer:
            try:
                self._writer.write(b"<LD/>" + _CRLF)
                await self._writer.drain()
                self._writer.close()
            except Exception:
                pass
            self._writer = None
            self._reader = None
