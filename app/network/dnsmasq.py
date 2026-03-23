import ipaddress
import logging
import os
import subprocess
from datetime import datetime, timezone

logger = logging.getLogger(__name__)

CONF_FILE = "/etc/dnsmasq.d/captive-portal.conf"
LEASES_FILE = "/var/lib/misc/dnsmasq.leases"


def write_config(config) -> None:
    """Write dnsmasq config from a DhcpConfig ORM object. If disabled, stop dnsmasq instead."""
    if not config.enabled:
        subprocess.run(["systemctl", "stop", "dnsmasq"], check=False, capture_output=True)
        logger.info("dnsmasq stopped (enabled=False)")
        return

    netmask = str(ipaddress.IPv4Network(config.subnet, strict=False).netmask)
    dns_mode = config.dns_mode.value if hasattr(config.dns_mode, "value") else config.dns_mode

    lines = [
        "# Managed by WiFi Captive Portal — do not edit manually",
        f"interface={config.interface}",
        "except-interface=lo",
        "bind-interfaces",
        "no-resolv",
        "",
        "# DHCP",
        f"dhcp-range={config.dhcp_range_start},{config.dhcp_range_end},{netmask},{config.lease_time}",
        f"dhcp-option=option:router,{config.gateway_ip}",
        f"dhcp-option=option:dns-server,{config.gateway_ip}",
        "",
        "# DNS upstream",
        f"server={config.dns_upstream_1}",
        f"server={config.dns_upstream_2}",
    ]

    if dns_mode == "redirect":
        lines += [
            "",
            "# DNS mode: redirect (catch-all to portal IP)",
            f"address=/#/{config.gateway_ip}",
        ]

    if config.log_queries:
        lines += [
            "",
            "# Logging",
            "log-dhcp",
            "log-queries",
        ]

    content = "\n".join(lines) + "\n"
    with open(CONF_FILE, "w") as f:
        f.write(content)
    logger.info(f"dnsmasq config written to {CONF_FILE}")


def reload_dnsmasq() -> bool:
    """Restart dnsmasq to apply new config. Returns True on success."""
    try:
        subprocess.run(["systemctl", "restart", "dnsmasq"], check=True, capture_output=True)
        logger.info("dnsmasq restarted")
        return True
    except subprocess.CalledProcessError as e:
        logger.error(f"dnsmasq restart failed: {e.stderr}")
        return False


def get_status() -> dict:
    """Return dnsmasq service status dict."""
    try:
        result = subprocess.run(
            ["systemctl", "is-active", "dnsmasq"],
            check=False, capture_output=True
        )
        running = result.returncode == 0
    except Exception:
        running = False

    lease_count = 0
    try:
        with open(LEASES_FILE) as f:
            lease_count = sum(1 for line in f if line.strip())
    except (FileNotFoundError, OSError):
        pass

    return {
        "running": running,
        "lease_count": lease_count,
        "config_file_exists": os.path.exists(CONF_FILE),
    }


def get_leases() -> list[dict]:
    """Parse /var/lib/misc/dnsmasq.leases and return list of lease dicts."""
    try:
        with open(LEASES_FILE) as f:
            lines = f.readlines()
    except (FileNotFoundError, OSError):
        return []

    leases = []
    for line in lines:
        parts = line.strip().split()
        if len(parts) < 4:
            continue
        epoch, mac, ip, hostname = parts[0], parts[1], parts[2], parts[3]
        try:
            expires_at = datetime.fromtimestamp(int(epoch), tz=timezone.utc).isoformat()
        except (ValueError, OSError):
            expires_at = None
        leases.append({"mac": mac, "ip": ip, "hostname": hostname, "expires_at": expires_at})
    return leases
