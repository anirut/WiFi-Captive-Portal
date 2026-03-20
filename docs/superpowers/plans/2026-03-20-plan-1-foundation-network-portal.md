# WiFi Captive Portal — Plan 1: Foundation, Network & Portal MVP

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a fully working hotel WiFi captive portal on Ubuntu Linux — guests can authenticate via Room+LastName (Standalone PMS) or Voucher code, iptables enforces network access, and sessions expire automatically.

**Architecture:** Modular monolith in FastAPI with 6 modules (portal, admin stub, network, pms, voucher, core). Network enforcement uses iptables FORWARD rules + tc HTB bandwidth shaping. Standalone PMS adapter manages guests in local DB. Admin dashboard is stubbed (session list + kick only) — full admin UI is Plan 3.

**Tech Stack:** Python 3.11+, FastAPI, SQLAlchemy (async), PostgreSQL, Redis, APScheduler, iptables/nftables, tc, dnsmasq, pytest + pytest-asyncio, httpx TestClient, Alembic

---

## File Map

```
wifi-captive-portal/
├── app/
│   ├── core/
│   │   ├── config.py           # Pydantic Settings, loads .env
│   │   ├── database.py         # async SQLAlchemy engine + session factory
│   │   ├── models.py           # all SQLAlchemy ORM models
│   │   ├── encryption.py       # Fernet wrapper for PMS config
│   │   └── auth.py             # JWT encode/decode + Redis blocklist
│   ├── network/
│   │   ├── iptables.py         # add/remove FORWARD rules (subprocess)
│   │   ├── tc.py               # add/remove tc HTB classes/filters
│   │   ├── arp.py              # read MAC from /proc/net/arp
│   │   ├── session_manager.py  # create/expire sessions, calls iptables+tc
│   │   └── scheduler.py        # APScheduler job: expire sessions every 60s
│   ├── pms/
│   │   ├── base.py             # PMSAdapter ABC + GuestInfo dataclass
│   │   ├── standalone.py       # StandaloneAdapter (DB-backed)
│   │   └── factory.py          # load active adapter from DB
│   ├── portal/
│   │   ├── router.py           # GET /, POST /auth/room, POST /auth/voucher, etc.
│   │   ├── schemas.py          # Pydantic request/response models
│   │   └── templates/
│   │       ├── login.html      # split layout: branding left, form right
│   │       ├── success.html    # connected + session info
│   │       ├── expired.html    # session expired
│   │       └── error.html      # auth error with message
│   ├── voucher/
│   │   ├── router.py           # admin voucher CRUD (stub for Plan 3)
│   │   └── generator.py        # generate unique codes, validate vouchers
│   ├── admin/
│   │   └── router.py           # stub: GET /admin/sessions, DELETE /admin/sessions/{id}
│   └── main.py                 # FastAPI app factory, include routers, startup events
├── static/
│   └── css/
│       └── portal.css          # Glassmorphism base styles
├── tests/
│   ├── conftest.py             # pytest fixtures: async DB, test client, mock iptables
│   ├── test_core/
│   │   ├── test_config.py
│   │   ├── test_encryption.py
│   │   └── test_auth.py
│   ├── test_network/
│   │   ├── test_iptables.py
│   │   ├── test_tc.py
│   │   ├── test_arp.py
│   │   └── test_session_manager.py
│   ├── test_pms/
│   │   ├── test_base.py
│   │   └── test_standalone.py
│   ├── test_portal/
│   │   └── test_portal_routes.py
│   └── test_voucher/
│       └── test_generator.py
├── alembic/
│   ├── env.py
│   └── versions/               # migration files (auto-generated)
├── scripts/
│   ├── setup-iptables.sh       # initial chain setup (run as root)
│   └── setup-tc.sh             # initial HTB qdisc on WAN interface
├── .env.example
├── alembic.ini
├── requirements.txt
└── requirements-dev.txt
```

---

## Task 1: Project Bootstrap

**Files:**
- Create: `requirements.txt`
- Create: `requirements-dev.txt`
- Create: `app/__init__.py`, `app/core/__init__.py`, etc. (all `__init__.py` files)
- Create: `.env.example`
- Create: `app/core/config.py`

- [ ] **Step 1: Create directory structure**

```bash
mkdir -p app/{core,network,pms,portal/templates,voucher,admin} \
         static/css tests/{test_core,test_network,test_pms,test_portal,test_voucher} \
         scripts alembic/versions docs/superpowers/plans
touch app/__init__.py app/core/__init__.py app/network/__init__.py \
      app/pms/__init__.py app/portal/__init__.py app/voucher/__init__.py \
      app/admin/__init__.py tests/__init__.py tests/test_core/__init__.py \
      tests/test_network/__init__.py tests/test_pms/__init__.py \
      tests/test_portal/__init__.py tests/test_voucher/__init__.py
```

- [ ] **Step 2: Create `requirements.txt`**

```
fastapi==0.115.0
uvicorn[standard]==0.30.6
sqlalchemy[asyncio]==2.0.35
asyncpg==0.29.0
alembic==1.13.2
redis[asyncio]==5.0.8
pydantic-settings==2.4.0
python-jose[cryptography]==3.3.0
passlib[bcrypt]==1.7.4
cryptography==43.0.1
httpx==0.27.2
apscheduler==3.10.4
jinja2==3.1.4
python-multipart==0.0.9
```

- [ ] **Step 3: Create `requirements-dev.txt`**

```
pytest==8.3.3
pytest-asyncio==0.24.0
pytest-cov==5.0.0
anyio==4.6.0
```

- [ ] **Step 4: Create `.env.example`**

```bash
# Application
SECRET_KEY=change_me_generate_with_openssl_rand_hex_32
ENCRYPTION_KEY=change_me_generate_with_python_cryptography_fernet_generate_key
ENVIRONMENT=development

# Database
DATABASE_URL=postgresql+asyncpg://captive:captive@localhost:5432/captive_portal

# Redis
REDIS_URL=redis://localhost:6379/0

# Network interfaces
WIFI_INTERFACE=wlan0
WAN_INTERFACE=eth0
PORTAL_IP=192.168.1.1
PORTAL_PORT=8080

# JWT
JWT_ALGORITHM=HS256
JWT_EXPIRE_HOURS=8

# Rate limiting
AUTH_RATE_LIMIT_ATTEMPTS=5
AUTH_RATE_LIMIT_WINDOW_SECONDS=600
```

- [ ] **Step 5: Write failing test for config**

Create `tests/test_core/test_config.py`:

```python
import pytest
from app.core.config import Settings

def test_settings_loads_defaults():
    s = Settings(
        SECRET_KEY="a" * 32,
        ENCRYPTION_KEY="Zm9vYmFyYmF6cXV4Zm9vYmFyYmF6cXV4Zm9vYmFyYmF6cXU=",
        DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
        REDIS_URL="redis://localhost:6379/0",
    )
    assert s.JWT_ALGORITHM == "HS256"
    assert s.JWT_EXPIRE_HOURS == 8
    assert s.AUTH_RATE_LIMIT_ATTEMPTS == 5
    assert s.WIFI_INTERFACE == "wlan0"
```

- [ ] **Step 6: Run test — expect FAIL (module not found)**

```bash
pytest tests/test_core/test_config.py -v
```

- [ ] **Step 7: Create `app/core/config.py`**

```python
from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    SECRET_KEY: str
    ENCRYPTION_KEY: str
    ENVIRONMENT: str = "development"

    DATABASE_URL: str
    REDIS_URL: str

    WIFI_INTERFACE: str = "wlan0"
    WAN_INTERFACE: str = "eth0"
    PORTAL_IP: str = "192.168.1.1"
    PORTAL_PORT: int = 8080

    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 8

    AUTH_RATE_LIMIT_ATTEMPTS: int = 5
    AUTH_RATE_LIMIT_WINDOW_SECONDS: int = 600

    class Config:
        env_file = ".env"

settings = Settings()
```

- [ ] **Step 8: Run test — expect PASS**

```bash
pytest tests/test_core/test_config.py -v
```

Expected: `PASSED`

- [ ] **Step 9: Commit**

```bash
git add . && git commit -m "feat: project bootstrap — structure, requirements, config"
```

---

## Task 2: Database Models + Migrations

**Files:**
- Create: `app/core/models.py`
- Create: `app/core/database.py`
- Create: `alembic.ini`
- Create: `alembic/env.py`

- [ ] **Step 1: Write failing test for models import**

Create `tests/test_core/test_models.py`:

