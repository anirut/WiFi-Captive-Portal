#!/usr/bin/env bash
# =============================================================================
# WiFi Captive Portal — Uninstall Script
# Removes all components installed by install.sh
# Must run as root: sudo bash uninstall.sh
# =============================================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "  ${BLUE}[INFO]${NC}  $*"; }
success() { echo -e "  ${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "  ${YELLOW}[WARN]${NC}  $*"; }
step()    { echo -e "\n${BOLD}${BLUE}━━━ $* ━━━${NC}"; }
ask()     { echo -e "${YELLOW}[?]${NC} $*"; }

[[ $EUID -ne 0 ]] && { echo -e "${RED}[ERROR]${NC} Must run as root: sudo bash $0" >&2; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$APP_DIR/.env"

# ── load .env if available ────────────────────────────────────────────────────
if [[ -f "$ENV_FILE" ]]; then
    set -a; source "$ENV_FILE"; set +a
fi

DB_NAME="${DB_NAME:-captive_portal}"
DB_USER="${DB_USER:-captive}"
WIFI_INTERFACE="${WIFI_INTERFACE:-wlan0}"
WAN_INTERFACE="${WAN_INTERFACE:-eth0}"

# ── banner ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${RED}  WiFi Captive Portal — Uninstaller${NC}"
echo ""
warn "This will remove the captive portal service and all its configuration."
echo ""

# ── parse DATABASE_URL for credentials if .env uses it ───────────────────────
if [[ -n "${DATABASE_URL:-}" ]]; then
    # postgresql+asyncpg://user:pass@host:port/name
    _url="${DATABASE_URL#postgresql+asyncpg://}"
    DB_USER_URL="${_url%%:*}"
    _rest="${_url#*:}"
    _pass_and_rest="${_rest%%@*}"
    DB_PASS_URL="$_pass_and_rest"
    _host_and_rest="${_rest#*@}"
    _host_port="${_host_and_rest%%/*}"
    DB_NAME_URL="${_host_and_rest##*/}"
    DB_HOST_URL="${_host_port%%:*}"
    DB_PORT_URL="${_host_port##*:}"

    DB_NAME="${DB_NAME_URL:-$DB_NAME}"
    DB_USER="${DB_USER_URL:-$DB_USER}"
fi

# ── interactive options ──────────────────────────────────────────────────────
echo -e "${BOLD}What to remove:${NC}"
echo ""

ask "Stop and remove systemd service? [Y/n]:"
read -r RM_SERVICE; RM_SERVICE="${RM_SERVICE:-Y}"

ask "Remove nftables and tc network rules? [Y/n]:"
read -r RM_NETWORK; RM_NETWORK="${RM_NETWORK:-Y}"

ask "Drop database '${DB_NAME}' and user '${DB_USER}'? [y/N]:"
read -r RM_DB; RM_DB="${RM_DB:-N}"

ask "Remove PostgreSQL 17 (from pgdg repo)? [y/N]:"
read -r RM_POSTGRES; RM_POSTGRES="${RM_POSTGRES:-N}"

ask "Remove Redis (from redis.io repo)? [y/N]:"
read -r RM_REDIS; RM_REDIS="${RM_REDIS:-N}"

ask "Remove system dependencies (iptables-persistent, dnsmasq, etc.)? [y/N]:"
read -r RM_DEPS; RM_DEPS="${RM_DEPS:-N}"

ask "Remove virtual environment (.venv)? [y/N]:"
read -r RM_VENV; RM_VENV="${RM_VENV:-N}"

ask "Remove .env configuration file? [y/N]:"
read -r RM_ENV; RM_ENV="${RM_ENV:-N}"

ask "Remove application directory entirely ($APP_DIR)? [y/N]:"
read -r RM_APP; RM_APP="${RM_APP:-N}"

echo ""
ask "Proceed? [y/N]:"
read -r CONFIRM
[[ ! "${CONFIRM:-N}" =~ ^[Yy]$ ]] && { info "Uninstall cancelled."; exit 0; }

# =============================================================================
step "STOPPING SERVICE"
# =============================================================================

if [[ "${RM_SERVICE:-Y}" =~ ^[Yy]$ ]]; then
    if systemctl is-active --quiet captive-portal 2>/dev/null; then
        info "Stopping captive-portal service..."
        systemctl stop captive-portal
        success "Service stopped."
    else
        info "Service not running."
    fi

    if systemctl is-enabled --quiet captive-portal 2>/dev/null; then
        systemctl disable captive-portal
        info "Service disabled."
    fi

    if [[ -f /etc/systemd/system/captive-portal.service ]]; then
        rm -f /etc/systemd/system/captive-portal.service
        systemctl daemon-reload
        success "Service unit file removed."
    fi
fi

# =============================================================================
step "REMOVING NETWORK RULES"
# =============================================================================

if [[ "${RM_NETWORK:-Y}" =~ ^[Yy]$ ]]; then
    WIFI_IF="$WIFI_INTERFACE"
    WAN_IF="$WAN_INTERFACE"
    PORTAL_IP_VAL="${PORTAL_IP:-192.168.1.1}"
    PORTAL_PORT_VAL="${PORTAL_PORT:-8080}"

    info "Flushing nftables rules..."
    nft delete table inet captive_portal 2>/dev/null || true
    iptables -P FORWARD ACCEPT 2>/dev/null || true
    success "nftables rules removed."

    info "Removing tc qdisc on $WAN_IF..."
    tc qdisc del dev "$WAN_IF" root 2>/dev/null || true
    success "tc rules removed."

    # Clear persisted rules
    if [[ -f /etc/iptables/rules.v4 ]]; then
        rm -f /etc/iptables/rules.v4
        info "Removed persisted iptables rules."
    fi
fi

# =============================================================================
step "REMOVING DATABASE"
# =============================================================================

if [[ "${RM_DB:-N}" =~ ^[Yy]$ ]]; then
    if command -v psql &>/dev/null; then
        info "Dropping database '$DB_NAME'..."
        sudo -u postgres psql -c "DROP DATABASE IF EXISTS $DB_NAME;" 2>/dev/null || \
            warn "Could not drop database (may not exist)."

        info "Dropping user '$DB_USER'..."
        sudo -u postgres psql -c "DROP USER IF EXISTS $DB_USER;" 2>/dev/null || \
            warn "Could not drop user (may not exist)."

        success "Database and user removed."
    else
        warn "psql not found — skipping database removal."
    fi
fi

# =============================================================================
step "REMOVING POSTGRESQL"
# =============================================================================

if [[ "${RM_POSTGRES:-N}" =~ ^[Yy]$ ]]; then
    if command -v psql &>/dev/null; then
        info "Stopping PostgreSQL service..."
        systemctl stop postgresql 2>/dev/null || true
        systemctl disable postgresql 2>/dev/null || true

        info "Removing PostgreSQL packages..."
        apt-get remove -y -qq \
            postgresql-17 postgresql-contrib-17 postgresql-client-17 \
            postgresql-common postgresql-client-common \
            2>/dev/null || true

        info "Purging PostgreSQL packages..."
        apt-get purge -y -qq \
            postgresql-17 postgresql-contrib-17 postgresql-client-17 \
            postgresql-common postgresql-client-common \
            2>/dev/null || true

        # Remove PostgreSQL data directory
        if [[ -d /var/lib/postgresql ]]; then
            info "Removing PostgreSQL data directory..."
            rm -rf /var/lib/postgresql
        fi

        # Remove PostgreSQL config directory
        if [[ -d /etc/postgresql ]]; then
            info "Removing PostgreSQL config directory..."
            rm -rf /etc/postgresql
        fi

        # Remove pgdg repo list
        if [[ -f /etc/apt/sources.list.d/pgdg.list ]]; then
            info "Removing PostgreSQL APT repository..."
            rm -f /etc/apt/sources.list.d/pgdg.list
        fi

        # Remove pgdg GPG keyring
        if [[ -f /usr/share/keyrings/postgresql-keyring.gpg ]]; then
            rm -f /usr/share/keyrings/postgresql-keyring.gpg
        fi

        apt-get update -qq
        success "PostgreSQL removed."
    else
        info "PostgreSQL not found — skipping."
    fi
fi

# =============================================================================
step "REMOVING REDIS"
# =============================================================================

if [[ "${RM_REDIS:-N}" =~ ^[Yy]$ ]]; then
    if command -v redis-server &>/dev/null || [[ -f /etc/apt/sources.list.d/redis.list ]]; then
        info "Stopping Redis service..."
        systemctl stop redis-server 2>/dev/null || true
        systemctl disable redis-server 2>/dev/null || true

        info "Removing Redis packages..."
        apt-get remove -y -qq redis redis-server redis-tools 2>/dev/null || true

        info "Purging Redis packages..."
        apt-get purge -y -qq redis redis-server redis-tools 2>/dev/null || true

        # Remove Redis data directory
        if [[ -d /var/lib/redis ]]; then
            info "Removing Redis data directory..."
            rm -rf /var/lib/redis
        fi

        # Remove Redis config
        if [[ -d /etc/redis ]]; then
            info "Removing Redis config directory..."
            rm -rf /etc/redis
        fi

        # Remove Redis repo list
        if [[ -f /etc/apt/sources.list.d/redis.list ]]; then
            info "Removing Redis APT repository..."
            rm -f /etc/apt/sources.list.d/redis.list
        fi

        # Remove Redis GPG keyring
        if [[ -f /usr/share/keyrings/redis-keyring.gpg ]]; then
            rm -f /usr/share/keyrings/redis-keyring.gpg
        fi

        apt-get update -qq
        success "Redis removed."
    else
        info "Redis not found — skipping."
    fi
fi

# =============================================================================
step "REMOVING SYSTEM DEPENDENCIES"
# =============================================================================

if [[ "${RM_DEPS:-N}" =~ ^[Yy]$ ]]; then
    info "Removing system dependencies..."

    # Remove dnsmasq if installed
    if command -v dnsmasq &>/dev/null; then
        info "Removing dnsmasq..."
        apt-get remove -y -qq dnsmasq 2>/dev/null || true
        apt-get purge -y -qq dnsmasq 2>/dev/null || true
        # Remove dnsmasq config
        rm -f /etc/dnsmasq.d/captive-portal.conf 2>/dev/null || true
    fi

    # Remove iptables-persistent and netfilter-persistent
    info "Removing iptables-persistent..."
    apt-get remove -y -qq iptables-persistent netfilter-persistent 2>/dev/null || true
    apt-get purge -y -qq iptables-persistent netfilter-persistent 2>/dev/null || true

    # Clean up iptables rules file
    rm -f /etc/iptables/rules.v4 2>/dev/null || true
    rm -f /etc/iptables/rules.v6 2>/dev/null || true

    # Remove deadsnakes PPA if we added it (for Python 3.12)
    if [[ -f /etc/apt/sources.list.d/deadsnakes-ubuntu-ppa-*.list ]]; then
        info "Removing deadsnakes PPA..."
        rm -f /etc/apt/sources.list.d/deadsnakes-ubuntu-ppa-*.list
    fi

    # Autoremove unused packages
    info "Running apt autoremove..."
    apt-get autoremove -y -qq 2>/dev/null || true

    apt-get update -qq
    success "System dependencies removed."
fi

# =============================================================================
step "REMOVING FILES"
# =============================================================================

if [[ "${RM_VENV:-N}" =~ ^[Yy]$ ]] && [[ -d "$APP_DIR/.venv" ]]; then
    info "Removing virtual environment..."
    rm -rf "$APP_DIR/.venv"
    success "Virtual environment removed."
fi

if [[ "${RM_ENV:-N}" =~ ^[Yy]$ ]] && [[ -f "$ENV_FILE" ]]; then
    info "Removing .env file..."
    rm -f "$ENV_FILE"
    success ".env removed."
fi

if [[ "${RM_APP:-N}" =~ ^[Yy]$ ]]; then
    warn "Removing application directory: $APP_DIR"
    ask "Type 'DELETE' to confirm:"
    read -r CONFIRM_DELETE
    if [[ "$CONFIRM_DELETE" == "DELETE" ]]; then
        rm -rf "$APP_DIR"
        success "Application directory removed."
    else
        info "Skipped — application directory preserved."
    fi
fi

# =============================================================================
echo ""
echo -e "${BOLD}${GREEN}  Uninstall complete.${NC}"
echo ""
