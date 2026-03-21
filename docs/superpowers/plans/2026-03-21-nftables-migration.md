# nftables Migration Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate from iptables to nftables with flowtables for improved performance (20-30% CPU reduction, O(1) lookup).

**Architecture:** Replace iptables.py with nftables.py using set-based whitelist/dns_bypass. Keep tc for bandwidth shaping. Single setup-nftables.sh script for initialization.

**Tech Stack:** nftables (0.9.3+, kernel 4.16+), Python 3.12, tc (iproute2)

---

## File Structure

### New Files
| File | Purpose |
|------|---------|
| `app/network/nftables.py` | nftables set operations |
| `scripts/setup-nftables.sh` | Combined nftables + tc + flowtables setup |
| `tests/test_network/test_nftables.py` | Unit tests for nftables |

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
| `tests/conftest.py` | Update patches |
| `scripts/install.sh` | Use setup-nftables.sh |
| `scripts/uninstall.sh` | Use nftables flush |
| `scripts/test.sh` | Use nftables checks |
| `docs/installation-guide.md` | Update all iptables references |
| `docs/features.md` | Update technology table |
| `docs/user-manual.md` | Update emergency commands |

---

## Task 1: Create nftables.py

**Files:**
- Create: `app/network/nftables.py`

- [ ] **Step 1: Write nftables.py**

```python
"""
nftables.py - nftables set operations for captive portal.

Replaces iptables.py with set-based O(1) lookups and flowtable support.
"""
import subprocess
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

    # ── Whitelist Operations ─────────────────────────────────────────

    @classmethod
    def add_to_whitelist(cls, ip: str) -> None:
        """Add IP to whitelist set."""
        try:
            cls._run(["add", "element", cls.TABLE, "whitelist", f"{{ {ip} }}"])
            logger.info(f"nftables: added {ip} to whitelist")
        except subprocess.CalledProcessError as e:
            logger.error(f"nftables add failed for {ip}: {e.stderr}")
            raise

    @classmethod
    def remove_from_whitelist(cls, ip: str) -> None:
        """Remove IP from whitelist set (ignores errors if not present)."""
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
        """Check if IP is in whitelist set."""
        result = subprocess.run(
            ["nft", "get", "element", cls.TABLE, "whitelist", f"{{ {ip} }}"],
            check=False,
            capture_output=True
        )
        return result.returncode == 0

    # ── DNS Bypass Operations ──────────────────────────────────────

    @classmethod
    def add_dns_bypass(cls, ip: str) -> None:
        """Add IP to dns_bypass set."""
        try:
            cls._run(["add", "element", cls.TABLE, "dns_bypass", f"{{ {ip} }}"])
            logger.info(f"nftables: added {ip} to DNS bypass")
        except subprocess.CalledProcessError as e:
            logger.error(f"nftables dns_bypass add failed for {ip}: {e.stderr}")
            raise

    @classmethod
    def remove_dns_bypass(cls, ip: str) -> None:
        """Remove IP from dns_bypass set (ignores errors if not present)."""
        result = subprocess.run(
            ["nft", "delete", "element", cls.TABLE, "dns_bypass", f"{{ {ip} }}"],
            check=False,
            capture_output=True
        )
        if result.returncode == 0:
            logger.info(f"nftables: removed {ip} from DNS bypass")
        else:
            logger.warning(f"nftables dns_bypass remove failed for {ip} (may not exist)")

    # ── Session Helpers (Combined) ─────────────────────────────────

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

- [ ] **Step 2: Commit**

```bash
git add app/network/nftables.py
git commit -m "feat: add nftables.py - set-based whitelist with O(1) lookup"
```

---

## Task 2: Create test_nftables.py

**Files:**
- Create: `tests/test_network/test_nftables.py`

- [ ] **Step 1: Write the failing tests**

```python
"""
Tests for nftables.py module.
"""
import pytest
from unittest.mock import patch, MagicMock