```python
from app.core.models import Guest, Session, Voucher, Room, Policy, PMSAdapter, AdminUser

def test_models_importable():
    # All models have expected table names
    assert Guest.__tablename__ == "guests"
    assert Session.__tablename__ == "sessions"
    assert Voucher.__tablename__ == "vouchers"
    assert Room.__tablename__ == "rooms"
    assert Policy.__tablename__ == "policies"
    assert PMSAdapter.__tablename__ == "pms_adapters"
    assert AdminUser.__tablename__ == "admin_users"
```

- [ ] **Step 2: Run test — expect FAIL**

```bash
pytest tests/test_core/test_models.py -v
```

- [ ] **Step 3: Create `app/core/database.py`**

```python
from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.core.config import settings

class Base(DeclarativeBase):
    pass

engine = create_async_engine(settings.DATABASE_URL, echo=settings.ENVIRONMENT == "development")
AsyncSessionFactory = async_sessionmaker(engine, expire_on_commit=False)

async def get_db() -> AsyncSession:
    async with AsyncSessionFactory() as session:
        yield session
```

- [ ] **Step 4: Create `app/core/models.py`**

```python
import uuid
import enum
from datetime import datetime
from sqlalchemy import String, Integer, Boolean, BigInteger, ForeignKey, Enum, DateTime, LargeBinary
from sqlalchemy.dialects.postgresql import UUID, INET, MACADDR, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from app.core.database import Base

def uuid_pk():
    return mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)

class SessionStatus(enum.Enum):
    active = "active"
    expired = "expired"
    kicked = "kicked"

class VoucherType(enum.Enum):
    time = "time"
    data = "data"

class PMSAdapterType(enum.Enum):
    opera = "opera"
    cloudbeds = "cloudbeds"
    mews = "mews"
    custom = "custom"
    standalone = "standalone"

class AdminRole(enum.Enum):
    superadmin = "superadmin"
    staff = "staff"

class Guest(Base):
    __tablename__ = "guests"
    id: Mapped[uuid.UUID] = uuid_pk()
    room_number: Mapped[str] = mapped_column(String(20))
    last_name: Mapped[str] = mapped_column(String(100))
    first_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    pms_guest_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    check_in: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    check_out: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    max_devices: Mapped[int] = mapped_column(Integer, default=3)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    sessions: Mapped[list["Session"]] = relationship(back_populates="guest")

class Session(Base):
    __tablename__ = "sessions"
    id: Mapped[uuid.UUID] = uuid_pk()
    guest_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("guests.id"), nullable=True)
    voucher_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("vouchers.id"), nullable=True)
    ip_address: Mapped[str] = mapped_column(INET)
    mac_address: Mapped[str | None] = mapped_column(MACADDR, nullable=True)
    connected_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=datetime.utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    bytes_up: Mapped[int] = mapped_column(BigInteger, default=0)
    bytes_down: Mapped[int] = mapped_column(BigInteger, default=0)
    status: Mapped[SessionStatus] = mapped_column(Enum(SessionStatus), default=SessionStatus.active)
    guest: Mapped["Guest | None"] = relationship(back_populates="sessions")
    voucher: Mapped["Voucher | None"] = relationship(back_populates="sessions")

class Voucher(Base):
    __tablename__ = "vouchers"
    id: Mapped[uuid.UUID] = uuid_pk()
    code: Mapped[str] = mapped_column(String(50), unique=True)
    type: Mapped[VoucherType] = mapped_column(Enum(VoucherType))
    duration_minutes: Mapped[int | None] = mapped_column(Integer, nullable=True)
    data_limit_mb: Mapped[int | None] = mapped_column(Integer, nullable=True)
    max_devices: Mapped[int] = mapped_column(Integer, default=1)
    created_by: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), ForeignKey("admin_users.id"))
    expires_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    used_count: Mapped[int] = mapped_column(Integer, default=0)
    max_uses: Mapped[int] = mapped_column(Integer, default=1)
    sessions: Mapped[list["Session"]] = relationship(back_populates="voucher")

class Room(Base):
    __tablename__ = "rooms"
    id: Mapped[uuid.UUID] = uuid_pk()
    number: Mapped[str] = mapped_column(String(20), unique=True)
    room_type: Mapped[str] = mapped_column(String(50), default="standard")
    policy_id: Mapped[uuid.UUID | None] = mapped_column(UUID(as_uuid=True), ForeignKey("policies.id"), nullable=True)
    pms_room_id: Mapped[str | None] = mapped_column(String(100), nullable=True)

class Policy(Base):
    __tablename__ = "policies"
    id: Mapped[uuid.UUID] = uuid_pk()
    name: Mapped[str] = mapped_column(String(100))
    bandwidth_up_kbps: Mapped[int] = mapped_column(Integer, default=0)
    bandwidth_down_kbps: Mapped[int] = mapped_column(Integer, default=0)
    session_duration_min: Mapped[int] = mapped_column(Integer, default=0)
    max_devices: Mapped[int] = mapped_column(Integer, default=3)

class PMSAdapter(Base):
    __tablename__ = "pms_adapters"
    id: Mapped[uuid.UUID] = uuid_pk()
    type: Mapped[PMSAdapterType] = mapped_column(Enum(PMSAdapterType))
    config_encrypted: Mapped[bytes | None] = mapped_column(LargeBinary, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    webhook_secret: Mapped[str | None] = mapped_column(String(200), nullable=True)

class AdminUser(Base):
    __tablename__ = "admin_users"
    id: Mapped[uuid.UUID] = uuid_pk()
    username: Mapped[str] = mapped_column(String(100), unique=True)
    password_hash: Mapped[str] = mapped_column(String(200))
    role: Mapped[AdminRole] = mapped_column(Enum(AdminRole), default=AdminRole.staff)
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
```

- [ ] **Step 5: Run test — expect PASS**

```bash
pytest tests/test_core/test_models.py -v
```

- [ ] **Step 6: Set up Alembic**

```bash
pip install -r requirements.txt
alembic init alembic
```

Edit `alembic/env.py` — add after existing imports:

```python
from app.core.database import Base
from app.core import models  # noqa: F401 — ensures models are registered
from app.core.config import settings

# Replace the config.set_main_option line:
config.set_main_option("sqlalchemy.url", settings.DATABASE_URL.replace("+asyncpg", ""))

# In run_migrations_online(), replace connectable with:
# connectable = engine_from_config(...) stays as-is
# but target_metadata must be set:
target_metadata = Base.metadata
```

- [ ] **Step 7: Generate initial migration**

```bash
alembic revision --autogenerate -m "initial schema"
```

Expected: Creates `alembic/versions/<hash>_initial_schema.py`

- [ ] **Step 8: Apply migration (requires running PostgreSQL)**

```bash
# Ensure PostgreSQL is running and DB exists:
# createdb captive_portal
alembic upgrade head
```

Expected: All tables created

- [ ] **Step 9: Commit**

```bash
git add . && git commit -m "feat: database models and initial Alembic migration"
```

---

## Task 3: Encryption + Admin Auth (JWT)

**Files:**
- Create: `app/core/encryption.py`
- Create: `app/core/auth.py`
- Test: `tests/test_core/test_encryption.py`
- Test: `tests/test_core/test_auth.py`

- [ ] **Step 1: Write failing test for encryption**

Create `tests/test_core/test_encryption.py`:

```python
from app.core.encryption import encrypt_config, decrypt_config

def test_encrypt_decrypt_roundtrip():
    data = {"api_url": "https://pms.example.com", "api_key": "secret123"}
    encrypted = encrypt_config(data)
    assert isinstance(encrypted, bytes)
    assert encrypted != str(data).encode()
    decrypted = decrypt_config(encrypted)
    assert decrypted == data

def test_encrypted_values_differ_each_call():
    data = {"key": "value"}
    assert encrypt_config(data) != encrypt_config(data)  # Fernet uses random IV
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_core/test_encryption.py -v
```

- [ ] **Step 3: Create `app/core/encryption.py`**

```python
import json
from cryptography.fernet import Fernet
from app.core.config import settings

def _get_fernet() -> Fernet:
    return Fernet(settings.ENCRYPTION_KEY.encode() if isinstance(settings.ENCRYPTION_KEY, str) else settings.ENCRYPTION_KEY)

def encrypt_config(data: dict) -> bytes:
    return _get_fernet().encrypt(json.dumps(data).encode())

def decrypt_config(data: bytes) -> dict:
    return json.loads(_get_fernet().decrypt(data).decode())
```

- [ ] **Step 4: Write failing test for auth**

