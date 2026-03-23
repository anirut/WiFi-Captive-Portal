#!/usr/bin/env bash
# =============================================================================
# FIAS Emulator — Installation Script
# Installs the Opera FIAS TCP emulator as a standalone systemd service.
# Tested on: Ubuntu 22.04 LTS / Ubuntu 24.04 LTS
# Must run as root: sudo bash install.sh
# =============================================================================
set -euo pipefail

# ── colours ──────────────────────────────────────────────────────────────────
RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

info()    { echo -e "${CYAN}[INFO]${NC}  $*"; }
success() { echo -e "${GREEN}[OK]${NC}    $*"; }
warn()    { echo -e "${YELLOW}[WARN]${NC}  $*"; }
error()   { echo -e "${RED}[ERROR]${NC} $*" >&2; exit 1; }
step()    { echo -e "\n${BOLD}${BLUE}━━━ $* ━━━${NC}"; }
ask()     { echo -e "${YELLOW}[?]${NC} $*"; }

# ── root check ───────────────────────────────────────────────────────────────
[[ $EUID -ne 0 ]] && error "This script must be run as root: sudo bash $0"

# ── banner ───────────────────────────────────────────────────────────────────
if [[ -t 1 ]]; then clear; fi
echo -e "${BOLD}${BLUE}"
cat <<'EOF'
  ███████╗██╗ █████╗ ███████╗    ███████╗███╗   ███╗██╗   ██╗██╗      █████╗ ████████╗ ██████╗ ██████╗
  ██╔════╝██║██╔══██╗██╔════╝    ██╔════╝████╗ ████║██║   ██║██║     ██╔══██╗╚══██╔══╝██╔═══██╗██╔══██╗
  █████╗  ██║███████║███████╗    █████╗  ██╔████╔██║██║   ██║██║     ███████║   ██║   ██║   ██║██████╔╝
  ██╔══╝  ██║██╔══██║╚════██║    ██╔══╝  ██║╚██╔╝██║██║   ██║██║     ██╔══██║   ██║   ██║   ██║██╔══██╗
  ██║     ██║██║  ██║███████║    ███████╗██║ ╚═╝ ██║╚██████╔╝███████╗██║  ██║   ██║   ╚██████╔╝██║  ██║
  ╚═╝     ╚═╝╚═╝  ╚═╝╚══════╝    ╚══════╝╚═╝     ╚═╝ ╚═════╝ ╚══════╝╚═╝  ╚═╝   ╚═╝    ╚═════╝ ╚═╝  ╚═╝
        Opera FIAS TCP Emulator  —  I N S T A L L E R
EOF
echo -e "${NC}"
echo "  Test your captive portal PMS integration without a real Opera PMS system."
echo ""

# ── detect install directory ─────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
info "Source directory: $SCRIPT_DIR"

# =============================================================================
# SECTION 1: Interactive Configuration
# =============================================================================
step "CONFIGURATION"

echo ""
echo "  Press ENTER to accept the default value shown in [brackets]."
echo ""

ask "Install directory [/opt/fias-emulator]:"
read -r INSTALL_DIR
INSTALL_DIR="${INSTALL_DIR:-/opt/fias-emulator}"

ask "Run service as user [$(logname 2>/dev/null || echo www-data)]:"
read -r SERVICE_USER
SERVICE_USER="${SERVICE_USER:-$(logname 2>/dev/null || echo www-data)}"

echo ""
echo -e "${BOLD}Ports${NC}"

ask "HTTP management / dashboard port [8081]:"
read -r HTTP_PORT
HTTP_PORT="${HTTP_PORT:-8081}"

ask "FIAS TCP server port [9090]:"
read -r TCP_PORT
TCP_PORT="${TCP_PORT:-9090}"

echo ""
echo -e "${BOLD}FIAS Authentication${NC}"
echo "  Leave blank if your captive portal does not set an AuthKey."

ask "FIAS AuthKey (optional) []:"
read -r AUTH_KEY
AUTH_KEY="${AUTH_KEY:-}"

ask "FIAS VendorID [wifi-portal]:"
read -r VENDOR_ID
VENDOR_ID="${VENDOR_ID:-wifi-portal}"

echo ""
ask "Seed pre-configured test scenarios? [Y/n]:"
read -r SEED_DATA
SEED_DATA="${SEED_DATA:-Y}"

# ── summary ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}━━━ Configuration Summary ━━━${NC}"
echo "  Install directory: $INSTALL_DIR"
echo "  Service user:      $SERVICE_USER"
echo "  HTTP port:         $HTTP_PORT  (dashboard + REST API)"
echo "  TCP port:          $TCP_PORT   (FIAS protocol)"
echo "  FIAS AuthKey:      ${AUTH_KEY:-(none)}"
echo "  FIAS VendorID:     $VENDOR_ID"
echo "  Seed scenarios:    $([[ ${SEED_DATA:-Y} =~ ^[Yy] ]] && echo yes || echo no)"
echo ""

