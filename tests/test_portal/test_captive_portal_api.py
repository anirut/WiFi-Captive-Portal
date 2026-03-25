import pytest
import pytest_asyncio
from unittest.mock import patch
from httpx import AsyncClient, ASGITransport


@pytest.mark.asyncio
async def test_portal_info_endpoint():
    with (
        patch("app.network.nftables.NftablesManager.add_to_whitelist"),
        patch("app.network.nftables.NftablesManager.remove_from_whitelist"),
        patch("app.network.nftables.NftablesManager.add_dns_bypass"),
        patch("app.network.nftables.NftablesManager.remove_dns_bypass"),
        patch("app.network.tc.apply_bandwidth_limit"),
        patch("app.network.tc.remove_bandwidth_limit"),
        patch("app.network.arp.get_mac_for_ip", return_value=None),
        patch("app.network.scheduler.start_scheduler"),
        patch("app.pms.factory.load_adapter"),
    ):
        from app.main import app
        from app.core.database import get_db
        from unittest.mock import AsyncMock, MagicMock

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

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/captive-portal/api/v1/portal-info")
            assert response.status_code == 200
            data = response.json()
            assert data["captive"] == True
            assert "user-portal-url" in data
            assert data["version"] == "1.0"

        app.dependency_overrides.clear()


@pytest.mark.asyncio
async def test_captive_portal_probe_redirects():
    with (
        patch("app.network.nftables.NftablesManager.add_to_whitelist"),
        patch("app.network.nftables.NftablesManager.remove_from_whitelist"),
        patch("app.network.nftables.NftablesManager.add_dns_bypass"),
        patch("app.network.nftables.NftablesManager.remove_dns_bypass"),
        patch("app.network.tc.apply_bandwidth_limit"),
        patch("app.network.tc.remove_bandwidth_limit"),
        patch("app.network.arp.get_mac_for_ip", return_value=None),
        patch("app.network.scheduler.start_scheduler"),
        patch("app.pms.factory.load_adapter"),
    ):
        from app.main import app
        from app.core.database import get_db
        from unittest.mock import AsyncMock, MagicMock

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

        async with AsyncClient(
            transport=ASGITransport(app=app), base_url="http://test"
        ) as client:
            response = await client.get("/generate_204")
            assert response.status_code == 302

        app.dependency_overrides.clear()
