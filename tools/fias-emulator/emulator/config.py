"""
Configuration settings for the FIAS Emulator.
"""

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # FIAS TCP Server settings
    fias_tcp_host: str = "0.0.0.0"
    fias_tcp_port: int = 9090

    # HTTP Management API settings
    http_host: str = "0.0.0.0"
    http_port: int = 8081

    # Database settings
    database_url: str = "sqlite+aiosqlite:///./fias_emulator.db"

    # Authentication settings
    auth_key: str = ""
    vendor_id: str = "FIAS_EMULATOR"


# Global settings instance
settings = Settings()
