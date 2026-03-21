import pytest
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
import os
os.environ.setdefault("SECRET_KEY", "test_secret_key_32_chars_long_xxx")
os.environ.setdefault("ENCRYPTION_KEY", "AF7LzGfwqzgX6h8uF89ph9XUwy-_GilZDJp0zv2y0hs=")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")


def _make_app_with_db(mock_db):
    with patch("app.network.scheduler.start_scheduler"), \
         patch("app.pms.factory.load_adapter"):
        from app.main import app
        from app.core.database import get_db

        async def override():
            yield mock_db

        app.dependency_overrides[get_db] = override
        app.state.redis = AsyncMock()
        return app


@pytest.mark.asyncio
async def test_login_success():
    import bcrypt as _bcrypt
    from app.core.models import AdminUser, AdminRole
    user = MagicMock(spec=AdminUser)
    user.id = __import__("uuid").uuid4()
    user.username = "admin"
    user.password_hash = _bcrypt.hashpw(b"secret123", _bcrypt.gensalt()).decode()
    user.role = AdminRole.superadmin
    user.last_login_at = None

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = user
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    mock_db.commit = AsyncMock()

    app = _make_app_with_db(mock_db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/admin/login", json={"username": "admin", "password": "secret123"})

    assert resp.status_code == 200
    assert "access_token" in resp.json()
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_login_wrong_password():
    import bcrypt as _bcrypt
    from app.core.models import AdminUser
    user = MagicMock(spec=AdminUser)
    user.password_hash = _bcrypt.hashpw(b"correct", _bcrypt.gensalt()).decode()

    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = user
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    app = _make_app_with_db(mock_db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.post("/admin/login", json={"username": "admin", "password": "wrong"})

    assert resp.status_code == 401
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_sessions_without_token_returns_401():
    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    app = _make_app_with_db(mock_db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/admin/sessions")

    assert resp.status_code == 401
    app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_sessions_with_valid_token_returns_200():
    from app.core.auth import create_access_token
    token = create_access_token({"sub": "admin", "role": "superadmin"})

    mock_result = MagicMock()
    mock_result.scalars.return_value.all.return_value = []
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)

    app = _make_app_with_db(mock_db)
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
        resp = await c.get("/admin/sessions",
                           headers={"Authorization": f"Bearer {token}"})

    assert resp.status_code == 200
    app.dependency_overrides.clear()
