# nftables Migration Design

**Version:** 2.0.0
**Date:** 2026-03-21
**Status:** Draft

## Context

The current WiFi Captive Portal uses `iptables` for firewall/NAT and `tc` (HTB) for bandwidth shaping. This design proposes migrating to `nftables` with `flowtables` for improved performance:

- **Problem:** iptables has higher CPU overhead per packet, linear chain lookups
- **Solution:** nftables with set-based O(1) lookups + flowtables for fast-path bypass
- **Benefit:** ~20-30% CPU reduction for packet processing, better scalability

## Scope

| In Scope | Out of Scope |
|----------|--------------|
| Replace iptables with nftables | Database schema changes |
| Add flowtables for established traffic | PMS adapter changes |
| Keep tc for bandwidth shaping | Frontend changes |
| Redesign Python API | Portal routes changes |
| Single setup script | - |

## File Changes

### Files to Create

| File | Purpose |
|------|---------|
| `app/network/nftables.py` | nftables operations (sets, flowtables) |
| `scripts/setup-nftables.sh` | Combined initialization script |

### Files to Delete

| File | Reason |
|------|--------|
| `app/network/iptables.py` | Replaced by nftables.py |
| `scripts/setup-iptables.sh` | Merged into setup-nftables.sh |
| `scripts/setup-tc.sh` | Merged into setup-nftables.sh |
| `tests/test_network/test_iptables.py` | Replaced by test_nftables.py |

### Files to Modify

| File | Changes |
|------|---------|
| `app/network/session_manager.py` | Import nftables instead of iptables |
| `app/core/config.py` | Add `DNS_UPSTREAM_IP` setting |
| `.env.example` | Add `DNS_UPSTREAM_IP=8.8.8.8` |
| `tests/conftest.py` | Update patches |
| `tests/test_network/test_session_manager.py` | Update mock imports |
| `scripts/install.sh` | Replace `setup-iptables.sh` + `setup-tc.sh` with `setup-nftables.sh` |
| `scripts/uninstall.sh` | Replace iptables flush with nftables flush |
| `scripts/test.sh` | Replace iptables checks with nftables checks |
| `docs/installation-guide.md` | Update all references from iptables to nftables |
| `docs/features.md` | Update architecture diagram and technology section |
| `docs/user-manual.md` | Update emergency commands and troubleshooting |

## Architecture

### nftables Table Design

```
table inet captive_portal {
    set whitelist { type ipv4_addr; }
    set dns_bypass { type ipv4_addr; }

    flowtable f {
        hook ingress priority 0
        devices = { $WIFI_INTERFACE, $WAN_INTERFACE }
    }

    # DNAT for DNS bypass and portal redirect
    chain prerouting {
        type nat hook prerouting priority dstnat; policy accept;

        # DNS bypass for authenticated users (before portal redirect)
        ip saddr @dns_bypass udp dport 53 dnat to $DNS_UPSTREAM_IP:53
        ip saddr @dns_bypass tcp dport 53 dnat to $DNS_UPSTREAM_IP:53

        # Portal redirect for unauthenticated users (HTTP/HTTPS)
        ip saddr != @whitelist tcp dport 80 dnat to $PORTAL_IP:$PORTAL_PORT
        ip saddr != @whitelist tcp dport 443 dnat to $PORTAL_IP:$PORTAL_PORT
    }

    # SNAT/Masquerade for internet access
    chain postrouting {
        type nat hook postrouting priority srcnat; policy accept;
        oifname $WAN_INTERFACE ip saddr @whitelist masquerade
    }

    chain forward {
        type filter hook forward priority filter; policy drop;
        ct state established,related flow add @f accept
        ip saddr @whitelist accept
        reject with icmp type host-unreachable
    }
}
```

### New Config Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `DNS_UPSTREAM_IP` | DNS server for authenticated users | `8.8.8.8` |
| `PORTAL_IP` | Captive portal IP for redirects | Required |
| `PORTAL_PORT` | Captive portal port | `8080` |

