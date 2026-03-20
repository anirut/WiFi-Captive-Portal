from datetime import datetime, timedelta, timezone
from typing import Any
from jose import jwt, JWTError
from app.core.config import settings

def create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRE_HOURS)
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None

async def is_token_revoked(token: str, redis_client: Any) -> bool:
    return await redis_client.get(f"revoked:{token}") is not None

async def revoke_token(token: str, redis_client: Any) -> None:
    payload = decode_access_token(token)
    if payload and "exp" in payload:
        ttl = int(payload["exp"] - datetime.now(timezone.utc).timestamp())
        if ttl > 0:
            await redis_client.setex(f"revoked:{token}", ttl, "1")
