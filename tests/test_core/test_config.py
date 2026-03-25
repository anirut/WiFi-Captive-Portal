import pytest
from app.core.config import Settings

def test_settings_loads_defaults():
    s = Settings(
        SECRET_KEY="a" * 32,
        ENCRYPTION_KEY="Zm9vYmFyYmF6cXV4Zm9vYmFyYmF6cXV4Zm9vYmFyYmF6cXU=",
        DATABASE_URL="postgresql+asyncpg://u:p@localhost/db",
        REDIS_URL="redis://localhost:6379/0",
    )
    assert s.JWT_ALGORITHM == "HS256"
    assert s.JWT_EXPIRE_HOURS == 8
    assert s.AUTH_RATE_LIMIT_ATTEMPTS == 20
    assert s.WIFI_INTERFACE == "wlan0"