### Data Flow

```
┌─────────────────────────────────────────────────────────────────────┐
│                         PACKET INGRESS                               │
└─────────────────────────────────────────────────────────────────────┘
                                │
                                ▼
                    ┌───────────────────────┐
                    │    Flowtable Lookup   │
                    │   (established conn)  │
                    └───────────────────────┘
                      │                 │
                 HIT │                 │ MISS
                      ▼                 ▼
            ┌──────────────┐   ┌───────────────────┐
            │  FAST PATH   │   │  Normal Forward   │
            │  (bypass)    │   │     Chain         │
            └──────────────┘   └───────────────────┘
                                      │
                          ┌───────────┼───────────┐
                          ▼           ▼           ▼
                    ┌──────────┐ ┌──────────┐ ┌──────────┐
                    │ @whitelist│ │  DNS     │ │  REJECT  │
                    │  ACCEPT  │ │  DNAT    │ │  (drop)  │
                    └──────────┘ └──────────┘ └──────────┘
```

### Set Operations

| Operation | nft Command |
|-----------|-------------|
| Add IP to whitelist | `nft add element inet captive_portal whitelist { 192.168.1.100 }` |
| Remove IP | `nft delete element inet captive_portal whitelist { 192.168.1.100 }` |
| Check IP | `nft get element inet captive_portal whitelist { 192.168.1.100 }` |
| List all | `nft list set inet captive_portal whitelist` |

## Python API

### nftables.py

```python
import subprocess
import json
import logging
from typing import Optional

logger = logging.getLogger(__name__)


class NftablesManager:
    """Manage nftables sets and rules for captive portal."""

    TABLE = "inet captive_portal"

    @staticmethod
    def _run(args: list[str], check: bool = True) -> Optional[str]:
        """Execute nft command."""
        result = subprocess.run(
            ["nft"] + args,
            check=check,
            capture_output=True,
            text=True
        )
        return result.stdout if result.returncode == 0 else None

    # Whitelist Operations
    @classmethod
    def add_to_whitelist(cls, ip: str) -> None:
        try:
            cls._run(["add", "element", cls.TABLE, "whitelist", f"{{ {ip} }}"])
            logger.info(f"nftables: added {ip} to whitelist")
        except subprocess.CalledProcessError as e:
            logger.error(f"nftables add failed for {ip}: {e.stderr}")
            raise

    @classmethod
    def remove_from_whitelist(cls, ip: str) -> None:
        # Use check=False to handle non-existent entries gracefully
        result = subprocess.run(
            ["nft", "delete", "element", cls.TABLE, "whitelist", f"{{ {ip} }}"],
            check=False,
            capture_output=True
        )
        if result.returncode == 0:
            logger.info(f"nftables: removed {ip} from whitelist")
        else:
            logger.warning(f"nftables remove failed for {ip} (may not exist)")

    @classmethod
    def is_whitelisted(cls, ip: str) -> bool:
        result = subprocess.run(
            ["nft", "get", "element", cls.TABLE, "whitelist", f"{{ {ip} }}"],
            check=False,
            capture_output=True
        )
        return result.returncode == 0

    # DNS Bypass Operations
    @classmethod
    def add_dns_bypass(cls, ip: str) -> None:
        try:
            cls._run(["add", "element", cls.TABLE, "dns_bypass", f"{{ {ip} }}"])
            logger.info(f"nftables: added {ip} to DNS bypass")
        except subprocess.CalledProcessError as e:
            logger.error(f"nftables dns_bypass add failed for {ip}: {e.stderr}")
            raise

    @classmethod
    def remove_dns_bypass(cls, ip: str) -> None:
        result = subprocess.run(
            ["nft", "delete", "element", cls.TABLE, "dns_bypass", f"{{ {ip} }}"],
            check=False,
            capture_output=True
        )
        if result.returncode == 0:
            logger.info(f"nftables: removed {ip} from DNS bypass")
        else:
            logger.warning(f"nftables dns_bypass remove failed for {ip} (may not exist)")

    # Session Helpers (Combined)
    @classmethod
    def create_session_rules(cls, ip: str) -> None:
        """Add to both whitelist + dns_bypass sets."""
        cls.add_to_whitelist(ip)
        cls.add_dns_bypass(ip)
        logger.info(f"nftables: created session rules for {ip}")

    @classmethod
    def remove_session_rules(cls, ip: str) -> None:
        """Remove from both sets (ignores errors if not present)."""
        cls.remove_from_whitelist(ip)
        cls.remove_dns_bypass(ip)
        logger.info(f"nftables: removed session rules for {ip}")
```