class TestNftablesManager:
    """Test NftablesManager class."""

    @patch("app.network.nftables.subprocess.run")
    def test_add_to_whitelist_calls_nft(self, mock_run):
        """Test add_to_whitelist calls nft with correct args."""
        from app.network.nftables import NftablesManager

        NftablesManager.add_to_whitelist("192.168.1.100")

        mock_run.assert_called_once()
        cmd = mock_run.call_args[0][0]
        assert "nft" in cmd
        assert "add" in cmd
        assert "whitelist" in cmd
        assert "192.168.1.100" in cmd

    @patch("app.network.nftables.subprocess.run")
    def test_remove_from_whitelist_uses_check_false(self, mock_run):
        """Test remove_from_whitelist uses check=False for graceful handling."""
        from app.network.nftables import NftablesManager

        NftablesManager.remove_from_whitelist("192.168.1.100")

        # Should not raise even if element doesn't exist
        mock_run.assert_called()
        call_kwargs = mock_run.call_args[1]
        assert call_kwargs.get("check") is False

    @patch("app.network.nftables.subprocess.run")
    def test_is_whitelisted_returns_true_when_present(self, mock_run):
        """Test is_whitelisted returns True when IP is in set."""
        from app.network.nftables import NftablesManager

        mock_run.return_value = MagicMock(returncode=0)

        result = NftablesManager.is_whitelisted("192.168.1.100")

        assert result is True

    @patch("app.network.nftables.subprocess.run")
    def test_is_whitelisted_returns_false_when_absent(self, mock_run):
        """Test is_whitelisted returns False when IP is not in set."""
        from app.network.nftables import NftablesManager

        mock_run.return_value = MagicMock(returncode=1)

        result = NftablesManager.is_whitelisted("192.168.1.100")

        assert result is False

    @patch("app.network.nftables.subprocess.run")
    def test_add_dns_bypass_calls_nft(self, mock_run):
        """Test add_dns_bypass calls nft with correct args."""
        from app.network.nftables import NftablesManager

        NftablesManager.add_dns_bypass("192.168.1.100")

        cmd = " ".join(mock_run.call_args[0][0])
        assert "dns_bypass" in cmd

    @patch("app.network.nftables.subprocess.run")
    def test_create_session_rules_calls_both(self, mock_run):
        """Test create_session_rules adds to both sets."""
        from app.network.nftables import NftablesManager

        NftablesManager.create_session_rules("192.168.1.100")

        # Should call nft twice (whitelist + dns_bypass)
        assert mock_run.call_count == 2

    @patch("app.network.nftables.subprocess.run")
    def test_remove_session_rules_calls_both(self, mock_run):
        """Test remove_session_rules removes from both sets."""
        from app.network.nftables import NftablesManager

        NftablesManager.remove_session_rules("192.168.1.100")

        # Should call nft twice
        assert mock_run.call_count == 2

    @patch("app.network.nftables.subprocess.run")
    def test_add_to_whitelist_raises_on_error(self, mock_run):
        """Test add_to_whitelist raises on subprocess error."""
        from app.network.nftables import NftablesManager
        import subprocess

        mock_run.side_effect = subprocess.CalledProcessError(1, "nft", stderr="error")

        with pytest.raises(subprocess.CalledProcessError):
            NftablesManager.add_to_whitelist("192.168.1.100")
```

- [ ] **Step 2: Run tests to verify they fail**

```bash
pytest tests/test_network/test_nftables.py -v
```
Expected: FAIL (module not found)

- [ ] **Step 3: Commit**

```bash
git add tests/test_network/test_nftables.py
git commit -m "test: add nftables.py unit tests"
```

---

## Task 3: Update session_manager.py

**Files:**
- Modify: `app/network/session_manager.py:7-8,40-42,47-49`

- [ ] **Step 1: Update imports (lines 7-8)**

```python
# BEFORE:
from app.network.iptables import add_whitelist, remove_whitelist, add_dns_bypass, remove_dns_bypass

# AFTER:
from app.network.nftables import NftablesManager as nft
```

- [ ] **Step 2: Update create_session (line 40-42)**

```python
# BEFORE:
add_whitelist(ip)
add_dns_bypass(ip)