Create `tests/test_core/test_auth.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch
from app.core.auth import create_access_token, decode_access_token, is_token_revoked, revoke_token

def test_create_and_decode_token():
    token = create_access_token({"sub": "admin_user_id", "role": "superadmin"})
    payload = decode_access_token(token)
    assert payload["sub"] == "admin_user_id"
    assert payload["role"] == "superadmin"

def test_decode_invalid_token_returns_none():
    assert decode_access_token("not.a.valid.token") is None

@pytest.mark.asyncio
async def test_revoke_and_check_token():
    token = create_access_token({"sub": "user1"})
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    assert not await is_token_revoked(token, mock_redis)
    mock_redis.get.return_value = b"1"
    assert await is_token_revoked(token, mock_redis)
```

- [ ] **Step 5: Run — expect FAIL**

```bash
pytest tests/test_core/test_auth.py -v
```

- [ ] **Step 6: Create `app/core/auth.py`**

```python
from datetime import datetime, timedelta
from typing import Any
from jose import jwt, JWTError
from app.core.config import settings

def create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.utcnow() + timedelta(hours=settings.JWT_EXPIRE_HOURS)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None

async def is_token_revoked(token: str, redis_client: Any) -> bool:
    return await redis_client.get(f"revoked:{token}") is not None

async def revoke_token(token: str, redis_client: Any) -> None:
    payload = decode_access_token(token)
    if payload and "exp" in payload:
        ttl = int(payload["exp"] - datetime.utcnow().timestamp())
        if ttl > 0:
            await redis_client.setex(f"revoked:{token}", ttl, "1")
```

- [ ] **Step 7: Run tests — expect PASS**

```bash
pytest tests/test_core/ -v
```

- [ ] **Step 8: Commit**

```bash
git add . && git commit -m "feat: Fernet encryption and JWT auth with Redis blocklist"
```

---

## Task 4: Network — ARP + iptables Manager

**Files:**
- Create: `app/network/arp.py`
- Create: `app/network/iptables.py`
- Test: `tests/test_network/test_arp.py`
- Test: `tests/test_network/test_iptables.py`

- [ ] **Step 1: Write failing test for ARP lookup**

Create `tests/test_network/test_arp.py`:

```python
from unittest.mock import patch, mock_open
from app.network.arp import get_mac_for_ip

ARP_TABLE = """\
IP address       HW type     Flags       HW address            Mask     Device
192.168.1.45     0x1         0x2         aa:bb:cc:dd:ee:ff     *        wlan0
192.168.1.46     0x1         0x0         00:00:00:00:00:00     *        wlan0
"""

def test_get_mac_for_known_ip():
    with patch("builtins.open", mock_open(read_data=ARP_TABLE)):
        assert get_mac_for_ip("192.168.1.45") == "aa:bb:cc:dd:ee:ff"

def test_get_mac_incomplete_entry_returns_none():
    with patch("builtins.open", mock_open(read_data=ARP_TABLE)):
        # Flags 0x0 = incomplete ARP entry
        assert get_mac_for_ip("192.168.1.46") is None

def test_get_mac_unknown_ip_returns_none():
    with patch("builtins.open", mock_open(read_data=ARP_TABLE)):
        assert get_mac_for_ip("192.168.1.99") is None
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_network/test_arp.py -v
```

- [ ] **Step 3: Create `app/network/arp.py`**

```python
def get_mac_for_ip(ip: str) -> str | None:
    """Read MAC from ARP table. Returns None if not found or entry incomplete."""
    try:
        with open("/proc/net/arp") as f:
            for line in f.readlines()[1:]:  # skip header
                parts = line.split()
                if len(parts) >= 4 and parts[0] == ip:
                    flags = int(parts[2], 16)
                    if flags & 0x2:  # complete entry
                        mac = parts[3]
                        return mac if mac != "00:00:00:00:00:00" else None
    except OSError:
        pass
    return None
```

- [ ] **Step 4: Write failing test for iptables**

Create `tests/test_network/test_iptables.py`:

```python
import pytest
from unittest.mock import patch, call
from app.network.iptables import add_whitelist, remove_whitelist, is_whitelisted

def test_add_whitelist_runs_correct_command():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        add_whitelist("192.168.1.45")
        mock_run.assert_called_once_with(
            ["iptables", "-I", "FORWARD", "-s", "192.168.1.45", "-j", "ACCEPT"],
            check=True, capture_output=True
        )

def test_remove_whitelist_runs_correct_command():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        remove_whitelist("192.168.1.45")
        mock_run.assert_called_once_with(
            ["iptables", "-D", "FORWARD", "-s", "192.168.1.45", "-j", "ACCEPT"],
            check=True, capture_output=True
        )

def test_is_whitelisted_true():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        assert is_whitelisted("192.168.1.45") is True

def test_is_whitelisted_false():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 1
        assert is_whitelisted("192.168.1.45") is False
```

- [ ] **Step 5: Run — expect FAIL**

```bash
pytest tests/test_network/test_iptables.py -v
```

- [ ] **Step 6: Create `app/network/iptables.py`**

```python
import subprocess
import logging

logger = logging.getLogger(__name__)

def _run(cmd: list[str]) -> int:
    result = subprocess.run(cmd, check=True, capture_output=True)
    return result.returncode

def add_whitelist(ip: str) -> None:
    try:
        _run(["iptables", "-I", "FORWARD", "-s", ip, "-j", "ACCEPT"])
        logger.info(f"iptables: added {ip} to whitelist")
    except subprocess.CalledProcessError as e:
        logger.error(f"iptables add failed for {ip}: {e.stderr}")
        raise

def remove_whitelist(ip: str) -> None:
    try:
        _run(["iptables", "-D", "FORWARD", "-s", ip, "-j", "ACCEPT"])
        logger.info(f"iptables: removed {ip} from whitelist")
    except subprocess.CalledProcessError as e:
        logger.warning(f"iptables remove failed for {ip} (may not exist): {e.stderr}")

def is_whitelisted(ip: str) -> bool:
    result = subprocess.run(
        ["iptables", "-C", "FORWARD", "-s", ip, "-j", "ACCEPT"],
        check=False, capture_output=True
    )
    return result.returncode == 0
```

- [ ] **Step 7: Run tests — expect PASS**

```bash
pytest tests/test_network/test_arp.py tests/test_network/test_iptables.py -v
```

- [ ] **Step 8: Commit**

```bash
git add . && git commit -m "feat: ARP lookup and iptables whitelist manager"
```

---

## Task 5: Network — TC Bandwidth Control

**Files:**
- Create: `app/network/tc.py`
- Test: `tests/test_network/test_tc.py`

- [ ] **Step 1: Write failing test**

Create `tests/test_network/test_tc.py`:

```python
from unittest.mock import patch, call
from app.network.tc import apply_bandwidth_limit, remove_bandwidth_limit, _ip_to_class_id

def test_ip_to_class_id():
    # Uses last two octets of IP
    assert _ip_to_class_id("192.168.1.45") == "1:145"
    assert _ip_to_class_id("192.168.2.100") == "2:200"  # 2*100 + 100 = 300? No: octet3=2, octet4=100 -> 2*256+100=612 -> hex
    # Simple: class_id = f"1:{int(parts[2])*256 + int(parts[3])}"
    assert _ip_to_class_id("192.168.1.1") == "1:257"

def test_apply_bandwidth_limit_calls_tc():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        apply_bandwidth_limit("192.168.1.45", up_kbps=10240, down_kbps=51200, wan_if="eth0")
        assert mock_run.call_count >= 2  # at least class add + filter add

def test_remove_bandwidth_limit_calls_tc():
    with patch("subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        remove_bandwidth_limit("192.168.1.45", wan_if="eth0")
        assert mock_run.call_count >= 1

def test_zero_kbps_skips_tc(caplog):
    with patch("subprocess.run") as mock_run:
        apply_bandwidth_limit("192.168.1.45", up_kbps=0, down_kbps=0, wan_if="eth0")
        mock_run.assert_not_called()
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_network/test_tc.py -v
```

- [ ] **Step 3: Create `app/network/tc.py`**