### session_manager.py Changes

```python
# Before
from app.network.iptables import add_whitelist, remove_whitelist, add_dns_bypass, remove_dns_bypass

# After
from app.network.nftables import NftablesManager as nft

# In create_session():
nft.create_session_rules(ip)

# In expire_session():
nft.remove_session_rules(ip)
```

### config.py Addition

```python
class Settings(BaseSettings):
    # ... existing ...
    DNS_UPSTREAM_IP: str = "8.8.8.8"
```

## Setup Script

### scripts/setup-nftables.sh

```bash
#!/bin/bash
# setup-nftables.sh - Initialize nftables + tc + flowtables for captive portal
# Usage: sudo ./setup-nftables.sh [OPTIONS]
#
# Options:
#   --dns-ip IP      DNS upstream IP (default: 8.8.8.8 or $DNS_UPSTREAM_IP)
#   --portal-ip IP   Captive portal IP (default: $PORTAL_IP)
#   --portal-port N  Captive portal port (default: 8080 or $PORTAL_PORT)
#   --wifi IF        WiFi interface (default: eth0 or $WIFI_INTERFACE)
#   --wan IF         WAN interface (default: eth1 or $WAN_INTERFACE)

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

echo "Setting up nftables captive portal..."
echo "  DNS upstream: $DNS_IP"
echo "  Portal: $PORTAL_IP:$PORTAL_PORT"
echo "  WiFi interface: $WIFI_IF"
echo "  WAN interface: $WAN_IF"

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

        # Portal redirect for unauthenticated users
        ip saddr != @whitelist tcp dport 80 dnat to $PORTAL_IP:$PORTAL_PORT
        ip saddr != @whitelist tcp dport 443 dnat to $PORTAL_IP:$PORTAL_PORT
    }

    chain postrouting {
        type nat hook postrouting priority srcnat; policy accept;
        oifname $WAN_IF ip saddr @whitelist masquerade
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

# WiFi ingress -> IFB (upload shaping)
tc qdisc del dev $WIFI_IF ingress 2>/dev/null || true
tc qdisc add dev $WIFI_IF handle ffff: ingress
tc filter add dev $WIFI_IF parent ffff: protocol ip u32 \
    match u32 0 0 action mirred egress redirect dev ifb0

tc qdisc del dev ifb0 root 2>/dev/null || true
tc qdisc add dev ifb0 root handle 1: htb default 999

echo "  ✓ tc HTB configured"

# ── 3. Verify ──────────────────────────────────────────────────────
echo "[3/3] Verifying..."

if nft list table inet captive_portal > /dev/null 2>&1; then
    echo "  ✓ nftables table verified"
else
    echo "  ✗ nftables table verification failed"
    exit 1
fi

echo ""
echo "=========================================="
echo "✓ nftables + flowtables + tc initialized"
echo "=========================================="
```

## Testing

### Test Files

| File | Status |
|------|--------|
| `tests/test_network/test_nftables.py` | **New** |
| `tests/test_network/test_iptables.py` | Delete |
| `tests/test_network/test_tc.py` | Keep, update imports |
| `tests/conftest.py` | Update patches |

