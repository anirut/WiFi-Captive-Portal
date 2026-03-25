from typing import Literal
import uuid
from datetime import datetime
from pydantic import BaseModel, Field, model_validator
from app.core.models import PMSAdapterType, VoucherType


class PMSConfigResponse(BaseModel):
    id: uuid.UUID
    type: PMSAdapterType
    is_active: bool
    last_sync_at: datetime | None
    config: dict  # credentials replaced with "***"


class PMSConfigUpdate(BaseModel):
    type: PMSAdapterType
    config: dict | None = None  # plaintext — encrypted before DB write
    webhook_secret: str | None = None

    # Individual fields for form submission
    host: str | None = None
    port: str | None = None
    auth_key: str | None = None
    vendor_id: str | None = None
    base_url: str | None = None
    client_id: str | None = None
    client_secret: str | None = None
    hotel_id: str | None = None

    @model_validator(mode="before")
    @classmethod
    def build_config_dict(cls, data):
        """Build config dict from individual fields if not provided."""
        if isinstance(data, dict):
            # If config not provided, build it from individual fields
            if "config" not in data or data["config"] is None:
                config = {}
                for field in [
                    "host",
                    "port",
                    "auth_key",
                    "vendor_id",
                    "base_url",
                    "client_id",
                    "client_secret",
                    "hotel_id",
                ]:
                    if field in data and data[field]:
                        config[field] = data[field]
                if config:
                    data["config"] = config
                else:
                    data["config"] = {}  # Empty dict is required
        return data


class PMSTestResult(BaseModel):
    ok: bool
    latency_ms: float = 0.0
    error: str | None = None


class VoucherCreate(BaseModel):
    type: VoucherType
    duration_minutes: int | None = None
    data_limit_mb: int | None = None
    max_devices: int = 1
    max_uses: int = 1
    expires_at: datetime | None = None

    @model_validator(mode="before")
    @classmethod
    def coerce_string_ints(cls, data):
        """Convert string numbers and empty strings to int/None."""
        if isinstance(data, dict):
            for field in [
                "duration_minutes",
                "data_limit_mb",
                "max_devices",
                "max_uses",
            ]:
                if field in data:
                    v = data[field]
                    if v == "" or v is None:
                        data[field] = None
                    elif isinstance(v, str):
                        try:
                            data[field] = int(float(v))
                        except (ValueError, TypeError):
                            data[field] = None
        return data


class BatchVoucherCreate(BaseModel):
    type: str  # "time" | "data"
    duration_minutes: int | None = None
    data_limit_mb: int | None = None
    max_uses: int = 1
    max_devices: int = 1
    expires_at: datetime | None = None
    count: int = Field(ge=1, le=100)

    @model_validator(mode="before")
    @classmethod
    def coerce_string_ints(cls, data):
        """Convert string numbers and empty strings to int/None."""
        if isinstance(data, dict):
            for field in [
                "duration_minutes",
                "data_limit_mb",
                "max_uses",
                "max_devices",
                "count",
            ]:
                if field in data:
                    v = data[field]
                    if v == "" or v is None:
                        data[field] = None
                    elif isinstance(v, str):
                        try:
                            data[field] = int(float(v))
                        except (ValueError, TypeError):
                            data[field] = None
        return data


class VoucherResponse(BaseModel):
    id: uuid.UUID
    code: str
    type: VoucherType
    duration_minutes: int | None
    data_limit_mb: int | None
    max_devices: int
    max_uses: int
    used_count: int
    expires_at: datetime | None
    created_by: uuid.UUID


class DhcpConfigUpdate(BaseModel):
    enabled: bool | None = None
    interface: str | None = None
    gateway_ip: str | None = None
    subnet: str | None = None
    dhcp_range_start: str | None = None
    dhcp_range_end: str | None = None
    lease_time: Literal["30m", "1h", "4h", "8h", "12h", "24h"] | None = None
    dns_upstream_1: str | None = None
    dns_upstream_2: str | None = None
    dns_mode: str | None = None
    log_queries: bool | None = None


class DhcpConfigResponse(BaseModel):
    id: str
    enabled: bool
    interface: str
    gateway_ip: str
    subnet: str
    dhcp_range_start: str
    dhcp_range_end: str
    lease_time: str
    dns_upstream_1: str
    dns_upstream_2: str
    dns_mode: str
    log_queries: bool
    updated_at: str


class MacBypassCreate(BaseModel):
    mac_address: str = Field(..., pattern=r"^([0-9A-Fa-f]{2}:){5}[0-9A-Fa-f]{2}$")
    description: str | None = None
    expires_at: datetime | None = None


class MacBypassResponse(BaseModel):
    id: uuid.UUID
    mac_address: str
    description: str | None
    created_by: uuid.UUID
    created_at: datetime
    expires_at: datetime | None
    is_active: bool

    class Config:
        from_attributes = True


class WalledGardenDomainCreate(BaseModel):
    domain: str = Field(..., max_length=253)
    description: str | None = None


class WalledGardenDomainResponse(BaseModel):
    id: uuid.UUID
    domain: str
    description: str | None
    created_by: uuid.UUID
    created_at: datetime
    is_active: bool

    class Config:
        from_attributes = True