```python
import subprocess
import logging

logger = logging.getLogger(__name__)

def _ip_to_class_id(ip: str) -> str:
    parts = ip.split(".")
    numeric = int(parts[2]) * 256 + int(parts[3])
    return f"1:{numeric}"

def _run(cmd: list[str]) -> None:
    subprocess.run(cmd, check=False, capture_output=True)

def apply_bandwidth_limit(ip: str, up_kbps: int, down_kbps: int, wan_if: str) -> None:
    if up_kbps == 0 and down_kbps == 0:
        return
    class_id = _ip_to_class_id(ip)
    # Add HTB class for download (traffic going TO guest = outbound on WAN)
    if down_kbps > 0:
        _run(["tc", "class", "add", "dev", wan_if, "parent", "1:", "classid",
              class_id, "htb", "rate", f"{down_kbps}kbit", "ceil", f"{down_kbps}kbit"])
        _run(["tc", "filter", "add", "dev", wan_if, "parent", "1:", "protocol",
              "ip", "prio", "1", "u32", "match", "ip", "dst", f"{ip}/32", "flowid", class_id])
    logger.info(f"tc: applied limit {down_kbps}kbps down for {ip}")

def remove_bandwidth_limit(ip: str, wan_if: str) -> None:
    class_id = _ip_to_class_id(ip)
    _run(["tc", "filter", "del", "dev", wan_if, "parent", "1:", "protocol",
          "ip", "prio", "1", "u32", "match", "ip", "dst", f"{ip}/32", "flowid", class_id])
    _run(["tc", "class", "del", "dev", wan_if, "parent", "1:", "classid", class_id])
    logger.info(f"tc: removed limit for {ip}")
```

- [ ] **Step 4: Fix test to match implementation**

Update `test_ip_to_class_id` in `tests/test_network/test_tc.py`:

```python
def test_ip_to_class_id():
    # class_id = int(parts[2])*256 + int(parts[3])
    assert _ip_to_class_id("192.168.1.45") == f"1:{1*256+45}"   # 1:301
    assert _ip_to_class_id("192.168.0.1") == f"1:{0*256+1}"      # 1:1
    assert _ip_to_class_id("192.168.2.100") == f"1:{2*256+100}"  # 1:612
```

- [ ] **Step 5: Run tests — expect PASS**

```bash
pytest tests/test_network/test_tc.py -v
```

- [ ] **Step 6: Commit**

```bash
git add . && git commit -m "feat: tc HTB bandwidth control per IP"
```

---

## Task 6: Session Manager + Scheduler

**Files:**
- Create: `app/network/session_manager.py`
- Create: `app/network/scheduler.py`
- Test: `tests/test_network/test_session_manager.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_network/test_session_manager.py`:

```python
import pytest
from unittest.mock import AsyncMock, patch, MagicMock
from datetime import datetime, timedelta
import uuid
from app.network.session_manager import SessionManager

@pytest.fixture
def manager():
    return SessionManager(wifi_if="wlan0", wan_if="eth0")

@pytest.mark.asyncio
async def test_create_session_adds_whitelist(manager):
    mock_db = AsyncMock()
    mock_db.add = MagicMock()
    mock_db.commit = AsyncMock()
    mock_db.refresh = AsyncMock()

    with patch("app.network.session_manager.add_whitelist") as mock_ipt, \
         patch("app.network.session_manager.apply_bandwidth_limit") as mock_tc, \
         patch("app.network.session_manager.get_mac_for_ip", return_value="aa:bb:cc:dd:ee:ff"):

        await manager.create_session(
            db=mock_db,
            ip="192.168.1.45",
            guest_id=uuid.uuid4(),
            expires_at=datetime.utcnow() + timedelta(hours=24),
            bandwidth_up_kbps=0,
            bandwidth_down_kbps=0,
        )
        mock_ipt.assert_called_once_with("192.168.1.45")

@pytest.mark.asyncio
async def test_expire_session_removes_whitelist(manager):
    mock_db = AsyncMock()
    mock_session = MagicMock()
    mock_session.ip_address = "192.168.1.45"
    mock_session.status.value = "active"

    with patch("app.network.session_manager.remove_whitelist") as mock_ipt, \
         patch("app.network.session_manager.remove_bandwidth_limit") as mock_tc:
        await manager.expire_session(db=mock_db, session=mock_session)
        mock_ipt.assert_called_once_with("192.168.1.45")
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_network/test_session_manager.py -v
```

- [ ] **Step 3: Create `app/network/session_manager.py`**

```python
import uuid
import logging
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, update
from app.core.models import Session, SessionStatus
from app.network.iptables import add_whitelist, remove_whitelist
from app.network.tc import apply_bandwidth_limit, remove_bandwidth_limit
from app.network.arp import get_mac_for_ip
from app.core.config import settings

logger = logging.getLogger(__name__)

class SessionManager:
    def __init__(self, wifi_if: str = None, wan_if: str = None):
        self.wifi_if = wifi_if or settings.WIFI_INTERFACE
        self.wan_if = wan_if or settings.WAN_INTERFACE

    async def create_session(
        self, db: AsyncSession, ip: str,
        expires_at: datetime,
        bandwidth_up_kbps: int = 0,
        bandwidth_down_kbps: int = 0,
        guest_id: uuid.UUID | None = None,
        voucher_id: uuid.UUID | None = None,
    ) -> Session:
        mac = get_mac_for_ip(ip)
        session = Session(
            ip_address=ip,
            mac_address=mac,
            guest_id=guest_id,
            voucher_id=voucher_id,
            expires_at=expires_at,
            status=SessionStatus.active,
        )
        db.add(session)
        await db.commit()
        await db.refresh(session)
        add_whitelist(ip)
        apply_bandwidth_limit(ip, bandwidth_up_kbps, bandwidth_down_kbps, self.wan_if)
        logger.info(f"Session created: {session.id} for {ip}")
        return session

    async def expire_session(self, db: AsyncSession, session: Session, status: SessionStatus = SessionStatus.expired) -> None:
        remove_whitelist(session.ip_address)
        remove_bandwidth_limit(session.ip_address, self.wan_if)
        session.status = status
        await db.commit()
        logger.info(f"Session {session.id} expired ({status.value})")

    async def expire_overdue_sessions(self, db: AsyncSession) -> int:
        result = await db.execute(
            select(Session).where(
                Session.status == SessionStatus.active,
                Session.expires_at <= datetime.utcnow()
            )
        )
        sessions = result.scalars().all()
        for s in sessions:
            await self.expire_session(db, s)
        return len(sessions)
```

- [ ] **Step 4: Create `app/network/scheduler.py`**

```python
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from app.core.database import AsyncSessionFactory
from app.network.session_manager import SessionManager
import logging

logger = logging.getLogger(__name__)
scheduler = AsyncIOScheduler()
_manager = SessionManager()

async def _expire_job():
    async with AsyncSessionFactory() as db:
        count = await _manager.expire_overdue_sessions(db)
        if count:
            logger.info(f"Scheduler expired {count} sessions")

def start_scheduler():
    scheduler.add_job(_expire_job, "interval", seconds=60, id="expire_sessions")
    scheduler.start()
    logger.info("Session expiry scheduler started")

def stop_scheduler():
    scheduler.shutdown()
```

- [ ] **Step 5: Run tests — expect PASS**

```bash
pytest tests/test_network/ -v
```

- [ ] **Step 6: Commit**

```bash
git add . && git commit -m "feat: session manager with iptables/tc integration and expiry scheduler"
```

---

## Task 7: PMS Base + Standalone Adapter

**Files:**
- Create: `app/pms/base.py`
- Create: `app/pms/standalone.py`
- Create: `app/pms/factory.py`
- Test: `tests/test_pms/test_standalone.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_pms/test_standalone.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
import uuid
from app.pms.standalone import StandaloneAdapter
from app.pms.base import GuestInfo

@pytest.fixture
def adapter():
    return StandaloneAdapter()

@pytest.mark.asyncio
async def test_verify_guest_found(adapter):
    mock_guest = MagicMock()
    mock_guest.pms_guest_id = str(uuid.uuid4())
    mock_guest.room_number = "101"
    mock_guest.last_name = "Smith"
    mock_guest.first_name = "John"
    mock_guest.check_in = datetime.utcnow() - timedelta(hours=2)
    mock_guest.check_out = datetime.utcnow() + timedelta(hours=22)

    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_guest
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await adapter.verify_guest("101", "Smith", db=mock_db)
    assert isinstance(result, GuestInfo)
    assert result.room_number == "101"

@pytest.mark.asyncio
async def test_verify_guest_not_found(adapter):
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    result = await adapter.verify_guest("999", "Nobody", db=mock_db)
    assert result is None

@pytest.mark.asyncio
async def test_health_check_returns_true(adapter):
    assert await adapter.health_check() is True
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_pms/test_standalone.py -v
```

- [ ] **Step 3: Create `app/pms/base.py`**

