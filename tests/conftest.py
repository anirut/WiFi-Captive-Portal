import os

os.environ.setdefault("SECRET_KEY", "test_secret_key_32_chars_long_xxx")
os.environ.setdefault("ENCRYPTION_KEY", "AF7LzGfwqzgX6h8uF89ph9XUwy-_GilZDJp0zv2y0hs=")
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://test:test@localhost/test_db")
os.environ.setdefault("REDIS_URL", "redis://localhost:6379/0")

import pytest
import pytest_asyncio
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, AsyncMock, MagicMock

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
        from app.core.database import get_db

        # Override get_db dependency to avoid real DB connections
        # The mock db execute() must return an object with scalar_one_or_none() -> None
        mock_db = AsyncMock()
        mock_result = MagicMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_result.scalars.return_value.all.return_value = []
        mock_db.execute = AsyncMock(return_value=mock_result)

        async def override_get_db():
            yield mock_db

        app.dependency_overrides[get_db] = override_get_db
        # Provide a fake redis on app.state
        app.state.redis = AsyncMock()
        app.state.redis.incr = AsyncMock(return_value=1)
        app.state.redis.expire = AsyncMock()
        async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as c:
            yield c
        app.dependency_overrides.clear()