### Test Cases for test_nftables.py

```python
class TestNftablesManager:
    def test_add_to_whitelist_calls_nft()
    def test_remove_from_whitelist_calls_nft()
    def test_is_whitelisted_returns_true_when_present()
    def test_is_whitelisted_returns_false_when_absent()
    def test_add_dns_bypass_calls_nft()
    def test_remove_dns_bypass_calls_nft()
    def test_create_session_rules_calls_both()
    def test_remove_session_rules_calls_both()
```

### conftest.py Patches

```python
# Replace iptables patches with nftables patches
@pytest.fixture(autouse=True)
def patch_network():
    with patch("app.network.nftables.NftablesManager.add_to_whitelist"), \
         patch("app.network.nftables.NftablesManager.remove_from_whitelist"), \
         patch("app.network.nftables.NftablesManager.add_dns_bypass"), \
         patch("app.network.nftables.NftablesManager.remove_dns_bypass"), \
         patch("app.network.tc.apply_bandwidth_limit"), \
         patch("app.network.tc.remove_bandwidth_limit"):
        yield
```

## Migration Guide

### Pre-migration Checklist

- [ ] Ensure kernel >= 4.16 (for flowtables)
- [ ] Ensure nftables installed (`nft --version`)
- [ ] Backup current iptables rules (`iptables-save > backup.rules`)
- [ ] Schedule maintenance window

### Migration Steps

```bash
# 0. Extract current active sessions (preserve state)
# Get list of currently whitelisted IPs from iptables
iptables -L FORWARD -n | grep ACCEPT | awk '{print $4}' | grep -E '^[0-9]' > /tmp/active_ips.txt
echo "Found $(wc -l < /tmp/active_ips.txt) active sessions to preserve"

# 1. Stop service
sudo systemctl stop captive-portal

# 2. Pull new version
git fetch origin
git checkout v2.0.0

# 3. Update .env
echo "DNS_UPSTREAM_IP=8.8.8.8" >> .env
echo "PORTAL_IP=192.168.1.1" >> .env
echo "PORTAL_PORT=8080" >> .env

# 4. Flush old iptables rules (comprehensive)
iptables -F
iptables -t nat -F
iptables -t mangle -F
iptables -X
iptables-save > /root/iptables-backup-$(date +%Y%m%d).rules

# 5. Run new setup script
sudo bash scripts/setup-nftables.sh --wifi eth0 --wan eth1

# 6. Restore active sessions to nftables
while read ip; do
    nft add element inet captive_portal whitelist { $ip }
    nft add element inet captive_portal dns_bypass { $ip }
done < /tmp/active_ips.txt
echo "Restored $(wc -l < /tmp/active_ips.txt) active sessions"

# 7. Restart service
sudo systemctl start captive-portal

# 8. Verify
nft list table inet captive_portal
nft list set inet captive_portal whitelist
```

### Rollback Plan

```bash
# If issues occur:

# 1. Checkout old version
git checkout v1.x.x

# 2. Flush nftables
nft delete table inet captive_portal

# 3. Restore iptables
sudo bash scripts/setup-iptables.sh
sudo bash scripts/setup-tc.sh

# 4. Restart
sudo systemctl restart captive-portal
```

## Performance Expectations

| Metric | Before (iptables) | After (nftables) |
|--------|-------------------|------------------|
| Lookup complexity | O(n) chain | O(1) set |
| CPU per packet | Higher | ~20-30% lower |
| Memory footprint | Higher | Lower |
| Rule updates | Non-atomic | Atomic |

## Risks & Mitigations

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| nftables not installed | Low | High | Add to installation docs |
| Kernel too old for flowtables | Medium | Medium | Fallback to nftables without flowtables |
| Set sync issues | Low | Medium | Add set verification on startup |

## Success Criteria

- [ ] All existing tests pass with new nftables mocks
- [ ] Manual testing: guest can authenticate and access internet
- [ ] Manual testing: session expiration removes IP from sets
- [ ] Manual testing: flowtables offload established connections
- [ ] Performance: CPU usage lower than iptables baseline