```python
from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import datetime

@dataclass
class GuestInfo:
    pms_id: str
    room_number: str
    last_name: str
    check_in: datetime
    check_out: datetime
    first_name: str | None = None

class PMSAdapter(ABC):
    @abstractmethod
    async def verify_guest(self, room: str, last_name: str, **kwargs) -> GuestInfo | None:
        """Verify guest is currently checked in. Returns GuestInfo or None."""

    @abstractmethod
    async def get_guest_by_room(self, room: str, **kwargs) -> GuestInfo | None:
        """Get current guest in room. Returns GuestInfo or None."""

    @abstractmethod
    async def health_check(self) -> bool:
        """Check connectivity to PMS. Returns True if healthy."""

    async def get_checkouts_since(self, since: datetime, **kwargs) -> list[str]:
        """Return room numbers that checked out since given time. Override for PMS sync."""
        return []
```

- [ ] **Step 4: Create `app/pms/standalone.py`**

```python
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from app.pms.base import PMSAdapter, GuestInfo
from app.core.models import Guest
import logging

logger = logging.getLogger(__name__)

class StandaloneAdapter(PMSAdapter):
    """Manages guests entirely in local DB. No external PMS."""

    async def verify_guest(self, room: str, last_name: str, db: AsyncSession = None, **kwargs) -> GuestInfo | None:
        now = datetime.utcnow()
        result = await db.execute(
            select(Guest).where(
                and_(
                    Guest.room_number == room,
                    Guest.last_name.ilike(last_name),
                    Guest.check_in <= now,
                    Guest.check_out >= now,
                )
            )
        )
        guest = result.scalar_one_or_none()
        if not guest:
            return None
        return GuestInfo(
            pms_id=str(guest.id),
            room_number=guest.room_number,
            last_name=guest.last_name,
            first_name=guest.first_name,
            check_in=guest.check_in,
            check_out=guest.check_out,
        )

    async def get_guest_by_room(self, room: str, db: AsyncSession = None, **kwargs) -> GuestInfo | None:
        now = datetime.utcnow()
        result = await db.execute(
            select(Guest).where(
                and_(Guest.room_number == room, Guest.check_in <= now, Guest.check_out >= now)
            )
        )
        guest = result.scalar_one_or_none()
        if not guest:
            return None
        return GuestInfo(
            pms_id=str(guest.id),
            room_number=guest.room_number,
            last_name=guest.last_name,
            first_name=guest.first_name,
            check_in=guest.check_in,
            check_out=guest.check_out,
        )

    async def health_check(self) -> bool:
        return True
```

- [ ] **Step 5: Create `app/pms/factory.py`**

```python
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.models import PMSAdapter as PMSAdapterModel, PMSAdapterType
from app.pms.base import PMSAdapter
from app.pms.standalone import StandaloneAdapter
import logging

logger = logging.getLogger(__name__)
_active_adapter: PMSAdapter | None = None

async def load_adapter(db: AsyncSession) -> PMSAdapter:
    global _active_adapter
    result = await db.execute(
        select(PMSAdapterModel).where(PMSAdapterModel.is_active == True)
    )
    record = result.scalar_one_or_none()
    if not record or record.type == PMSAdapterType.standalone:
        _active_adapter = StandaloneAdapter()
    else:
        # Plan 2 adds Opera, Cloudbeds, Mews, Custom
        logger.warning(f"Adapter type {record.type} not yet implemented, falling back to standalone")
        _active_adapter = StandaloneAdapter()
    return _active_adapter

def get_adapter() -> PMSAdapter:
    if _active_adapter is None:
        return StandaloneAdapter()
    return _active_adapter
```

- [ ] **Step 6: Run tests — expect PASS**

```bash
pytest tests/test_pms/ -v
```

- [ ] **Step 7: Commit**

```bash
git add . && git commit -m "feat: PMS adapter base class, Standalone adapter, factory"
```

---

## Task 8: Voucher Generator

**Files:**
- Create: `app/voucher/generator.py`
- Test: `tests/test_voucher/test_generator.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_voucher/test_generator.py`:

```python
import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from datetime import datetime, timedelta
from app.voucher.generator import generate_code, validate_voucher, VoucherValidationError

def test_generate_code_format():
    code = generate_code()
    assert len(code) == 8
    assert code.isupper()
    assert code.isalnum()

def test_generate_code_unique():
    codes = {generate_code() for _ in range(100)}
    assert len(codes) == 100

@pytest.mark.asyncio
async def test_validate_valid_voucher():
    mock_db = AsyncMock()
    mock_voucher = MagicMock()
    mock_voucher.used_count = 0
    mock_voucher.max_uses = 5
    mock_voucher.expires_at = None
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_voucher
    mock_db.execute = AsyncMock(return_value=mock_result)

    voucher = await validate_voucher("ABCD1234", db=mock_db)
    assert voucher == mock_voucher

@pytest.mark.asyncio
async def test_validate_nonexistent_voucher_raises():
    mock_db = AsyncMock()
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = None
    mock_db.execute = AsyncMock(return_value=mock_result)

    with pytest.raises(VoucherValidationError, match="invalid_code"):
        await validate_voucher("INVALID1", db=mock_db)

@pytest.mark.asyncio
async def test_validate_exhausted_voucher_raises():
    mock_db = AsyncMock()
    mock_voucher = MagicMock()
    mock_voucher.used_count = 5
    mock_voucher.max_uses = 5
    mock_voucher.expires_at = None
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = mock_voucher
    mock_db.execute = AsyncMock(return_value=mock_result)

    with pytest.raises(VoucherValidationError, match="no_uses_remaining"):
        await validate_voucher("USED1234", db=mock_db)
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_voucher/ -v
```

- [ ] **Step 3: Create `app/voucher/generator.py`**

```python
import random
import string
from datetime import datetime
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.models import Voucher

class VoucherValidationError(Exception):
    def __init__(self, reason: str):
        self.reason = reason
        super().__init__(reason)

def generate_code(length: int = 8) -> str:
    chars = string.ascii_uppercase + string.digits
    # Remove ambiguous chars
    chars = chars.replace("0", "").replace("O", "").replace("I", "").replace("1", "")
    return "".join(random.choices(chars, k=length))

async def validate_voucher(code: str, db: AsyncSession) -> Voucher:
    result = await db.execute(select(Voucher).where(Voucher.code == code))
    voucher = result.scalar_one_or_none()
    if not voucher:
        raise VoucherValidationError("invalid_code")
    if voucher.expires_at and voucher.expires_at < datetime.utcnow():
        raise VoucherValidationError("expired")
    if voucher.used_count >= voucher.max_uses:
        raise VoucherValidationError("no_uses_remaining")
    return voucher
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
pytest tests/test_voucher/ -v
```

- [ ] **Step 5: Commit**

```bash
git add . && git commit -m "feat: voucher code generator and validation"
```

---

## Task 9: Rate Limiter

**Files:**
- Create: `app/core/rate_limit.py`
- Test: `tests/test_core/test_rate_limit.py`

- [ ] **Step 1: Write failing tests**

Create `tests/test_core/test_rate_limit.py`:

```python
import pytest
from unittest.mock import AsyncMock
from app.core.rate_limit import check_rate_limit, RateLimitExceeded

@pytest.mark.asyncio
async def test_allows_under_limit():
    mock_redis = AsyncMock()
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock()
    # Should not raise
    await check_rate_limit("192.168.1.45", mock_redis, max_attempts=5, window_seconds=600)

@pytest.mark.asyncio
async def test_blocks_over_limit():
    mock_redis = AsyncMock()
    mock_redis.incr = AsyncMock(return_value=6)
    mock_redis.expire = AsyncMock()
    with pytest.raises(RateLimitExceeded):
        await check_rate_limit("192.168.1.45", mock_redis, max_attempts=5, window_seconds=600)
```

- [ ] **Step 2: Run — expect FAIL**

```bash
pytest tests/test_core/test_rate_limit.py -v
```

- [ ] **Step 3: Create `app/core/rate_limit.py`**

```python
class RateLimitExceeded(Exception):
    pass

async def check_rate_limit(ip: str, redis_client, max_attempts: int, window_seconds: int) -> None:
    key = f"rate_limit:auth:{ip}"
    count = await redis_client.incr(key)
    if count == 1:
        await redis_client.expire(key, window_seconds)
    if count > max_attempts:
        raise RateLimitExceeded(f"Too many attempts from {ip}")
```

- [ ] **Step 4: Run — expect PASS**

```bash
pytest tests/test_core/test_rate_limit.py -v
```

- [ ] **Step 5: Commit**

```bash
git add . && git commit -m "feat: Redis-based auth rate limiter"
```

---

## Task 10: Portal Routes + conftest

**Files:**
- Create: `tests/conftest.py`
- Create: `app/portal/schemas.py`
- Create: `app/portal/router.py`
- Test: `tests/test_portal/test_portal_routes.py`

