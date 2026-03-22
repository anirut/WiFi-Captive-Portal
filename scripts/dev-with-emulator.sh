#!/bin/bash
#
# Development script to run both the main captive portal and FIAS emulator.
#
# This script:
# 1. Kills any existing processes on our ports
# 2. Starts FIAS emulator in background
# 3. Waits for emulator to be ready
# 4. Starts main portal with emulator config
# 5. Cleans up on exit (trap signals)
#
# Services:
#   - Main Portal:      http://localhost:8080
#   - FIAS Emulator UI: http://localhost:8081
#   - FIAS TCP Server:  localhost:9090
#
# Usage:
#   ./scripts/dev-with-emulator.sh
#
# Environment variables (can be set in .env):
#   PMS_AUTH_KEY  - Authentication key for FIAS (default: dev-test-key)
#   PMS_VENDOR_ID - Vendor ID for FIAS (default: wifi-portal-dev)

set -e

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Project directories
PROJECT_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EMULATOR_DIR="${PROJECT_ROOT}/tools/fias-emulator"

# Service ports
PORTAL_PORT=8080
EMULATOR_HTTP_PORT=8081
EMULATOR_TCP_PORT=9090

# FIAS configuration (defaults)
PMS_AUTH_KEY="${PMS_AUTH_KEY:-dev-test-key}"
PMS_VENDOR_ID="${PMS_VENDOR_ID:-wifi-portal-dev}"

# PIDs to track
EMULATOR_PID=""
PORTAL_PID=""

# Log function
log_info() {
    echo -e "${BLUE}[INFO]${NC} $1"
}

log_success() {
    echo -e "${GREEN}[SUCCESS]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

# Cleanup function
cleanup() {
    echo ""
    log_info "Cleaning up..."

    # Kill emulator
    if [ -n "$EMULATOR_PID" ] && kill -0 "$EMULATOR_PID" 2>/dev/null; then
        log_info "Stopping FIAS emulator (PID: $EMULATOR_PID)..."
        kill "$EMULATOR_PID" 2>/dev/null || true
        wait "$EMULATOR_PID" 2>/dev/null || true
    fi

    # Kill portal
    if [ -n "$PORTAL_PID" ] && kill -0 "$PORTAL_PID" 2>/dev/null; then
        log_info "Stopping main portal (PID: $PORTAL_PID)..."
        kill "$PORTAL_PID" 2>/dev/null || true
        wait "$PORTAL_PID" 2>/dev/null || true
    fi

    log_success "Cleanup complete"
    exit 0
}

# Trap signals for cleanup
trap cleanup SIGINT SIGTERM SIGQUIT

# Kill existing processes on our ports
kill_existing_processes() {
    log_info "Checking for existing processes on ports..."

    for port in $PORTAL_PORT $EMULATOR_HTTP_PORT $EMULATOR_TCP_PORT; do
        local pids=$(lsof -ti:$port 2>/dev/null || true)
        if [ -n "$pids" ]; then
            log_warn "Killing existing process(es) on port $port: $pids"
            echo "$pids" | xargs kill 2>/dev/null || true
            sleep 1
        fi
    done
}

# Check if a command exists
command_exists() {
    command -v "$1" >/dev/null 2>&1
}

# Wait for emulator to be ready
wait_for_emulator() {
    log_info "Waiting for FIAS emulator to be ready..."
    local max_attempts=30
    local attempt=0

    while [ $attempt -lt $max_attempts ]; do
        if curl -s "http://localhost:${EMULATOR_HTTP_PORT}/health" >/dev/null 2>&1; then
            log_success "FIAS emulator is ready!"
            return 0
        fi
        attempt=$((attempt + 1))
        sleep 1
    done

    log_error "FIAS emulator failed to start within ${max_attempts} seconds"
    return 1
}

# Main function
main() {
    echo ""
    echo "=========================================="
    echo "  Captive Portal + FIAS Emulator Dev"
    echo "=========================================="
    echo ""

    # Check prerequisites
    if ! command_exists lsof; then
        log_error "lsof is required but not installed. Install with: sudo apt install lsof"
        exit 1
    fi

    if ! command_exists curl; then
        log_error "curl is required but not installed"
        exit 1
    fi

    # Check virtual environments exist
    if [ ! -d "${PROJECT_ROOT}/.venv" ]; then
        log_error "Main project virtualenv not found at ${PROJECT_ROOT}/.venv"
        exit 1
    fi

    if [ ! -d "${EMULATOR_DIR}/.venv" ]; then
        log_error "FIAS emulator virtualenv not found at ${EMULATOR_DIR}/.venv"
        exit 1
    fi

    # Check for .env file in main project
    if [ ! -f "${PROJECT_ROOT}/.env" ]; then
        log_error "No .env file found in main project root"
        log_info "Copy .env.example to .env and configure required settings:"
        log_info "  cp ${PROJECT_ROOT}/.env.example ${PROJECT_ROOT}/.env"
        exit 1
    fi

    # Kill any existing processes
    kill_existing_processes

    # Start FIAS emulator
    log_info "Starting FIAS emulator..."
    cd "${EMULATOR_DIR}"
    source .venv/bin/activate

    # Set environment variables for emulator
    export AUTH_KEY="${PMS_AUTH_KEY}"
    export VENDOR_ID="${PMS_VENDOR_ID}"

    # Run emulator in background
    python -m uvicorn emulator.main:app --host 0.0.0.0 --port ${EMULATOR_HTTP_PORT} &
    EMULATOR_PID=$!

    log_info "FIAS emulator starting (PID: $EMULATOR_PID)"

    # Wait for emulator to be ready
    if ! wait_for_emulator; then
        cleanup
        exit 1
    fi

    # Start main portal
    log_info "Starting main captive portal..."
    cd "${PROJECT_ROOT}"
    source .venv/bin/activate

    # Set environment variables for portal to use emulator
    export PMS_TYPE=opera_fias
    export PMS_HOST=localhost
    export PMS_PORT=${EMULATOR_TCP_PORT}
    export PMS_AUTH_KEY="${PMS_AUTH_KEY}"
    export PMS_VENDOR_ID="${PMS_VENDOR_ID}"

    # Run portal
    python -m uvicorn app.main:app --host 0.0.0.0 --port ${PORTAL_PORT} --reload &
    PORTAL_PID=$!

    log_info "Main portal starting (PID: $PORTAL_PID)"

    # Wait a moment and show status
    sleep 2

    echo ""
    log_success "Both services are running!"
    echo ""
    echo "Services:"
    echo "  - Main Portal:       http://localhost:${PORTAL_PORT}"
    echo "  - FIAS Emulator UI:  http://localhost:${EMULATOR_HTTP_PORT}"
    echo "  - FIAS TCP Server:   localhost:${EMULATOR_TCP_PORT}"
    echo ""
    echo "Press Ctrl+C to stop both services"
    echo ""

    # Wait for either process to exit
    wait $PORTAL_PID $EMULATOR_PID
}

# Run main
main "$@"
