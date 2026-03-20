import subprocess
import logging

logger = logging.getLogger(__name__)

def _ip_to_class_id(ip: str) -> str:
    parts = ip.split(".")
    numeric = int(parts[2]) * 256 + int(parts[3])
    return f"1:{numeric}"

def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=False, capture_output=True)

def apply_bandwidth_limit(ip: str, up_kbps: int, down_kbps: int, wan_if: str) -> None:
    if up_kbps == 0 and down_kbps == 0:
        return
    class_id = _ip_to_class_id(ip)
    # Add HTB class for download (traffic going TO guest = outbound on WAN)
    if down_kbps > 0:
        _run(["tc", "class", "add", "dev", wan_if, "parent", "1:", "classid",
              class_id, "htb", "rate", f"{down_kbps}kbit", "ceil", f"{down_kbps}kbit"])
        _run(["tc", "filter", "add", "dev", wan_if, "parent", "1:", "protocol",
              "ip", "prio", "1", "u32", "match", "ip", "dst", f"{ip}/32", "flowid", class_id])
    logger.info(f"tc: applied limit {down_kbps}kbps down for {ip}")

def remove_bandwidth_limit(ip: str, wan_if: str) -> None:
    class_id = _ip_to_class_id(ip)
    _run(["tc", "filter", "del", "dev", wan_if, "parent", "1:", "protocol",
          "ip", "prio", "1", "u32", "match", "ip", "dst", f"{ip}/32", "flowid", class_id])
    _run(["tc", "class", "del", "dev", wan_if, "parent", "1:", "classid", class_id])
    logger.info(f"tc: removed limit for {ip}")
