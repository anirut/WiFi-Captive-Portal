import pytest
import hmac
import hashlib
from unittest.mock import AsyncMock, MagicMock, patch
from httpx import AsyncClient, ASGITransport

# Set env vars before importing app
import os
os.environ.setdefault("SECRET_KEY", "test_secret_key_32_chars_long_xxx")
os.environ.setdefault("ENCRYPTION_KEY", "AF7LzGfwqzgX6h8uF89ph9XUwy-_GilZDJp0zv2y0hs=")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

SECRET = "webhook_secret_123"
SECRET_HASH = hashlib.sha256(SECRET.encode()).hexdigest()

def _make_db_with_adapter(adapter_type_value, webhook_secret_hash):
    record = MagicMock()
    record.type.value = adapter_type_value
    record.webhook_secret = webhook_secret_hash
    mock_result = MagicMock()
    mock_result.scalar_one_or_none.return_value = record
    mock_db = AsyncMock()
    mock_db.execute = AsyncMock(return_value=mock_result)
    return mock_db

@pytest.mark.asyncio
async def test_webhook_opera_cloud_checkout():
    with patch("app.network.scheduler.start_scheduler"), \
         patch("app.pms.factory.load_adapter"):
        from app.main import app
        from app.core.database import get_db

        mock_db = _make_db_with_adapter("opera_cloud", SECRET_HASH)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        app.state.redis = AsyncMock()

        import uuid
        adapter_id = str(uuid.uuid4())

        with patch("app.pms.webhook_router.expire_sessions_for_room", new_callable=AsyncMock) as mock_expire:
            async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
                resp = await c.post(
                    f"/internal/pms/webhook/{adapter_id}",
                    json={"eventType": "CHECKED_OUT", "roomNumber": "101"},
                    headers={"X-PMS-Secret": SECRET},
                )

        assert resp.status_code == 200
        mock_expire.assert_called_once()
        app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_webhook_invalid_secret_returns_401():
    with patch("app.network.scheduler.start_scheduler"), \
         patch("app.pms.factory.load_adapter"):
        from app.main import app
        from app.core.database import get_db

        mock_db = _make_db_with_adapter("opera_cloud", SECRET_HASH)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        app.state.redis = AsyncMock()

        import uuid
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                f"/internal/pms/webhook/{uuid.uuid4()}",
                json={"eventType": "CHECKED_OUT", "roomNumber": "101"},
                headers={"X-PMS-Secret": "wrong_secret"},
            )

        assert resp.status_code == 401
        app.dependency_overrides.clear()

@pytest.mark.asyncio
async def test_webhook_unknown_adapter_returns_404():
    with patch("app.network.scheduler.start_scheduler"), \
         patch("app.pms.factory.load_adapter"):
        from app.main import app
        from app.core.database import get_db

        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_db = AsyncMock()
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        app.state.redis = AsyncMock()

        import uuid
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            resp = await c.post(
                f"/internal/pms/webhook/{uuid.uuid4()}",
                json={},
                headers={"X-PMS-Secret": "x"},
            )

        assert resp.status_code == 404
        app.dependency_overrides.clear()
