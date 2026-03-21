import pytest
from unittest.mock import AsyncMock, MagicMock
import uuid

@pytest.mark.asyncio
async def test_create_policy_returns_201(client):
    from app.core.auth import create_access_token
    from app.main import app
    app.state.redis.exists = AsyncMock(return_value=False)
    token = create_access_token({"sub": "admin", "role": "superadmin"})
    resp = await client.post(
        "/admin/api/policies",
        json={"name": "Standard", "bandwidth_up_kbps": 1024,
              "bandwidth_down_kbps": 5120, "session_duration_min": 0, "max_devices": 3},
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code in (200, 201)

@pytest.mark.asyncio
async def test_staff_cannot_access_policies(client):
    from app.core.auth import create_access_token
    from app.main import app
    app.state.redis.exists = AsyncMock(return_value=False)
    token = create_access_token({"sub": "staff", "role": "staff"})
    resp = await client.get(
        "/admin/api/policies",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403