- [ ] **Step 1: Create `tests/conftest.py`**

```python
import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock

@pytest.fixture(scope="session")
def anyio_backend():
    return "asyncio"

@pytest_asyncio.fixture
async def client():
    # Patch iptables, tc, DB for portal tests
    with patch("app.network.iptables.add_whitelist"), \
         patch("app.network.iptables.remove_whitelist"), \
         patch("app.network.tc.apply_bandwidth_limit"), \
         patch("app.network.tc.remove_bandwidth_limit"), \
         patch("app.network.arp.get_mac_for_ip", return_value=None), \
         patch("app.network.scheduler.start_scheduler"), \
         patch("app.pms.factory.load_adapter"):
        from app.main import app
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c
```

- [ ] **Step 2: Write failing portal route tests**

Create `tests/test_portal/test_portal_routes.py`:

```python
import pytest
from unittest.mock import patch, AsyncMock, MagicMock
from datetime import datetime, timedelta
from app.pms.base import GuestInfo

@pytest.mark.asyncio
async def test_get_portal_login_page(client):
    response = await client.get("/")
    assert response.status_code == 200
    assert "text/html" in response.headers["content-type"]

@pytest.mark.asyncio
async def test_auth_room_success(client):
    guest_info = GuestInfo(
        pms_id="pms-1", room_number="101", last_name="Smith",
        check_in=datetime.utcnow() - timedelta(hours=1),
        check_out=datetime.utcnow() + timedelta(hours=23),
    )
    with patch("app.portal.router.get_adapter") as mock_adapter_fn, \
         patch("app.portal.router.session_manager") as mock_sm, \
         patch("app.portal.router.get_db"):
        mock_adapter = AsyncMock()
        mock_adapter.verify_guest = AsyncMock(return_value=guest_info)
        mock_adapter_fn.return_value = mock_adapter
        mock_sm.create_session = AsyncMock(return_value=MagicMock(id="sess-1", expires_at=datetime.utcnow() + timedelta(hours=8)))

        response = await client.post("/auth/room", json={
            "room_number": "101", "last_name": "Smith", "tc_accepted": True
        })
        assert response.status_code == 200
        data = response.json()
        assert "session_id" in data

@pytest.mark.asyncio
async def test_auth_room_wrong_credentials(client):
    with patch("app.portal.router.get_adapter") as mock_adapter_fn, \
         patch("app.portal.router.get_db"):
        mock_adapter = AsyncMock()
        mock_adapter.verify_guest = AsyncMock(return_value=None)
        mock_adapter_fn.return_value = mock_adapter

        response = await client.post("/auth/room", json={
            "room_number": "101", "last_name": "Wrong", "tc_accepted": True
        })
        assert response.status_code == 401
        assert response.json()["error"] == "guest_not_checked_in"

@pytest.mark.asyncio
async def test_auth_room_tc_not_accepted(client):
    response = await client.post("/auth/room", json={
        "room_number": "101", "last_name": "Smith", "tc_accepted": False
    })
    assert response.status_code == 422
```

- [ ] **Step 3: Run — expect FAIL**

```bash
pytest tests/test_portal/ -v
```

- [ ] **Step 4: Create `app/portal/schemas.py`**

```python
from pydantic import BaseModel, field_validator
from datetime import datetime

class RoomAuthRequest(BaseModel):
    room_number: str
    last_name: str
    tc_accepted: bool

    @field_validator("tc_accepted")
    @classmethod
    def must_accept_tc(cls, v):
        if not v:
            raise ValueError("Must accept terms and conditions")
        return v

class VoucherAuthRequest(BaseModel):
    code: str
    tc_accepted: bool

    @field_validator("tc_accepted")
    @classmethod
    def must_accept_tc(cls, v):
        if not v:
            raise ValueError("Must accept terms and conditions")
        return v

class SessionResponse(BaseModel):
    session_id: str
    expires_at: datetime
```

- [ ] **Step 5: Create `app/portal/router.py`**

```python
from datetime import datetime, timedelta
from fastapi import APIRouter, Request, Depends, HTTPException
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.database import get_db
from app.core.config import settings
from app.core.rate_limit import check_rate_limit, RateLimitExceeded
from app.pms.factory import get_adapter
from app.network.session_manager import SessionManager
from app.voucher.generator import validate_voucher, VoucherValidationError
from app.portal.schemas import RoomAuthRequest, VoucherAuthRequest, SessionResponse
import logging

logger = logging.getLogger(__name__)
router = APIRouter()
templates = Jinja2Templates(directory="app/portal/templates")
session_manager = SessionManager()

async def _get_redis(request: Request):
    return request.app.state.redis

@router.get("/", response_class=HTMLResponse)
async def portal_login(request: Request):
    return templates.TemplateResponse("login.html", {"request": request})

@router.post("/auth/room")
async def auth_room(
    request: Request,
    body: RoomAuthRequest,
    db: AsyncSession = Depends(get_db),
):
    redis = await _get_redis(request)
    try:
        await check_rate_limit(
            request.client.host, redis,
            max_attempts=settings.AUTH_RATE_LIMIT_ATTEMPTS,
            window_seconds=settings.AUTH_RATE_LIMIT_WINDOW_SECONDS,
        )
    except RateLimitExceeded:
        raise HTTPException(status_code=429, detail={"error": "rate_limited"})

    adapter = get_adapter()
    guest_info = await adapter.verify_guest(body.room_number, body.last_name, db=db)
    if not guest_info:
        raise HTTPException(status_code=401, detail={"error": "guest_not_checked_in"})

    # Look up room policy for session duration + bandwidth limits
    from sqlalchemy import select as sa_select
    from app.core.models import Room, Policy
    room_result = await db.execute(sa_select(Room).where(Room.number == body.room_number))
    room = room_result.scalar_one_or_none()
    policy = None
    if room and room.policy_id:
        policy_result = await db.execute(sa_select(Policy).where(Policy.id == room.policy_id))
        policy = policy_result.scalar_one_or_none()

    if policy and policy.session_duration_min > 0:
        expires_at = min(guest_info.check_out, datetime.utcnow() + timedelta(minutes=policy.session_duration_min))
    else:
        expires_at = guest_info.check_out

    up_kbps = policy.bandwidth_up_kbps if policy else 0
    down_kbps = policy.bandwidth_down_kbps if policy else 0

    session = await session_manager.create_session(
        db=db, ip=request.client.host,
        guest_id=None,
        expires_at=expires_at,
        bandwidth_up_kbps=up_kbps,
        bandwidth_down_kbps=down_kbps,
    )
    return SessionResponse(session_id=str(session.id), expires_at=session.expires_at)

@router.post("/auth/voucher")
async def auth_voucher(
    request: Request,
    body: VoucherAuthRequest,
    db: AsyncSession = Depends(get_db),
):
    redis = await _get_redis(request)
    try:
        await check_rate_limit(
            request.client.host, redis,
            max_attempts=settings.AUTH_RATE_LIMIT_ATTEMPTS,
            window_seconds=settings.AUTH_RATE_LIMIT_WINDOW_SECONDS,
        )
    except RateLimitExceeded:
        raise HTTPException(status_code=429, detail={"error": "rate_limited"})

    try:
        voucher = await validate_voucher(body.code, db=db)
    except VoucherValidationError as e:
        raise HTTPException(status_code=401, detail={"error": e.reason})

    if voucher.duration_minutes:
        expires_at = datetime.utcnow() + timedelta(minutes=voucher.duration_minutes)
    else:
        expires_at = datetime.utcnow() + timedelta(hours=24)

    session = await session_manager.create_session(
        db=db, ip=request.client.host,
        voucher_id=voucher.id,
        expires_at=expires_at,
    )
    voucher.used_count += 1
    await db.commit()
    return SessionResponse(session_id=str(session.id), expires_at=session.expires_at)

@router.get("/success", response_class=HTMLResponse)
async def portal_success(request: Request):
    return templates.TemplateResponse("success.html", {"request": request})

@router.get("/expired", response_class=HTMLResponse)
async def portal_expired(request: Request):
    return templates.TemplateResponse("expired.html", {"request": request})

@router.post("/session/disconnect")
async def disconnect(request: Request, db: AsyncSession = Depends(get_db)):
    from sqlalchemy import select
    from app.core.models import Session, SessionStatus
    result = await db.execute(
        select(Session).where(
            Session.ip_address == request.client.host,
            Session.status == SessionStatus.active
        )
    )
    session = result.scalar_one_or_none()
    if session:
        await session_manager.expire_session(db, session, SessionStatus.kicked)
    return {"status": "disconnected"}
```

