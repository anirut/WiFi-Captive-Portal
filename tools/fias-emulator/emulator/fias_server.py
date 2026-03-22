"""
FIAS TCP Server implementation for the FIAS Emulator.

This module implements the Opera FIAS (Fidelio Interface Application Specification)
TCP protocol for PMS integration testing.
"""

import asyncio
import logging
import random
import re
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from emulator.config import settings
from emulator.database import AsyncSessionFactory
from emulator.models import ActivityLog, Connection, FailureRule, Guest, Scenario

logger = logging.getLogger(__name__)

# FIAS protocol uses CRLF as record terminator
CRLF = b"\r\n"


@dataclass
class FIASContext:
    """Context for a FIAS connection session."""

    connection_id: Optional[int] = None
    client_host: str = ""
    client_port: int = 0
    vendor_id: str = ""
    authenticated: bool = False
    writer: Optional[asyncio.StreamWriter] = None


@dataclass
class FailureActionResult:
    """Result of evaluating failure rules."""

    should_fail: bool = False
    action: str = ""
    delay_seconds: float = 0.0
    malformed_type: Optional[str] = None


class FIASProtocolHandler:
    """
    Handles FIAS protocol for a single TCP connection.

    This class parses incoming FIAS records, processes them according to
    the protocol specification, and generates appropriate responses.
    """

    def __init__(self, db_session: AsyncSession, context: FIASContext):
        self.db = db_session
        self.context = context
        self._running = True

    async def handle_data(self, data: str) -> Optional[str]:
        """
        Parse and handle a FIAS record.

        Args:
            data: Raw FIAS XML record string (without CRLF)

        Returns:
            Response XML string or None if no response should be sent
        """
        # Parse the XML record
        try:
            root = ET.fromstring(data)
        except ET.ParseError as e:
            logger.warning(f"Failed to parse XML: {e}")
            return None

        record_type = root.tag.upper()

        # Log incoming record
        await self._log_activity("in", record_type, data)

        # Handle based on record type
        handler = getattr(self, f"_handle_{record_type.lower()}", None)
        if handler is None:
            logger.warning(f"Unknown record type: {record_type}")
            return None

        response = await handler(root)

        # Log outgoing record if any
        if response:
            await self._log_activity("out", response.split(">")[0].replace("<", "").split()[0], response)

        return response

    async def _handle_lr(self, root: ET.Element) -> str:
        """Handle Login Request."""
        auth_key = root.get("AuthKey", "")
        vendor_id = root.get("VendorID", "")

        # Check for failure injection
        failure = await self._check_failure_rules("on_login")
        if failure.should_fail:
            return await self._apply_failure(failure, self._make_la_denied())

        # Validate auth key if configured
        if settings.auth_key and auth_key != settings.auth_key:
            logger.warning(f"Invalid auth key from {self.context.client_host}")
            return self._make_la_denied()

        # Store vendor ID and mark as authenticated
        self.context.vendor_id = vendor_id
        self.context.authenticated = True

        # Update connection record
        if self.context.connection_id:
            await self._update_connection_vendor(vendor_id)

        return '<LA Result="OK"/>'

    async def _handle_ka(self, root: ET.Element) -> str:
        """Handle Keep-Alive."""
        # Check for failure injection
        failure = await self._check_failure_rules("on_heartbeat")
        if failure.should_fail:
            return await self._apply_failure(failure, "<KR/>")

        return "<KR/>"

    async def _handle_giq(self, root: ET.Element) -> str:
        """Handle Guest Info Query."""
        room_number = root.get("RoomNumber", "")
        last_name = root.get("LastName", "")

        # Check for room-specific failure injection
        failure = await self._check_failure_rules(f"on_room:{room_number}")
        if not failure.should_fail:
            failure = await self._check_failure_rules("on_query")

        if failure.should_fail:
            return await self._apply_failure(failure, self._make_gi_not_found())

        # Query guest from database
        guest = await self._find_guest(room_number, last_name)

        if guest is None:
            return self._make_gi_not_found()

        return self._make_gi_response(guest)

    async def _handle_drq(self, root: ET.Element) -> str:
        """Handle Departure Query."""
        departure_date_str = root.get("DepartureDate", "")

        # Check for failure injection
        failure = await self._check_failure_rules("on_query")
        if failure.should_fail:
            # For DRQ, failure means no response or empty response
            return await self._apply_failure(failure, "")

        # Parse departure date
        try:
            departure_date = datetime.strptime(departure_date_str, "%m-%d-%y").date()
        except ValueError:
            logger.warning(f"Invalid departure date format: {departure_date_str}")
            return ""

        # Find all guests departing on this date
        departing_rooms = await self._find_departing_rooms(departure_date)

        if not departing_rooms:
            return ""

        # Generate DR records for each room
        dr_records = [f'<DR RoomNumber="{room}"/>' for room in departing_rooms]
        return "".join(dr_records)

    async def _handle_ld(self, root: ET.Element) -> str:
        """Handle Logout."""
        self._running = False
        self.context.authenticated = False

        # Mark connection as inactive
        if self.context.connection_id:
            await self._deactivate_connection()

        return ""  # LD has no response

    def _make_la_denied(self) -> str:
        """Create a Login Denied response."""
        return '<LA Result="DENIED"/>'

    def _make_gi_not_found(self) -> str:
        """Create a Guest Not Found response."""
        return '<GI Result="NOT_FOUND"/>'

    def _make_gi_response(self, guest: Guest) -> str:
        """Create a Guest Info response from a Guest model."""
        arrival_str = guest.arrival_date.strftime("%m-%d-%y")
        departure_str = guest.departure_date.strftime("%m-%d-%y")

        attrs = [
            f'ReservationNumber="{guest.reservation_number}"',
            f'RoomNumber="{guest.room_number}"',
            f'LastName="{self._escape_xml(guest.last_name)}"',
        ]

        if guest.first_name:
            attrs.append(f'FirstName="{self._escape_xml(guest.first_name)}"')

        attrs.append(f'ArrivalDate="{arrival_str}"')
        attrs.append(f'DepartureDate="{departure_str}"')

        return f'<GI {" ".join(attrs)}/>'

    def _escape_xml(self, value: str) -> str:
        """Escape special characters for XML attribute values."""
        return (
            value.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )

    async def _find_guest(self, room_number: str, last_name: str) -> Optional[Guest]:
        """Find a guest by room number and last name."""
        stmt = (
            select(Guest)
            .where(
                Guest.room_number == room_number,
                Guest.last_name.ilike(last_name),
                Guest.is_active == True,
            )
            .limit(1)
        )
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def _find_departing_rooms(self, departure_date: date) -> list[str]:
        """Find all room numbers departing on the given date."""
        stmt = (
            select(Guest.room_number)
            .where(
                Guest.departure_date == departure_date,
                Guest.is_active == True,
            )
            .distinct()
        )
        result = await self.db.execute(stmt)
        return [row[0] for row in result.all()]

    async def _check_failure_rules(self, trigger: str) -> FailureActionResult:
        """
        Check if any failure rules should fire for the given trigger.

        Returns FailureActionResult with action details if failure should occur.
        """
        # Get active scenario's failure rules and global rules
        stmt = (
            select(FailureRule)
            .outerjoin(Scenario, FailureRule.scenario_id == Scenario.id)
            .where(
                FailureRule.trigger == trigger,
                (Scenario.is_active == True) | (FailureRule.scenario_id == None),
            )
        )
        result = await self.db.execute(stmt)
        rules = result.scalars().all()

        for rule in rules:
            # Check probability
            if random.random() > rule.probability:
                continue

            # Parse action
            action = rule.action

            if action == "drop_connection":
                return FailureActionResult(should_fail=True, action=action)
            elif action == "login_denied":
                return FailureActionResult(should_fail=True, action=action)
            elif action == "timeout":
                return FailureActionResult(should_fail=True, action=action, delay_seconds=9999)
            elif action.startswith("delay:"):
                match = re.match(r"delay:(\d+(?:\.\d+)?)[sS]?", action)
                if match:
                    delay = float(match.group(1))
                    return FailureActionResult(should_fail=True, action=action, delay_seconds=delay)
            elif action == "malformed_xml":
                return FailureActionResult(
                    should_fail=True,
                    action=action,
                    malformed_type=rule.malformed_type,
                )

        return FailureActionResult()

    async def _apply_failure(self, failure: FailureActionResult, original_response: str) -> str:
        """Apply a failure action and return the appropriate response."""
        if failure.delay_seconds > 0:
            await asyncio.sleep(failure.delay_seconds)

        if failure.action == "drop_connection":
            if self.context.writer:
                self.context.writer.close()
                try:
                    await self.context.writer.wait_closed()
                except Exception:
                    pass
            self._running = False
            return ""

        if failure.action == "malformed_xml":
            return self._generate_malformed_xml(failure.malformed_type, original_response)

        if failure.action == "login_denied":
            return self._make_la_denied()

        if failure.action == "timeout":
            return ""  # Never respond

        return original_response

    def _generate_malformed_xml(self, malformed_type: Optional[str], original: str) -> str:
        """Generate malformed XML based on type."""
        if malformed_type == "missing_field":
            # Remove a random attribute
            return re.sub(r' \w+="[^"]*"', "", original, count=1)
        elif malformed_type == "bad_encoding":
            # Insert invalid bytes
            return original.replace(">", ">\xff\xfe", 1)
        elif malformed_type == "unknown_tag":
            # Change tag name
            return original.replace("<GI ", "<UNKNOWN ").replace("<LA ", "<UNKNOWN ")
        else:
            # Default: truncated XML
            return original[:-5] if len(original) > 5 else original

    async def _log_activity(self, direction: str, record_type: str, raw_content: str) -> None:
        """Log activity to the database."""
        log = ActivityLog(
            connection_id=self.context.connection_id,
            direction=direction,
            record_type=record_type,
            raw_content=raw_content,
        )
        self.db.add(log)
        await self.db.commit()

    async def _update_connection_vendor(self, vendor_id: str) -> None:
        """Update connection record with vendor ID."""
        if not self.context.connection_id:
            return
        stmt = select(Connection).where(Connection.id == self.context.connection_id)
        result = await self.db.execute(stmt)
        conn = result.scalar_one_or_none()
        if conn:
            conn.vendor_id = vendor_id
            await self.db.commit()

    async def _deactivate_connection(self) -> None:
        """Mark connection as inactive."""
        if not self.context.connection_id:
            return
        stmt = select(Connection).where(Connection.id == self.context.connection_id)
        result = await self.db.execute(stmt)
        conn = result.scalar_one_or_none()
        if conn:
            conn.is_active = False
            await self.db.commit()


