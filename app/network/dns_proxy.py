"""
dns_proxy.py — Minimal async DNS proxy for authenticated (whitelisted) clients.

Listens on portal_ip:5354 (UDP).
- Queries for 'logout' → respond with portal IP (A record)
- All other queries → forwarded to upstream DNS (8.8.8.8)

nftables redirects 'dns_bypass' clients to this port instead of going
directly to the upstream, so they can still resolve the 'logout' shortcut.
"""
import asyncio
import socket
import struct
import logging

logger = logging.getLogger(__name__)

AUTH_DNS_PORT = 5354


def _parse_qname(data: bytes, offset: int) -> tuple[str, int]:
    """Parse DNS label sequence into a dotted hostname string."""
    labels: list[str] = []
    visited = set()
    while True:
        if offset in visited:
            break
        visited.add(offset)
        length = data[offset]
        if length == 0:
            offset += 1
            break
        if length >= 0xC0:  # compression pointer
            ptr = ((length & 0x3F) << 8) | data[offset + 1]
            label, _ = _parse_qname(data, ptr)
            labels.append(label)
            offset += 2
            break
        labels.append(data[offset + 1 : offset + 1 + length].decode("ascii", errors="replace"))
        offset += 1 + length
    return ".".join(labels), offset


def _build_a_response(query: bytes, ip: str) -> bytes:
    """Build a minimal DNS A-record response.

    Extracts only the question section (QNAME+QTYPE+QCLASS) from the query —
    modern resolvers include EDNS OPT records in the additional section which
    must NOT be copied into the response verbatim.
    """
    tid = query[:2]
    flags = b"\x81\x80"       # QR=1 AA=0 TC=0 RD=1 RA=1 RCODE=NOERROR
    qdcount = b"\x00\x01"
    ancount = b"\x00\x01"
    nsarcount = b"\x00\x00\x00\x00"  # NSCOUNT + ARCOUNT (no extras)

    # Extract just the question section (skip EDNS/additional records)
    try:
        _, qoff = _parse_qname(query, 12)
        qoff += 4  # skip QTYPE (2) + QCLASS (2)
        question = query[12:qoff]
    except Exception:
        question = query[12:]  # fallback: copy everything

    answer = (
        b"\xc0\x0c"           # name: pointer to offset 12 (start of question)
        b"\x00\x01"           # TYPE A
        b"\x00\x01"           # CLASS IN
        b"\x00\x00\x00\x3c"  # TTL 60 s
        b"\x00\x04"           # RDLENGTH 4
        + socket.inet_aton(ip)
    )
    return tid + flags + qdcount + ancount + nsarcount + question + answer


# ── Asyncio protocols ──────────────────────────────────────────────────────────

class _ForwardProtocol(asyncio.DatagramProtocol):
    """Forwards a single query to upstream and relays the reply to the client."""

    def __init__(self, query: bytes, client_addr: tuple, client_transport: asyncio.DatagramTransport):
        self.query = query
        self.client_addr = client_addr
        self.client_transport = client_transport
        self._transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:  # type: ignore[override]
        self._transport = transport
        transport.sendto(self.query)

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        try:
            self.client_transport.sendto(data, self.client_addr)
        except Exception:
            pass
        if self._transport:
            self._transport.close()

    def error_received(self, exc: Exception) -> None:
        if self._transport:
            self._transport.close()

    def connection_lost(self, exc: Exception | None) -> None:
        pass


class _ProxyProtocol(asyncio.DatagramProtocol):
    """Main UDP listener: handles 'logout', forwards everything else."""

    def __init__(self, portal_ip: str, upstream_dns: str):
        self.portal_ip = portal_ip
        self.upstream_dns = upstream_dns
        self._transport: asyncio.DatagramTransport | None = None

    def connection_made(self, transport: asyncio.DatagramTransport) -> None:  # type: ignore[override]
        self._transport = transport

    def datagram_received(self, data: bytes, addr: tuple) -> None:
        asyncio.create_task(self._handle(data, addr))

    async def _handle(self, data: bytes, addr: tuple) -> None:
        if len(data) < 12 or self._transport is None:
            return
        try:
            qname, qoff = _parse_qname(data, 12)
            qtype = struct.unpack_from("!H", data, qoff)[0]
        except Exception:
            return

        hostname = qname.rstrip(".").lower()

        if hostname in ("logout", "logout.wifi") and qtype == 1:  # A query
            self._transport.sendto(_build_a_response(data, self.portal_ip), addr)
            return

        # Forward to upstream DNS
        try:
            loop = asyncio.get_running_loop()
            await loop.create_datagram_endpoint(
                lambda: _ForwardProtocol(data, addr, self._transport),  # type: ignore[arg-type]
                remote_addr=(self.upstream_dns, 53),
            )
        except Exception as exc:
            logger.debug("DNS forward failed: %s", exc)

    def error_received(self, exc: Exception) -> None:
        logger.debug("DNS proxy error: %s", exc)

    def connection_lost(self, exc: Exception | None) -> None:
        pass


# ── Public API ────────────────────────────────────────────────────────────────

async def start_auth_dns_proxy(
    portal_ip: str,
    upstream_dns: str = "8.8.8.8",
) -> asyncio.DatagramTransport:
    """Start the auth DNS proxy.  Returns the transport (call .close() to stop)."""
    loop = asyncio.get_running_loop()
    transport, _ = await loop.create_datagram_endpoint(
        lambda: _ProxyProtocol(portal_ip, upstream_dns),
        local_addr=(portal_ip, AUTH_DNS_PORT),
    )
    logger.info("Auth DNS proxy listening on %s:%d → upstream %s", portal_ip, AUTH_DNS_PORT, upstream_dns)
    return transport  # type: ignore[return-value]
