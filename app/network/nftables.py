"""
nftables.py - nftables set operations for captive portal.

Replaces iptables.py with set-based O(1) lookups.
"""
import subprocess
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class NftablesManager:
    """Manage nftables sets and rules for captive portal."""

    TABLE = "inet captive_portal"

    @staticmethod
    def _run(args: list[str], check: bool = True) -> Optional[str]:
        """Execute nft command."""
        result = subprocess.run(
            ["nft"] + args,
            check=check,
            capture_output=True,
            text=True
        )
        return result.stdout if result.returncode == 0 else None

    # ── Whitelist Operations ─────────────────────────────────────────

    @classmethod
    def add_to_whitelist(cls, ip: str) -> None:
        """Add IP to whitelist set."""
        try:
            cls._run(["add", "element", cls.TABLE, "whitelist", f"{{ {ip} }}"])
            logger.info(f"nftables: added {ip} to whitelist")
        except subprocess.CalledProcessError as e:
            logger.error(f"nftables add failed for {ip}: {e.stderr}")
            raise

    @classmethod
    def remove_from_whitelist(cls, ip: str) -> None:
        """Remove IP from whitelist set (ignores errors if not present)."""
        result = subprocess.run(
            ["nft", "delete", "element", cls.TABLE, "whitelist", f"{{ {ip} }}"],
            check=False,
            capture_output=True
        )
        if result.returncode == 0:
            logger.info(f"nftables: removed {ip} from whitelist")
        else:
            logger.warning(f"nftables remove failed for {ip} (may not exist)")

    @classmethod
    def is_whitelisted(cls, ip: str) -> bool:
        """Check if IP is in whitelist set."""
        result = subprocess.run(
            ["nft", "get", "element", cls.TABLE, "whitelist", f"{{ {ip} }}"],
            check=False,
            capture_output=True
        )
        return result.returncode == 0

    # ── DNS Bypass Operations ──────────────────────────────────────

    @classmethod
    def add_dns_bypass(cls, ip: str) -> None:
        """Add IP to dns_bypass set."""
        try:
            cls._run(["add", "element", cls.TABLE, "dns_bypass", f"{{ {ip} }}"])
            logger.info(f"nftables: added {ip} to DNS bypass")
        except subprocess.CalledProcessError as e:
            logger.error(f"nftables dns_bypass add failed for {ip}: {e.stderr}")
            raise

    @classmethod
    def remove_dns_bypass(cls, ip: str) -> None:
        """Remove IP from dns_bypass set (ignores errors if not present)."""
        result = subprocess.run(
            ["nft", "delete", "element", cls.TABLE, "dns_bypass", f"{{ {ip} }}"],
            check=False,
            capture_output=True
        )
        if result.returncode == 0:
            logger.info(f"nftables: removed {ip} from DNS bypass")
        else:
            logger.warning(f"nftables dns_bypass remove failed for {ip} (may not exist)")

    # ── Session Helpers (Combined) ─────────────────────────────────

    @classmethod
    def create_session_rules(cls, ip: str) -> None:
        """Add to both whitelist + dns_bypass sets."""
        cls.add_to_whitelist(ip)
        cls.add_dns_bypass(ip)
        logger.info(f"nftables: created session rules for {ip}")

    @classmethod
    def remove_session_rules(cls, ip: str) -> None:
        """Remove from both sets (ignores errors if not present)."""
        cls.remove_from_whitelist(ip)
        cls.remove_dns_bypass(ip)
        logger.info(f"nftables: removed session rules for {ip}")