# AFTER:
nft.create_session_rules(ip)
```

- [ ] **Step 3: Update expire_session (lines 47-49)**

```python
# BEFORE:
remove_whitelist(session.ip_address)
remove_dns_bypass(session.ip_address)

# AFTER:
nft.remove_session_rules(session.ip_address)
```

- [ ] **Step 4: Run tests**

```bash
pytest tests/test_network/test_session_manager.py -v
```

- [ ] **Step 5: Commit**

```bash
git add app/network/session_manager.py
git commit -m "refactor: session_manager uses nftables instead of iptables"
```

---

## Task 4: Update config.py and .env.example

**Files:**
- Modify: `app/core/config.py`
- Modify: `.env.example`

- [ ] **Step 1: Add DNS_UPSTREAM_IP setting to config.py**

Add to the Settings class:

```python
class Settings(BaseSettings):
    # ... existing settings ...

    # DNS upstream for authenticated guests
    DNS_UPSTREAM_IP: str = "8.8.8.8"
```

- [ ] **Step 2: Update .env.example**

Add DNS_UPSTREAM_IP to .env.example:

```bash
echo "DNS_UPSTREAM_IP=8.8.8.8  # DNS server for authenticated guests" >> .env.example
```

- [ ] **Step 3: Run tests**

```bash
pytest tests/test_core/test_config.py -v
```

- [ ] **Step 4: Commit**

```bash
git add app/core/config.py .env.example
git commit -m "feat: add DNS_UPSTREAM_IP config setting"
```

---

## Task 5: Create setup-nftables.sh

**Files:**
- Create: `scripts/setup-nftables.sh`

- [ ] **Step 1: Write setup-nftables.sh**

```bash
#!/bin/bash
# =============================================================================
# setup-nftables.sh - Initialize nftables + tc + flowtables for captive portal
# Usage: sudo ./setup-nftables.sh [OPTIONS]
#
# Options:
#   --dns-ip IP      DNS upstream IP (default: 8.8.8.8 or $DNS_UPSTREAM_IP)
#   --portal-ip IP   Captive portal IP (default: $PORTAL_IP)
#   --portal-port N  Captive portal port (default: 8080 or $PORTAL_PORT)
#   --wifi IF        WiFi interface (default: eth0 or $WIFI_INTERFACE)
#   --wan IF         WAN interface (default: eth1 or $WAN_INTERFACE)
# =============================================================================
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

- [ ] **Step 2: Make executable**

```bash
chmod +x scripts/setup-nftables.sh
```

- [ ] **Step 3: Commit**

```bash
git add scripts/setup-nftables.sh
git commit -m "feat: add setup-nftables.sh - combined nftables + tc + flowtables"
```

---

## Task 6: Update install.sh

**Files:**
- Modify: `scripts/install.sh:386-404`

- [ ] **Step 1: Replace iptables/tc setup section (lines 386-404)**

Replace the entire network rules section:

```bash
# BEFORE (lines 386-404):
# =============================================================================
# SECTION 8: Network Rules (iptables + tc)
# =============================================================================
step "CONFIGURING NETWORK RULES"

info "Setting up iptables rules..."
WIFI_IF="$WIFI_INTERFACE" PORTAL_IP="$PORTAL_IP" PORTAL_PORT="$PORTAL_PORT" \
    bash "$SCRIPT_DIR/setup-iptables.sh"

info "Setting up tc HTB traffic shaping..."
WAN_IF="$WAN_INTERFACE" \
    bash "$SCRIPT_DIR/setup-tc.sh"

info "Setting up dnsmasq DHCP+DNS..."
bash "$SCRIPT_DIR/setup-dnsmasq.sh"

# Persist iptables rules across reboots
info "Persisting iptables rules..."
netfilter-persistent save 2>/dev/null || iptables-save > /etc/iptables/rules.v4

success "Network rules configured."

# AFTER:
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
```

- [ ] **Step 2: Update systemd service ExecStartPre (lines ~427-428)**

