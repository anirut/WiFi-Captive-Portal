#!/usr/bin/env bash
# =============================================================================
# WiFi Captive Portal — Full Installation Script
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
clear
echo -e "${BOLD}${BLUE}"
cat <<'EOF'
 ██╗    ██╗██╗███████╗██╗     ██████╗ ██████╗ ██████╗ ████████╗ █████╗ ██╗
 ██║    ██║██║██╔════╝██║    ██╔════╝██╔═══██╗██╔══██╗╚══██╔══╝██╔══██╗██║
 ██║ █╗ ██║██║█████╗  ██║    ██║     ██║   ██║██████╔╝   ██║   ███████║██║
 ██║███╗██║██║██╔══╝  ██║    ██║     ██║   ██║██╔══██╗   ██║   ██╔══██║██║
 ╚███╔███╔╝██║██║     ██║    ╚██████╗╚██████╔╝██║  ██║   ██║   ██║  ██║███████╗
  ╚══╝╚══╝ ╚═╝╚═╝     ╚═╝     ╚═════╝ ╚═════╝ ╚═╝  ╚═╝   ╚═╝   ╚═╝  ╚═╝╚══════╝
        C A P T I V E   P O R T A L  —  I N S T A L L E R
EOF
echo -e "${NC}"
echo "  Hotel WiFi Captive Portal with PMS Integration"
echo "  Phase 2 — Full Stack Setup"
echo ""

# ── detect install directory ─────────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"
info "Application directory: $APP_DIR"

# =============================================================================
# SECTION 1: Interactive Configuration
# =============================================================================
step "CONFIGURATION"

echo ""
echo "  Please answer the following questions."
echo "  Press ENTER to accept the default value shown in [brackets]."
echo ""

# ── network ──────────────────────────────────────────────────────────────────
echo -e "${BOLD}Network Interfaces${NC}"
echo "  Available interfaces:"
ip -o link show | awk '{print "   ", NR".", $2}' | sed 's/://'
echo ""

ask "WiFi interface (AP/hotspot side) [wlan0]:"
read -r WIFI_INTERFACE
WIFI_INTERFACE="${WIFI_INTERFACE:-wlan0}"

ask "WAN interface (internet/uplink side) [eth0]:"
read -r WAN_INTERFACE
WAN_INTERFACE="${WAN_INTERFACE:-eth0}"

ask "Portal gateway IP (this server's IP on WiFi network) [192.168.1.1]:"
read -r PORTAL_IP
PORTAL_IP="${PORTAL_IP:-192.168.1.1}"

ask "Portal application port [8080]:"
read -r PORTAL_PORT
PORTAL_PORT="${PORTAL_PORT:-8080}"

echo ""

# ── database ─────────────────────────────────────────────────────────────────
echo -e "${BOLD}PostgreSQL Database${NC}"

ask "PostgreSQL host [localhost]:"
read -r DB_HOST
DB_HOST="${DB_HOST:-localhost}"

ask "PostgreSQL port [5432]:"
read -r DB_PORT
DB_PORT="${DB_PORT:-5432}"

ask "Database name [captive_portal]:"
read -r DB_NAME
DB_NAME="${DB_NAME:-captive_portal}"

ask "Database user [captive]:"
read -r DB_USER
DB_USER="${DB_USER:-captive}"

ask "Database password [auto-generate]:"
read -r -s DB_PASS
echo ""
if [[ -z "$DB_PASS" ]]; then
    DB_PASS="$(openssl rand -base64 24 | tr -d '/+=' | head -c 24)"
    info "Generated database password: ${BOLD}$DB_PASS${NC}"
    info "(Saved to .env — keep this safe)"
fi

echo ""

# ── redis ────────────────────────────────────────────────────────────────────
echo -e "${BOLD}Redis${NC}"

ask "Redis host [localhost]:"
read -r REDIS_HOST
REDIS_HOST="${REDIS_HOST:-localhost}"

ask "Redis port [6379]:"
read -r REDIS_PORT
REDIS_PORT="${REDIS_PORT:-6379}"

ask "Redis database number [0]:"
read -r REDIS_DB
REDIS_DB="${REDIS_DB:-0}"

echo ""

