"""Input validators for the installer."""

import re
from typing import Tuple


def validate_ip_address(ip: str) -> Tuple[bool, str]:
    """Validate an IPv4 address."""
    pattern = r'^(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})$'
    match = re.match(pattern, ip)
    if not match:
        return False, "Invalid IP address format"

    for octet in match.groups():
        if int(octet) > 255:
            return False, f"Octet {octet} is out of range (0-255)"

    return True, ""


def validate_port(port: int) -> Tuple[bool, str]:
    """Validate a port number."""
    if not isinstance(port, int):
        return False, "Port must be a number"
    if port < 1 or port > 65535:
        return False, "Port must be between 1 and 65535"
    if port < 1024:
        return False, "Port below 1024 requires root privileges"
    return True, ""


def validate_password(password: str) -> Tuple[bool, str]:
    """Validate admin password strength."""
    if len(password) < 8:
        return False, "Password must be at least 8 characters"
    if len(password) > 128:
        return False, "Password must be at most 128 characters"
    return True, ""


def validate_username(username: str) -> Tuple[bool, str]:
    """Validate admin username."""
    if not username:
        return False, "Username cannot be empty"
    if len(username) < 3:
        return False, "Username must be at least 3 characters"
    if len(username) > 32:
        return False, "Username must be at most 32 characters"
    if not re.match(r'^[a-zA-Z0-9_]+$', username):
        return False, "Username can only contain letters, numbers, and underscores"
    return True, ""


def validate_dhcp_range(start_ip: str, end_ip: str, portal_ip: str, subnet: str = "255.255.255.0") -> Tuple[bool, str]:
    """Validate DHCP range is within the same subnet as portal IP."""
    # Simple check: first 3 octets should match for /24 subnet
    portal_prefix = ".".join(portal_ip.split(".")[:3])
    start_prefix = ".".join(start_ip.split(".")[:3])
    end_prefix = ".".join(end_ip.split(".")[:3])

    if portal_prefix != start_prefix or portal_prefix != end_prefix:
        return False, "DHCP range must be in the same subnet as portal IP"

    # Check that range is valid (start < end)
    start_last = int(start_ip.split(".")[3])
    end_last = int(end_ip.split(".")[3])
    portal_last = int(portal_ip.split(".")[3])

    if start_last >= end_last:
        return False, "Start IP must be less than end IP"

    if portal_last >= start_last and portal_last <= end_last:
        return False, "Portal IP should not be within DHCP range"

    return True, ""


def validate_interface_name(name: str) -> Tuple[bool, str]:
    """Validate network interface name."""
    if not name:
        return False, "Interface name cannot be empty"
    if len(name) > 15:
        return False, "Interface name too long (max 15 characters)"
    if not re.match(r'^[a-zA-Z0-9_]+$', name):
        return False, "Invalid interface name"
    return True, ""