---

## Script Updates

### scripts/install.sh Changes

Replace iptables/tc setup with nftables:

```bash
# BEFORE (lines 390-403):
info "Setting up iptables rules..."
WIFI_IF="$WIFI_INTERFACE" PORTAL_IP="$PORTAL_IP" PORTAL_PORT="$PORTAL_PORT" \
    bash "$SCRIPT_DIR/setup-iptables.sh"

info "Setting up tc HTB traffic shaping..."
WAN_IF="$WAN_INTERFACE" \
    bash "$SCRIPT_DIR/setup-tc.sh"

# AFTER:
info "Setting up nftables + flowtables + tc..."
bash "$SCRIPT_DIR/setup-nftables.sh" \
    --wifi "$WIFI_INTERFACE" \
    --wan "$WAN_INTERFACE" \
    --portal-ip "$PORTAL_IP" \
    --portal-port "$PORTAL_PORT" \
    --dns-ip "${DNS_UPSTREAM_IP:-8.8.8.8}"
```

### scripts/uninstall.sh Changes

Replace iptables flush with nftables flush:

```bash
# BEFORE (lines 121-136):
info "Flushing iptables rules on $WIFI_IF..."
iptables -F FORWARD 2>/dev/null || true
iptables -t nat -F PREROUTING 2>/dev/null || true
iptables -P FORWARD ACCEPT 2>/dev/null || true
success "iptables rules removed."

# AFTER:
info "Flushing nftables rules..."
nft delete table inet captive_portal 2>/dev/null || true
success "nftables rules removed."
```

### scripts/test.sh Changes

Replace iptables checks with nftables checks:

```bash
# BEFORE (lines 187-196):
# iptables
if command -v iptables &>/dev/null; then
    run_check "iptables FORWARD rules present" bash -c \
        "iptables -L FORWARD -n 2>/dev/null | grep -q '$WIFI_INTERFACE'"

    run_check "iptables NAT PREROUTING redirect present" bash -c \
        "iptables -t nat -L PREROUTING -n 2>/dev/null | grep -q '$PORTAL_PORT'"
else
    warn_result "iptables not available — skipping firewall checks"
fi

# AFTER:
# nftables
if command -v nft &>/dev/null; then
    run_check "nftables table exists" bash -c \
        "nft list table inet captive_portal 2>/dev/null | grep -q 'whitelist'"

    run_check "nftables flowtable configured" bash -c \
        "nft list table inet captive_portal 2>/dev/null | grep -q 'flowtable'"
else
    fail "nftables not available — required for v2.0"
fi
```

---

## Documentation Updates

### docs/installation-guide.md Changes

| Section | Change |
|---------|--------|
| **Software Requirements** | Replace `iptables` with `nftables (4.16+ kernel)` |
| **Manual Step 9** | Replace `setup-iptables.sh` + `setup-tc.sh` with `setup-nftables.sh` |
| **systemd Service** | Update `ExecStartPre` to use single `setup-nftables.sh` |
| **Verify iptables rules** | Replace with "Verify nftables rules" section |
| **Troubleshooting: iptables** | Replace with "Troubleshooting: nftables" section |
| **Reset network rules** | Replace commands with nftables equivalents |

#### Updated Software Requirements Table

```markdown
### Software
| Package | เวอร์ชันขั้นต่ำ |
|---------|--------------|
| Ubuntu | 22.04 LTS |
| Python | 3.12+ |
| PostgreSQL | 12+ |
| Redis | 6+ |
| nftables | 0.9.3+ (kernel 4.16+) |
| iproute2 (tc) | (pre-installed) |
| dnsmasq | 2.x |
```

#### Updated Step 9 (Manual Installation)

