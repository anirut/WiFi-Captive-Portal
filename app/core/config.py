from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    SECRET_KEY: str
    ENCRYPTION_KEY: str
    ENVIRONMENT: str = "development"

    DATABASE_URL: str
    REDIS_URL: str

    WIFI_INTERFACE: str = "wlan0"
    WAN_INTERFACE: str = "eth0"
    PORTAL_IP: str = "192.168.1.1"
    PORTAL_PORT: int = 8080

    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 8

    AUTH_RATE_LIMIT_ATTEMPTS: int = 5
    AUTH_RATE_LIMIT_WINDOW_SECONDS: int = 600

    class Config:
        env_file = ".env"

try:
    settings = Settings()
except Exception:
    settings = None  # type: ignore[assignment]
