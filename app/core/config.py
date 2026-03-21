from pydantic_settings import BaseSettings, SettingsConfigDict

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")

    SECRET_KEY: str
    ENCRYPTION_KEY: str
    ENVIRONMENT: str = "development"

    DATABASE_URL: str
    REDIS_URL: str

    WIFI_INTERFACE: str = "wlan0"
    WAN_INTERFACE: str = "eth0"
    PORTAL_IP: str = "192.168.1.1"
    PORTAL_PORT: int = 8080

    # DNS upstream for authenticated guests
    DNS_UPSTREAM_IP: str = "8.8.8.8"

    JWT_ALGORITHM: str = "HS256"
    JWT_EXPIRE_HOURS: int = 8

    AUTH_RATE_LIMIT_ATTEMPTS: int = 5
    AUTH_RATE_LIMIT_WINDOW_SECONDS: int = 600

settings = Settings()