```bash
# nftables + flowtables + tc (ต้องรัน root)
sudo bash scripts/setup-nftables.sh \
    --wifi wlan0 \
    --wan eth0 \
    --portal-ip 192.168.1.1 \
    --portal-port 8080 \
    --dns-ip 8.8.8.8
```

#### Updated Verify Commands

```bash
# ดู nftables table
sudo nft list table inet captive_portal

# ดู whitelist set
sudo nft list set inet captive_portal whitelist

# ดู tc rules (unchanged)
sudo tc qdisc show dev eth0
sudo tc class show dev eth0
```

#### Updated Troubleshooting Section

```bash
### nftables ไม่ทำงาน

# ตรวจว่า nftables ติดตั้ง
nft --version

# ตรวจ kernel version (ต้อง >= 4.16 สำหรับ flowtables)
uname -r

# ตรวจว่า table มีอยู่
nft list tables

# รัน setup-nftables.sh ใหม่
sudo bash scripts/setup-nftables.sh --wifi wlan0 --wan eth0
```

### docs/features.md Changes

| Section | Change |
|---------|--------|
| **Architecture Diagram** | Replace `iptables/tc Gateway` with `nftables/tc Gateway` |
| **เทคโนโลยีที่ใช้** | Replace `iptables + tc` with `nftables + flowtables + tc` |
| **Network Security** | Update iptables DROP to nftables reference |
| **DNS Bypass** | Update iptables DNAT to nftables reference |

#### Updated Technology Table

```markdown
| ส่วนประกอบ | เทคโนโลยี |
|-----------|-----------|
| Web Framework | FastAPI (Python 3.12) |
| Database | PostgreSQL 14+ (asyncpg) |
| Cache / Rate Limit / Token Blocklist | Redis |
| ORM | SQLAlchemy 2.0 (Async) |
| Migration | Alembic |
| Network Control | nftables + flowtables + tc (iproute2) |
| DHCP + DNS | dnsmasq |
```

### docs/user-manual.md Changes

| Section | Change |
|---------|--------|
| **2.3 Kick Session** | Update iptables reference to nftables |
| **4.4 คำสั่งฉุกเฉิน** | Replace iptables commands with nftables equivalents |

#### Updated Emergency Commands

```bash
# ปิด WiFi ทุกคน (emergency)
sudo nft delete table inet captive_portal
sudo iptables -P FORWARD DROP

# เปิด WiFi ทุกคน (ไม่มี auth - ใช้เฉพาะกรณีฉุกเฉิน)
sudo nft delete table inet captive_portal
sudo iptables -P FORWARD ACCEPT

# Reset กลับเป็นปกติ
sudo bash /opt/captive-portal/scripts/setup-nftables.sh

# ดู whitelist ปัจจุบัน
sudo nft list set inet captive_portal whitelist
```

---

## systemd Service Update

### /etc/systemd/system/captive-portal.service

```bash
# BEFORE:
ExecStartPre=$SCRIPT_DIR/setup-iptables.sh
ExecStartPre=$SCRIPT_DIR/setup-tc.sh

# AFTER:
ExecStartPre=$SCRIPT_DIR/setup-nftables.sh
```

Full updated service file:

```ini
[Unit]
Description=WiFi Captive Portal
Documentation=https://github.com/your-org/wifi-captive-portal
After=network.target postgresql.service redis-server.service
Requires=postgresql.service redis-server.service

[Service]
Type=simple
User=root
Group=root
WorkingDirectory=/opt/captive-portal
EnvironmentFile=/opt/captive-portal/.env
ExecStartPre=/opt/captive-portal/scripts/setup-nftables.sh
ExecStart=/opt/captive-portal/.venv/bin/uvicorn app.main:app --host 0.0.0.0 --port 8080 --workers 1
ExecReload=/bin/kill -HUP $MAINPID
Restart=on-failure
RestartSec=5
StandardOutput=journal
StandardError=journal
SyslogIdentifier=captive-portal

[Install]
WantedBy=multi-user.target
```