```bash
# BEFORE:
ExecStartPre=$SCRIPT_DIR/setup-iptables.sh
ExecStartPre=$SCRIPT_DIR/setup-tc.sh

# AFTER:
ExecStartPre=$SCRIPT_DIR/setup-nftables.sh
```

- [ ] **Step 3: Commit**

```bash
git add scripts/install.sh
git commit -m "refactor: install.sh uses setup-nftables.sh"
```

---

## Task 7: Update uninstall.sh

**Files:**
- Modify: `scripts/uninstall.sh:121-136`

- [ ] **Step 1: Replace iptables flush with nftables flush (lines 121-136)**

```bash
# BEFORE:
info "Flushing iptables rules on $WIFI_IF..."
iptables -F FORWARD 2>/dev/null || true
iptables -t nat -F PREROUTING 2>/dev/null || true
iptables -P FORWARD ACCEPT 2>/dev/null || true
success "iptables rules removed."

# AFTER:
info "Flushing nftables rules..."
nft delete table inet captive_portal 2>/dev/null || true
iptables -P FORWARD ACCEPT 2>/dev/null || true
success "nftables rules removed."
```

- [ ] **Step 2: Update question text (line 66)**

```bash
# BEFORE:
ask "Remove iptables and tc network rules? [Y/n]:"

# AFTER:
ask "Remove nftables and tc network rules? [Y/n]:"
```

- [ ] **Step 3: Commit**

```bash
git add scripts/uninstall.sh
git commit -m "refactor: uninstall.sh uses nftables flush"
```

---

## Task 8: Update test.sh

**Files:**
- Modify: `scripts/test.sh:187-204`

- [ ] **Step 1: Replace iptables checks with nftables checks (lines 187-204)**

```bash
# BEFORE:
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

- [ ] **Step 2: Commit**

```bash
git add scripts/test.sh
git commit -m "refactor: test.sh uses nftables checks"
```

---

## Task 9: Update conftest.py

**Files:**
- Modify: `tests/conftest.py`

- [ ] **Step 1: Replace iptables patches with nftables patches**

Find the existing iptables patches and replace:

```python
# BEFORE:
with patch("app.network.iptables.add_whitelist"), \
     patch("app.network.iptables.remove_whitelist"), \
     patch("app.network.iptables.add_dns_bypass"), \
     patch("app.network.iptables.remove_dns_bypass"):

# AFTER:
with patch("app.network.nftables.NftablesManager.add_to_whitelist"), \
     patch("app.network.nftables.NftablesManager.remove_from_whitelist"), \
     patch("app.network.nftables.NftablesManager.add_dns_bypass"), \
     patch("app.network.nftables.NftablesManager.remove_dns_bypass"):
```

- [ ] **Step 2: Run all tests**

```bash
pytest tests/ -v
```

- [ ] **Step 3: Commit**

```bash
git add tests/conftest.py
git commit -m "refactor: conftest.py patches nftables instead of iptables"
```

---

## Task 9b: Update test_session_manager.py

**Files:**
- Modify: `tests/test_network/test_session_manager.py`

- [ ] **Step 1: Update patch imports in test_create_session_adds_whitelist (lines 18-21)**

```python
# BEFORE:
with patch("app.network.session_manager.add_whitelist") as mock_ipt, \
     patch("app.network.session_manager.add_dns_bypass"), \
     patch("app.network.session_manager.apply_bandwidth_limit") as mock_tc, \
     patch("app.network.session_manager.get_mac_for_ip", return_value="aa:bb:cc:dd:ee:ff"):

# AFTER:
with patch("app.network.session_manager.nft.create_session_rules") as mock_nft, \
     patch("app.network.session_manager.apply_bandwidth_limit") as mock_tc, \
     patch("app.network.session_manager.get_mac_for_ip", return_value="aa:bb:cc:dd:ee:ff"):
```

- [ ] **Step 2: Update assertion (line 31)**

```python
# BEFORE:
mock_ipt.assert_called_once_with("192.168.1.45")

