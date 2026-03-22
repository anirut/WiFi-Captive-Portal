"""Network utilities for detecting interfaces and checking connectivity."""

import subprocess
import socket
import shutil
from typing import Dict, List, Optional, Tuple


def get_network_interfaces() -> Dict[str, List[str]]:
    """Detect available network interfaces, categorized by type."""
    result = {"all": [], "physical": [], "wireless": [], "virtual": []}

    try:
        # Get all interfaces
        output = subprocess.run(
            ["ip", "-o", "link", "show"],
            capture_output=True,
            text=True,
            check=True
        ).stdout

        for line in output.strip().split("\n"):
            if not line:
                continue
            # Extract interface name (format: "2: eth0: ...")
            parts = line.split(":")
            if len(parts) >= 2:
                name = parts[1].strip().split("@")[0]  # Handle vlan@interface format
                if name != "lo":  # Skip loopback
                    result["all"].append(name)

                    # Categorize
                    if name.startswith(("eth", "en", "em")):
                        result["physical"].append(name)
                    elif name.startswith(("wlan", "wl", "wlp")):
                        result["wireless"].append(name)
                    elif name.startswith(("docker", "veth", "br", "virbr")):
                        result["virtual"].append(name)
                    else:
                        # Default to physical for unknown types
                        result["physical"].append(name)

    except subprocess.CalledProcessError:
        pass

    return result


def get_interface_ip(interface: str) -> Optional[str]:
    """Get the IP address of a specific interface."""
    try:
        output = subprocess.run(
            ["ip", "-o", "-4", "addr", "show", interface],
            capture_output=True,
            text=True,
            check=True
        ).stdout

        # Parse output: "2: eth0    inet 192.168.1.100/24 brd ..."
        for line in output.strip().split("\n"):
            if "inet " in line:
                ip = line.split("inet ")[1].split("/")[0]
                return ip
    except subprocess.CalledProcessError:
        pass
    return None


def check_internet_connectivity(interface: Optional[str] = None, test_host: str = "8.8.8.8") -> bool:
    """Check if the system has internet connectivity."""
    try:
        # Try to ping Google DNS
        cmd = ["ping", "-c", "1", "-W", "2", test_host]
        if interface:
            cmd.extend(["-I", interface])

        subprocess.run(cmd, capture_output=True, check=True)
        return True
    except subprocess.CalledProcessError:
        return False


def check_dns_resolution(hostname: str = "google.com") -> bool:
    """Check if DNS resolution is working."""
    try:
        socket.gethostbyname(hostname)
        return True
    except socket.gaierror:
        return False


def is_interface_up(interface: str) -> bool:
    """Check if an interface is up."""
    try:
        output = subprocess.run(
            ["ip", "-o", "link", "show", interface],
            capture_output=True,
            text=True,
            check=True
        ).stdout
        return "UP" in output or "UNKNOWN" in output.lower()
    except subprocess.CalledProcessError:
        return False


def get_interface_mac(interface: str) -> Optional[str]:
    """Get the MAC address of an interface."""
    try:
        with open(f"/sys/class/net/{interface}/address", "r") as f:
            return f.read().strip()
    except FileNotFoundError:
        return None


def configure_interface_ip(interface: str, ip: str, netmask: str = "255.255.255.0") -> Tuple[bool, str]:
    """Configure static IP on an interface."""
    try:
        # Calculate CIDR prefix from netmask
        prefix = sum(bin(int(x)).count("1") for x in netmask.split("."))
        cidr = f"{ip}/{prefix}"

        subprocess.run(
            ["ip", "addr", "flush", "dev", interface],
            capture_output=True,
            check=True
        )
        subprocess.run(
            ["ip", "addr", "add", cidr, "dev", interface],
            capture_output=True,
            check=True
        )
        subprocess.run(
            ["ip", "link", "set", interface, "up"],
            capture_output=True,
            check=True
        )
        return True, ""
    except subprocess.CalledProcessError as e:
        return False, str(e)


def enable_ip_forwarding() -> Tuple[bool, str]:
    """Enable IP forwarding for NAT."""
    try:
        # Enable immediately
        with open("/proc/sys/net/ipv4/ip_forward", "w") as f:
            f.write("1")

        # Make persistent
        with open("/etc/sysctl.conf", "r") as f:
            content = f.read()

        if "net.ipv4.ip_forward=1" not in content:
            with open("/etc/sysctl.conf", "a") as f:
                f.write("\n# WiFi Captive Portal\nnet.ipv4.ip_forward=1\n")

        return True, ""
    except PermissionError:
        return False, "Permission denied. Run as root."
    except Exception as e:
        return False, str(e)


def check_required_tools() -> Dict[str, bool]:
    """Check if required network tools are installed."""
    tools = ["ip", "nft", "dnsmasq", "tc"]
    return {tool: shutil.which(tool) is not None for tool in tools}
