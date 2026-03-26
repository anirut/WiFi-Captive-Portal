#!/usr/bin/env bash
# =============================================================================
# setup-nftables.sh - Initialize nftables + tc for captive portal
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

    # Well-known DoH (DNS-over-HTTPS) server IPs.
    # Authenticated clients are blocked from reaching these so their OS/browser
    # falls back to plain UDP port 53, which we intercept for 'logout' resolution.
    set doh_servers {
        type ipv4_addr
        flags interval
        elements = {
            8.8.8.8, 8.8.4.4,              # Google
            1.1.1.1, 1.0.0.1,              # Cloudflare
            9.9.9.9, 149.112.112.112,       # Quad9
            208.67.222.222, 208.67.220.220  # OpenDNS
        }
    }

    # Client MAC addresses that bypass the captive portal entirely
    set mac_bypass {
        type ether_addr
    }

    chain prerouting {
        type nat hook prerouting priority dstnat; policy accept;

        # DNS for authenticated users → auth DNS proxy (resolves 'logout', forwards rest to upstream)
        ip saddr @dns_bypass udp dport 53 dnat to $PORTAL_IP:5354
        ip saddr @dns_bypass tcp dport 53 dnat to $PORTAL_IP:5354

        # Force all unauthenticated DNS to local dnsmasq
        # (handles clients with hardcoded DNS like 8.8.8.8, 1.1.1.1)
        ip saddr != @dns_bypass udp dport 53 dnat to $PORTAL_IP:53
        ip saddr != @dns_bypass tcp dport 53 dnat to $PORTAL_IP:53

        # MAC bypass: mark connection and skip portal redirect
        ether saddr @mac_bypass ct mark set 0x2 accept

        # http://logout and https://logout — let ALL clients reach the portal
        # (authenticated/whitelisted clients would otherwise bypass the DNAT below)
        ip daddr $PORTAL_IP tcp dport 80 dnat to $PORTAL_IP:$PORTAL_PORT
        ip daddr $PORTAL_IP tcp dport 443 dnat to $PORTAL_IP:8443

        # Portal redirect for unauthenticated users (HTTP)
        ip saddr != @whitelist tcp dport 80 dnat to $PORTAL_IP:$PORTAL_PORT

        # NOTE: HTTPS (port 443) for unauthenticated clients is NOT DNAT'd here.
        # Instead, the forward chain sends a TCP RST, which causes browsers to
        # trigger their built-in captive portal detection immediately.
        # (Intercepting TLS with a self-signed cert breaks browser security and
        #  HSTS-preloaded sites like google.com cannot be intercepted at all.)
    }

    chain postrouting {
        type nat hook postrouting priority srcnat; policy accept;
        oifname $WAN_IF ip saddr @whitelist masquerade
        oifname $WAN_IF ct mark 0x2 masquerade
    }

    chain input {
        type filter hook input priority filter; policy accept;
    }

    chain forward {
        type filter hook forward priority filter; policy drop;
        ct state established,related accept
        # Block DoH to well-known servers for authenticated clients so their
        # OS/browser falls back to plain DNS port 53 (intercepted → our proxy)
        ip saddr @dns_bypass ip daddr @doh_servers tcp dport 443 reject with icmp type admin-prohibited
        ip saddr @whitelist accept
        # MAC bypass: allow full internet access for bypassed devices
        ct mark 0x2 accept
        # Fast-fail HTTPS for unauthenticated clients: TCP RST causes browsers to
        # immediately re-run captive portal detection (generate_204 / hotspot-detect)
        # and show the "Sign in to network" prompt — much faster than a timeout.
        tcp dport 443 reject with tcp reset
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
echo "✓ nftables + tc initialized"
echo "=========================================="
