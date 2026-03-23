#!/usr/bin/env bash
# =============================================================================
# WiFi Captive Portal — Installation Test Script
# Verifies all components are installed and working correctly
# Usage: bash test.sh [--quick] [--verbose]
# =============================================================================
set -euo pipefail

RED='\033[0;31m'; GREEN='\033[0;32m'; YELLOW='\033[1;33m'
BLUE='\033[0;34m'; CYAN='\033[0;36m'; BOLD='\033[1m'; NC='\033[0m'

PASS=0; FAIL=0; WARN_COUNT=0
VERBOSE=0; QUICK=0

for arg in "$@"; do
    [[ "$arg" == "--verbose" ]] && VERBOSE=1
    [[ "$arg" == "--quick" ]]   && QUICK=1
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
APP_DIR="$(dirname "$SCRIPT_DIR")"
ENV_FILE="$APP_DIR/.env"
VENV_PYTHON="$APP_DIR/.venv/bin/python"

# ── helpers ───────────────────────────────────────────────────────────────────
pass() {
    PASS=$((PASS + 1))
    echo -e "  ${GREEN}✓${NC}  $*"
}

fail() {
    FAIL=$((FAIL + 1))
    echo -e "  ${RED}✗${NC}  $*"
}

warn_result() {
    WARN_COUNT=$((WARN_COUNT + 1))
    echo -e "  ${YELLOW}!${NC}  $*"
}

section() {
    echo ""
    echo -e "${BOLD}${BLUE}  ── $* ──${NC}"
}

run_check() {
    local label="$1"; shift
    if "$@" &>/dev/null; then
        pass "$label"
    else
        fail "$label"
        [[ $VERBOSE -eq 1 ]] && "$@" 2>&1 | sed 's/^/     /' || true
    fi
}

# ── load .env ────────────────────────────────────────────────────────────────
if [[ -f "$ENV_FILE" ]]; then
    set -a; source "$ENV_FILE"; set +a
else
    echo -e "${YELLOW}[WARN]${NC} .env not found at $ENV_FILE — using defaults"
fi

PORTAL_IP="${PORTAL_IP:-192.168.1.1}"
PORTAL_PORT="${PORTAL_PORT:-8080}"
WIFI_INTERFACE="${WIFI_INTERFACE:-wlan0}"
WAN_INTERFACE="${WAN_INTERFACE:-eth0}"

# Parse DATABASE_URL
if [[ -n "${DATABASE_URL:-}" ]]; then
    _url="${DATABASE_URL#postgresql+asyncpg://}"
    DB_USER="${_url%%:*}"
    _rest="${_url#*:}"
    _pass="${_rest%%@*}"
    _host_and_rest="${_rest#*@}"
    _host_port="${_host_and_rest%%/*}"
    DB_NAME="${_host_and_rest##*/}"
    DB_HOST="${_host_port%%:*}"
    DB_PORT="${_host_port##*:}"
    DB_PASS="$_pass"
fi
DB_HOST="${DB_HOST:-localhost}"
DB_PORT="${DB_PORT:-5432}"
DB_NAME="${DB_NAME:-captive_portal}"
DB_USER="${DB_USER:-captive}"

# Parse REDIS_URL
if [[ -n "${REDIS_URL:-}" ]]; then
    _rurl="${REDIS_URL#redis://}"
    REDIS_HOST="${_rurl%%:*}"
    _rrest="${_rurl#*:}"
    REDIS_PORT="${_rrest%%/*}"
    REDIS_DB="${_rrest##*/}"
fi
REDIS_HOST="${REDIS_HOST:-localhost}"
REDIS_PORT="${REDIS_PORT:-6379}"

# ── banner ───────────────────────────────────────────────────────────────────
echo ""
echo -e "${BOLD}${CYAN}  WiFi Captive Portal — Installation Tests${NC}"
echo "  $(date '+%Y-%m-%d %H:%M:%S')"

# =============================================================================
section "System"
# =============================================================================

run_check "python3 >= 3.12 available" bash -c \
    'python3 --version 2>/dev/null | python3 -c "import sys,re; v=input(); m=re.match(r\"Python (\d+)\.(\d+)\",v); sys.exit(0 if m and (int(m[1]),int(m[2])) >= (3,12) else 1)"'

