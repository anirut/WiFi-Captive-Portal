import pytest
import time
from unittest.mock import AsyncMock, patch
from jose import jwt

@pytest.mark.asyncio
async def test_access_token_contains_jti(client):
    """JWT must include jti claim."""
    from app.core.auth import create_access_token
    from app.core.config import settings
    token = create_access_token({"sub": "admin", "role": "superadmin"})
    payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    assert "jti" in payload
    assert len(payload["jti"]) == 36  # UUID format

@pytest.mark.asyncio
async def test_logout_blocklists_token(client):
    """POST /admin/logout should store jti in Redis blocklist."""
    from app.core.auth import create_access_token
    token = create_access_token({"sub": "admin", "role": "superadmin"})
    from app.main import app
    app.state.redis.exists = AsyncMock(return_value=False)
    app.state.redis.set = AsyncMock()
    resp = await client.post(
        "/admin/logout",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "logged_out"
    assert app.state.redis.set.called
    call_args = app.state.redis.set.call_args
    assert call_args[0][0].startswith("blocklist:")
    assert call_args[1].get("ex", 0) > 0  # TTL must be set

@pytest.mark.asyncio
async def test_blocklisted_token_rejected(client):
    """Request with blocklisted jti should return 401."""
    from app.core.auth import create_access_token
    token = create_access_token({"sub": "admin", "role": "superadmin"})
    from app.main import app
    app.state.redis.exists = AsyncMock(return_value=True)  # simulate blocklisted
    resp = await client.get(
        "/admin/sessions",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 401

@pytest.mark.asyncio
async def test_cookie_auth_accepted(client):
    """admin_token cookie should authenticate as Bearer equivalent."""
    from app.core.auth import create_access_token
    from app.main import app
    token = create_access_token({"sub": "admin", "role": "superadmin"})
    app.state.redis.exists = AsyncMock(return_value=False)
    resp = await client.get(
        "/admin/sessions",
        cookies={"admin_token": token},
    )
    assert resp.status_code == 200
