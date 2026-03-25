"""
nftables.py - nftables set operations for captive portal.

Replaces iptables.py with set-based O(1) lookups.
"""

import ipaddress
import subprocess
import logging
from typing import Optional

logger = logging.getLogger(__name__)

PRIVATE_NETWORKS = [
    ipaddress.ip_network("10.0.0.0/8"),
    ipaddress.ip_network("172.16.0.0/12"),
    ipaddress.ip_network("192.168.0.0/16"),
    ipaddress.ip_network("127.0.0.0/8"),
    ipaddress.ip_network("169.254.0.0/16"),
    ipaddress.ip_network("0.0.0.0/8"),
]


def _validate_ip(ip: str) -> str:
    try:
        ipaddress.ip_address(ip)
        return ip
    except ValueError:
        raise ValueError(f"Invalid IP address: {ip}")


class NftablesManager:
    """Manage nftables sets and rules for captive portal."""

    TABLE = "inet captive_portal"

    @staticmethod
    def _run(args: list[str], check: bool = True) -> Optional[str]:
        """Execute nft command."""
        cmd = ["nft"] + args
        logger.debug(f"nftables: executing: {' '.join(cmd)}")
        result = subprocess.run(cmd, check=check, capture_output=True, text=True)
        if result.returncode != 0:
            logger.warning(
                f"nftables command returned {result.returncode}: {result.stderr}"
            )
        return result.stdout if result.returncode == 0 else None

    # ── Whitelist Operations ─────────────────────────────────────────

    @classmethod
    def add_to_whitelist(cls, ip: str) -> None:
        """Add IP to whitelist set."""
        try:
            ip = _validate_ip(ip)
            logger.debug(f"nftables: attempting to add {ip} to whitelist")
            cls._run(["add", "element", cls.TABLE, "whitelist", f"{{ {ip} }}"])
            logger.info(f"nftables: added {ip} to whitelist")
        except subprocess.CalledProcessError as e:
            logger.error(f"nftables add failed for {ip}: {e.stderr}")
            raise
        except Exception as e:
            logger.error(
                f"nftables add failed with unexpected error for {ip}: {type(e).__name__}: {e}"
            )
            raise

    @classmethod
    def remove_from_whitelist(cls, ip: str) -> None:
        """Remove IP from whitelist set (ignores errors if not present)."""
        ip = _validate_ip(ip)
        result = subprocess.run(
            ["nft", "delete", "element", cls.TABLE, "whitelist", f"{{ {ip} }}"],
            check=False,
            capture_output=True,
        )
        if result.returncode == 0:
            logger.info(f"nftables: removed {ip} from whitelist")
        else:
            logger.warning(f"nftables remove failed for {ip} (may not exist)")

    @classmethod
    def is_whitelisted(cls, ip: str) -> bool:
        """Check if IP is in whitelist set."""
        ip = _validate_ip(ip)
        result = subprocess.run(
            ["nft", "get", "element", cls.TABLE, "whitelist", f"{{ {ip} }}"],
            check=False,
            capture_output=True,
        )
        return result.returncode == 0

    # ── DNS Bypass Operations ──────────────────────────────────────

    @classmethod
    def add_dns_bypass(cls, ip: str) -> None:
        """Add IP to dns_bypass set."""
        try:
            ip = _validate_ip(ip)
            cls._run(["add", "element", cls.TABLE, "dns_bypass", f"{{ {ip} }}"])
            logger.info(f"nftables: added {ip} to DNS bypass")
        except subprocess.CalledProcessError as e:
            logger.error(f"nftables dns_bypass add failed for {ip}: {e.stderr}")
            raise

    @classmethod
    def remove_dns_bypass(cls, ip: str) -> None:
        """Remove IP from dns_bypass set (ignores errors if not present)."""
        ip = _validate_ip(ip)
        result = subprocess.run(
            ["nft", "delete", "element", cls.TABLE, "dns_bypass", f"{{ {ip} }}"],
            check=False,
            capture_output=True,
        )
        if result.returncode == 0:
            logger.info(f"nftables: removed {ip} from DNS bypass")
        else:
            logger.warning(
                f"nftables dns_bypass remove failed for {ip} (may not exist)"
            )

    # ── Session Helpers (Combined) ─────────────────────────────────

    @classmethod
    def create_session_rules(cls, ip: str) -> None:
        """Add to both whitelist + dns_bypass sets."""
        logger.info(f"nftables: creating session rules for {ip}")
        cls.add_to_whitelist(ip)
        cls.add_dns_bypass(ip)
        logger.info(f"nftables: created session rules for {ip}")

    @classmethod
    def remove_session_rules(cls, ip: str) -> None:
        """Remove from both sets (ignores errors if not present)."""
        cls.remove_from_whitelist(ip)
        cls.remove_dns_bypass(ip)
        logger.info(f"nftables: removed session rules for {ip}")

    # ── MAC Bypass Operations ───────────────────────────────────────

    @classmethod
    def add_mac_bypass(cls, mac: str) -> None:
        """Add MAC to mac_bypass set (format: xx:xx:xx:xx:xx:xx)."""
        try:
            cls._run(["add", "element", cls.TABLE, "mac_bypass", f"{{ {mac} }}"])
            logger.info(f"nftables: added {mac} to mac_bypass")
        except subprocess.CalledProcessError as e:
            logger.error(f"nftables mac_bypass add failed for {mac}: {e.stderr}")
            raise

    @classmethod
    def remove_mac_bypass(cls, mac: str) -> None:
        """Remove MAC from mac_bypass set."""
        result = subprocess.run(
            ["nft", "delete", "element", cls.TABLE, "mac_bypass", f"{{ {mac} }}"],
            check=False,
            capture_output=True,
        )
        if result.returncode == 0:
            logger.info(f"nftables: removed {mac} from mac_bypass")

    # ── Walled Garden Operations ────────────────────────────────────

    @classmethod
    def add_walled_garden(cls, ip: str) -> None:
        """Add IP to walled_garden set (pre-auth access)."""
        try:
            ip = _validate_ip(ip)
            cls._run(["add", "element", cls.TABLE, "walled_garden", f"{{ {ip} }}"])
            logger.info(f"nftables: added {ip} to walled_garden")
        except subprocess.CalledProcessError as e:
            logger.error(f"nftables walled_garden add failed for {ip}: {e.stderr}")
            raise

    @classmethod
    def remove_walled_garden(cls, ip: str) -> None:
        """Remove IP from walled_garden set."""
        ip = _validate_ip(ip)
        result = subprocess.run(
            ["nft", "delete", "element", cls.TABLE, "walled_garden", f"{{ {ip} }}"],
            check=False,
            capture_output=True,
        )
        if result.returncode == 0:
            logger.info(f"nftables: removed {ip} from walled_garden")

    @classmethod
    def sync_walled_garden(cls, domains: list[str]) -> None:
        """Sync walled garden: resolve domains to IPs and add to set."""
        import socket

        for domain in domains:
            try:
                ips = socket.getaddrinfo(domain, 80, socket.AF_INET)
                for ip_info in ips:
                    ip_address = str(ip_info[4][0])
                    try:
                        addr = ipaddress.ip_address(ip_address)
                        is_private = any(addr in net for net in PRIVATE_NETWORKS)
                        if is_private:
                            logger.warning(
                                f"nftables: rejecting private IP {ip_address} from domain {domain}"
                            )
                            continue
                    except ValueError:
                        logger.warning(
                            f"nftables: invalid IP {ip_address} from domain {domain}"
                        )
                        continue
                    cls.add_walled_garden(ip_address)
                    logger.debug(f"nftables: resolved {domain} to {ip_address}")
            except socket.gaierror:
                logger.warning(f"Could not resolve domain: {domain}")
