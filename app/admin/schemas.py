from typing import Literal, Union
import uuid
from datetime import datetime
from pydantic import BaseModel, Field, field_validator, ConfigDict
from app.core.models import PMSAdapterType, VoucherType


class PMSConfigResponse(BaseModel):
    id: uuid.UUID
    type: PMSAdapterType
    is_active: bool
    last_sync_at: datetime | None
    config: dict  # credentials replaced with "***"


class PMSConfigUpdate(BaseModel):
    type: PMSAdapterType
    config: dict  # plaintext — encrypted before DB write
    webhook_secret: str | None = None


class PMSTestResult(BaseModel):
    ok: bool
    latency_ms: float = 0.0
    error: str | None = None


class VoucherCreate(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=False)

    type: VoucherType
    duration_minutes: Union[int, str, None] = None
    data_limit_mb: Union[int, str, None] = None
    max_devices: Union[int, str] = 1
    max_uses: Union[int, str] = 1
    expires_at: datetime | None = None

    @field_validator('duration_minutes', 'data_limit_mb', 'max_uses', 'max_devices', mode='before')
    @classmethod
    def coerce_fields(cls, v):
        """Convert empty strings to None, convert string integers."""
        if isinstance(v, str):
            if v == '' or v.strip() == '':
                return None
            try:
                return int(v)
            except (ValueError, TypeError):
                return None
        if v is None or v == '':
            return None
        return v


class BatchVoucherCreate(BaseModel):
    model_config = ConfigDict(coerce_numbers_to_str=False)

    type: str  # "time" | "data"
    duration_minutes: Union[int, str, None] = None
    data_limit_mb: Union[int, str, None] = None
    max_uses: Union[int, str] = 1
    max_devices: Union[int, str] = 1
    expires_at: datetime | None = None
    count: Union[int, str] = Field(ge=1, le=100)

    @field_validator('duration_minutes', 'data_limit_mb', 'count', 'max_uses', 'max_devices', mode='before')
    @classmethod
    def coerce_fields(cls, v):
        """Convert empty strings to None, convert string integers."""
        if isinstance(v, str):
            if v == '' or v.strip() == '':
                return None
            try:
                return int(v)
            except (ValueError, TypeError):
                return None
        if v is None or v == '':
            return None
        return v


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
