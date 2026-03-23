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

# Disable systemd-resolved DNS stub listener (frees port 53 for dnsmasq)
info "Disabling systemd-resolved stub listener on port 53..."
RESOLVED_CONF=/etc/systemd/resolved.conf
if grep -q "^#*DNSStubListener" "$RESOLVED_CONF" 2>/dev/null; then
    sed -i 's/^#*DNSStubListener=.*/DNSStubListener=no/' "$RESOLVED_CONF"
else
    echo "DNSStubListener=no" >> "$RESOLVED_CONF"
fi
systemctl restart systemd-resolved || true

info "Configuring dnsmasq to use drop-in directory..."
cat > /etc/dnsmasq.conf <<'EOF'
# Managed by WiFi Captive Portal
# Do not add settings here — use /etc/dnsmasq.d/captive-portal.conf
conf-dir=/etc/dnsmasq.d/,*.conf
EOF

mkdir -p /etc/dnsmasq.d

info "Enabling dnsmasq service..."
systemctl enable dnsmasq

# Prevent cloud-init from overwriting network config on reboot
if [[ -d /etc/cloud/cloud.cfg.d ]]; then
    echo "network: {config: disabled}" > /etc/cloud/cloud.cfg.d/99-disable-network-config.cfg
    info "Disabled cloud-init network management."
fi

success "dnsmasq setup complete. Config will be written by the portal app on first start."