class FIASServer:
    """
    Async TCP server for FIAS protocol.

    This server listens for incoming connections and spawns handlers
    for each connection.
    """

    def __init__(self, host: str = "0.0.0.0", port: int = 9090):
        self.host = host
        self.port = port
        self._server: Optional[asyncio.Server] = None
        self._running = False

    async def start(self) -> None:
        """Start the TCP server."""
        self._server = await asyncio.start_server(
            self._handle_connection,
            self.host,
            self.port,
        )
        self._running = True

        addr = self._server.sockets[0].getsockname()
        logger.info(f"FIAS TCP server listening on {addr[0]}:{addr[1]}")

        async with self._server:
            await self._server.serve_forever()

    async def stop(self) -> None:
        """Stop the TCP server."""
        self._running = False
        if self._server:
            self._server.close()
            await self._server.wait_closed()
            logger.info("FIAS TCP server stopped")

    async def _handle_connection(
        self, reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        """Handle a single client connection."""
        addr = writer.get_extra_info("peername")
        client_host, client_port = addr if addr else ("unknown", 0)

        logger.info(f"New connection from {client_host}:{client_port}")

        context = FIASContext(
            client_host=client_host,
            client_port=client_port,
            writer=writer,
        )

        # Create database session for this connection
        async with AsyncSessionFactory() as db:
            # Create connection record
            conn = Connection(
                client_host=client_host,
                client_port=client_port,
            )
            db.add(conn)
            await db.commit()
            await db.refresh(conn)
            context.connection_id = conn.id

            handler = FIASProtocolHandler(db, context)

            try:
                await self._handle_connection_loop(reader, writer, handler)
            except asyncio.CancelledError:
                logger.info(f"Connection cancelled: {client_host}:{client_port}")
            except ConnectionResetError:
                logger.info(f"Connection reset: {client_host}:{client_port}")
            except Exception as e:
                logger.error(f"Error handling connection: {e}")
            finally:
                # Mark connection as inactive
                if context.connection_id:
                    try:
                        stmt = select(Connection).where(Connection.id == context.connection_id)
                        result = await db.execute(stmt)
                        conn_record = result.scalar_one_or_none()
                        if conn_record:
                            conn_record.is_active = False
                            await db.commit()
                    except Exception as e:
                        logger.error(f"Error marking connection inactive: {e}")

                writer.close()
                try:
                    await writer.wait_closed()
                except Exception:
                    pass

                logger.info(f"Connection closed: {client_host}:{client_port}")

    async def _handle_connection_loop(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
        handler: FIASProtocolHandler,
    ) -> None:
        """Main loop for handling a connection."""
        buffer = b""

        while handler._running:
            try:
                # Read data with timeout
                data = await asyncio.wait_for(reader.read(4096), timeout=300.0)
            except asyncio.TimeoutError:
                logger.debug("Connection timeout, sending keep-alive check")
                continue

            if not data:
                logger.debug("Client disconnected (empty data)")
                break

            buffer += data

            # Process complete records (terminated by CRLF)
            while CRLF in buffer:
                line, buffer = buffer.split(CRLF, 1)
                if not line:
                    continue

                try:
                    record = line.decode("utf-8")
                    response = await handler.handle_data(record)

                    if response:
                        writer.write(response.encode("utf-8") + CRLF)
                        await writer.drain()

                except UnicodeDecodeError as e:
                    logger.warning(f"Failed to decode data: {e}")
                except Exception as e:
                    logger.error(f"Error processing record: {e}")
                    raise


async def run_server() -> None:
    """Run the FIAS TCP server."""
    server = FIASServer(
        host=settings.fias_tcp_host,
        port=settings.fias_tcp_port,
    )

    try:
        await server.start()
    except asyncio.CancelledError:
        await server.stop()


if __name__ == "__main__":
    asyncio.run(run_server())