run_check "nft (nftables) available" bash -c 'command -v nft'
run_check "tc (iproute2) available" bash -c 'command -v tc'
run_check "psql client available" bash -c 'command -v psql'
run_check "redis-cli available" bash -c 'command -v redis-cli'

# =============================================================================
section "Application Files"
# =============================================================================

run_check ".venv exists" test -d "$APP_DIR/.venv"
run_check "Python venv functional" "$VENV_PYTHON" -c 'import sys; sys.exit(0 if sys.prefix != sys.base_prefix else 1)'
run_check ".env file present" test -f "$ENV_FILE"
run_check ".env not world-readable" bash -c \
    '[[ "$(stat -c %a '"$ENV_FILE"')" != *"4" ]] && [[ "$(stat -c %a '"$ENV_FILE"')" != *"5" ]] && [[ "$(stat -c %a '"$ENV_FILE"')" != *"6" ]] && [[ "$(stat -c %a '"$ENV_FILE"')" != *"7" ]]' 2>/dev/null || \
    warn_result ".env permissions — should be 600 (currently $(stat -c %a "$ENV_FILE" 2>/dev/null || echo 'unknown'))"

run_check "app/main.py exists" test -f "$APP_DIR/app/main.py"
run_check "alembic.ini exists" test -f "$APP_DIR/alembic.ini"

# Python imports
if [[ -f "$VENV_PYTHON" ]]; then
    run_check "fastapi importable" "$VENV_PYTHON" -c 'import fastapi'
    run_check "sqlalchemy importable" "$VENV_PYTHON" -c 'import sqlalchemy'
    run_check "httpx importable" "$VENV_PYTHON" -c 'import httpx'
    run_check "cryptography importable" "$VENV_PYTHON" -c 'import cryptography'
    run_check "app config loads" bash -c \
        "cd $APP_DIR && $VENV_PYTHON -c 'from app.core.config import settings; print(settings.ENVIRONMENT)'"
fi

# =============================================================================
section "PostgreSQL"
# =============================================================================

run_check "PostgreSQL service running" systemctl is-active postgresql

run_check "DB host reachable ($DB_HOST:$DB_PORT)" bash -c \
    "timeout 3 bash -c 'echo > /dev/tcp/$DB_HOST/$DB_PORT' 2>/dev/null"

run_check "DB '$DB_NAME' exists" bash -c \
    "PGPASSWORD='${DB_PASS:-}' psql -h $DB_HOST -p $DB_PORT -U $DB_USER -d $DB_NAME -c 'SELECT 1' -t -A 2>/dev/null | grep -q 1"

# Schema check
if [[ $QUICK -eq 0 ]] && command -v psql &>/dev/null; then
    TABLES=$(PGPASSWORD="${DB_PASS:-}" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
        -tAc "SELECT string_agg(tablename, ',') FROM pg_tables WHERE schemaname='public'" 2>/dev/null || echo "")
    for tbl in guests sessions vouchers rooms policies pms_adapters admin_users; do
        if echo "$TABLES" | grep -q "$tbl"; then
            pass "Table '$tbl' exists"
        else
            fail "Table '$tbl' missing — run: alembic upgrade head"
        fi
    done

    ADMIN_COUNT=$(PGPASSWORD="${DB_PASS:-}" psql -h "$DB_HOST" -p "$DB_PORT" -U "$DB_USER" -d "$DB_NAME" \
        -tAc "SELECT COUNT(*) FROM admin_users" 2>/dev/null || echo "0")
    if [[ "${ADMIN_COUNT:-0}" -gt 0 ]]; then
        pass "Admin user exists ($ADMIN_COUNT user(s))"
    else
        fail "No admin users found — run installer again"
    fi
fi

# =============================================================================
section "Redis"
# =============================================================================

run_check "Redis service running" systemctl is-active redis-server

run_check "Redis host reachable ($REDIS_HOST:$REDIS_PORT)" bash -c \
    "timeout 3 bash -c 'echo > /dev/tcp/$REDIS_HOST/$REDIS_PORT' 2>/dev/null"

run_check "Redis responds to PING" bash -c \
    "redis-cli -h $REDIS_HOST -p $REDIS_PORT PING 2>/dev/null | grep -q PONG"

