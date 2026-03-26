# Network Features Phase: MAC Bypass, RFC 8910/8908

> **For agentic workers:** REQUIRED: Use superpowers:subagent-driven-development (if subagents available) or superpowers:executing-plans to implement this plan. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two network features to the captive portal: MAC address bypass list and RFC 8910/8908 Captive Portal API support.

**Architecture:**
- **MAC Bypass**: New `MacBypass` model with admin CRUD, check in portal login flow before showing auth page, bypass rules added to nftables `mac_bypass` set
- **RFC 8910/8908**: Add DHCP option 114 (captive-portal-url) to dnsmasq config, add `/captive-portal/api/v1/portal-info` JSON endpoint

**Tech Stack:** Python, SQLAlchemy, Alembic, nftables, dnsmasq, FastAPI

---

## File Structure

```
app/core/models.py                  # Add: MacBypass model
app/network/nftables.py            # Add: mac_bypass set operations
app/network/dnsmasq.py             # Add: RFC 8910 DHCP option
app/admin/router.py                # Add: CRUD for MacBypass
app/admin/schemas.py                # Add: Pydantic schemas for new models
app/portal/router.py               # Add: MAC bypass check in portal login
alembic/versions/                  # Add: migration for new tables
tests/                             # Add: tests for new functionality
```

---

## Task 1: Database Models

**Files:**
- Modify: `app/core/models.py:144-163`
- Create: `alembic/versions/xxxxxxxx_add_mac_bypass.py`

- [ ] **Step 1: Add MacBypass model to models.py**

Add after `class DhcpConfig`:

```python
class MacBypass(Base):
    __tablename__ = "mac_bypass"
    id: Mapped[uuid.UUID] = uuid_pk()
    mac_address: Mapped[str] = mapped_column(MACADDR, unique=True, nullable=False)
    description: Mapped[Optional[str]] = mapped_column(String(200), nullable=True)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("admin_users.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    expires_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
```

- [ ] **Step 2: Create alembic migration**

Run: `alembic revision --autogenerate -m "add mac_bypass table"`

- [ ] **Step 3: Verify migration file was created**

Run: `ls -la alembic/versions/ | tail -3`

---

## Task 2: Nftables Set Operations

**Files:**
- Modify: `app/network/nftables.py`

- [ ] **Step 1: Add mac_bypass set operations**

Add to `NftablesManager` class:

```python
# ── MAC Bypass Operations ───────────────────────────────────────

@classmethod
def add_mac_bypass(cls, mac: str) -> None:
    """Add MAC to mac_bypass set (format: xx:xx:xx:xx:xx:xx)."""
    try:
        cls._run(["add", "element", cls.TABLE, "mac_bypass", f"{{ {mac} }}"])
        logger.info(f"nftables: added {mac} to mac_bypass")
    except subprocess.CalledProcessError as e:
        logger.error(f"nftables mac_bypass add failed for {mac}: {e.stderr}")
        raise

@classmethod
def remove_mac_bypass(cls, mac: str) -> None:
    """Remove MAC from mac_bypass set."""
    result = subprocess.run(
        ["nft", "delete", "element", cls.TABLE, "mac_bypass", f"{{ {mac} }}"],
        check=False, capture_output=True
    )
    if result.returncode == 0:
        logger.info(f"nftables: removed {mac} from mac_bypass")

@classmethod
def is_mac_bypassed(cls, mac: str) -> bool:
    """Check if MAC is in mac_bypass set."""
    result = subprocess.run(
        ["nft", "get", "element", cls.TABLE, "mac_bypass", f"{{ {mac} }}"],
        check=False, capture_output=True
    )
    return result.returncode == 0
```

- [ ] **Step 2: Verify nftables commands work**

Run test:
```python
# In pytest or manual test
from app.network.nftables import NftablesManager
# These require root and actual nftables setup — mock in unit tests
```

---

## Task 3: Admin Schemas

**Files:**
- Modify: `app/admin/schemas.py`

- [ ] **Step 1: Add Pydantic schemas**

Add after existing schemas:

```python
class MacBypassCreate(BaseModel):
    mac_address: str = Field(..., pattern=r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
    description: str | None = None
    expires_at: datetime | None = None

class MacBypassResponse(BaseModel):
    id: uuid.UUID
    mac_address: str
    description: str | None
    created_by: uuid.UUID
    created_at: datetime
    expires_at: datetime | None
    is_active: bool

    class Config:
        from_attributes = True

```

