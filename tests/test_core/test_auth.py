import pytest
from unittest.mock import AsyncMock
from app.core.auth import create_access_token, decode_access_token, is_token_revoked, revoke_token

def test_create_and_decode_token():
    token = create_access_token({"sub": "admin_user_id", "role": "superadmin"})
    payload = decode_access_token(token)
    assert payload["sub"] == "admin_user_id"
    assert payload["role"] == "superadmin"

def test_decode_invalid_token_returns_none():
    assert decode_access_token("not.a.valid.token") is None

@pytest.mark.asyncio
async def test_token_not_revoked_initially():
    token = create_access_token({"sub": "user1"})
    mock_redis = AsyncMock()
    mock_redis.get.return_value = None
    assert not await is_token_revoked(token, mock_redis)

@pytest.mark.asyncio
async def test_token_is_revoked_after_revoke():
    token = create_access_token({"sub": "user1"})
    mock_redis = AsyncMock()
    mock_redis.get.return_value = b"1"
    assert await is_token_revoked(token, mock_redis)