ask "Proceed with installation? [Y/n]:"
read -r CONFIRM
[[ "${CONFIRM:-Y}" =~ ^[Nn]$ ]] && { info "Installation cancelled."; exit 0; }

# =============================================================================
# SECTION 2: System Prerequisites
# =============================================================================
step "CHECKING PREREQUISITES"

export DEBIAN_FRONTEND=noninteractive

# Python 3.10+
PYTHON_VERSION=$(python3 --version 2>/dev/null | awk '{print $2}' || echo "0")
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [[ "$PYTHON_MAJOR" -lt 3 ]] || [[ "$PYTHON_MAJOR" -eq 3 && "$PYTHON_MINOR" -lt 10 ]]; then
    info "Python 3.10+ required (found $PYTHON_VERSION). Installing..."
    apt-get update -qq
    add-apt-repository -y ppa:deadsnakes/ppa 2>/dev/null || true
    apt-get update -qq
    apt-get install -y -qq python3.12 python3.12-venv python3.12-dev python3-pip
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1
    success "Python 3.12 installed."
else
    success "Python $PYTHON_VERSION — OK"
    # Ensure venv package available
    apt-get install -y -qq "python3.${PYTHON_MINOR}-venv" python3-pip 2>/dev/null || \
        apt-get install -y -qq python3-venv python3-pip 2>/dev/null || true
fi

# Verify service user exists
if ! id "$SERVICE_USER" &>/dev/null; then
    info "Creating system user '$SERVICE_USER'..."
    useradd --system --no-create-home --shell /usr/sbin/nologin "$SERVICE_USER"
    success "User '$SERVICE_USER' created."
else
    success "User '$SERVICE_USER' — OK"
fi

# =============================================================================
# SECTION 3: Copy Application Files
# =============================================================================
step "INSTALLING APPLICATION FILES"

# Backup existing install if present
if [[ -d "$INSTALL_DIR" ]]; then
    BACKUP_DIR="${INSTALL_DIR}.backup.$(date +%Y%m%d_%H%M%S)"
    warn "Existing installation found at $INSTALL_DIR"
    info "Backing up to $BACKUP_DIR ..."
    cp -a "$INSTALL_DIR" "$BACKUP_DIR"
    # Preserve existing database
    if [[ -f "$INSTALL_DIR/fias_emulator.db" ]]; then
        cp "$INSTALL_DIR/fias_emulator.db" /tmp/fias_emulator.db.bak
        info "Existing database preserved."
    fi
fi

info "Copying files to $INSTALL_DIR ..."
mkdir -p "$INSTALL_DIR"
cp -r "$SCRIPT_DIR/emulator" "$INSTALL_DIR/"
cp "$SCRIPT_DIR/pyproject.toml" "$INSTALL_DIR/"

# Restore database if backed up
if [[ -f /tmp/fias_emulator.db.bak ]]; then
    cp /tmp/fias_emulator.db.bak "$INSTALL_DIR/fias_emulator.db"
    rm -f /tmp/fias_emulator.db.bak
    info "Database restored from backup."
fi

chown -R "$SERVICE_USER:$SERVICE_USER" "$INSTALL_DIR"
success "Files installed to $INSTALL_DIR"

# =============================================================================
# SECTION 4: Python Virtual Environment & Dependencies
# =============================================================================
step "INSTALLING PYTHON DEPENDENCIES"

VENV_DIR="$INSTALL_DIR/.venv"

if [[ ! -d "$VENV_DIR" ]] || [[ ! -f "$VENV_DIR/bin/pip" ]]; then
    [[ -d "$VENV_DIR" ]] && { info "Removing broken virtual environment..."; rm -rf "$VENV_DIR"; }
    info "Creating virtual environment at $VENV_DIR ..."
    python3 -m venv "$VENV_DIR"
fi

info "Upgrading pip..."
"$VENV_DIR/bin/pip" install --quiet --upgrade pip

info "Installing dependencies..."
"$VENV_DIR/bin/pip" install --quiet -e "$INSTALL_DIR"

chown -R "$SERVICE_USER:$SERVICE_USER" "$VENV_DIR"
success "Python dependencies installed."

# =============================================================================
# SECTION 5: Write .env Configuration
# =============================================================================
step "WRITING CONFIGURATION"

ENV_FILE="$INSTALL_DIR/.env"

cat > "$ENV_FILE" <<EOF
# FIAS Emulator — Environment Configuration
# Generated by install.sh on $(date '+%Y-%m-%d %H:%M:%S')