---

## Task 4: Admin CRUD Routes

**Files:**
- Modify: `app/admin/router.py`

- [ ] **Step 1: Add MacBypass routes**

Add after `# ── Policy CRUD` section:

```python
# ── MAC Bypass ─────────────────────────────────────────────────────────────────

@router.get("/api/mac-bypass", response_model=list[MacBypassResponse])
async def list_mac_bypass(
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_superadmin),
):
    result = await db.execute(
        select(MacBypass).order_by(MacBypass.created_at.desc())
    )
    return result.scalars().all()

@router.post("/api/mac-bypass", status_code=201)
async def create_mac_bypass(
    body: MacBypassCreate,
    db: AsyncSession = Depends(get_db),
    current_user: dict = Depends(require_superadmin),
):
    mac = MacBypass(
        mac_address=body.mac_address.upper(),
        description=body.description,
        expires_at=body.expires_at,
        created_by=uuid.UUID(current_user["sub"]),
    )
    db.add(mac)
    await db.commit()
    await db.refresh(mac)
    
    # Add to nftables mac_bypass set
    from app.network.nftables import NftablesManager
    try:
        NftablesManager.add_mac_bypass(mac.mac_address)
    except Exception as e:
        logger.warning(f"Failed to add MAC to nftables: {e}")
    
    return mac

@router.delete("/api/mac-bypass/{mac_id}")
async def delete_mac_bypass(
    mac_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    _: dict = Depends(require_superadmin),
):
    result = await db.execute(select(MacBypass).where(MacBypass.id == mac_id))
    mac = result.scalar_one_or_none()
    if not mac:
        raise HTTPException(404, {"error": "not_found"})
    
    # Remove from nftables
    from app.network.nftables import NftablesManager
    try:
        NftablesManager.remove_mac_bypass(mac.mac_address)
    except Exception as e:
        logger.warning(f"Failed to remove MAC from nftables: {e}")
    
    await db.delete(mac)
    await db.commit()
    return {"status": "deleted"}
```

---

## Task 5: RFC 8910/8908 Captive Portal API

**Files:**
- Modify: `app/network/dnsmasq.py`
- Modify: `app/portal/router.py`

- [ ] **Step 1: Add RFC 8910 DHCP option to dnsmasq config**

In `write_config()`, add after DHCP options:

```python
# RFC 8910: Captive Portal Identification
# DHCP Option 114: captive-portal-url
lines += [
    "",
    "# RFC 8910: Captive Portal API",
    f"dhcp-option=option:captive-portal-url,{config.gateway_ip}",
]
```

- [ ] **Step 2: Add RFC 8908 portal-info API endpoint**

Add to `app/portal/router.py`:

```python
@router.get("/captive-portal/api/v1/portal-info")
async def captive_portal_info(request: Request):
    """
    RFC 8908 Captive Portal API endpoint.
    Returns JSON with portal URL for client detection.
    """
    from app.core.config import settings
    return {
        "captive": True,
        "user-portal-url": f"http://{settings.PORTAL_IP}:{settings.PORTAL_PORT}/",
        "version": "1.0",
    }
```

---

## Task 6: Portal Login Integration

**Files:**
- Modify: `app/portal/router.py`

- [ ] **Step 1: Add MAC bypass check in portal login**

In `portal_login()` function, after MAC address lookup:

```python
@router.get("/", response_class=HTMLResponse)
async def portal_login(request: Request, db: AsyncSession = Depends(get_db)):
    from app.network.arp import get_mac_for_ip
    from app.network.nftables import NftablesManager
    from app.core.models import MacBypass

    # Check if client already has an active session
    mac = get_mac_for_ip(request.client.host)
    if mac:
        # Check for active session
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
        
        # Check MAC bypass list
        mac_upper = mac.upper()
        if mac_upper:
            bypass_result = await db.execute(
                sa_select(MacBypass).where(
                    MacBypass.mac_address == mac_upper,
                    MacBypass.is_active == True,
                    or_(
                        MacBypass.expires_at.is_(None),
                        MacBypass.expires_at > datetime.now(timezone.utc)
                    )
                )
            )
            bypass = bypass_result.scalar_one_or_none()
            if bypass:
                # Auto-create session for bypassed MAC
                session = await session_manager.create_session(
                    db=db, ip=request.client.host,
                    guest_id=None, voucher_id=None,
                    expires_at=datetime.now(timezone.utc) + timedelta(hours=24),
                )
                return templates.TemplateResponse(
                    request, "success.html",
                    {"auto_bypass": True}
                )

    return templates.TemplateResponse(request, "login.html")
```

