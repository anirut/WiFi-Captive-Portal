"""
https_redirect.py - Mini asyncio HTTPS server for captive portal.

Accepts TLS connections on port 8443, responds with HTTP 302 redirect
to the HTTP portal login page. nftables DNATs port 443 here for
unauthenticated clients so HTTPS browsing triggers the portal.
"""

import asyncio
import ssl
import logging
from pathlib import Path

logger = logging.getLogger(__name__)

HTTPS_REDIRECT_PORT = 8443
_CERT_DIR = Path("certs")
_CERT_FILE = _CERT_DIR / "portal.crt"
_KEY_FILE = _CERT_DIR / "portal.key"


def _generate_self_signed_cert() -> None:
    """Generate a self-signed certificate using the cryptography library."""
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa
    from datetime import datetime, timezone, timedelta

    logger.info("Generating self-signed certificate for HTTPS redirect...")
    _CERT_DIR.mkdir(exist_ok=True)

    key = rsa.generate_private_key(public_exponent=65537, key_size=4096)

    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "captive.portal")])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=3650))
        .add_extension(
            x509.SubjectAlternativeName([x509.DNSName("captive.portal")]),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    _KEY_FILE.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    _CERT_FILE.write_bytes(cert.public_bytes(serialization.Encoding.PEM))
    logger.info(f"Self-signed certificate written to {_CERT_FILE}")


def _ensure_cert() -> None:
    if not _CERT_FILE.exists() or not _KEY_FILE.exists():
        _generate_self_signed_cert()


async def start_https_redirect_server(
    portal_ip: str, portal_port: int
) -> asyncio.Server:
    """Start SSL server on HTTPS_REDIRECT_PORT that redirects all requests to the portal."""
    _ensure_cert()

    ssl_ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
    ssl_ctx.load_cert_chain(str(_CERT_FILE), str(_KEY_FILE))

    redirect_to = f"http://{portal_ip}:{portal_port}/"

    async def _handler(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            # Consume the request so the browser doesn't get a RST mid-stream
            await asyncio.wait_for(reader.read(4096), timeout=5.0)
        except Exception:
            pass
        try:
            writer.write(
                f"HTTP/1.1 302 Found\r\n"
                f"Location: {redirect_to}\r\n"
                f"Content-Length: 0\r\n"
                f"Connection: close\r\n"
                f"\r\n".encode()
            )
            await writer.drain()
        except Exception:
            pass
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    server = await asyncio.start_server(
        _handler, "0.0.0.0", HTTPS_REDIRECT_PORT, ssl=ssl_ctx
    )
    logger.info(
        f"HTTPS redirect server listening on :{HTTPS_REDIRECT_PORT} → {redirect_to}"
    )
    return server
