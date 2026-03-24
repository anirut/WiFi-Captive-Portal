# Logout URL Feature Design

**Date:** 2026-03-24
**Status:** Approved

## Problem

Users who close the browser after logging into the WiFi portal have no easy way to disconnect their session later. They don't know where to find the logout page.

## Solution

Allow users to type `http://logout` in their browser to access a dedicated disconnect page.

## Implementation

### 1. DNS Configuration (Manual - User Side)

Configure DNS server (dnsmasq, Pi-hole, or router) to resolve `logout` to the portal IP:

```
logout  →  192.168.x.x  (portal IP)
```

Optionally also add:
```
wifi    →  192.168.x.x  (portal IP)
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

### 4. User Flow

1. User authenticates → redirected to `/success`
2. User closes browser tab
3. Later, user types `http://logout` in browser
4. DNS resolves to portal IP
5. Portal checks for active session by MAC address
6. Active session found → shows `disconnect.html`
7. User clicks Disconnect → POST to `/session/disconnect`
8. Session expired → redirect to `/` → shows `login.html`

## Files Changed

| File | Action |
|------|--------|
| `app/portal/router.py` | Modify - add session check to `/` route |
| `app/portal/templates/disconnect.html` | Create - new dedicated disconnect page |

## Testing

1. Login to portal
2. Close browser tab
3. Open new tab, navigate to `http://<portal-ip>/`
4. Verify disconnect.html is shown
5. Click disconnect button
6. Verify session is terminated and login page is shown
