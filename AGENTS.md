# AGENTS.md - WiFi Captive Portal

**For AI coding agents working in this repository**

---

## Build / Lint / Test Commands

```bash
# Activate virtualenv
source .venv/bin/activate

# Run all tests
pytest tests/ -v

# Run tests with coverage
pytest tests/ --cov=app --cov-report=term-missing

# Run a single test file
pytest tests/test_portal/test_portal_routes.py -v

# Run a single test
pytest tests/test_portal/test_portal_routes.py::test_room_auth_success -v

# Run tests matching a pattern
pytest -k "test_room_auth" -v

# Dev server
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080

# Apply database migrations
alembic upgrade head

# Check migration status
alembic current
alembic history
```

---

## Code Style Guidelines

### Python Version & Environment
- **Python 3.12+** required
- Use `async`/`await` for all database and I/O operations
- Use `datetime.now(timezone.utc)` — **never** `datetime.utcnow()`

### Imports
- Stdlib modules first, then third-party, then local
- Local imports should use full module paths (e.g., `from app.core.config import settings`)
- Sort imports within each group (stdlib, third-party, local)

```python
# ✅ Correct
import time
import uuid
from datetime import datetime, timezone
from fastapi import APIRouter, Depends
from app.core.config import settings

# ❌ Avoid - don't sort local imports separately
from fastapi import APIRouter
from app.core.config import settings
```

### Formatting
- 4 spaces for indentation (no tabs)
- Line length: 120 characters maximum
- Single blank line between sections in a file
- No trailing whitespace

### Type Annotations
- Use modern Python type hints with `|` union syntax (Python 3.12+)
- Use `X | None` instead of `Optional[X]` for simple cases
- Use `X | Y` instead of `Union[X, Y]`

```python
# ✅ Correct
def process_data(user_id: uuid.UUID, name: str | None = None) -> dict[str, Any]:
    ...

# ❌ Avoid
def process_data(user_id: Optional[UUID], name: Optional[str] = None) -> Dict[str, Any]:
    ...
```

### Pydantic Models
- Inherit from `pydantic.BaseModel`
- Use `Field()` for validation and descriptions
- Always set `response_model` on FastAPI endpoints

```python
class MacBypassResponse(BaseModel):
    id: uuid.UUID
    mac_address: str
    description: str | None = None
    is_active: bool = True
```

### SQLAlchemy Models
- Use SQLAlchemy 2.0 Mapped types
- Use `Mapped[X]` and `mapped_column()` syntax
- Create a helper `uuid_pk()` for primary keys
- Always use `with_timezone=True` on DateTime columns

```python
def uuid_pk():
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[uuid.UUID] = uuid_pk()
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
```

### Enums
- Use `enum.Enum` for database-backed enums
- Use `str, enum.Enum` for enums that serialize as strings

```python
class SessionStatus(enum.Enum):
    active = "active"
    expired = "expired"
    kicked = "kicked"
```

### Error Handling
- HTTPException detail must be a dict: `{"error": "reason_string"}`
- Never raise `HTTPException(detail="string")` with a bare string
- Use specific exception types, not generic `Exception`

```python
# ✅ Correct
raise HTTPException(status_code=401, detail={"error": "unauthorized"})

# ❌ Avoid
raise HTTPException(status_code=401, detail="unauthorized")
```

### Logging
- Use `logger = logging.getLogger(__name__)` at module level
- Log levels: DEBUG for dev details, INFO for significant events, WARNING/ERROR for problems

```python
logger = logging.getLogger(__name__)
logger.info(f"Created session for IP {ip}")
logger.warning(f"PMS unavailable: {e}")
```

### FastAPI Routes
- Use `APIRouter` with explicit `prefix` for route grouping
- Always specify `response_model` for endpoints returning data
- Use `Depends()` for dependency injection
- Admin routes use `require_superadmin` or `get_current_admin` dependencies

```python
router = APIRouter(prefix="/admin")

@router.get("/api/mac-bypass", response_model=list[MacBypassResponse])
async def list_mac_bypass(
    request: Request,
    payload: dict = Depends(require_superadmin),
    db: AsyncSession = Depends(get_db),
):
    ...
```

### Async/Await
- All database operations must be `await`ed
- Use `async with AsyncSessionFactory() as session:` for context-managed sessions
- Never use `sync` database operations in async contexts

### Testing
- Use `pytest-asyncio` with `@pytest.mark.asyncio` decorator
- Mock network operations (nftables, tc, pms.factory.load_adapter) in tests
- Test patch targets must be module-local paths

```python
# ✅ Correct
with patch("app.network.nftables.subprocess.run"):

# ❌ Avoid
with patch("subprocess.run"):
```

### File Structure
```
app/
├── core/          # Config, database, models, auth
├── network/       # nftables, tc, session_manager, dnsmasq
├── pms/           # PMS adapters
├── voucher/       # Voucher generation
├── portal/        # Guest-facing routes
├── admin/         # Admin dashboard routes + templates
└── main.py       # FastAPI entry point
tests/
├── conftest.py   # Shared fixtures
├── test_portal/
├── test_admin/
└── test_network/
```

### Security
- Never log secrets or credentials
- Use Fernet encryption for PMS credentials
- Passwords hashed with bcrypt
- Admin routes protected with JWT + role-based access
- Validate all user input with Pydantic

### Database Migrations (Alembic)
- One migration per logical change
- Migration file name format: `{revision}_{short_description}.py`
- Always include `upgrade()` and `downgrade()` functions
- Use raw SQL for seed data: `op.execute(f"INSERT INTO ...")`

### Environment Variables
- All config via `pydantic-settings` from `.env`
- Required vars: `SECRET_KEY`, `ENCRYPTION_KEY`, `DATABASE_URL`, `REDIS_URL`
- Optional vars have sensible defaults in `app/core/config.py`

### Redis
- Always use `decode_responses=True` when connecting
- Used for: rate limiting, JWT blocklist, scheduler state

---

## Key Architecture Notes

- **FastAPI modular monolith** for hotel captive portal
- **MAC-based session persistence**: sessions tracked by MAC address, not IP
- **Dual DNS**: dnsmasq on port 53 (unauthenticated) + dnsmasq-auth on port 5354 (authenticated)
- **nftables sets**: whitelist, dns_bypass, doh_servers, mac_bypass, walled_garden
- **tc HTB**: bandwidth shaping via class ID = `int(octet3) * 256 + int(octet4)`
- **Scheduler**: APScheduler with `wait=False` on shutdown

---

## Common Patterns

### Creating a new admin API endpoint:
1. Add Pydantic schema in `app/admin/schemas.py`
2. Add route in `app/admin/router.py` with `require_superadmin` dependency
3. Add HTML page handler if needed
4. Create Jinja2 template in `app/admin/templates/`
5. Add nav link in `base.html`
6. Add test in `tests/test_admin/`

### Creating a database model:
1. Add model class in `app/core/models.py`
2. Create Alembic migration in `alembic/versions/`
3. Run `alembic upgrade head`

### Testing an API endpoint:
```python
@pytest.mark.asyncio
async def test_mac_bypass_create(client):
    # Login first if auth required
    response = await client.post("/admin/login", data={"username": "admin", "password": "secret123"})
    assert response.status_code == 200

    # Make request
    response = await client.post(
        "/admin/api/mac-bypass",
        json={"mac_address": "AA:BB:CC:DD:EE:FF", "description": "Test"},
        cookies=response.cookies
    )
    assert response.status_code == 201
```
