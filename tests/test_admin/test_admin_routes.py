import pytest
import pytest_asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport


@pytest_asyncio.fixture
async def admin_client():
    with patch("app.network.nftables.NftablesManager.add_to_whitelist"), \
         patch("app.network.nftables.NftablesManager.remove_from_whitelist"), \
         patch("app.network.tc.apply_bandwidth_limit"), \
         patch("app.network.tc.remove_bandwidth_limit"), \
         patch("app.network.arp.get_mac_for_ip", return_value=None), \
         patch("app.network.scheduler.start_scheduler"), \
         patch("app.pms.factory.load_adapter"):
        from app.main import app
        from app.core.database import get_db
        from app.core.auth import create_access_token

        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        app.state.redis = AsyncMock()
        app.state.redis.incr = AsyncMock(return_value=1)
        app.state.redis.expire = AsyncMock()
        app.state.redis.exists = AsyncMock(return_value=False)

        token = create_access_token({"sub": "admin", "role": "superadmin"})
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as c:
            yield c
        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_list_sessions_returns_empty(admin_client):
    response = await admin_client.get("/admin/api/sessions")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_kick_nonexistent_session_returns_404(admin_client):
    fake_id = str(uuid.uuid4())
    response = await admin_client.delete(f"/admin/sessions/{fake_id}")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_sessions_rows_fragment_returns_html(client):
    from app.core.auth import create_access_token
    from app.main import app
    from unittest.mock import AsyncMock
    app.state.redis.exists = AsyncMock(return_value=False)
    token = create_access_token({"sub": "admin", "role": "superadmin"})
    resp = await client.get(
        "/admin/sessions/rows",
        cookies={"admin_token": token},
        headers={"Accept": "text/html"},
    )
    assert resp.status_code == 200
    assert b"session-tbody" in resp.content or b"No active sessions" in resp.content
