import subprocess
import logging

logger = logging.getLogger(__name__)

def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=True, capture_output=True)

def add_whitelist(ip: str) -> None:
    try:
        _run(["iptables", "-I", "FORWARD", "-s", ip, "-j", "ACCEPT"])
        logger.info(f"iptables: added {ip} to whitelist")
    except subprocess.CalledProcessError as e:
        logger.error(f"iptables add failed for {ip}: {e.stderr}")
        raise

def remove_whitelist(ip: str) -> None:
    try:
        _run(["iptables", "-D", "FORWARD", "-s", ip, "-j", "ACCEPT"])
        logger.info(f"iptables: removed {ip} from whitelist")
    except subprocess.CalledProcessError as e:
        logger.warning(f"iptables remove failed for {ip} (may not exist): {e.stderr}")

def is_whitelisted(ip: str) -> bool:
    # Calls subprocess.run directly (bypasses _run) because we need check=False
    # to inspect the return code without raising on a non-zero exit.
    result = subprocess.run(
        ["iptables", "-C", "FORWARD", "-s", ip, "-j", "ACCEPT"],
        check=False, capture_output=True
    )
    return result.returncode == 0
