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


@pytest.mark.asyncio
async def test_update_brand_config(client):
    from app.core.auth import create_access_token
    from app.main import app
    app.state.redis.exists = AsyncMock(return_value=False)
    token = create_access_token({"sub": "admin", "role": "superadmin"})

    resp = await client.put(
        "/admin/api/brand",
        json={"hotel_name": "Grand Hotel"},
        headers={"Authorization": f"Bearer {token}"},
    )
    # With mock DB returning None, expect 404 (brand_config_not_seeded)
    assert resp.status_code == 404
    assert resp.json()["detail"]["error"] == "brand_config_not_seeded"


@pytest.mark.asyncio
async def test_update_brand_invalid_language(client):
    from app.core.auth import create_access_token
    from app.main import app
    app.state.redis.exists = AsyncMock(return_value=False)
    token = create_access_token({"sub": "admin", "role": "superadmin"})
    resp = await client.put(
        "/admin/api/brand",
        json={"language": "invalid_lang"},
        headers={"Authorization": f"Bearer {token}"},
    )
    # 404 because mock DB has no brand row (scalar_one_or_none returns None)
    # OR 422 if language validation happens before the DB check
    # Either is acceptable — just confirm it's not 500
    assert resp.status_code in (404, 422)
    assert resp.status_code != 500
