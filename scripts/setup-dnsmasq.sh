#!/usr/bin/env bash
# =============================================================================
# WiFi Captive Portal — dnsmasq Setup
# Installs dnsmasq and configures it for captive portal management.
# Called by install.sh. Must run as root.
# =============================================================================
set -e

GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
info() { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }

[[ $EUID -ne 0 ]] && { echo "Must run as root"; exit 1; }

info "Installing dnsmasq..."
apt-get install -y -qq dnsmasq

info "Stopping dnsmasq to take over config..."
systemctl stop dnsmasq || true

info "Configuring dnsmasq to use drop-in directory..."
cat > /etc/dnsmasq.conf <<'EOF'
# Managed by WiFi Captive Portal
# Do not add settings here — use /etc/dnsmasq.d/captive-portal.conf
conf-dir=/etc/dnsmasq.d/,*.conf
EOF

mkdir -p /etc/dnsmasq.d

info "Enabling dnsmasq service (will start via captive-portal lifespan)..."
systemctl enable dnsmasq

success "dnsmasq setup complete. Config will be written by the portal app on first start."