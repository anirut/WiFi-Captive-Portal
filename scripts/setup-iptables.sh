#!/usr/bin/env bash
set -e
WIFI_IF="${WIFI_IF:-wlan0}"
PORTAL_IP="${PORTAL_IP:-192.168.1.1}"
PORTAL_PORT="${PORTAL_PORT:-8080}"

echo "Setting up iptables for captive portal..."
# Flush existing rules
iptables -F FORWARD
iptables -t nat -F PREROUTING

# Default: drop unauthenticated forwarding
iptables -A FORWARD -i "$WIFI_IF" -j DROP

# Allow established connections
iptables -I FORWARD -i "$WIFI_IF" -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# Redirect HTTP to portal
iptables -t nat -A PREROUTING -i "$WIFI_IF" -p tcp --dport 80 \
    -m conntrack ! --ctstate ESTABLISHED \
    -j DNAT --to "$PORTAL_IP":"$PORTAL_PORT"

# Allow DNS for unauthenticated clients (needed for captive portal detection)
iptables -I FORWARD -i "$WIFI_IF" -p tcp --dport 53 -j ACCEPT
iptables -I FORWARD -i "$WIFI_IF" -p udp --dport 53 -j ACCEPT

echo "iptables setup complete."
