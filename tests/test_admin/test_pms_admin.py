import pytest
import pytest_asyncio
import uuid
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport
from app.core.encryption import encrypt_config

@pytest_asyncio.fixture
async def admin_client():
    with patch("app.network.scheduler.start_scheduler"), \
         patch("app.pms.factory.load_adapter"):
        from app.main import app
        from app.core.database import get_db

        record = MagicMock()
        record.id = uuid.uuid4()
        record.type = MagicMock()
        record.type.value = "cloudbeds"
        record.is_active = True
        record.last_sync_at = None
        record.config_encrypted = encrypt_config(
            {"api_url": "https://api.cloudbeds.com", "api_key": "k", "property_id": "P1"}
        )
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = record
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)
        mock_db.commit = AsyncMock()

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        app.state.redis = AsyncMock()

        from app.core.auth import create_access_token
        token = create_access_token({"sub": "admin", "role": "superadmin"})
        async with AsyncClient(
            transport=ASGITransport(app=app),
            base_url="http://test",
            headers={"Authorization": f"Bearer {token}"},
        ) as c:
            yield c, mock_db

        app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_get_pms_returns_config_with_masked_credentials(admin_client):
    client, _ = admin_client
    resp = await client.get("/admin/pms")
    assert resp.status_code == 200
    data = resp.json()
    assert data["type"] == "cloudbeds"
    assert data["config"].get("api_key") == "***"

@pytest.mark.asyncio
async def test_put_pms_updates_config(admin_client):
    client, mock_db = admin_client
    with patch("app.admin.router.load_adapter", new_callable=AsyncMock):
        resp = await client.put("/admin/pms", json={
            "type": "cloudbeds",
            "config": {"api_url": "https://api.cloudbeds.com", "api_key": "new_key", "property_id": "P2"},
        })
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

@pytest.mark.asyncio
async def test_post_pms_test_returns_ok_true(admin_client):
    client, _ = admin_client
    with patch("app.pms.cloudbeds.CloudbedsAdapter.health_check", new_callable=AsyncMock, return_value=True):
        resp = await client.post("/admin/pms/test", json={
            "type": "cloudbeds",
            "config": {"api_url": "https://api.cloudbeds.com", "api_key": "k", "property_id": "P1"},
        })
    assert resp.status_code == 200
    assert resp.json()["ok"] is True

@pytest.mark.asyncio
async def test_post_pms_test_returns_ok_false_on_error(admin_client):
    client, _ = admin_client
    with patch("app.pms.cloudbeds.CloudbedsAdapter.health_check", new_callable=AsyncMock, return_value=False):
        resp = await client.post("/admin/pms/test", json={
            "type": "cloudbeds",
            "config": {"api_url": "https://api.cloudbeds.com", "api_key": "bad", "property_id": "P1"},
        })
    assert resp.status_code == 200
    assert resp.json()["ok"] is False

@pytest.mark.asyncio
async def test_post_pms_test_returns_ok_false_on_exception(admin_client):
    client, _ = admin_client
    with patch("app.pms.cloudbeds.CloudbedsAdapter.health_check", new_callable=AsyncMock, side_effect=Exception("connection refused")):
        resp = await client.post("/admin/pms/test", json={
            "type": "cloudbeds",
            "config": {"api_url": "https://api.cloudbeds.com", "api_key": "bad", "property_id": "P1"},
        })
    assert resp.status_code == 200
    data = resp.json()
    assert data["ok"] is False
    assert "connection refused" in data["error"]
