import pytest
from unittest.mock import AsyncMock, MagicMock, patch


@pytest.mark.asyncio
async def test_get_dhcp_config_returns_defaults(client):
    from app.core.auth import create_access_token
    from app.main import app
    app.state.redis.exists = AsyncMock(return_value=False)
    token = create_access_token({"sub": "admin", "role": "superadmin"})
    with patch("app.network.dnsmasq.get_status", return_value={"running": False, "lease_count": 0, "config_file_exists": False}):
        resp = await client.get(
            "/admin/api/dhcp",
            headers={"Authorization": f"Bearer {token}"},
        )
    # With mock DB returning None, expect 404 (not seeded) or 200 with defaults
    assert resp.status_code in (200, 404)
    assert resp.status_code != 500


@pytest.mark.asyncio
async def test_update_dhcp_config(client):
    from app.core.auth import create_access_token
    from app.main import app
    app.state.redis.exists = AsyncMock(return_value=False)
    token = create_access_token({"sub": "admin", "role": "superadmin"})
    with patch("app.network.dnsmasq.write_config"), \
         patch("app.network.dnsmasq.reload_dnsmasq", return_value=True):
        resp = await client.put(
            "/admin/api/dhcp",
            json={"lease_time": "1h"},
            headers={"Authorization": f"Bearer {token}"},
        )
    # 404 from mock DB (no seeded row) or 200 — never 500
    assert resp.status_code in (200, 404)
    assert resp.status_code != 500


@pytest.mark.asyncio
async def test_staff_cannot_access_dhcp(client):
    from app.core.auth import create_access_token
    from app.main import app
    app.state.redis.exists = AsyncMock(return_value=False)
    token = create_access_token({"sub": "staff", "role": "staff"})
    resp = await client.get(
        "/admin/api/dhcp",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert resp.status_code == 403


@pytest.mark.asyncio
async def test_dhcp_leases_endpoint(client):
    from app.core.auth import create_access_token
    from app.main import app
    app.state.redis.exists = AsyncMock(return_value=False)
    token = create_access_token({"sub": "admin", "role": "superadmin"})
    with patch("app.network.dnsmasq.get_leases", return_value=[]):
        resp = await client.get(
            "/admin/api/dhcp/leases",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    assert isinstance(resp.json(), list)


@pytest.mark.asyncio
async def test_dhcp_status_endpoint(client):
    from app.core.auth import create_access_token
    from app.main import app
    app.state.redis.exists = AsyncMock(return_value=False)
    token = create_access_token({"sub": "admin", "role": "superadmin"})
    with patch("app.network.dnsmasq.get_status", return_value={"running": False, "lease_count": 0, "config_file_exists": False}):
        resp = await client.get(
            "/admin/api/dhcp/status",
            headers={"Authorization": f"Bearer {token}"},
        )
    assert resp.status_code == 200
    assert "running" in resp.json()