# AFTER:
mock_nft.assert_called_once_with("192.168.1.45")
```

- [ ] **Step 3: Update patch imports in test_expire_session_removes_whitelist (lines 42-44)**

```python
# BEFORE:
with patch("app.network.session_manager.remove_whitelist") as mock_ipt, \
     patch("app.network.session_manager.remove_dns_bypass"), \
     patch("app.network.session_manager.remove_bandwidth_limit") as mock_tc:

# AFTER:
with patch("app.network.session_manager.nft.remove_session_rules") as mock_nft, \
     patch("app.network.session_manager.remove_bandwidth_limit") as mock_tc:
```

- [ ] **Step 4: Update assertion (line 46)**

```python
# BEFORE:
mock_ipt.assert_called_once_with("192.168.1.45")

# AFTER:
mock_nft.assert_called_once_with("192.168.1.45")
```

- [ ] **Step 5: Update patch imports in test_expire_overdue_sessions_returns_count (lines 67-69)**

```python
# BEFORE:
with patch("app.network.session_manager.remove_whitelist"), \
     patch("app.network.session_manager.remove_dns_bypass"), \
     patch("app.network.session_manager.remove_bandwidth_limit"):

# AFTER:
with patch("app.network.session_manager.nft.remove_session_rules"), \
     patch("app.network.session_manager.remove_bandwidth_limit"):
```

- [ ] **Step 6: Update patch imports in test_expire_sessions_for_room_expires_active_sessions (lines 90-92)**

```python
# BEFORE:
with patch("app.network.session_manager.remove_whitelist") as mock_ipt, \
     patch("app.network.session_manager.remove_dns_bypass"), \
     patch("app.network.session_manager.remove_bandwidth_limit") as mock_tc:

# AFTER:
with patch("app.network.session_manager.nft.remove_session_rules") as mock_nft, \
     patch("app.network.session_manager.remove_bandwidth_limit") as mock_tc:
```

- [ ] **Step 7: Update assertions (lines 96-97)**

```python
# BEFORE:
assert mock_ipt.call_count == 2
assert mock_tc.call_count == 2

# AFTER:
assert mock_nft.call_count == 2
assert mock_tc.call_count == 2
```

- [ ] **Step 8: Run tests**

```bash
pytest tests/test_network/test_session_manager.py -v
```

- [ ] **Step 9: Commit**

```bash
git add tests/test_network/test_session_manager.py
git commit -m "refactor: test_session_manager.py patches nftables"
```

---

## Task 10: Delete iptables files

**Files:**
- Delete: `app/network/iptables.py`
- Delete: `scripts/setup-iptables.sh`
- Delete: `scripts/setup-tc.sh`
- Delete: `tests/test_network/test_iptables.py`

- [ ] **Step 1: Delete files**

```bash
rm app/network/iptables.py
rm scripts/setup-iptables.sh
rm scripts/setup-tc.sh
rm tests/test_network/test_iptables.py
```

- [ ] **Step 2: Run tests to verify nothing is broken**

```bash
pytest tests/ -v
```

- [ ] **Step 3: Commit**

```bash
git add -A
git commit -m "refactor: remove iptables.py, setup-iptables.sh, setup-tc.sh, test_iptables.py"
```

---

## Task 11: Update documentation

**Files:**
- Modify: `docs/installation-guide.md`
- Modify: `docs/features.md`
- Modify: `docs/user-manual.md`

### Sub-task 11a: Update installation-guide.md

- [ ] **Step 1: Update Software Requirements table**

Replace `iptables` with `nftables`:

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

- [ ] **Step 2: Update Step 9 (Network Rules)**

Replace iptables/tc commands with nftables:

```bash
### ขั้นตอนที่ 9: ตั้งค่า Network Rules

```bash
# nftables + flowtables + tc (ต้องรัน root)
sudo bash scripts/setup-nftables.sh \
    --wifi wlan0 \
    --wan eth0 \
    --portal-ip 192.168.1.1 \
    --portal-port 8080 \
    --dns-ip 8.8.8.8
```
```

- [ ] **Step 3: Update systemd Service example**

Replace ExecStartPre lines:

```ini
ExecStartPre=/opt/captive-portal/scripts/setup-nftables.sh
```

- [ ] **Step 4: Update Verify section**

```bash
### ตรวจสอบ nftables rules

