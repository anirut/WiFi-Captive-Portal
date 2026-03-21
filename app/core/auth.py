import time
import uuid as _uuid
from datetime import datetime, timedelta, timezone
from typing import Any, NoReturn
from jose import jwt, JWTError
from fastapi import Depends, HTTPException, Request, status
from fastapi.responses import RedirectResponse
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from app.core.config import settings

_bearer = HTTPBearer(auto_error=False)

# ── Token creation ──────────────────────────────────────────────────────────

def create_access_token(data: dict) -> str:
    payload = data.copy()
    payload["exp"] = datetime.now(timezone.utc) + timedelta(hours=settings.JWT_EXPIRE_HOURS)
    payload["jti"] = str(_uuid.uuid4())
    return jwt.encode(payload, settings.SECRET_KEY, algorithm=settings.JWT_ALGORITHM)

def decode_access_token(token: str) -> dict | None:
    try:
        return jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.JWT_ALGORITHM])
    except JWTError:
        return None

# ── Auth helpers ────────────────────────────────────────────────────────────

def _raise_or_redirect(request: Request) -> NoReturn:
    """Always raises. HTML clients get a redirect; JSON clients get 401."""
    if "text/html" in request.headers.get("accept", ""):
        raise HTTPException(
            status_code=302,
            headers={"Location": f"/admin/login?next={request.url.path}"},
        )
    raise HTTPException(status_code=401, detail={"error": "unauthorized"})

# ── Dependencies ─────────────────────────────────────────────────────────────

async def get_current_admin(request: Request) -> dict:
    """Cookie-first, then Bearer. Checks Redis blocklist."""
    token = request.cookies.get("admin_token")
    if not token:
        credentials: HTTPAuthorizationCredentials | None = await _bearer(request)
        if credentials:
            token = credentials.credentials
    if not token:
        _raise_or_redirect(request)
    payload = decode_access_token(token)
    if not payload:
        _raise_or_redirect(request)
    redis = request.app.state.redis
    if await redis.exists(f"blocklist:{payload['jti']}"):
        _raise_or_redirect(request)
    return payload

async def require_superadmin(payload: dict = Depends(get_current_admin)) -> dict:
    if payload.get("role") != "superadmin":
        raise HTTPException(status_code=403, detail={"error": "forbidden"})
    return payload

# ── Legacy alias (used by existing portal routes — keep until portal migrated) ──
async def get_current_user(
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer),
) -> dict:
    """Bearer-only dependency for non-admin routes (portal internal use)."""
    if not credentials:
        raise HTTPException(status_code=401, detail={"error": "not_authenticated"},
                            headers={"WWW-Authenticate": "Bearer"})
    payload = decode_access_token(credentials.credentials)
    if not payload:
        raise HTTPException(status_code=401, detail={"error": "invalid_token"},
                            headers={"WWW-Authenticate": "Bearer"})
    return payload

# ── Legacy token revocation functions (kept for backward compatibility) ──────

async def is_token_revoked(token: str, redis_client: Any) -> bool:
    return await redis_client.get(f"revoked:{token}") is not None

async def revoke_token(token: str, redis_client: Any) -> None:
    payload = decode_access_token(token)
    if payload and "exp" in payload:
        ttl = int(payload["exp"] - datetime.now(timezone.utc).timestamp())
        if ttl > 0:
            await redis_client.setex(f"revoked:{token}", ttl, "1")
