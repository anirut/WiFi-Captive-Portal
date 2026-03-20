import pytest
from unittest.mock import AsyncMock
from app.core.rate_limit import check_rate_limit, RateLimitExceeded

@pytest.mark.asyncio
async def test_allows_under_limit():
    mock_redis = AsyncMock()
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock()
    # Should not raise
    await check_rate_limit("192.168.1.45", mock_redis, max_attempts=5, window_seconds=600)

@pytest.mark.asyncio
async def test_blocks_over_limit():
    mock_redis = AsyncMock()
    mock_redis.incr = AsyncMock(return_value=6)
    mock_redis.expire = AsyncMock()
    with pytest.raises(RateLimitExceeded):
        await check_rate_limit("192.168.1.45", mock_redis, max_attempts=5, window_seconds=600)

@pytest.mark.asyncio
async def test_allows_at_limit():
    """Test that exactly at limit does NOT raise"""
    mock_redis = AsyncMock()
    mock_redis.incr = AsyncMock(return_value=5)
    mock_redis.expire = AsyncMock()
    # Should not raise - at limit is OK
    await check_rate_limit("192.168.1.45", mock_redis, max_attempts=5, window_seconds=600)

@pytest.mark.asyncio
async def test_expire_only_on_first_call():
    """Test that expire is only called when count == 1"""
    mock_redis = AsyncMock()
    mock_redis.incr = AsyncMock(return_value=2)
    mock_redis.expire = AsyncMock()
    await check_rate_limit("192.168.1.45", mock_redis, max_attempts=5, window_seconds=600)
    # expire should NOT be called when count == 2
    mock_redis.expire.assert_not_called()

@pytest.mark.asyncio
async def test_expire_called_on_first_increment():
    """Test that expire is called when count == 1"""
    mock_redis = AsyncMock()
    mock_redis.incr = AsyncMock(return_value=1)
    mock_redis.expire = AsyncMock()
    await check_rate_limit("192.168.1.45", mock_redis, max_attempts=5, window_seconds=600)
    # expire should be called with the right key and window
    mock_redis.expire.assert_called_once_with("rate_limit:auth:192.168.1.45", 600)
