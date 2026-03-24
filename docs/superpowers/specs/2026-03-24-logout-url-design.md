# Logout URL Feature Design

**Date:** 2026-03-24
**Status:** Implemented

## Problem

Users who close the browser after logging into the WiFi portal have no easy way to disconnect their session later. They don't know where to find the logout page.

## Solution

Allow users to type `http://logout.wifi` (primary) or `http://logout` (fallback) in their browser to access a dedicated disconnect page.

> **Note:** `logout.wifi` is the primary URL because macOS, iOS, and Chrome require at least one dot in a hostname to treat it as a DNS name rather than a search query. `logout` (no dot) works on Linux/Android but not reliably on Apple devices.

## Implementation

### 1. DNS Configuration (Automatic — via dnsmasq)

`app/network/dnsmasq.py` `write_config()` automatically adds to `/etc/dnsmasq.d/captive-portal.conf`:

```
address=/logout.wifi/<gateway_ip>
address=/logout/<gateway_ip>
```

Both resolve to the portal/gateway IP regardless of `dns_mode` (redirect or forward).

#### DHCP Search Domain

`write_config()` also sets DHCP options so clients automatically try `logout.wifi` when resolving bare `logout`:

```
dhcp-option=option:domain-name,wifi
dhcp-option=option:domain-search,wifi
```

With this, typing `http://logout` on macOS/curl resolves via the search domain to `logout.wifi` → portal IP.

#### Auth DNS (dnsmasq-auth service — port 5354)

Authenticated (whitelisted) clients have their DNS redirected to a **second dnsmasq instance** on port 5354 (`/etc/dnsmasq-auth.conf`) instead of going directly to 8.8.8.8. This second instance:
- Answers `logout` and `logout.wifi` → portal IP
- Forwards all other domains to upstream (8.8.8.8, 8.8.4.4) — no catch-all

This allows authenticated clients to still resolve the logout shortcut even though they bypass the main dnsmasq catch-all.

#### DoH Blocking (for macOS/Chrome)

nftables blocks port 443 to well-known DoH providers (Google 8.8.8.8, Cloudflare 1.1.1.1, Quad9 9.9.9.9, OpenDNS) for authenticated clients. This forces DoH to fail and fall back to plain DNS port 53, which is intercepted and forwarded to the auth dnsmasq on port 5354.

```nft
ip saddr @dns_bypass ip daddr @doh_servers tcp dport 443 reject with icmp admin-prohibited
```

### 2. Portal Route Logic Change

**File:** `app/portal/router.py`

Modify `GET /` to check for active session:

```python
@router.get("/", response_class=HTMLResponse)
async def portal_login(request: Request, db: AsyncSession = Depends(get_db)):
    # Check if client already has an active session
    from app.network.arp import get_mac_for_ip
    from app.core.models import Session, SessionStatus
    from sqlalchemy import cast, String

    mac = get_mac_for_ip(request.client.host)
    if mac:
        result = await db.execute(
            sa_select(Session).where(
                cast(Session.mac_address, String) == mac,
                Session.status == SessionStatus.active
            )
        )
        active_session = result.scalar_one_or_none()
        if active_session:
            return templates.TemplateResponse(
                request, "disconnect.html",
                {"expires_at": active_session.expires_at}
            )

    return templates.TemplateResponse(request, "login.html")
```

### 3. New Template: disconnect.html

**File:** `app/portal/templates/disconnect.html`

Create a new dedicated disconnect page with:

- Header: "Connected" with checkmark icon
- Session info: expiry time
- Large, prominent "Disconnect" button (easy to tap on mobile)
- Secondary link to continue browsing

**Visual Design:**
- Reuse existing portal.css styles for consistency
- Button should be large (min 48px height for touch targets)
- Use the same color scheme as success.html

**Wireframe:**
```
┌─────────────────────────────────┐
│                                 │
│         ✓ Connected             │
│                                 │
│    You're online at Hotel X     │
│                                 │
│    Session expires: 14:30       │
│                                 │
│   ┌─────────────────────────┐   │
│   │      DISCONNECT         │   │
│   └─────────────────────────┘   │
│                                 │
│    Continue browsing            │
│                                 │
└─────────────────────────────────┘
```

### 4. nftables Rules for Portal IP Access

Added to `scripts/setup-nftables.sh` so all clients (authenticated or not) can reach the portal on port 80/443:

```nft
# prerouting chain
ip daddr $PORTAL_IP tcp dport 80  dnat to $PORTAL_IP:$PORTAL_PORT
ip daddr $PORTAL_IP tcp dport 443 dnat to $PORTAL_IP:8443
```

Without these rules, authenticated (whitelisted) clients bypass the normal DNAT, so `http://logout.wifi` would connect to portal_ip:80 but nothing listens there.

### 5. User Flow

**Unauthenticated client:**
1. Types `http://logout.wifi`
2. DNS (dnsmasq, catch-all mode) → portal IP
3. HTTP port 80 → DNAT → portal port 8080
4. No active session found → shows `login.html`

**Authenticated client:**
1. Types `http://logout.wifi`
2. DNS (dnsmasq-auth, port 5354) → portal IP
3. HTTP port 80 → DNAT to portal port 8080 (new rule above)
4. Active session found by MAC → shows `disconnect.html`
5. Clicks Disconnect → `POST /session/disconnect`
6. Session expired → redirected to `/` → shows `login.html`

### Known Limitations

| Device | `http://logout.wifi` | `http://logout` |
|--------|---------------------|-----------------|
| macOS / iOS / Chrome | ✅ | ✅ (after DHCP renew for search domain) |
| Android / Linux | ✅ | ✅ |
| iCloud Private Relay enabled | ⚠️ DNS bypassed entirely | ⚠️ |

For iCloud Private Relay: user must disable it in System Settings → Apple ID → iCloud → Private Relay → Off for this network.

## Files Changed

| File | Action |
|------|--------|
| `app/portal/router.py` | Modify — add session check to `/` route |
| `app/portal/templates/disconnect.html` | Create — new dedicated disconnect page |
| `app/network/dnsmasq.py` | Modify — add `logout.wifi`/`logout` address entries, DHCP search domain, auth config writing |
| `scripts/setup-nftables.sh` | Modify — add portal IP redirect rules, `doh_servers` set, DoH blocking |
| `scripts/setup-dnsmasq.sh` | Modify — add `dnsmasq-auth.service` systemd unit |

## Testing

1. Login to portal
2. Close browser tab
3. Open new tab, navigate to `http://logout.wifi`
4. Verify `disconnect.html` is shown
5. Click disconnect button
6. Verify session is terminated and `login.html` is shown
7. From macOS terminal: `nslookup logout.wifi` should return portal IP
8. From macOS terminal: `curl http://logout.wifi` should return HTML
