import re
import subprocess
import logging
from app.core.config import settings

logger = logging.getLogger(__name__)

def _ip_to_class_id(ip: str) -> str:
    parts = ip.split(".")
    numeric = int(parts[2]) * 256 + int(parts[3])
    return f"1:{numeric}"

def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=False, capture_output=True)

# ── IFB setup (call once at startup) ────────────────────────────────────────

def ensure_ifb_ready() -> None:
    """Load ifb module, bring up ifb0, redirect WIFI_INTERFACE ingress."""
    wifi_if = settings.WIFI_INTERFACE
    _run(["modprobe", "ifb"])
    _run(["ip", "link", "add", "ifb0", "type", "ifb"])
    _run(["ip", "link", "set", "ifb0", "up"])
    _run(["tc", "qdisc", "add", "dev", wifi_if, "handle", "ffff:", "ingress"])
    _run(["tc", "filter", "add", "dev", wifi_if, "parent", "ffff:", "protocol",
          "ip", "u32", "match", "u32", "0", "0", "action", "mirred", "egress",
          "redirect", "dev", "ifb0"])
    _run(["tc", "qdisc", "add", "dev", "ifb0", "root", "handle", "1:", "htb", "default", "999"])
    logger.info("tc: IFB ready for upload shaping")

# ── Bandwidth shaping ────────────────────────────────────────────────────────

def apply_bandwidth_limit(ip: str, up_kbps: int, down_kbps: int, wan_if: str) -> None:
    if up_kbps == 0 and down_kbps == 0:
        return
    class_id = _ip_to_class_id(ip)
    if down_kbps > 0:
        _run(["tc", "class", "add", "dev", wan_if, "parent", "1:", "classid",
              class_id, "htb", "rate", f"{down_kbps}kbit", "ceil", f"{down_kbps}kbit"])
        _run(["tc", "filter", "add", "dev", wan_if, "parent", "1:", "protocol",
              "ip", "prio", "1", "u32", "match", "ip", "dst", f"{ip}/32", "flowid", class_id])
    if up_kbps > 0:
        _run(["tc", "class", "add", "dev", "ifb0", "parent", "1:", "classid",
              class_id, "htb", "rate", f"{up_kbps}kbit", "ceil", f"{up_kbps}kbit"])
        _run(["tc", "filter", "add", "dev", "ifb0", "parent", "1:", "protocol",
              "ip", "prio", "1", "u32", "match", "ip", "src", f"{ip}/32", "flowid", class_id])
    logger.info(f"tc: applied {down_kbps}kbps down / {up_kbps}kbps up for {ip}")

def remove_bandwidth_limit(ip: str, up_kbps: int, wan_if: str) -> None:
    class_id = _ip_to_class_id(ip)
    _run(["tc", "filter", "del", "dev", wan_if, "parent", "1:", "protocol",
          "ip", "prio", "1", "u32", "match", "ip", "dst", f"{ip}/32", "flowid", class_id])
    _run(["tc", "class", "del", "dev", wan_if, "parent", "1:", "classid", class_id])
    if up_kbps > 0:
        _run(["tc", "filter", "del", "dev", "ifb0", "parent", "1:", "protocol",
              "ip", "prio", "1", "u32", "match", "ip", "src", f"{ip}/32", "flowid", class_id])
        _run(["tc", "class", "del", "dev", "ifb0", "parent", "1:", "classid", class_id])
    logger.info(f"tc: removed limit for {ip}")

# ── Bytes tracking ───────────────────────────────────────────────────────────

def get_bytes(ip: str) -> tuple[int, int]:
    """Returns (bytes_up, bytes_down) from tc stats. 0 if class not found."""
    class_id = _ip_to_class_id(ip)
    numeric_id = class_id.split(":")[1]

    def _parse(device: str) -> int:
        result = subprocess.run(
            ["tc", "-s", "class", "show", "dev", device],
            check=False, capture_output=True
        )
        text = result.stdout.decode(errors="replace")
        # Find the class block for our ID
        pattern = rf"class htb 1:{numeric_id}\b.*?Sent (\d+) bytes"
        m = re.search(pattern, text, re.DOTALL)
        return int(m.group(1)) if m else 0

    bytes_down = _parse(settings.WAN_INTERFACE)
    bytes_up = _parse("ifb0")
    return bytes_up, bytes_down
