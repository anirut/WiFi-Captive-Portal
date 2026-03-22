"""Network configuration for captive portal (nftables, dnsmasq, tc)."""

import subprocess
import logging
from typing import Tuple, Dict, Optional
from pathlib import Path


logger = logging.getLogger(__name__)


class NetworkConfigurator:
    """Handles network configuration for the captive portal."""

    def __init__(
        self,
        wifi_interface: str = "wlan0",
        wan_interface: str = "eth0",
        portal_ip: str = "192.168.4.1",
        portal_port: int = 8080,
        dhcp_start: str = "192.168.4.10",
        dhcp_end: str = "192.168.4.254",
        dhcp_netmask: str = "255.255.255.0",
    ):
        self.wifi_interface = wifi_interface
        self.wan_interface = wan_interface
        self.portal_ip = portal_ip
        self.portal_port = portal_port
        self.dhcp_start = dhcp_start
        self.dhcp_end = dhcp_end
        self.dhcp_netmask = dhcp_netmask

    def enable_ip_forwarding(self) -> Tuple[bool, str]:
        """Enable IP forwarding for NAT."""
        logger.info("Enabling IP forwarding...")
        try:
            # Enable immediately
            with open("/proc/sys/net/ipv4/ip_forward", "w") as f:
                f.write("1")

            # Make persistent in sysctl.conf
            sysctl_conf = Path("/etc/sysctl.conf")
            content = sysctl_conf.read_text() if sysctl_conf.exists() else ""

            if "net.ipv4.ip_forward=1" not in content:
                with open(sysctl_conf, "a") as f:
                    f.write("\n# WiFi Captive Portal\nnet.ipv4.ip_forward=1\n")

            return True, "IP forwarding enabled"
        except PermissionError:
            return False, "Permission denied. Run as root."
        except Exception as e:
            return False, str(e)

    def configure_wifi_interface(self) -> Tuple[bool, str]:
        """Configure WiFi interface with static IP."""
        logger.info(f"Configuring {self.wifi_interface} with IP {self.portal_ip}")
        try:
            # Flush existing IP
            subprocess.run(
                ["ip", "addr", "flush", "dev", self.wifi_interface],
                capture_output=True,
                check=True
            )

            # Add static IP (assume /24)
            subprocess.run(
                ["ip", "addr", "add", f"{self.portal_ip}/24", "dev", self.wifi_interface],
                capture_output=True,
                check=True
            )

            # Bring interface up
            subprocess.run(
                ["ip", "link", "set", self.wifi_interface, "up"],
                capture_output=True,
                check=True
            )

            return True, f"{self.wifi_interface} configured with {self.portal_ip}"
        except subprocess.CalledProcessError as e:
            return False, f"Failed to configure interface: {e.stderr}"

    def configure_nftables(self) -> Tuple[bool, str]:
        """Configure nftables rules for captive portal."""
        logger.info("Configuring nftables rules...")

        nftables_conf = f"""#!/usr/sbin/nft -f

# WiFi Captive Portal nftables configuration
# Flush existing captive_portal table if it exists
table inet captive_portal
delete table inet captive_portal

table inet captive_portal {{
    # NAT chain for masquerading outbound traffic
    chain postrouting {{
        type nat hook postrouting priority srcnat; policy accept;
        ip saddr 192.168.4.0/24 oif "{self.wan_interface}" masquerade
    }}

    # Forward chain for traffic control
    chain forward {{
        type filter hook forward priority filter; policy drop;

        # Allow established/related connections
        ct state established,related accept

        # Allow DNS queries (will be intercepted by dnsmasq)
        udp dport 53 accept
        tcp dport 53 accept

        # Allow DHCP
        udp dport 67 accept
        udp dport 68 accept

        # Redirect HTTP to portal
        tcp dport 80 ip saddr 192.168.4.0/24 jump redirect_to_portal

        # Allow HTTPS passthrough for authenticated clients
        tcp dport 443 accept

        # Whitelist for authenticated clients (managed by app)
        jump whitelist
    }}

    # Redirect chain
    chain redirect_to_portal {{
        tcp dport 80 redirect to :{self.portal_port}
    }}

    # Whitelist chain (IPs added dynamically by the app)
    chain whitelist {{
        # IPs will be added here by the portal app
        # Example: ip saddr 192.168.4.10 accept
    }}

    # Input chain for portal access
    chain input {{
        type filter hook input priority filter; policy accept;

        # Allow portal access
        tcp dport {self.portal_port} accept
    }}
}}
"""

        try:
            conf_path = Path("/etc/nftables.d/captive-portal.conf")
            conf_path.parent.mkdir(parents=True, exist_ok=True)
            conf_path.write_text(nftables_conf)

            # Apply rules
            subprocess.run(
                ["nft", "-f", str(conf_path)],
                capture_output=True,
                text=True,
                check=True
            )

            return True, "nftables rules configured"
        except subprocess.CalledProcessError as e:
            return False, f"Failed to configure nftables: {e.stderr}"
        except Exception as e:
            return False, str(e)

    def configure_dnsmasq(self) -> Tuple[bool, str]:
        """Configure dnsmasq for DHCP and DNS."""
        logger.info("Configuring dnsmasq...")

        dnsmasq_conf = f"""# WiFi Captive Portal dnsmasq configuration
# DHCP Configuration
interface={self.wifi_interface}
bind-interfaces

# DHCP range
dhcp-range={self.dhcp_start},{self.dhcp_end},{self.dhcp_netmask},12h

# Gateway (portal IP)
dhcp-option=3,{self.portal_ip}

# DNS servers (use portal for DNS interception)
dhcp-option=6,{self.portal_ip}

# Captive portal detection
# Apple
address=/captive.apple.com/{self.portal_ip}
# Android
address=/connectivitycheck.gstatic.com/{self.portal_ip}
address=/clients3.google.com/{self.portal_ip}
address=/clients4.google.com/{self.portal_ip}
# Windows
address=/www.msftconnecttest.com/{self.portal_ip}
address=/www.msftncsi.com/{self.portal_ip}
# DNS interception - redirect all DNS to portal
# This forces DNS queries through our dnsmasq
"""

        try:
            conf_path = Path("/etc/dnsmasq.d/captive-portal")
            conf_path.write_text(dnsmasq_conf)

            # Restart dnsmasq
            subprocess.run(
                ["systemctl", "restart", "dnsmasq"],
                capture_output=True,
                text=True,
                check=True
            )

            return True, "dnsmasq configured"
        except subprocess.CalledProcessError as e:
            return False, f"Failed to configure dnsmasq: {e.stderr}"
        except Exception as e:
            return False, str(e)

    def configure_tc(self, default_kbps: int = 1024) -> Tuple[bool, str]:
        """Configure traffic control for bandwidth shaping."""
        logger.info(f"Configuring traffic control (default: {default_kbps} kbps)...")
        try:
            # Clear existing qdisc
            subprocess.run(
                ["tc", "qdisc", "del", "dev", self.wifi_interface, "root"],
                capture_output=True  # Ignore errors if doesn't exist
            )

            # Add HTB root qdisc
            subprocess.run(
                ["tc", "qdisc", "add", "dev", self.wifi_interface, "root", "handle", "1:", "htb", "default", "10"],
                capture_output=True,
                text=True,
                check=True
            )

            # Add root class
            subprocess.run(
                ["tc", "class", "add", "dev", self.wifi_interface", "parent", "1:", "classid", "1:1", "htb", "rate", "1000mbit"],
                capture_output=True,
                text=True,
                check=True
            )

            # Add default class
            subprocess.run(
                ["tc", "class", "add", "dev", self.wifi_interface, "parent", "1:1", "classid", "1:10", "htb", "rate", f"{default_kbps}kbit", "ceil", f"{default_kbps}kbit"],
                capture_output=True,
                text=True,
                check=True
            )

            return True, "Traffic control configured"
        except subprocess.CalledProcessError as e:
            return False, f"Failed to configure tc: {e.stderr}"

    def verify_configuration(self) -> Tuple[bool, Dict[str, str]]:
        """Verify all network configurations are in place."""
        results = {}

        # Check IP forwarding
        try:
            with open("/proc/sys/net/ipv4/ip_forward", "r") as f:
                results["ip_forward"] = f.read().strip() == "1"
        except Exception:
            results["ip_forward"] = False

        # Check nftables
        try:
            result = subprocess.run(
                ["nft", "list", "table", "inet", "captive_portal"],
                capture_output=True,
                text=True
            )
            results["nftables"] = result.returncode == 0
        except Exception:
            results["nftables"] = False

        # Check dnsmasq
        try:
            result = subprocess.run(
                ["systemctl", "is-active", "dnsmasq"],
                capture_output=True,
                text=True
            )
            results["dnsmasq"] = result.returncode == 0
        except Exception:
            results["dnsmasq"] = False

        # Check WiFi interface
        try:
            result = subprocess.run(
                ["ip", "addr", "show", self.wifi_interface],
                capture_output=True,
                text=True
            )
            results["wifi_interface"] = self.portal_ip in result.stdout
        except Exception:
            results["wifi_interface"] = False

        all_ok = all(results.values())
        return all_ok, results

    def rollback(self) -> Tuple[bool, str]:
        """Remove all network configurations."""
        logger.info("Rolling back network configuration...")
        results = []

        # Flush nftables
        try:
            subprocess.run(
                ["nft", "flush", "table", "inet", "captive_portal"],
                capture_output=True
            )
            subprocess.run(
                ["nft", "delete", "table", "inet", "captive_portal"],
                capture_output=True
            )
            results.append("nftables rules removed")
        except Exception:
            pass

        # Remove dnsmasq config
        try:
            conf_path = Path("/etc/dnsmasq.d/captive-portal")
            if conf_path.exists():
                conf_path.unlink()
            subprocess.run(["systemctl", "restart", "dnsmasq"], capture_output=True)
            results.append("dnsmasq config removed")
        except Exception:
            pass

        # Remove tc rules
        try:
            subprocess.run(
                ["tc", "qdisc", "del", "dev", self.wifi_interface, "root"],
                capture_output=True
            )
            results.append("tc rules removed")
        except Exception:
            pass

        return True, "\n".join(results)

    def setup_complete(self) -> Tuple[bool, str]:
        """Complete network setup: IP forwarding, interface, nftables, dnsmasq, tc."""
        results = []

        # Enable IP forwarding
        ok, msg = self.enable_ip_forwarding()
        if not ok:
            return False, msg
        results.append(msg)

        # Configure WiFi interface
        ok, msg = self.configure_wifi_interface()
        if not ok:
            return False, msg
        results.append(msg)

        # Configure nftables
        ok, msg = self.configure_nftables()
        if not ok:
            return False, msg
        results.append(msg)

        # Configure dnsmasq
        ok, msg = self.configure_dnsmasq()
        if not ok:
            return False, msg
        results.append(msg)

        # Configure tc
        ok, msg = self.configure_tc()
        if not ok:
            # TC is optional, don't fail
            results.append(f"Warning: {msg}")
        else:
            results.append(msg)

        # Verify
        ok, verify_results = self.verify_configuration()
        if not ok:
            return False, f"Verification failed: {verify_results}"

        return True, "\n".join(results)
