# Captive Portal Detection Fix — Design Spec
Date: 2026-03-24

## Problem
When clients connect to WiFi, the OS/browser captive portal detection does not reliably trigger the login popup, so guests must manually navigate to the portal.

## Root Causes
1. **DNS interception missing for unauthenticated clients** — unauthenticated clients using hardcoded DNS (e.g. 8.8.8.8, 1.1.1.1) have their DNS queries silently dropped by the forward chain instead of being redirected to local dnsmasq. Result: DNS resolves correctly to external servers, devices assume internet is available, no captive portal popup.
2. **Firefox probe endpoints missing** — Firefox 89+ checks `detectportal.firefox.com/canonical.html`; older Firefox checks `/success.txt`. Neither path is in the current router, so the catch-all handles them, but the canonical Firefox detection path is not explicitly handled.

## Changes

### 1. `scripts/setup-nftables.sh`
Add two nftables rules in the `prerouting` chain (after the existing dns_bypass rules) to redirect all DNS queries from unauthenticated clients to local dnsmasq:

```nft
ip saddr != @dns_bypass udp dport 53 dnat to $PORTAL_IP:53
ip saddr != @dns_bypass tcp dport 53 dnat to $PORTAL_IP:53
```

This ensures clients with hardcoded DNS (8.8.8.8, 1.1.1.1, etc.) have their DNS intercepted and resolved by dnsmasq in redirect mode, returning the portal IP for all domains.

### 2. `app/portal/router.py`
Add explicit routes for Firefox and additional Chrome probe paths:
- `GET /canonical.html` — Firefox 89+
- `GET /success.txt` — Firefox legacy
- `GET /gen_204` — Chrome alternative

All return 302 redirect to the portal login page (same as existing probes).

## Deployment
- rsync modified files to `anirut@192.168.1.117:/home/anirut/WiFi_Captive_Portal/`
- Re-run nftables setup: `sudo /home/anirut/WiFi_Captive_Portal/scripts/setup-nftables.sh` (via systemd ExecStartPre on restart)
- `sudo systemctl restart captive-portal`

## Devices Covered After Fix
| OS/Browser | Probe URL | Status |
|---|---|---|
| Android / Chrome | `/generate_204` | ✓ (existing) |
| Android / Chrome alt | `/gen_204` | ✓ (new) |
| iOS / macOS | `/hotspot-detect.html` | ✓ (existing) |
| iOS legacy | `/library/test/success.html` | ✓ (existing) |
| Windows NCSI | `/connecttest.txt`, `/ncsi.txt` | ✓ (existing) |
| Windows redirect | `/redirect` | ✓ (existing) |
| Firefox 89+ | `/canonical.html` | ✓ (new) |
| Firefox legacy | `/success.txt` | ✓ (new) |
| Any other | catch-all `/{path}` | ✓ (existing) |
| Hardcoded DNS clients | DNS interception | ✓ (new) |