- [ ] **Step 6: Run tests — expect PASS**

```bash
pytest tests/test_portal/ -v
```

- [ ] **Step 7: Commit**

```bash
git add . && git commit -m "feat: portal auth routes — room and voucher authentication"
```

---

## Task 11: Portal Templates (Glassmorphism)

**Files:**
- Create: `app/portal/templates/login.html`
- Create: `app/portal/templates/success.html`
- Create: `app/portal/templates/expired.html`
- Create: `app/portal/templates/error.html`
- Create: `static/css/portal.css`

> **Note:** Use the `frontend-design` skill when implementing these templates.

- [ ] **Step 1: Create base Glassmorphism CSS**

Create `static/css/portal.css`:

```css
/* Glassmorphism base — variables override per hotel brand config */
:root {
    --primary: #6366f1;
    --bg-from: #1a1a2e;
    --bg-to: #0f3460;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body {
    font-family: 'Inter', system-ui, sans-serif;
    min-height: 100vh;
    background: linear-gradient(135deg, var(--bg-from) 0%, #16213e 50%, var(--bg-to) 100%);
    color: white;
}
.glass {
    background: rgba(255,255,255,0.08);
    backdrop-filter: blur(12px);
    -webkit-backdrop-filter: blur(12px);
    border: 1px solid rgba(255,255,255,0.15);
    border-radius: 16px;
}
.btn-primary {
    background: linear-gradient(90deg, var(--primary), #8b5cf6);
    border: none; border-radius: 8px; color: white;
    padding: 0.75rem 1.5rem; font-weight: 600; cursor: pointer; width: 100%;
    font-size: 1rem; transition: opacity 0.2s;
}
.btn-primary:hover { opacity: 0.9; }
.input-field {
    width: 100%; padding: 0.75rem 1rem;
    background: rgba(255,255,255,0.07);
    border: 1px solid rgba(255,255,255,0.15);
    border-radius: 8px; color: white; font-size: 0.95rem;
}
.input-field::placeholder { color: rgba(255,255,255,0.4); }
.input-field:focus { outline: none; border-color: var(--primary); }
.tab { cursor: pointer; padding: 0.4rem 1rem; border-radius: 6px; font-size: 0.9rem; color: rgba(255,255,255,0.5); }
.tab.active { background: rgba(255,255,255,0.15); color: white; }
```

- [ ] **Step 2: Create `app/portal/templates/login.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{{ hotel_name|default('Hotel WiFi') }} — Login</title>
    <link rel="stylesheet" href="/static/css/portal.css">
</head>
<body>
<div style="display:grid;grid-template-columns:1fr 1fr;min-height:100vh">
    <!-- Left: Branding -->
    <div style="display:flex;flex-direction:column;align-items:center;justify-content:center;padding:3rem;border-right:1px solid rgba(255,255,255,0.08)">
        <div style="font-size:3rem;margin-bottom:1rem">🏨</div>
        <h1 style="font-size:1.8rem;font-weight:800;letter-spacing:0.05em;margin-bottom:0.5rem">
            {{ hotel_name|default('Grand Hotel') }}
        </h1>
        <p style="color:rgba(255,255,255,0.5);font-size:0.9rem;text-align:center">Complimentary WiFi Access</p>
        <div style="margin:2rem 0;width:40px;height:1px;background:rgba(255,255,255,0.2)"></div>
        <div style="color:rgba(255,255,255,0.35);font-size:0.8rem;text-align:center">
            <p>Available throughout your stay</p>
        </div>
    </div>
    <!-- Right: Form -->
    <div style="display:flex;align-items:center;justify-content:center;padding:3rem">
        <div class="glass" style="width:100%;max-width:380px;padding:2rem">
            <h2 style="font-size:1.3rem;font-weight:700;margin-bottom:0.5rem">Sign In</h2>
            <p style="color:rgba(255,255,255,0.5);font-size:0.85rem;margin-bottom:1.5rem">Enter your room details to connect</p>

            <!-- Tabs -->
            <div style="display:flex;gap:0.5rem;background:rgba(0,0,0,0.2);border-radius:8px;padding:4px;margin-bottom:1.5rem">
                <div class="tab active" id="tab-room" onclick="switchTab('room')">Room Guest</div>
                <div class="tab" id="tab-voucher" onclick="switchTab('voucher')">Voucher Code</div>
            </div>

            <!-- Room form -->
            <form id="form-room" onsubmit="submitRoom(event)">
                <div style="margin-bottom:1rem">
                    <label style="font-size:0.8rem;color:rgba(255,255,255,0.6);display:block;margin-bottom:0.4rem">Room Number</label>
                    <input class="input-field" name="room_number" placeholder="e.g. 101" required>
                </div>
                <div style="margin-bottom:1.5rem">
                    <label style="font-size:0.8rem;color:rgba(255,255,255,0.6);display:block;margin-bottom:0.4rem">Last Name</label>
                    <input class="input-field" name="last_name" placeholder="e.g. Smith" required>
                </div>
                <div style="margin-bottom:1.5rem;display:flex;align-items:flex-start;gap:0.5rem">
                    <input type="checkbox" id="tc-room" style="margin-top:3px">
                    <label for="tc-room" style="font-size:0.78rem;color:rgba(255,255,255,0.5)">
                        I agree to the <a href="#" style="color:rgba(255,255,255,0.7)">Terms & Conditions</a>
                    </label>
                </div>
                <div id="error-room" style="color:#f87171;font-size:0.8rem;margin-bottom:0.75rem;display:none"></div>
                <button class="btn-primary" type="submit">Connect →</button>
            </form>

            <!-- Voucher form -->
            <form id="form-voucher" style="display:none" onsubmit="submitVoucher(event)">
                <div style="margin-bottom:1.5rem">
                    <label style="font-size:0.8rem;color:rgba(255,255,255,0.6);display:block;margin-bottom:0.4rem">Voucher Code</label>
                    <input class="input-field" name="code" placeholder="e.g. ABCD1234" required
                           style="text-transform:uppercase;letter-spacing:0.1em">
                </div>
                <div style="margin-bottom:1.5rem;display:flex;align-items:flex-start;gap:0.5rem">
                    <input type="checkbox" id="tc-voucher" style="margin-top:3px">
                    <label for="tc-voucher" style="font-size:0.78rem;color:rgba(255,255,255,0.5)">
                        I agree to the <a href="#" style="color:rgba(255,255,255,0.7)">Terms & Conditions</a>
                    </label>
                </div>
                <div id="error-voucher" style="color:#f87171;font-size:0.8rem;margin-bottom:0.75rem;display:none"></div>
                <button class="btn-primary" type="submit">Connect →</button>
            </form>
        </div>
    </div>
</div>
<script>
function switchTab(tab) {
    document.getElementById('form-room').style.display = tab === 'room' ? 'block' : 'none';
    document.getElementById('form-voucher').style.display = tab === 'voucher' ? 'block' : 'none';
    document.getElementById('tab-room').className = 'tab' + (tab === 'room' ? ' active' : '');
    document.getElementById('tab-voucher').className = 'tab' + (tab === 'voucher' ? ' active' : '');
}
async function submitRoom(e) {
    e.preventDefault();
    const f = e.target;
    const err = document.getElementById('error-room');
    err.style.display = 'none';
    if (!document.getElementById('tc-room').checked) { err.textContent = 'Please accept the Terms & Conditions'; err.style.display = 'block'; return; }
    const res = await fetch('/auth/room', { method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ room_number: f.room_number.value, last_name: f.last_name.value, tc_accepted: true }) });
    if (res.ok) { window.location.href = '/success'; }
    else { const d = await res.json(); err.textContent = {'guest_not_checked_in':'Room or name not found','pms_unavailable':'Service temporarily unavailable','rate_limited':'Too many attempts. Please wait.'}[d.detail?.error] || 'Authentication failed'; err.style.display = 'block'; }
}
async function submitVoucher(e) {
    e.preventDefault();
    const f = e.target;
    const err = document.getElementById('error-voucher');
    err.style.display = 'none';
    if (!document.getElementById('tc-voucher').checked) { err.textContent = 'Please accept the Terms & Conditions'; err.style.display = 'block'; return; }
    const res = await fetch('/auth/voucher', { method: 'POST', headers: {'Content-Type':'application/json'},
        body: JSON.stringify({ code: f.code.value.toUpperCase(), tc_accepted: true }) });
    if (res.ok) { window.location.href = '/success'; }
    else { const d = await res.json(); err.textContent = {'invalid_code':'Invalid voucher code','expired':'This voucher has expired','no_uses_remaining':'This voucher has been fully used','rate_limited':'Too many attempts. Please wait.'}[d.detail?.error] || 'Authentication failed'; err.style.display = 'block'; }
}
</script>
</body>
</html>
```