# ── admin account ────────────────────────────────────────────────────────────
echo -e "${BOLD}Initial Admin Account${NC}"

ask "Admin username [admin]:"
read -r ADMIN_USER
ADMIN_USER="${ADMIN_USER:-admin}"

while true; do
    ask "Admin password (min 8 chars):"
    read -r -s ADMIN_PASS
    echo ""
    if [[ ${#ADMIN_PASS} -ge 8 ]]; then
        break
    fi
    warn "Password must be at least 8 characters. Try again."
done

echo ""

# ── environment ──────────────────────────────────────────────────────────────
echo -e "${BOLD}Deployment${NC}"

ask "Environment [production]:"
read -r ENVIRONMENT
ENVIRONMENT="${ENVIRONMENT:-production}"

# ── summary ──────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}━━━ Configuration Summary ━━━${NC}"
echo "  WiFi interface:    $WIFI_INTERFACE"
echo "  WAN interface:     $WAN_INTERFACE"
echo "  Portal IP:         $PORTAL_IP"
echo "  Portal port:       $PORTAL_PORT"
echo "  DB host:           $DB_HOST:$DB_PORT"
echo "  DB name:           $DB_NAME"
echo "  DB user:           $DB_USER"
echo "  Redis:             $REDIS_HOST:$REDIS_PORT/$REDIS_DB"
echo "  Admin user:        $ADMIN_USER"
echo "  Environment:       $ENVIRONMENT"
echo ""

ask "Proceed with installation? [Y/n]:"
read -r CONFIRM
[[ "${CONFIRM:-Y}" =~ ^[Nn]$ ]] && { info "Installation cancelled."; exit 0; }

# =============================================================================
# SECTION 2: System Packages
# =============================================================================
step "INSTALLING SYSTEM PACKAGES"

export DEBIAN_FRONTEND=noninteractive

info "Updating package index..."
apt-get update -qq

info "Installing base dependencies..."
apt-get install -y -qq \
    curl wget gnupg2 ca-certificates lsb-release \
    software-properties-common apt-transport-https \
    build-essential libssl-dev libffi-dev \
    iptables iptables-persistent netfilter-persistent \
    iproute2 net-tools \
    git

# ── Python 3.12 ──────────────────────────────────────────────────────────────
PYTHON_VERSION=$(python3 --version 2>/dev/null | awk '{print $2}' || echo "0")
PYTHON_MAJOR=$(echo "$PYTHON_VERSION" | cut -d. -f1)
PYTHON_MINOR=$(echo "$PYTHON_VERSION" | cut -d. -f2)

if [[ "$PYTHON_MAJOR" -lt 3 ]] || [[ "$PYTHON_MAJOR" -eq 3 && "$PYTHON_MINOR" -lt 12 ]]; then
    info "Python 3.12+ required (found $PYTHON_VERSION). Installing..."
    add-apt-repository -y ppa:deadsnakes/ppa
    apt-get update -qq
    apt-get install -y -qq python3.12 python3.12-venv python3.12-dev python3-pip
    update-alternatives --install /usr/bin/python3 python3 /usr/bin/python3.12 1
    success "Python 3.12 installed."
else
    success "Python $PYTHON_VERSION already installed."
fi

# ── PostgreSQL ───────────────────────────────────────────────────────────────
if ! command -v psql &>/dev/null; then
    info "Installing PostgreSQL..."
    apt-get install -y -qq postgresql postgresql-contrib
    systemctl enable postgresql
    systemctl start postgresql
    success "PostgreSQL installed and started."
else
    PG_VER=$(psql --version | awk '{print $3}' | cut -d. -f1)
    success "PostgreSQL $PG_VER already installed."
fi

# ── Redis ────────────────────────────────────────────────────────────────────
if ! command -v redis-server &>/dev/null; then
    info "Installing Redis..."
    apt-get install -y -qq redis-server
    systemctl enable redis-server
    systemctl start redis-server
    success "Redis installed and started."
else
    success "Redis already installed."
fi

# =============================================================================
# SECTION 3: Database Setup
# =============================================================================
step "CONFIGURING DATABASE"

DB_EXISTS=$(sudo -u postgres psql -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" 2>/dev/null || echo "")
USER_EXISTS=$(sudo -u postgres psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DB_USER'" 2>/dev/null || echo "")

if [[ -z "$USER_EXISTS" ]]; then
    info "Creating database user '$DB_USER'..."
    sudo -u postgres psql -c "CREATE USER $DB_USER WITH PASSWORD '$DB_PASS';"
    success "Database user created."
else
    info "Database user '$DB_USER' already exists. Updating password..."
    sudo -u postgres psql -c "ALTER USER $DB_USER WITH PASSWORD '$DB_PASS';"
fi

if [[ -z "$DB_EXISTS" ]]; then
    info "Creating database '$DB_NAME'..."
    sudo -u postgres psql -c "CREATE DATABASE $DB_NAME OWNER $DB_USER;"
    success "Database '$DB_NAME' created."
else
    warn "Database '$DB_NAME' already exists — skipping creation."
fi

sudo -u postgres psql -c "GRANT ALL PRIVILEGES ON DATABASE $DB_NAME TO $DB_USER;" 2>/dev/null || true

# Allow pg_hba auth for our user
PG_HBA=$(find /etc/postgresql -name "pg_hba.conf" 2>/dev/null | head -1)
if [[ -n "$PG_HBA" ]]; then
    if ! grep -q "^host.*$DB_NAME.*$DB_USER" "$PG_HBA"; then
        echo "host    $DB_NAME    $DB_USER    127.0.0.1/32    md5" >> "$PG_HBA"
        echo "host    $DB_NAME    $DB_USER    ::1/128          md5" >> "$PG_HBA"
        systemctl reload postgresql
        info "Added pg_hba rule for $DB_USER."
    fi
fi

success "Database configured."

# =============================================================================
# SECTION 4: Python Virtual Environment & Dependencies
# =============================================================================
step "INSTALLING PYTHON DEPENDENCIES"

VENV_DIR="$APP_DIR/.venv"

if [[ ! -d "$VENV_DIR" ]]; then
    info "Creating virtual environment at $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
fi

info "Upgrading pip..."
"$VENV_DIR/bin/pip" install --quiet --upgrade pip

info "Installing Python dependencies..."
"$VENV_DIR/bin/pip" install --quiet -r "$APP_DIR/requirements.txt"

success "Python dependencies installed."

# =============================================================================
# SECTION 5: Generate Secrets & Write .env
# =============================================================================
step "GENERATING SECRETS & WRITING .env"

SECRET_KEY="$(openssl rand -hex 32)"
ENCRYPTION_KEY="$("$VENV_DIR/bin/python" -c \
    'from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())')"

DATABASE_URL="postgresql+asyncpg://${DB_USER}:${DB_PASS}@${DB_HOST}:${DB_PORT}/${DB_NAME}"
REDIS_URL="redis://${REDIS_HOST}:${REDIS_PORT}/${REDIS_DB}"

ENV_FILE="$APP_DIR/.env"
cat > "$ENV_FILE" <<EOF
# WiFi Captive Portal — Environment Configuration
# Generated by install.sh on $(date '+%Y-%m-%d %H:%M:%S')

# ── Security ──────────────────────────────────────────────────────────────────
SECRET_KEY=$SECRET_KEY
ENCRYPTION_KEY=$ENCRYPTION_KEY
ENVIRONMENT=$ENVIRONMENT

# ── Database ──────────────────────────────────────────────────────────────────
DATABASE_URL=$DATABASE_URL

# ── Redis ─────────────────────────────────────────────────────────────────────
REDIS_URL=$REDIS_URL

# ── Network ───────────────────────────────────────────────────────────────────
WIFI_INTERFACE=$WIFI_INTERFACE
WAN_INTERFACE=$WAN_INTERFACE
PORTAL_IP=$PORTAL_IP
PORTAL_PORT=$PORTAL_PORT

# ── Session & Auth ────────────────────────────────────────────────────────────
JWT_ALGORITHM=HS256
JWT_EXPIRE_HOURS=8
AUTH_RATE_LIMIT_ATTEMPTS=5
AUTH_RATE_LIMIT_WINDOW_SECONDS=600
EOF

chmod 600 "$ENV_FILE"
success ".env written to $ENV_FILE"

# =============================================================================
# SECTION 6: Database Migrations
# =============================================================================
step "RUNNING DATABASE MIGRATIONS"

cd "$APP_DIR"
info "Running Alembic migrations..."
"$VENV_DIR/bin/alembic" upgrade head

success "Database schema up to date."

# =============================================================================
# SECTION 7: Create Initial Admin User
# =============================================================================
step "CREATING ADMIN USER"

info "Creating admin user '$ADMIN_USER'..."
"$VENV_DIR/bin/python" - <<PYEOF
import asyncio, os, sys
sys.path.insert(0, "$APP_DIR")
os.chdir("$APP_DIR")

async def create_admin():
    from app.core.database import AsyncSessionFactory
    from app.core.models import AdminUser, AdminRole
    from passlib.context import CryptContext
    from sqlalchemy import select

    pwd_ctx = CryptContext(schemes=["bcrypt"], deprecated="auto")
    hashed = pwd_ctx.hash("$ADMIN_PASS")

    async with AsyncSessionFactory() as db:
        result = await db.execute(select(AdminUser).where(AdminUser.username == "$ADMIN_USER"))
        existing = result.scalar_one_or_none()
        if existing:
            existing.password_hash = hashed
            print("  Admin user updated.")
        else:
            admin = AdminUser(
                username="$ADMIN_USER",
                password_hash=hashed,
                role=AdminRole.superadmin,
            )
            db.add(admin)
            print("  Admin user created.")
        await db.commit()

asyncio.run(create_admin())
PYEOF

success "Admin user '$ADMIN_USER' ready."

# =============================================================================
# SECTION 8: Network Rules (nftables + tc)
# =============================================================================
step "CONFIGURING NETWORK RULES"

info "Setting up nftables + flowtables + tc..."
bash "$SCRIPT_DIR/setup-nftables.sh" \
    --wifi "$WIFI_INTERFACE" \
    --wan "$WAN_INTERFACE" \
    --portal-ip "$PORTAL_IP" \
    --portal-port "$PORTAL_PORT" \
    --dns-ip "${DNS_UPSTREAM_IP:-8.8.8.8}"

info "Setting up dnsmasq DHCP+DNS..."
bash "$SCRIPT_DIR/setup-dnsmasq.sh"

success "Network rules configured."

# =============================================================================
# SECTION 9: systemd Service
# =============================================================================
step "INSTALLING SYSTEMD SERVICE"

SERVICE_FILE="/etc/systemd/system/captive-portal.service"

cat > "$SERVICE_FILE" <<EOF
[Unit]
Description=WiFi Captive Portal
Documentation=https://github.com/anirut/WiFi-Captive-Portal
After=network.target postgresql.service redis-server.service
Requires=postgresql.service redis-server.service

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=$APP_DIR
EnvironmentFile=$ENV_FILE
ExecStartPre=$SCRIPT_DIR/setup-nftables.sh
ExecStart=$VENV_DIR/bin/uvicorn app.main:app --host 0.0.0.0 --port $PORTAL_PORT --workers 1
ExecReload=/bin/kill -HUP \$MAINPID
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=captive-portal

[Install]
WantedBy=multi-user.target
EOF

systemctl daemon-reload
systemctl enable captive-portal
systemctl start captive-portal

sleep 2

if systemctl is-active --quiet captive-portal; then
    success "Service 'captive-portal' started and enabled."
else
    warn "Service failed to start. Check logs: journalctl -u captive-portal -n 50"
fi

# =============================================================================
# SECTION 10: Final Summary
# =============================================================================
echo ""
echo -e "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo -e "${BOLD}${GREEN}  ✓  Installation Complete!${NC}"
echo -e "${BOLD}${GREEN}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""
echo "  Portal URL:    http://$PORTAL_IP:$PORTAL_PORT"
echo "  Admin URL:     http://$PORTAL_IP:$PORTAL_PORT/admin"
echo "  Admin login:   $ADMIN_USER"
echo ""
echo "  Service:       systemctl status captive-portal"
echo "  Logs:          journalctl -u captive-portal -f"
echo "  Config:        $ENV_FILE"
echo ""
echo "  Test install:  bash $SCRIPT_DIR/test.sh"
echo "  Uninstall:     bash $SCRIPT_DIR/uninstall.sh"
echo ""
