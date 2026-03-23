#!/usr/bin/env bash
# =============================================================================
# setup-nftables.sh - Initialize nftables + tc + flowtables for captive portal
# Usage: sudo ./setup-nftables.sh [OPTIONS]
#
# Options:
#   --dns-ip IP      DNS upstream IP (default: 8.8.8.8 or $DNS_UPSTREAM_IP)
#   --portal-ip IP   Captive portal IP (default: $PORTAL_IP)
#   --portal-port N  Captive portal port (default: 8080 or $PORTAL_PORT)
#   --wifi IF        WiFi interface (default: eth0 or $WIFI_INTERFACE)
#   --wan IF         WAN interface (default: eth1 or $WAN_INTERFACE)
# =============================================================================

# Root privilege check
if [[ $EUID -ne 0 ]]; then
    echo "Error: This script must be run as root (use sudo)" >&2
    exit 1
fi

set -e

# Parse arguments
while [[ $# -gt 0 ]]; do
    case $1 in
        --dns-ip) DNS_IP="$2"; shift 2 ;;
        --portal-ip) PORTAL_IP="$2"; shift 2 ;;
        --portal-port) PORTAL_PORT="$2"; shift 2 ;;
        --wifi) WIFI_IF="$2"; shift 2 ;;
        --wan) WAN_IF="$2"; shift 2 ;;
        *) echo "Unknown: $1"; exit 1 ;;
    esac
done

# Defaults from env or hardcoded
DNS_IP="${DNS_IP:-${DNS_UPSTREAM_IP:-8.8.8.8}}"
PORTAL_IP="${PORTAL_IP:-${PORTAL_IP:-192.168.1.1}}"
PORTAL_PORT="${PORTAL_PORT:-${PORTAL_PORT:-8080}}"
WIFI_IF="${WIFI_IF:-${WIFI_INTERFACE:-eth0}}"
WAN_IF="${WAN_IF:-${WAN_INTERFACE:-eth1}}"

# Validate interfaces exist
if [[ ! -d "/sys/class/net/$WIFI_IF" ]]; then
    echo "Error: WiFi interface '$WIFI_IF' not found" >&2
    exit 1
fi
if [[ ! -d "/sys/class/net/$WAN_IF" ]]; then
    echo "Error: WAN interface '$WAN_IF' not found" >&2
    exit 1
fi

echo "Setting up nftables captive portal..."
echo "  DNS upstream: $DNS_IP"
echo "  Portal: $PORTAL_IP:$PORTAL_PORT"
echo "  WiFi interface: $WIFI_IF"
echo "  WAN interface: $WAN_IF"

# Bring WiFi interface up and ensure only portal IP is assigned
ip link set "$WIFI_IF" up 2>/dev/null || true
if ! ip addr show "$WIFI_IF" 2>/dev/null | grep -q "inet ${PORTAL_IP}/"; then
    ip addr add "${PORTAL_IP}/24" dev "$WIFI_IF" 2>/dev/null || true
    echo "  Assigned ${PORTAL_IP}/24 to $WIFI_IF"
fi

# Enable IP forwarding
sysctl -qw net.ipv4.ip_forward=1

# ── 1. Create nftables table ──────────────────────────────────────
echo "[1/3] Creating nftables table..."

# Delete existing table (idempotent)
nft delete table inet captive_portal 2>/dev/null || true

nft -f - <<EOF
table inet captive_portal {
    set whitelist {
        type ipv4_addr
    }

    set dns_bypass {
        type ipv4_addr
    }

    flowtable f {
        hook ingress priority 0
        devices = { $WIFI_IF, $WAN_IF }
    }

    chain prerouting {
        type nat hook prerouting priority dstnat; policy accept;

        # DNS bypass for authenticated users
        ip saddr @dns_bypass udp dport 53 dnat to $DNS_IP:53
        ip saddr @dns_bypass tcp dport 53 dnat to $DNS_IP:53

        # Portal redirect for unauthenticated users (HTTP only)
        ip saddr != @whitelist tcp dport 80 dnat to $PORTAL_IP:$PORTAL_PORT
    }

    chain postrouting {
        type nat hook postrouting priority srcnat; policy accept;
        oifname $WAN_IF ip saddr @whitelist masquerade
    }

    chain input {
        type filter hook input priority filter; policy accept;
        # TCP RST for unauthenticated HTTPS — triggers browser captive portal detection
        # Redirecting HTTPS to an HTTP port causes SSL error instead of captive portal
        tcp dport 443 ct state new ip saddr != @whitelist reject with tcp reset
    }

    chain forward {
        type filter hook forward priority filter; policy drop;
        ct state established,related flow add @f accept
        ip saddr @whitelist accept
        reject with icmp type host-unreachable
    }
}
EOF

echo "  ✓ nftables table created"

# ── 2. Setup tc (HTB on WAN + IFB for upload) ─────────────────────
echo "[2/3] Setting up tc HTB..."

# IFB for upload shaping
modprobe ifb 2>/dev/null || true
ip link add ifb0 type ifb 2>/dev/null || true
ip link set ifb0 up 2>/dev/null || true

# WAN egress (download shaping)
tc qdisc del dev $WAN_IF root 2>/dev/null || true
tc qdisc add dev $WAN_IF root handle 1: htb default 999
tc class add dev $WAN_IF parent 1: classid 1:999 htb rate 1000mbit ceil 1000mbit

# WiFi ingress -> IFB (upload shaping)
tc qdisc del dev $WIFI_IF ingress 2>/dev/null || true
tc qdisc add dev $WIFI_IF handle ffff: ingress
tc filter add dev $WIFI_IF parent ffff: protocol ip u32 \
    match u32 0 0 action mirred egress redirect dev ifb0

tc qdisc del dev ifb0 root 2>/dev/null || true
tc qdisc add dev ifb0 root handle 1: htb default 999
tc class add dev ifb0 parent 1: classid 1:999 htb rate 1000mbit ceil 1000mbit

echo "  ✓ tc HTB configured"

# ── 3. Verify ──────────────────────────────────────────────────────
echo "[3/3] Verifying..."

if nft list table inet captive_portal > /dev/null 2>&1; then
    echo "  ✓ nftables table verified"
else
    echo "  ✗ nftables table verification failed"
    exit 1
fi

if tc qdisc show dev $WAN_IF | grep -q "htb"; then
    echo "  ✓ tc HTB on WAN verified"
else
    echo "  ✗ tc HTB on WAN verification failed"
    exit 1
fi

if tc qdisc show dev ifb0 | grep -q "htb"; then
    echo "  ✓ tc HTB on IFB verified"
else
    echo "  ✗ tc HTB on IFB verification failed"
    exit 1
fi

echo ""
echo "=========================================="
echo "✓ nftables + flowtables + tc initialized"
echo "=========================================="