- [ ] **Step 3: Create `app/portal/templates/success.html`**

```html
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Connected — {{ hotel_name|default('Hotel WiFi') }}</title>
    <link rel="stylesheet" href="/static/css/portal.css">
</head>
<body style="display:flex;align-items:center;justify-content:center">
<div class="glass" style="text-align:center;padding:3rem;max-width:420px;width:90%">
    <div style="font-size:3rem;margin-bottom:1rem">✓</div>
    <h1 style="font-size:1.5rem;font-weight:700;margin-bottom:0.5rem">You're Connected!</h1>
    <p style="color:rgba(255,255,255,0.6);margin-bottom:2rem">Enjoy your stay and your internet access.</p>
    <button class="btn-primary" onclick="disconnect()" style="background:rgba(255,255,255,0.1);border:1px solid rgba(255,255,255,0.2)">
        Disconnect
    </button>
</div>
<script>
async function disconnect() {
    await fetch('/session/disconnect', { method: 'POST' });
    window.location.href = '/expired';
}
</script>
</body>
</html>
```

- [ ] **Step 4: Create `app/portal/templates/expired.html` and `error.html`**

`app/portal/templates/expired.html`:
```html
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Session Expired</title><link rel="stylesheet" href="/static/css/portal.css"></head>
<body style="display:flex;align-items:center;justify-content:center">
<div class="glass" style="text-align:center;padding:3rem;max-width:420px;width:90%">
    <div style="font-size:3rem;margin-bottom:1rem">⏱</div>
    <h1 style="font-size:1.5rem;font-weight:700;margin-bottom:0.5rem">Session Expired</h1>
    <p style="color:rgba(255,255,255,0.6);margin-bottom:2rem">Your WiFi session has ended. Sign in again to reconnect.</p>
    <a href="/" class="btn-primary" style="display:block;text-decoration:none;text-align:center;padding:0.75rem">Sign In Again</a>
</div>
</body>
</html>
```

`app/portal/templates/error.html`:
```html
<!DOCTYPE html>
<html lang="en">
<head><meta charset="UTF-8"><meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Error</title><link rel="stylesheet" href="/static/css/portal.css"></head>
<body style="display:flex;align-items:center;justify-content:center">
<div class="glass" style="text-align:center;padding:3rem;max-width:420px;width:90%">
    <div style="font-size:3rem;margin-bottom:1rem">⚠</div>
    <h1 style="font-size:1.5rem;font-weight:700;margin-bottom:0.5rem">Something went wrong</h1>
    <p style="color:rgba(255,255,255,0.6);margin-bottom:2rem">{{ message|default('Please try again or contact the front desk.') }}</p>
    <a href="/" class="btn-primary" style="display:block;text-decoration:none;text-align:center;padding:0.75rem">Try Again</a>
</div>
</body>
</html>
```

- [ ] **Step 5: Commit**

```bash
git add . && git commit -m "feat: portal templates — Glassmorphism split layout with tab switcher"
```

---

## Task 12: App Factory + Admin Stub + Startup

**Files:**
- Create: `app/admin/router.py`
- Create: `app/main.py`

- [ ] **Step 1: Create `app/admin/router.py` (stub)**

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from app.core.database import get_db
from app.core.models import Session, SessionStatus
from app.network.session_manager import SessionManager
import uuid

router = APIRouter(prefix="/admin")
session_manager = SessionManager()

@router.get("/sessions")
async def list_sessions(db: AsyncSession = Depends(get_db)):
    result = await db.execute(
        select(Session).where(Session.status == SessionStatus.active)
    )
    sessions = result.scalars().all()
    return [{"id": str(s.id), "ip": s.ip_address, "connected_at": s.connected_at, "expires_at": s.expires_at} for s in sessions]

@router.delete("/sessions/{session_id}")
async def kick_session(session_id: uuid.UUID, db: AsyncSession = Depends(get_db)):
    result = await db.execute(select(Session).where(Session.id == session_id))
    session = result.scalar_one_or_none()
    if not session:
        return {"error": "not_found"}
    await session_manager.expire_session(db, session, SessionStatus.kicked)
    return {"status": "kicked"}
```

- [ ] **Step 2: Create `app/main.py`**

```python
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
import redis.asyncio as aioredis
from app.core.config import settings
from app.core.database import engine
from app.portal.router import router as portal_router
from app.admin.router import router as admin_router
from app.network.scheduler import start_scheduler, stop_scheduler

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    app.state.redis = aioredis.from_url(settings.REDIS_URL, decode_responses=False)
    start_scheduler()
    yield
    # Shutdown
    stop_scheduler()
    await app.state.redis.aclose()
    await engine.dispose()

app = FastAPI(title="Hotel WiFi Captive Portal", lifespan=lifespan)
app.mount("/static", StaticFiles(directory="static"), name="static")
app.include_router(portal_router)
app.include_router(admin_router)
```

- [ ] **Step 3: Run all tests**

```bash
pytest tests/ -v --cov=app --cov-report=term-missing
```

Expected: All tests PASS, coverage > 70%

- [ ] **Step 4: Commit**

```bash
git add . && git commit -m "feat: FastAPI app factory, admin stub, lifespan startup/shutdown"
```

---

## Task 13: Scripts + Final Wiring

**Files:**
- Create: `scripts/setup-iptables.sh`
- Create: `scripts/setup-tc.sh`
- Create: `alembic.ini` (update DATABASE_URL reference)

- [ ] **Step 1: Create `scripts/setup-iptables.sh`**

```bash
#!/bin/bash
set -e
WIFI_IF="${WIFI_IF:-wlan0}"
PORTAL_IP="${PORTAL_IP:-192.168.1.1}"
PORTAL_PORT="${PORTAL_PORT:-8080}"

echo "Setting up iptables for captive portal..."
# Flush existing rules
iptables -F FORWARD
iptables -t nat -F PREROUTING

# Default: drop unauthenticated forwarding
iptables -A FORWARD -i $WIFI_IF -j DROP

# Allow established connections
iptables -I FORWARD -i $WIFI_IF -m conntrack --ctstate ESTABLISHED,RELATED -j ACCEPT

# Redirect HTTP to portal
iptables -t nat -A PREROUTING -i $WIFI_IF -p tcp --dport 80 \
    -m conntrack ! --ctstate ESTABLISHED \
    -j DNAT --to $PORTAL_IP:$PORTAL_PORT

# Allow portal itself
iptables -t nat -A PREROUTING -i $WIFI_IF -p tcp --dport 53 -j ACCEPT
iptables -t nat -A PREROUTING -i $WIFI_IF -p udp --dport 53 -j ACCEPT

echo "iptables setup complete."
```

- [ ] **Step 2: Create `scripts/setup-tc.sh`**

```bash
#!/bin/bash
set -e
WAN_IF="${WAN_IF:-eth0}"

echo "Setting up tc HTB on $WAN_IF..."
# Remove existing
tc qdisc del dev $WAN_IF root 2>/dev/null || true

# Add HTB root qdisc (default class 999 = unlimited)
tc qdisc add dev $WAN_IF root handle 1: htb default 999

# Default unlimited class
tc class add dev $WAN_IF parent 1: classid 1:999 htb rate 1000mbit ceil 1000mbit

echo "tc HTB setup complete on $WAN_IF."
```

- [ ] **Step 3: Make scripts executable**

```bash
chmod +x scripts/setup-iptables.sh scripts/setup-tc.sh
```

- [ ] **Step 4: Run full test suite one final time**

```bash
pytest tests/ -v --cov=app --cov-report=term-missing
```

Expected: All tests PASS

- [ ] **Step 5: Final commit**

```bash
git add . && git commit -m "feat: iptables and tc setup scripts — Plan 1 complete"
```

---

## Verification

After completing all tasks, verify the portal works end-to-end:

```bash
# 1. Start PostgreSQL and Redis
# 2. Apply migrations
alembic upgrade head

# 3. Run the server
uvicorn app.main:app --host 0.0.0.0 --port 8080 --reload

# 4. Open browser to http://localhost:8080
# 5. Should see the Glassmorphism split login page

# 6. Run full test suite
pytest tests/ -v --cov=app --cov-report=html
```

---

## What's Next

- **Plan 2:** PMS Adapters (Opera/OHIP, Cloudbeds, Mews, Custom REST) + webhook endpoints
- **Plan 3:** Full Admin Dashboard (analytics, voucher management, brand config, PMS settings)