---

## Task 7: Admin UI Templates

**Files:**
- Create: `app/admin/templates/mac_bypass.html`
- Modify: `app/admin/templates/base.html`

- [ ] **Step 1: MAC Bypass template**

Design: Dark theme with teal (#14b8a6) accent color to differentiate from blue. Hero card with device icon, table with MAC addresses in monospace, status badges, collapsible add form with MAC auto-formatting.

Features:
- Hero card explaining feature
- Collapsible add form with MAC auto-formatting (Alpine.js)
- Table with status badges (Active/Expired)
- Delete confirmation
- Empty state with icon
- Info box with usage instructions

- [ ] **Step 2: Navigation update**

Add nav item to `base.html` sidebar:
```html
<a href="/admin/mac-bypass" class="nav-item ...">
  <!-- MAC icon -->
  <span>MAC Bypass</span>
</a>
```

- [ ] **Step 3: Page routes in router**

Add to `app/admin/router.py`:
```python
@router.get("/mac-bypass", response_class=HTMLResponse)
async def mac_bypass_page(...):
    # Query MacBypass table, render mac_bypass.html
```

---

## Task 8: Unit Tests

**Files:**
- Create: `tests/test_mac_bypass.py`
- Create: `tests/test_captive_portal_api.py`

- [ ] **Step 1: Test MacBypass model and routes**

```python
# tests/test_mac_bypass.py
import pytest
from unittest.mock import patch, AsyncMock
from httpx import AsyncClient, ASGITransport
from app.main import app

@pytest.mark.asyncio
async def test_create_mac_bypass():
    with patch("app.network.nftables.NftablesManager.add_mac_bypass") as mock_nft:
        mock_nft.return_value = None
        
        # Create test client with auth
        # ... (see conftest.py for auth pattern)
        
        response = await client.post(
            "/admin/api/mac-bypass",
            json={"mac_address": "AA:BB:CC:DD:EE:FF", "description": "Test device"}
        )
        assert response.status_code == 201
        data = response.json()
        assert data["mac_address"] == "AA:BB:CC:DD:EE:FF"

@pytest.mark.asyncio
async def test_mac_bypass_login_flow():
    with patch("app.network.arp.get_mac_for_ip") as mock_arp:
        mock_arp.return_value = "AA:BB:CC:DD:EE:FF"
        with patch("app.network.nftables.NftablesManager.is_mac_bypassed") as mock_nft:
            mock_nft.return_value = True
            
            # ... test full flow
```

- [ ] **Step 2: Test RFC 8908 API**

```python
# tests/test_captive_portal_api.py
@pytest.mark.asyncio
async def test_portal_info_endpoint():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/captive-portal/api/v1/portal-info")
        assert response.status_code == 200
        data = response.json()
        assert data["captive"] == True
        assert "user-portal-url" in data
```

---

## Task 9: Database Migration

- [ ] **Step 1: Generate and apply migration**

Run: `alembic revision --autogenerate -m "add mac_bypass table"`

Run: `alembic upgrade head`

Verify: `alembic current`

---

## Task 10: Commit

- [ ] **Step 1: Stage and commit**

```bash
git add app/core/models.py app/network/nftables.py app/network/dnsmasq.py app/admin/router.py app/admin/schemas.py app/portal/router.py alembic/versions/ tests/
git commit -m "feat: add MAC bypass and RFC 8910/8908 support

- Add MacBypass model for device allowlisting
- Add nftables mac_bypass set
- Add RFC 8910 DHCP option for captive portal URL
- Add RFC 8908 /captive-portal/api/v1/portal-info endpoint
- Add admin CRUD for MAC bypass
- Integrate MAC bypass check in portal login flow
"
```

---

## nftables Set Requirements

Add these sets to `scripts/setup-nftables.sh`:

```bash
# Add before existing sets
add set inet captive_portal mac_bypass { type ether_addr\; }
```

---

## Verification Commands

```bash
# Test RFC 8908 endpoint
curl http://localhost:8080/captive-portal/api/v1/portal-info

# Check nftables sets exist
sudo nft list sets inet captive_portal

# Check DHCP option in dnsmasq
grep captive-portal-url /etc/dnsmasq.d/captive-portal.conf
```