# =============================================================================
section "Network Rules"
# =============================================================================

# nftables
if command -v nft &>/dev/null; then
    run_check "nftables table exists" bash -c \
        "nft list table inet captive_portal 2>/dev/null | grep -q 'whitelist'"

    run_check "nftables forward chain configured" bash -c \
        "nft list chain inet captive_portal forward 2>/dev/null | grep -q 'established,related accept'"
else
    fail "nftables not available — required for v2.0"
fi

# tc
if command -v tc &>/dev/null; then
    run_check "tc HTB qdisc on $WAN_INTERFACE" bash -c \
        "tc qdisc show dev $WAN_INTERFACE 2>/dev/null | grep -q htb"
else
    warn_result "tc not available — skipping traffic control checks"
fi

# =============================================================================
section "Captive Portal Service"
# =============================================================================

run_check "captive-portal systemd service enabled" systemctl is-enabled captive-portal
run_check "captive-portal service running" systemctl is-active captive-portal

# =============================================================================
section "HTTP Endpoints"
# =============================================================================

if [[ $QUICK -eq 0 ]]; then
    BASE_URL="http://$PORTAL_IP:$PORTAL_PORT"

    # Give service a moment if it just started
    sleep 1

    run_check "Portal root / responds (HTTP 2xx/3xx)" bash -c \
        "curl -s -o /dev/null -w '%{http_code}' --connect-timeout 5 '$BASE_URL/' | grep -qE '^[23]'"

    run_check "Portal /auth/room endpoint reachable" bash -c \
        "curl -s -o /dev/null -w '%{http_code}' --connect-timeout 5 -X POST '$BASE_URL/auth/room' \
         -H 'Content-Type: application/json' -d '{\"room_number\":\"0\",\"last_name\":\"test\"}' | \
         grep -qE '^[2-5]'"

    run_check "Admin /admin/sessions endpoint exists" bash -c \
        "curl -s -o /dev/null -w '%{http_code}' --connect-timeout 5 '$BASE_URL/admin/sessions' | \
         grep -qE '^(200|401|422)'"

    # Docs endpoint (only in non-production)
    if [[ "${ENVIRONMENT:-production}" != "production" ]]; then
        run_check "OpenAPI /docs available (dev mode)" bash -c \
            "curl -s -o /dev/null -w '%{http_code}' --connect-timeout 5 '$BASE_URL/docs' | grep -q 200"
    fi
fi

# =============================================================================
section "Environment Variables"
# =============================================================================

# Check required vars are set
for var in SECRET_KEY ENCRYPTION_KEY DATABASE_URL REDIS_URL; do
    if [[ -n "${!var:-}" ]]; then
        pass "$var is set"
    else
        fail "$var is NOT set in .env"
    fi
done

# SECRET_KEY length
if [[ ${#SECRET_KEY:-} -ge 32 ]]; then
    pass "SECRET_KEY length >= 32 chars"
else
    fail "SECRET_KEY is too short (< 32 chars)"
fi

# ENCRYPTION_KEY looks like a Fernet key (44 base64 chars ending with =)
if [[ "${ENCRYPTION_KEY:-}" =~ ^[A-Za-z0-9_\-]{43}=$ ]]; then
    pass "ENCRYPTION_KEY format valid (Fernet)"
else
    fail "ENCRYPTION_KEY does not look like a valid Fernet key"
fi

# =============================================================================
# FINAL REPORT
# =============================================================================
echo ""
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
TOTAL=$((PASS + FAIL))
if [[ $FAIL -eq 0 ]]; then
    echo -e "${BOLD}${GREEN}  Result: ALL TESTS PASSED ($PASS/$TOTAL)${NC}"
else
    echo -e "${BOLD}${RED}  Result: $FAIL TEST(S) FAILED  (${PASS} passed / ${FAIL} failed / ${TOTAL} total)${NC}"
fi
[[ $WARN_COUNT -gt 0 ]] && echo -e "  ${YELLOW}Warnings: $WARN_COUNT${NC}"
echo -e "${BOLD}━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━${NC}"
echo ""

[[ $FAIL -gt 0 ]] && exit 1 || exit 0
