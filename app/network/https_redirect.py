"""
https_redirect.py - Mini asyncio HTTPS server for captive portal.

Accepts TLS connections on port 8443, responds with HTTP 302 redirect
to the HTTP portal login page. nftables DNATs port 443 here for
unauthenticated clients so HTTPS browsing triggers the portal.

Uses SNI (Server Name Indication) to generate certificates for the requested
hostname, allowing the browser to accept the certificate and receive the redirect.
"""

import asyncio
import ssl
import logging
from pathlib import Path
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

HTTPS_REDIRECT_PORT = 8443
_CERT_DIR = Path("certs")
_CERT_CACHE = {}  # hostname -> (cert_path, key_path)


def _generate_self_signed_cert_for_hostname(hostname: str) -> tuple[str, str]:
    """Generate a self-signed certificate for a specific hostname on-demand."""
    from cryptography import x509
    from cryptography.x509.oid import NameOID
    from cryptography.hazmat.primitives import hashes, serialization
    from cryptography.hazmat.primitives.asymmetric import rsa

    _CERT_DIR.mkdir(exist_ok=True)

    # Generate RSA key (2048 for speed)
    key = rsa.generate_private_key(public_exponent=65537, key_size=2048)

    # Create certificate with the hostname and wildcard SAN
    san_list = [x509.DNSName(hostname)]

    # Add wildcard SAN for subdomain matching
    if not hostname.startswith("*."):
        san_list.append(x509.DNSName(f"*.{hostname}"))

    name = x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, hostname)])
    cert = (
        x509.CertificateBuilder()
        .subject_name(name)
        .issuer_name(name)
        .public_key(key.public_key())
        .serial_number(x509.random_serial_number())
        .not_valid_before(datetime.now(timezone.utc))
        .not_valid_after(datetime.now(timezone.utc) + timedelta(days=1))
        .add_extension(
            x509.SubjectAlternativeName(san_list),
            critical=False,
        )
        .sign(key, hashes.SHA256())
    )

    # Save cert and key to files
    cert_file = _CERT_DIR / f"{hostname}.crt"
    key_file = _CERT_DIR / f"{hostname}.key"

    key_file.write_bytes(
        key.private_bytes(
            serialization.Encoding.PEM,
            serialization.PrivateFormat.TraditionalOpenSSL,
            serialization.NoEncryption(),
        )
    )
    cert_file.write_bytes(cert.public_bytes(serialization.Encoding.PEM))

    logger.debug(f"Generated cert for {hostname}")
    return str(cert_file), str(key_file)


_CTX_CACHE = {}  # hostname -> ssl.SSLContext


def _get_ssl_context_for_hostname(hostname: str) -> ssl.SSLContext:
    """Get or build an SSLContext with a matching certificate for the hostname."""
    # Normalize: strip www., strip port
    hostname = hostname.lower().split(":")[0]
    if hostname.startswith("www."):
        hostname = hostname[4:]

    if hostname not in _CTX_CACHE:
        cert_file, key_file = _generate_self_signed_cert_for_hostname(hostname)
        ctx = ssl.SSLContext(ssl.PROTOCOL_TLS_SERVER)
        ctx.load_cert_chain(cert_file, key_file)
        _CTX_CACHE[hostname] = ctx

    return _CTX_CACHE[hostname]


async def start_https_redirect_server(
    portal_ip: str, portal_port: int
) -> asyncio.Server:
    """Start SSL server on HTTPS_REDIRECT_PORT that redirects all requests to the portal.

    Uses SNI to dynamically generate certificates for the requested hostname,
    so browsers accept the certificate and receive the HTTP 302 redirect.
    """
    redirect_to = f"http://{portal_ip}:{portal_port}/"

    # Build fallback SSL context (used when client sends no SNI)
    default_ctx = _get_ssl_context_for_hostname("localhost")

    def sni_callback(ssl_obj: ssl.SSLObject, server_name: str | None, _context) -> None:
        """Switch to a hostname-matching SSLContext based on the SNI extension."""
        target = server_name or "localhost"
        try:
            ssl_obj.context = _get_ssl_context_for_hostname(target)
        except Exception as e:
            logger.warning(f"SNI cert switch failed for {target}: {e}")

    default_ctx.sni_callback = sni_callback

    async def _handler(
        reader: asyncio.StreamReader, writer: asyncio.StreamWriter
    ) -> None:
        try:
            # Read the HTTP request line (e.g., "GET / HTTP/1.1\r\n")
            # Use readline with a timeout to wait for the request
            request_line = await asyncio.wait_for(reader.readline(), timeout=5.0)
            if not request_line:
                logger.debug("No HTTP request received")
                writer.close()
                return

            # Read remaining headers until empty line
            while True:
                header = await asyncio.wait_for(reader.readline(), timeout=5.0)
                if header == b"\r\n" or not header:
                    break
        except asyncio.TimeoutError:
            logger.debug("Timeout waiting for HTTP request")
            writer.close()
            return
        except Exception as e:
            logger.debug(f"Error reading request: {e}")
            writer.close()
            return

        try:
            # Send HTTP 302 redirect response
            response = (
                f"HTTP/1.1 302 Found\r\n"
                f"Location: {redirect_to}\r\n"
                f"Content-Length: 0\r\n"
                f"Connection: close\r\n"
                f"\r\n"
            )
            writer.write(response.encode())
            await writer.drain()
            logger.debug(f"Sent 302 redirect to {redirect_to}")
        except Exception as e:
            logger.warning(f"Error sending redirect response: {e}")
        finally:
            writer.close()
            try:
                await writer.wait_closed()
            except Exception:
                pass

    server = await asyncio.start_server(
        _handler, "0.0.0.0", HTTPS_REDIRECT_PORT, ssl=default_ctx
    )
    logger.info(
        f"HTTPS redirect server listening on :{HTTPS_REDIRECT_PORT} → {redirect_to}"
    )
    return server