FIAS_TCP_HOST=0.0.0.0
FIAS_TCP_PORT=$TCP_PORT
HTTP_HOST=0.0.0.0
HTTP_PORT=$HTTP_PORT
DATABASE_URL=sqlite+aiosqlite:///./fias_emulator.db
AUTH_KEY=$AUTH_KEY
VENDOR_ID=$VENDOR_ID
EOF

chmod 640 "$ENV_FILE"
chown "root:$SERVICE_USER" "$ENV_FILE"
success ".env written to $ENV_FILE"

# =============================================================================
# SECTION 6: Seed Test Data
# =============================================================================
if [[ "${SEED_DATA:-Y}" =~ ^[Yy] ]]; then
    step "SEEDING TEST SCENARIOS"

    # Only seed if database does not exist (fresh install)
    if [[ ! -f "$INSTALL_DIR/fias_emulator.db" ]]; then
        info "Seeding pre-configured scenarios..."
        cd "$INSTALL_DIR"
        sudo -u "$SERVICE_USER" \
            env "DATABASE_URL=sqlite+aiosqlite:///./fias_emulator.db" \
            "$VENV_DIR/bin/python" -m emulator.seed_data
        success "Test scenarios seeded."
    else
        info "Existing database found — skipping seed to preserve data."
        info "To re-seed: cd $INSTALL_DIR && sudo -u $SERVICE_USER $VENV_DIR/bin/python -m emulator.seed_data"
    fi
fi

# =============================================================================
# SECTION 7: systemd Service
# =============================================================================
step "INSTALLING SYSTEMD SERVICE"

SERVICE_FILE="/etc/systemd/system/fias-emulator.service"

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=FIAS Emulator - Opera PMS TCP Emulator
Documentation=https://github.com/anirut/WiFi-Captive-Portal
After=network.target

[Service]
Type=simple
User=$SERVICE_USER
Group=$SERVICE_USER
WorkingDirectory=$INSTALL_DIR
EnvironmentFile=$ENV_FILE
ExecStart=$VENV_DIR/bin/uvicorn emulator.main:app --host 0.0.0.0 --port $HTTP_PORT --workers 1
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=fias-emulator

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable fias-emulator
systemctl restart fias-emulator

sleep 2

if systemctl is-active --quiet fias-emulator; then
    success "Service 'fias-emulator' started and enabled."
else
    warn "Service failed to start. Check: journalctl -u fias-emulator -n 50"
fi

# =============================================================================
# SECTION 8: Verify Health
# =============================================================================
step "VERIFYING INSTALLATION"

info "Waiting for service to be ready..."
for i in {1..10}; do
    if curl -sf "http://localhost:${HTTP_PORT}/health" >/dev/null 2>&1; then
        break
    fi
    sleep 1
done

HEALTH=$(curl -s "http://localhost:${HTTP_PORT}/health" 2>/dev/null || echo '{}')
FIAS_RUNNING=$(echo "$HEALTH" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('fias_server_running','?'))" 2>/dev/null || echo "?")

if [[ "$FIAS_RUNNING" == "True" ]] || [[ "$FIAS_RUNNING" == "true" ]]; then
    success "HTTP API:   http://localhost:${HTTP_PORT}  — healthy"
    success "FIAS TCP:   0.0.0.0:${TCP_PORT}           — running"
else
    warn "Health check returned: $HEALTH"
    warn "Check logs: journalctl -u fias-emulator -n 30"
fi

# =============================================================================
# SECTION 9: Final Summary
# =============================================================================
echo ""
echo -e "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}${GREEN}  ✓  FIAS Emulator Installed Successfully!${NC}"
echo -e "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  Dashboard:     http://localhost:${HTTP_PORT}"
echo "  FIAS TCP:      localhost:${TCP_PORT}"
echo "  Install dir:   $INSTALL_DIR"
echo "  Config:        $ENV_FILE"
echo ""
echo "  Service:       systemctl status fias-emulator"
echo "  Logs:          journalctl -u fias-emulator -f"
echo ""
echo -e "${BOLD}  Connecting from captive portal:${NC}"
echo "  In Admin → PMS Settings → Adapter Type: Opera FIAS (TCP)"
echo "  Host: $(hostname -I | awk '{print $1}')  Port: ${TCP_PORT}  AuthKey: ${AUTH_KEY:-(blank)}  VendorID: ${VENDOR_ID}"
echo ""
echo -e "${BOLD}  Pre-configured test scenarios:${NC}"
echo "   happy_path    — Rooms 101-103, 201-202 (Smith, Johnson, Williams, Brown, Davis)"
echo "   edge_cases    — Rooms 501-503, 601-603 (multi-guest, same-day turnover)"
echo "   connection_failures / protocol_errors / business_logic"
echo ""
echo "  Activate a scenario via dashboard or:"
echo "  curl -X POST http://localhost:${HTTP_PORT}/api/scenarios/1/activate"
echo ""