```bash
# ดู nftables table
sudo nft list table inet captive_portal

# ดู whitelist set
sudo nft list set inet captive_portal whitelist
```
```

- [ ] **Step 5: Update Troubleshooting section**

Replace "iptables ไม่ทำงาน" with "nftables ไม่ทำงาน":

```bash
### nftables ไม่ทำงาน

# ตรวจว่า nftables ติดตั้ง
nft --version

# ตรวจ kernel version (ต้อง >= 4.16 สำหรับ flowtables)
uname -r

# ตรวจว่า table มีอยู่
nft list tables

# รัน setup-nftables.sh ใหม่
sudo WIFI_IF=wlan0 PORTAL_IP=192.168.1.1 PORTAL_PORT=8080 bash scripts/setup-nftables.sh
```
```

- [ ] **Step 6: Update Reset network rules section**

```bash
# Reset network rules
sudo bash /opt/captive-portal/scripts/setup-nftables.sh
```

- [ ] **Step 7: Commit**

```bash
git add docs/installation-guide.md
git commit -m "docs: update installation-guide.md for nftables"
```

### Sub-task 11b: Update features.md

- [ ] **Step 1: Update architecture diagram text**

Replace `iptables/tc Gateway` with `nftables/tc Gateway` in the ASCII diagram.

- [ ] **Step 2: Update technology table**

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

- [ ] **Step 3: Update Network Security section**

Change iptables DROP to nftables reference.

- [ ] **Step 4: Update DNS Bypass section**

Change iptables DNAT to nftables reference.

- [ ] **Step 5: Commit**

```bash
git add docs/features.md
git commit -m "docs: update features.md for nftables"
```

### Sub-task 11c: Update user-manual.md

- [ ] **Step 1: Update Kick Session section (2.3)**

Change iptables whitelist to nftables:

```markdown
ระบบจะ:
   - ลบ nftables whitelist entry
   - ลบ tc bandwidth limit
   - ลบ DNS bypass rule
   - อัปเดต status เป็น `kicked`
```

- [ ] **Step 2: Update emergency commands (4.4)**

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

- [ ] **Step 3: Commit**

```bash
git add docs/user-manual.md
git commit -m "docs: update user-manual.md for nftables"
```

---

## Task 12: Final verification

- [ ] **Step 1: Run all tests**

```bash
pytest tests/ -v
```

- [ ] **Step 2: Verify imports**

```bash
grep -r "iptables" app/ --include="*.py" || echo "No iptables imports found - GOOD"
grep -r "nftables" app/ --include="*.py" | head -5
```

- [ ] **Step 3: Verify scripts**

```bash
ls -la scripts/
```

Expected: setup-nftables.sh exists, setup-iptables.sh does not

- [ ] **Step 4: Create version bump commit**

```bash
# Update version in any version file if it exists
# Then create final commit
git add -A
git commit -m "release: v2.0.0 - nftables migration

BREAKING CHANGE: Migrate from iptables to nftables

- Replace iptables with nftables for firewall/NAT
- Add flowtables for established connection fast-path
- Keep tc for bandwidth shaping
- Single setup-nftables.sh script
- Configurable DNS_UPSTREAM_IP

Performance improvements:
- O(1) set lookups vs O(n) chain lookups
- ~20-30% CPU reduction for packet processing
- Atomic rule updates

Migration: See docs/superpowers/specs/2026-03-21-nftables-migration-design.md"
```

---

## Verification Checklist

- [ ] All tests pass: `pytest tests/ -v`
- [ ] No iptables imports in app/: `grep -r "iptables" app/`
- [ ] setup-nftables.sh exists and is executable
- [ ] setup-iptables.sh and setup-tc.sh are deleted
- [ ] Documentation updated
- [ ] Version bumped to 2.0.0
