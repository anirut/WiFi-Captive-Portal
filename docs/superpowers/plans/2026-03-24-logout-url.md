# Logout URL Feature Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Allow users to access a dedicated disconnect page by navigating to the portal when they already have an active session.

**Architecture:** Modify the portal root route to check for active sessions by MAC address. If found, render a new `disconnect.html` template instead of the login page. The disconnect page features a prominent disconnect button.

**Tech Stack:** FastAPI, Jinja2 templates, SQLAlchemy async, existing portal.css styles

---

## Task 1: Add test for portal showing disconnect page when session is active

**Files:**
- Modify: `tests/test_portal/test_portal_routes.py`

- [ ] **Step 1: Write the failing test**

Add a test that verifies GET `/` returns disconnect.html when user has an active session:

```python
@pytest.mark.asyncio
async def test_portal_shows_disconnect_when_session_active(client):
    """When client has an active session, GET / should show disconnect page."""
    from datetime import datetime, timedelta, timezone
    from app.core.models import Session, SessionStatus
    from unittest.mock import patch, MagicMock

    # Create a mock active session
    mock_session = MagicMock()
    mock_session.id = "session-uuid"
    mock_session.expires_at = datetime.now(timezone.utc) + timedelta(hours=8)
    mock_session.status = SessionStatus.active

    # Mock get_mac_for_ip to return a MAC address
    with patch("app.portal.router.get_mac_for_ip", return_value="aa:bb:cc:dd:ee:ff"):
        # Override DB to return the mock session
        from app.core.database import get_db
        from app.main import app

        async def mock_db_gen():
            mock_db = AsyncMock()
            mock_result = MagicMock()
            mock_result.scalar_one_or_none.return_value = mock_session
            mock_db.execute = AsyncMock(return_value=mock_result)
            yield mock_db

        app.dependency_overrides[get_db] = mock_db_gen

        response = await client.get("/")

        app.dependency_overrides.pop(get_db, None)

        assert response.status_code == 200
        # Check that we got the disconnect page, not login
        assert "Disconnect" in response.text
```

- [ ] **Step 2: Run test to verify it fails**

Run: `pytest tests/test_portal/test_portal_routes.py::test_portal_shows_disconnect_when_session_active -v`
Expected: FAIL - login page is returned instead of disconnect page

- [ ] **Step 3: Commit the failing test**

```bash
git add tests/test_portal/test_portal_routes.py
git commit -m "test(portal): add test for disconnect page when session active"
```

---

## Task 2: Create disconnect.html template

**Files:**
- Create: `app/portal/templates/disconnect.html`

- [ ] **Step 1: Create the disconnect template**

Create `app/portal/templates/disconnect.html` with a prominent disconnect button:

```html
<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta name="theme-color" content="#080d1a">
  <title>Connected — {{ hotel_name|default('Hotel WiFi') }}</title>
  <link rel="stylesheet" href="/static/css/portal.css">
</head>
<body>
  <div class="portal-bg" aria-hidden="true"></div>

  <main class="status-page">

    <div class="status-icon success" aria-hidden="true">
      <svg width="28" height="28" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
        <polyline points="20 6 9 17 4 12"/>
      </svg>
    </div>

    <h1 class="status-title">You're Connected</h1>
    <p class="status-body">You're online at {{ hotel_name|default('the hotel') }}.</p>

    <div class="session-info-card">
      <div class="session-info-row">
        <span class="label">Session expires</span>
        <span class="value" id="expires-text">{{ expires_at.strftime('%H:%M') if expires_at else '—' }}</span>
      </div>
      <div class="session-info-row">
        <span class="label">Status</span>
        <span class="value" style="color: oklch(72% 0.14 160)">Active</span>
      </div>
    </div>

    <button class="btn-disconnect" id="disconnect-btn" onclick="confirmDisconnect(event)">
      Disconnect
    </button>

    <a class="btn-secondary" href="http://detectportal.firefox.com/canonical.html" onclick="window.open(this.href,'_blank');return false;">
      Continue Browsing
    </a>

  </main>

  <style>
    .btn-disconnect {
      margin-top: 2rem;
      padding: 1rem 2.5rem;
      background: oklch(65% 0.18 25 / 0.15);
      border: 1px solid oklch(65% 0.18 25 / 0.4);
      border-radius: 12px;
      color: oklch(70% 0.15 25);
      font-family: 'Plus Jakarta Sans', system-ui, sans-serif;
      font-size: 1rem;
      font-weight: 600;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      cursor: pointer;
      transition: all 0.2s;
      min-height: 56px;
      animation: fadeUp 0.5s var(--ease-out-quart) 0.7s both;
    }

    .btn-disconnect:hover {
      background: oklch(65% 0.18 25 / 0.25);
      border-color: oklch(65% 0.18 25 / 0.6);
    }

    .btn-disconnect:active {
      transform: scale(0.98);
    }

    .btn-disconnect.loading {
      opacity: 0.7;
      pointer-events: none;
    }
  </style>

  <script>
    async function confirmDisconnect(e) {
      e.preventDefault();
      if (!confirm('Disconnect from WiFi?')) return;

      const btn = document.getElementById('disconnect-btn');
      btn.classList.add('loading');
      btn.textContent = 'Disconnecting...';

      try {
        await fetch('/session/disconnect', { method: 'POST' });
      } finally {
        window.location.href = '/';
      }
    }
  </script>
</body>
</html>
```

- [ ] **Step 2: Commit the template**

```bash
git add app/portal/templates/disconnect.html
git commit -m "feat(portal): add disconnect.html template"
```

---

## Task 3: Modify portal route to show disconnect page for active sessions

**Files:**
- Modify: `app/portal/router.py`

- [ ] **Step 1: Update the portal root route**

Modify `portal_login` function in `app/portal/router.py` to check for active sessions:

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

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/test_portal/test_portal_routes.py::test_portal_shows_disconnect_when_session_active -v`
Expected: PASS

- [ ] **Step 3: Run all portal tests**

Run: `pytest tests/test_portal/ -v`
Expected: All tests pass

- [ ] **Step 4: Commit the route change**

```bash
git add app/portal/router.py
git commit -m "feat(portal): show disconnect page for clients with active session"
```

---

## Task 4: Add test for portal showing login when no active session

**Files:**
- Modify: `tests/test_portal/test_portal_routes.py`

- [ ] **Step 1: Write test for login page when no session**

Add a test that verifies GET `/` returns login.html when no active session exists:

```python
@pytest.mark.asyncio
async def test_portal_shows_login_when_no_session(client):
    """When client has no active session, GET / should show login page."""
    # get_mac_for_ip returns None by default in conftest
    response = await client.get("/")
    assert response.status_code == 200
    # Should show login form, not disconnect
    assert "Room Number" in response.text or "Voucher" in response.text
    assert "Disconnect" not in response.text
```

- [ ] **Step 2: Run test to verify it passes**

Run: `pytest tests/test_portal/test_portal_routes.py::test_portal_shows_login_when_no_session -v`
Expected: PASS

- [ ] **Step 3: Commit the test**

```bash
git add tests/test_portal/test_portal_routes.py
git commit -m "test(portal): add test for login page when no session"
```

---

## Task 5: Run full test suite and verify

- [ ] **Step 1: Run all tests**

Run: `pytest tests/ -v`
Expected: All tests pass

- [ ] **Step 2: Manual verification**

Start the dev server and test manually:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080
```

1. Navigate to `/` - should show login page
2. Login with valid credentials
3. Navigate to `/` again - should show disconnect page
4. Click disconnect - should redirect to login page

---

## Summary

| Task | Description | Files |
|------|-------------|-------|
| 1 | Add test for disconnect page | `tests/test_portal/test_portal_routes.py` |
| 2 | Create disconnect.html template | `app/portal/templates/disconnect.html` |
| 3 | Modify portal route logic | `app/portal/router.py` |
| 4 | Add test for login page when no session | `tests/test_portal/test_portal_routes.py` |
| 5 | Run full test suite | — |
