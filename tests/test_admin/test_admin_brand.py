import pytest
import io
from unittest.mock import AsyncMock, MagicMock

@pytest.mark.asyncio
async def test_get_brand_config_returns_defaults(client):
    from app.core.auth import create_access_token
    from app.main import app
    app.state.redis.exists = AsyncMock(return_value=False)
    token = create_access_token({"sub": "admin", "role": "superadmin"})
    resp = await client.get("/admin/api/brand", headers={"Authorization": f"Bearer {token}"})
    assert resp.status_code == 200
    data = resp.json()
    assert "hotel_name" in data
    assert "primary_color" in data

@pytest.mark.asyncio
async def test_logo_upload_rejects_invalid_mime(client):
    from app.core.auth import create_access_token
    from app.main import app
    app.state.redis.exists = AsyncMock(return_value=False)
    token = create_access_token({"sub": "admin", "role": "superadmin"})
    resp = await client.post(
        "/admin/brand/logo",
        files={"file": ("test.txt", io.BytesIO(b"not an image"), "text/plain")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 422

@pytest.mark.asyncio
async def test_logo_upload_rejects_large_file(client):
    from app.core.auth import create_access_token
    from app.main import app
    app.state.redis.exists = AsyncMock(return_value=False)
    token = create_access_token({"sub": "admin", "role": "superadmin"})
    big_data = b"x" * (2 * 1024 * 1024 + 1)
    resp = await client.post(
        "/admin/brand/logo",
        files={"file": ("big.jpg", io.BytesIO(big_data), "image/jpeg")},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 413
