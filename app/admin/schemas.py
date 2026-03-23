from typing import Literal, Annotated
import uuid
from datetime import datetime
from pydantic import BaseModel, Field, BeforeValidator, field_validator
from app.core.models import PMSAdapterType, VoucherType


def coerce_int_or_none(v):
    """Convert string numbers, empty strings, None to int or None."""
    if v is None or v == '':
        return None
    if isinstance(v, str):
        try:
            return int(v)
        except ValueError:
            return None
    return v


# Type alias for integer fields that accept strings
OptionalInt = Annotated[int | None, BeforeValidator(coerce_int_or_none)]
RequiredInt = Annotated[int, BeforeValidator(coerce_int_or_none)]


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
    type: VoucherType
    duration_minutes: OptionalInt = None
    data_limit_mb: OptionalInt = None
    max_devices: RequiredInt = 1
    max_uses: RequiredInt = 1
    expires_at: datetime | None = None


class BatchVoucherCreate(BaseModel):
    type: str  # "time" | "data"
    duration_minutes: OptionalInt = None
    data_limit_mb: OptionalInt = None
    max_uses: RequiredInt = 1
    max_devices: RequiredInt = 1
    expires_at: datetime | None = None
    count: Annotated[int, Field(ge=1, le=100), BeforeValidator(coerce_int_or_none)]


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
